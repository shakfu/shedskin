#!/usr/bin/env python3
"""Dynamic escape census: how long do a Python program's allocations live?

Rewrites the program's AST so that every tuple/list/dict/set display, call and
binop result passes through _ss_track(), which registers new heap objects
(user-class instances, tuple, list, dict, set, str) with the current frame.
Floats, ints and bools are skipped, as shedskin stores them by value.

A profiler hook classifies a frame's objects when the frame returns. CPython
reference counts are exact, so an object is reachable from outside the frame
iff its refcount exceeds the references from the frame's locals, from other
objects the frame allocated, from the return value, and from this tool.
Returned objects move to the caller and are classified again there.

Levels:
  L0   unreachable when the allocating function returns
  L1   returned once, unreachable when the caller returns
  L2+  returned two or more times before becoming unreachable
  esc  reachable from outside (heap, globals, older objects) at some return

Objects are held until their frame returns, so an object that escapes and is
dropped again before the return counts as non-escaping: the census is an upper
bound for a static escape analysis. See docs/dev/type-alloc.md.

The program runs under a module name other than '__main__' and must define
main(), which is called; sys.argv is set to the program and its arguments.
Needs CPython 3.13+: older frame.f_locals snapshots hold extra references.

usage: python3 scripts/escape_census.py --selftest
       python3 scripts/escape_census.py examples/pygmy/pygmy.py 64 48
"""

import ast
import collections
import sys

TRACK_TYPES = {tuple, list, dict, set, str}
LEVELS = ["L0", "L1", "L2+", "esc"]
USER = set()
frames = [[]]  # one entry per active Python frame: the objects it owns
level = {}  # id(obj) -> times returned so far
site = {}  # id(obj) -> (allocating function, type name)
stats = collections.defaultdict(collections.Counter)
site_stats = collections.defaultdict(collections.Counter)
BASE = RET = 0  # refcount offsets, calibrated by selftest()
calib = []


def _ss_track(o):
    t = type(o)
    if t in USER:
        d = o.__dict__
        if "_trk" in d:
            return o
        d["_trk"] = True
    elif t in TRACK_TYPES:
        if id(o) in level or sys.getrefcount(o) > 1 << 30:  # tracked, or immortal
            return o
    else:
        return o
    level[id(o)] = 0
    site[id(o)] = (sys._getframe(1).f_code.co_qualname, t.__name__)
    frames[-1].append(o)
    return o


def refs_of(o):
    t = type(o)
    if t in USER:
        return [v for k, v in o.__dict__.items() if k != "_trk"]
    if t in (tuple, list, set):
        return list(o)
    if t is dict:
        return list(o.keys()) + list(o.values())
    return []


def count(i, o, c):
    stats[type(o).__name__][c] += 1
    site_stats[site.pop(i)][c] += 1
    del level[i]


def classify(entry, frame, retval):
    C = {id(o): o for o in entry}
    internal = collections.Counter()
    for o in entry:
        for r in refs_of(o):
            if id(r) in C:
                internal[id(r)] += 1
    local = collections.Counter()
    for v in frame.f_locals.values():
        if id(v) in C:
            local[id(v)] += 1
    v = r = None  # drop loop references before reading refcounts
    ext = {}
    for o in entry:
        ext[id(o)] = (
            sys.getrefcount(o)
            - BASE
            - local[id(o)]
            - internal[id(o)]
            - (RET if o is retval else 0)
        )
    o = None
    if calib is not None and frame.f_code.co_name.startswith("_calib"):
        calib.append((frame.f_code.co_name, list(ext.values())))
    # objects reachable from an escaping object escape too
    E = {i for i in C if ext[i] > 0}
    work = list(E)
    while work:
        for x in refs_of(C[work.pop()]):
            if id(x) in C and id(x) not in E:
                E.add(id(x))
                work.append(id(x))
    R, work = set(), [retval]
    while work:
        x = work.pop()
        if id(x) in C and id(x) not in E and id(x) not in R:
            R.add(id(x))
            work.extend(refs_of(x))
    for i, o in C.items():
        if i in E:
            count(i, o, "esc")
        elif i in R:
            level[i] += 1
            frames[-1].append(o)
        else:
            lv = level[i]
            count(i, o, "L0" if lv == 0 else "L1" if lv == 1 else "L2+")


SKIP = {_ss_track.__code__}


def prof(frame, event, arg):
    if frame.f_code in SKIP:
        return
    if event == "call":
        frames.append([])
    elif event == "return":
        entry = frames.pop()
        if entry:
            classify(entry, frame, arg)
            entry.clear()


class Wrap(ast.NodeTransformer):
    def wrap(self, n):
        self.generic_visit(n)
        return ast.copy_location(
            ast.Call(ast.Name("_ss_track", ast.Load()), [n], []), n
        )

    def visit_Tuple(self, n):
        return self.wrap(n) if isinstance(n.ctx, ast.Load) else self.generic_visit(n)

    visit_List = visit_Tuple

    def visit_Dict(self, n):
        return self.wrap(n)

    visit_Set = visit_Call = visit_BinOp = visit_JoinedStr = visit_Dict


def load(src, name):
    tree = ast.fix_missing_locations(Wrap().visit(ast.parse(src)))
    g = {"__name__": name, "_ss_track": _ss_track}
    exec(compile(tree, name, "exec"), g)  # noqa: S102 - running the measured program is the point
    USER.update(v for v in g.values() if isinstance(v, type) and v.__module__ == name)
    return g


def run(g):
    stats.clear()
    site_stats.clear()
    level.clear()
    site.clear()
    frames[:] = [[]]
    sys.setprofile(prof)
    try:
        g["main"]()
    finally:
        sys.setprofile(None)
    for o in frames[0]:  # returned to the top level
        count(id(o), o, "esc")


def report(title, top):
    def row(label, counts, width=16):
        return f"{label:<{width}}" + "".join(f"{c:>10}" for c in counts)

    print(title)
    print(row("type", [*LEVELS, "total"]))
    tot = collections.Counter()
    for k in sorted(stats, key=lambda k: -sum(stats[k].values())):
        s = stats[k]
        tot.update(s)
        print(row(k, [*(s[c] for c in LEVELS), sum(s.values())]))
    n = sum(tot.values())
    print(row("total", [*(tot[c] for c in LEVELS), n]))
    print(row("share", [f"{100 * tot[c] / n:.1f}%" for c in LEVELS]))
    if top:
        print()
        print(row("allocating function, type", LEVELS, 40))
        for (fn, ty), s in sorted(
            site_stats.items(), key=lambda kv: -sum(kv[1].values())
        )[:top]:
            print(row(f"{fn}, {ty}", [s[c] for c in LEVELS], 40))


SELFTEST = """
class Obj:
    pass
G = []
def _calib_local():
    x = Obj()
    return None
def _calib_ret():
    return Obj()
def local_temp():
    a = Obj(); b = [a, Obj()]
    return 1
def make():
    return Obj()
def use_once():
    o = make()
    return 2
def make2():
    return make()
def use_twice():
    o = make2()
    return 3
def store_global():
    G.append(Obj())
def store_attr(holder):
    holder.x = Obj()
def tuple_ret():
    return ("s", Obj(), Obj())
def unpack():
    s, a, b = tuple_ret()
    return 4
def main():
    h = Obj()
    G.append(h)
    local_temp(); use_once(); use_twice(); store_global(); store_attr(h); unpack()
"""


def selftest():
    """Calibrate the refcount offsets, then check 9 cases with known levels."""
    global BASE, RET, calib
    g = load(SELFTEST, "selftest")
    sys.setprofile(prof)
    g["_calib_local"]()
    g["_calib_ret"]()
    sys.setprofile(None)
    raw = dict(calib)
    BASE = raw["_calib_local"][0]
    RET = raw["_calib_ret"][0] - BASE
    calib = None
    run(g)
    # local_temp: 2 Obj L0 and a list L0; use_once: 1 L1; use_twice: 1 L2+;
    # unpack: a tuple and 2 Obj L1; store_global, store_attr, main's h: 3 esc
    s = stats["Obj"]
    expect = {"L0": 2, "L1": 3, "L2+": 1, "esc": 3}
    assert {c: s[c] for c in expect} == expect, dict(s)
    assert stats["list"]["L0"] == 1 and stats["tuple"]["L1"] == 1, (
        dict(stats["list"]),
        dict(stats["tuple"]),
    )
    print(f"selftest ok (BASE={BASE} RET={RET})")


if __name__ == "__main__":
    if sys.version_info < (3, 13):
        sys.exit("escape_census.py needs CPython 3.13 or later")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    selftest()
    if sys.argv[1] != "--selftest":
        prog = sys.argv[1]
        sys.argv = sys.argv[1:]
        with open(prog) as f:
            g = load(f.read(), "prog")
        run(g)
        report(prog, top=14)
