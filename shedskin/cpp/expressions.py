# SHED SKIN Python-to-C++ Compiler
# Copyright 2005-2024 Mark Dufour and contributors; GNU GPL version 3 (See LICENSE)
"""shedskin.cpp.expressions - Expression visitor methods

This module contains visitor methods for Python expression AST nodes.
"""

import ast
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Tuple, TypeAlias, Union

from .. import ast_utils, error, infer, python, typestr

if TYPE_CHECKING:
    pass

# Type aliases (from cpp.py)
Types: TypeAlias = set[Tuple["python.Class", int]]
Parent: TypeAlias = Union["python.Class", "python.Function"]


class ExpressionVisitorMixin:
    """Mixin for expression visitor methods"""

    def visit_BinOp(
        self, node: ast.BinOp, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a binary operation"""
        if isinstance(node.op, ast.Add):
            str_nodes = self.rec_string_addition(node)
            if len(str_nodes) > 2:
                self.append("__add_strs(%d, " % len(str_nodes))
                for i, str_node in enumerate(str_nodes):
                    self.visit(str_node, func)
                    if i < len(str_nodes) - 1:
                        self.append(", ")
                self.append(")")
            else:
                self.impl_visit_binary(
                    node.left,
                    node.right,
                    ast_utils.aug_msg(self.gx, node, "add"),
                    "+",
                    func,
                )
        elif isinstance(node.op, ast.Sub):
            self.impl_visit_binary(
                node.left,
                node.right,
                ast_utils.aug_msg(self.gx, node, "sub"),
                "-",
                func,
            )
        elif isinstance(node.op, ast.Mult):
            self.impl_visit_binary(
                node.left,
                node.right,
                ast_utils.aug_msg(self.gx, node, "mul"),
                "*",
                func,
            )
        elif isinstance(node.op, ast.Div):
            self.impl_visit_binary(
                node.left,
                node.right,
                ast_utils.aug_msg(self.gx, node, "truediv"),
                "/",
                func,
            )
        elif isinstance(node.op, ast.FloorDiv):
            self.impl_visit_binary(
                node.left,
                node.right,
                ast_utils.aug_msg(self.gx, node, "floordiv"),
                "//",
                func,
            )
        elif isinstance(node.op, ast.Pow):
            self.power(node.left, node.right, None, func)
        elif isinstance(node.op, ast.Mod):
            self.impl_visit_mod(node, func)
        elif isinstance(node.op, ast.LShift):
            self.impl_visit_binary(
                node.left,
                node.right,
                ast_utils.aug_msg(self.gx, node, "lshift"),
                "<<",
                func,
            )
        elif isinstance(node.op, ast.RShift):
            self.impl_visit_binary(
                node.left,
                node.right,
                ast_utils.aug_msg(self.gx, node, "rshift"),
                ">>",
                func,
            )
        elif isinstance(node.op, ast.BitOr):
            self.impl_visit_bitop(
                node, ast_utils.aug_msg(self.gx, node, "or"), "|", func
            )
        elif isinstance(node.op, ast.BitXor):
            self.impl_visit_bitop(
                node, ast_utils.aug_msg(self.gx, node, "xor"), "^", func
            )
        elif isinstance(node.op, ast.BitAnd):
            self.impl_visit_bitop(
                node, ast_utils.aug_msg(self.gx, node, "and"), "&", func
            )
        # PY3: elif type(node.op) == MatMult:
        else:
            error.error(
                "Unknown op type for ast.BinOp: %s" % type(node.op),
                self.gx,
                node,
                mv=self.mv,
            )

    def visit_UnaryOp(
        self, node: ast.UnaryOp, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a unary operation"""
        if isinstance(node.op, ast.USub):
            self.visitm("(", func)
            if typestr.unboxable(self.gx, self.mergeinh[node.operand]):
                self.visitm("-", node.operand, func)
            else:
                fakefunc = infer.inode(self.gx, node.operand).fakefunc
                assert fakefunc
                self.visit_Call(fakefunc, func)
            self.visitm(")", func)
        elif isinstance(node.op, ast.UAdd):
            self.visitm("(", func)
            if typestr.unboxable(self.gx, self.mergeinh[node.operand]):
                self.visitm("+", node.operand, func)
            else:
                fakefunc = infer.inode(self.gx, node.operand).fakefunc
                assert fakefunc
                self.visit_Call(fakefunc, func)
            self.visitm(")", func)
        elif isinstance(node.op, ast.Invert):
            if typestr.unboxable(self.gx, self.mergeinh[node.operand]):
                self.visitm("~", node.operand, func)
            else:
                fakefunc = infer.inode(self.gx, node.operand).fakefunc
                assert fakefunc
                self.visit_Call(fakefunc, func)
        elif isinstance(node.op, ast.Not):
            self.append("__NOT(")
            self.bool_test(node.operand, func)
            self.append(")")
        else:
            error.error(
                "Unknown op type for UnaryOp: %s" % type(node.op),
                self.gx,
                node,
                mv=self.mv,
            )

    def visit_BoolOp(
        self, node: ast.BoolOp, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a boolean operation"""
        if isinstance(node.op, ast.Or):
            self.impl_visit_and_or(node, node.values, "__OR", "or", func)
        elif isinstance(node.op, ast.And):
            self.impl_visit_and_or(node, node.values, "__AND", "and", func)

    def visit_Compare(
        self,
        node: ast.Compare,
        func: Optional["python.Function"] = None,
        wrapper: bool = True,
    ) -> None:
        """Visit a comparison operation"""
        if node not in self.bool_wrapper:
            self.append("___bool(")
        self.done = set()
        mapping = {
            ast.Gt: ("__gt__", ">", None),
            ast.Lt: ("__lt__", "<", None),
            ast.NotEq: ("__ne__", "!=", None),
            ast.Eq: ("__eq__", "==", None),
            ast.LtE: ("__le__", "<=", None),
            ast.GtE: ("__ge__", ">=", None),
            ast.Is: (None, "==", None),
            ast.IsNot: (None, "!=", None),
            ast.In: ("__contains__", None, None),
            ast.NotIn: ("__contains__", None, "!"),
        }
        left = node.left
        for op, right in zip(node.ops, node.comparators):
            msg, short, pre = mapping[type(op)]
            if msg == "__contains__":
                self.do_compare(right, left, msg, short, func, pre)
            else:
                self.do_compare(left, right, msg, short, func, pre)
            if right != node.comparators[-1]:
                self.append("&&")
            left = right
        if node not in self.bool_wrapper:
            self.append(")")

    def visit_Call(
        self,
        node: ast.Call,
        func: Optional["python.Function"] = None,
        argtypes: Optional[Types] = None,
    ) -> None:
        """Visit a call node"""
        (
            objexpr,
            ident,
            direct_call,
            method_call,
            constructor,
            parent_constr,
            anon_func,
        ) = infer.analyze_callfunc(self.gx, node, merge=self.gx.merged_inh)
        funcs = infer.callfunc_targets(self.gx, node, self.gx.merged_inh)

        if self.library_func(funcs, "re", None, "findall") or self.library_func(
            funcs, "re", "re_object", "findall"
        ):
            error.error(
                "'findall' does not work with groups (use 'finditer' instead)",
                self.gx,
                node,
                warning=True,
                mv=self.mv,
            )
        if self.library_func(
            funcs, "socket", "socket", "settimeout"
        ) or self.library_func(funcs, "socket", "socket", "gettimeout"):
            error.error(
                "socket.set/gettimeout do not accept/return None",
                self.gx,
                node,
                warning=True,
                mv=self.mv,
            )
        if self.library_func(funcs, "builtin", None, "map") and len(node.args) > 2:
            error.error(
                "default fillvalue for 'map' becomes 0 for integers",
                self.gx,
                node,
                warning=True,
                mv=self.mv,
            )
        if self.library_func(funcs, "itertools", None, "zip_longest"):
            error.error(
                "default fillvalue for 'zip_longest' becomes 0 for integers",
                self.gx,
                node,
                warning=True,
                mv=self.mv,
            )
        if self.library_func(funcs, "struct", None, "unpack"):
            error.error(
                "struct.unpack should be used as follows: 'a, .. = struct.unpack(..)'",
                self.gx,
                node,
                warning=True,
                mv=self.mv,
            )
        if self.library_func(funcs, "array", "array", "__init__"):
            if (
                not node.args
                or not isinstance(node.args[0], ast.Str)
                or node.args[0].s not in "bBhHiIlLfd"
            ):
                error.error(
                    "non-constant or unsupported type code",
                    self.gx,
                    node,
                    warning=True,
                    mv=self.mv,
                )
        if self.library_func(funcs, "builtin", None, "id"):
            if (
                struct.calcsize("P") == 8
                and struct.calcsize("i") == 4
                and not (self.gx.int64 or self.gx.int128)
            ):
                error.error(
                    "return value of 'id' does not fit in 32-bit integer (try shedskin --int64)",
                    self.gx,
                    node,
                    warning=True,
                    mv=self.mv,
                )

        nrargs = len(node.args)
        if isinstance(func, python.Function) and func.largs:
            nrargs = func.largs

        # --- target expression
        if isinstance(node.func, ast.Attribute):
            self.gx.called.add(node.func)

        if node.func in self.mergeinh and [
            t for t in self.mergeinh[node.func] if isinstance(t[0], python.Function)
        ]:  # anonymous function
            self.visitm(node.func, "(", func)

        elif constructor:
            ts = self.namer.nokeywords(
                typestr.nodetypestr(self.gx, node, func, mv=self.mv)
            )
            if ts == "complex ":
                self.append("mcomplex(")
                constructor = None  # XXX
            else:
                if argtypes is not None:  # XXX merge instance_new
                    ts = typestr.typestr(self.gx, argtypes, mv=self.mv)
                    if ts.startswith("pyseq") or ts.startswith("pyiter"):  # XXX
                        argtypes = self.gx.merged_inh[node]
                        ts = typestr.typestr(self.gx, argtypes, mv=self.mv)
                self.append("(new " + ts[:-2] + "(")
            if funcs and len(funcs[0].formals) == 1 and not funcs[0].mv.module.builtin:
                self.append("1")  # don't call default constructor

        elif parent_constr:
            assert isinstance(node.func, ast.Attribute)
            cl = python.lookup_class(node.func.value, self.mv)
            assert cl
            self.append(self.namer.namespace_class(cl) + "::" + node.func.attr + "(")

        elif direct_call:  # XXX no namespace (e.g., math.pow), check nr of args
            if (
                ident == "float"
                and node.args
                and self.mergeinh[node.args[0]]
                == set([(python.def_class(self.gx, "float_"), 0)])
            ):
                self.visit(node.args[0], func)
                return
            if ident in [
                "abs",
                "int",
                "float",
                "str",
                "bytes",
                "bytearray",
                "dict",
                "tuple",
                "list",
                "type",
                "cmp",
                "sum",
                "zip",
            ]:
                self.append("__" + ident + "(")
            elif ident in ["min", "max", "iter", "round"]:
                self.append("___" + ident + "(")
            elif ident == "bool":
                self.bool_test(node.args[0], func, always_wrap=True)
                return
            elif ident == "pow" and direct_call.mv.module.ident == "builtin":
                if nrargs == 3:
                    third = node.args[2]
                else:
                    third = None
                self.power(node.args[0], node.args[1], third, func)
                return
            elif ident == "hash":
                self.append("hasher(")  # XXX cleanup
            elif ident == "__print":  # XXX
                if not node.keywords:
                    self.append("print(")
                    for i, arg in enumerate(node.args):
                        self.visit(arg, func)
                        if i != len(node.args) - 1:
                            self.append(", ")
                    self.append(")")
                    return
                self.append("print_(")
            elif ident == "isinstance":
                self.append("True")
                return
            else:
                if isinstance(node.func, ast.Name):
                    if (
                        isinstance(func, python.Function)
                        and isinstance(func.parent, python.Class)
                        and ident in func.parent.funcs
                    ):  # masked by method
                        self.append(funcs[0].mv.module.full_path() + "::")
                    self.append(self.cpp_name(funcs[0]))
                else:
                    self.visit(node.func)
                self.append("(")

        elif method_call:
            assert objexpr
            for cl, _ in self.mergeinh[objexpr]:
                if (
                    isinstance(cl, python.Class)
                    and cl.ident != "none"
                    and ident not in cl.funcs
                ):
                    conv = {
                        "int_": "int",
                        "float_": "float",
                        "str_": "str",
                        "class_": "class",
                        "none": "none",
                    }
                    clname = conv.get(cl.ident, cl.ident)
                    error.error(
                        "class '%s' has no method '%s'" % (clname, ident),
                        self.gx,
                        node,
                        warning=True,
                        mv=self.mv,
                    )
                if isinstance(cl, python.Class) and ident in cl.staticmethods:
                    error.error(
                        "staticmethod '%s' called without using class name" % ident,
                        self.gx,
                        node,
                        warning=True,
                        mv=self.mv,
                    )
                    return

            # tuple2.__getitem -> __getfirst__/__getsecond
            if (
                ident == "__getitem__"
                and isinstance(node.args[0], ast.Num)
                and isinstance(node.args[0].n, int)
                and node.args[0].n in (0, 1)
                and self.only_classes(objexpr, ("tuple2",))
            ):
                assert isinstance(node.func, ast.Attribute)
                self.visit(node.func.value, func)
                self.append(
                    "->%s()" % ["__getfirst__", "__getsecond__"][node.args[0].n]
                )
                return

            if ident == "__call__":
                self.visitm(node.func, "->__call__(", func)
            elif (
                ident == "is_integer"
                and isinstance(node.func, ast.Attribute)
                and (python.def_class(self.gx, "float_"), 0)
                in self.mergeinh[node.func.value]
            ):
                assert isinstance(node.func, ast.Attribute)
                self.visitm("__ss_is_integer(", node.func.value, ")", func)
                return
            else:
                self.visitm(node.func, "(", func)

        else:
            if ident:
                error.error(
                    "unresolved call to '" + ident + "'",
                    self.gx,
                    node,
                    mv=self.mv,
                    warning=True,
                )
            else:
                error.error(
                    "unresolved call (possibly caused by method passing, which is currently not allowed)",
                    self.gx,
                    node,
                    mv=self.mv,
                    warning=True,
                )
            return

        if not funcs:
            if constructor:
                self.append(")")
            self.append(")")
            return

        self.visit_callfunc_args(funcs, node, func)

        self.append(")")
        if constructor:
            self.append(")")

    def visit_callfunc_args(
        self,
        funcs: List["python.Function"],
        node: ast.Call,
        func: Optional["python.Function"],
    ) -> None:
        """Visit the arguments of a call node"""
        (
            objexpr,
            ident,
            direct_call,
            method_call,
            constructor,
            parent_constr,
            anon_func,
        ) = infer.analyze_callfunc(self.gx, node, merge=self.gx.merged_inh)
        target: Union[
            "python.Function", "python.Class"
        ]  # TODO should be one of the two
        target = funcs[0]  # XXX

        swap_env = False
        for name in (
            "execle",
            "execlpe",
            "spawnle",
            "spawnlpe",
        ):
            if self.library_func(funcs, "os", None, name):
                swap_env = True

        castnull = False  # XXX
        if (
            self.library_func(funcs, "random", None, "seed")
            or self.library_func(funcs, "random", None, "triangular")
            or self.library_func(funcs, "random", "Random", "seed")
            or self.library_func(funcs, "random", "Random", "triangular")
        ):
            castnull = True
        for itertools_func in ["islice", "zip_longest", "permutations", "accumulate"]:
            if self.library_func(funcs, "itertools", None, itertools_func):
                castnull = True
                break

        for f in funcs:
            if len(f.formals) != len(target.formals):
                error.error(
                    "calling functions with different numbers of arguments",
                    self.gx,
                    node,
                    warning=True,
                    mv=self.mv,
                )
                self.append(")")
                return

        assert isinstance(target, python.Function)
        if target.inherited_from:
            target = target.inherited_from
        assert isinstance(target, python.Function)

        rest: Union[int, None]

        pairs, rest, err = infer.connect_actual_formal(
            self.gx, node, target, parent_constr, merge=self.mergeinh
        )

        if (
            err
            and not self.library_func(funcs, "builtin", None, "sum")
            and not self.library_func(funcs, "builtin", None, "next")
        ):
            error.error(
                "call with incorrect number of arguments",
                self.gx,
                node,
                warning=True,
                mv=self.mv,
            )

        if isinstance(func, python.Function) and func.lambdawrapper:
            rest = func.largs

        assert target.node
        if target.node.args.vararg:
            assert isinstance(rest, int)
            self.append("%d" % rest)
            if rest or pairs:
                self.append(", ")

        double = False
        if ident in ["min", "max"]:
            for arg2 in node.args:
                if (
                    arg2 in self.mergeinh
                    and (python.def_class(self.gx, "float_"), 0) in self.mergeinh[arg2]
                ):
                    double = True

        self.add_args_arg(node, funcs)

        if isinstance(func, python.Function) and func.largs is not None:
            kw = [p for p in pairs if p[1].name.startswith("__kw_")]
            nonkw = [p for p in pairs if not p[1].name.startswith("__kw_")]
            pairs = kw + nonkw[: func.largs]

        # os.exec*, os.spawn* (C++ does not yet support non-terminal variadic arguments)
        if swap_env:
            pairs.insert(1, pairs.pop())

        for arg, formal in pairs:
            cast = False
            builtin_types = self.cast_to_builtin(
                arg, func, formal, target, method_call, objexpr
            )
            formal_types = builtin_types or self.mergeinh[formal]

            if double and self.mergeinh[arg] == set(
                [(python.def_class(self.gx, "int_"), 0)]
            ):
                cast = True
                self.append("(__ss_float(")
            elif castnull and ast_utils.is_none(arg):
                cast = True
                self.append("((void *)(")

            if arg in target.mv.defaults:
                if self.mergeinh[arg] == set(
                    [(python.def_class(self.gx, "none"), 0)]
                ):
                    self.append("NULL")
                elif target.mv.module == self.mv.module:
                    self.append("default_%d" % (target.mv.defaults[arg][0]))
                else:
                    self.append(
                        "%s::default_%d"
                        % (target.mv.module.full_path(), target.mv.defaults[arg][0])
                    )

            elif isinstance(arg, ast.Constant) and arg in self.consts:
                self.append(self.consts[arg])
            else:
                if (
                    constructor
                    and ident in ["set", "frozenset"]
                    and typestr.nodetypestr(self.gx, arg, func, mv=self.mv)
                    in [
                        "list<void *> *",
                        "tuple<void *> *",
                        "pyiter<void *> *",
                        "pyseq<void *> *",
                        "pyset<void *>",
                    ]
                ):  # XXX
                    pass
                elif not builtin_types and target.mv.module.builtin:
                    self.visit(arg, func)
                else:
                    self.impl_visit_conv(arg, formal_types, func)

            if cast:
                self.append("))")
            if (arg, formal) != pairs[-1]:
                self.append(", ")

        if constructor and ident in ("frozenset", "bytearray"):
            if pairs:
                self.append(",")
            if ident == "frozenset":
                self.append("1")
            else:
                self.append("0")

    def visit_IfExp(
        self, node: ast.IfExp, func: Optional["python.Function"] = None
    ) -> None:
        """Visit an if expression"""
        types = self.mergeinh[node]
        self.append("((")
        self.bool_test(node.test, func)
        self.append(")?(")
        self.impl_visit_conv(node.body, types, func)
        self.append("):(")
        self.impl_visit_conv(node.orelse, types, func)
        self.append("))")

    def visit_Attribute(
        self, node: ast.Attribute, func: Optional["python.Function"] = None
    ) -> None:  # XXX merge with visitGetattr
        """Generate a reference to an attribute variable"""
        if isinstance(node.ctx, ast.Load):
            cl, module = python.lookup_class_module(
                node.value, infer.inode(self.gx, node).mv, func
            )

            # module.attr
            if module:
                self.append(module.full_path() + "::")

            # class.attr: staticmethod
            elif cl and node.attr in cl.staticmethods:
                ident = cl.ident
                if cl.ident in [
                    "dict",
                    "int_",
                    "defaultdict",
                ]:  # own namespace because of template vars
                    self.append("__" + cl.ident + "__::")
                elif isinstance(node.value, ast.Attribute):
                    submodule = python.lookup_module(
                        node.value.value, infer.inode(self.gx, node).mv
                    )
                    assert submodule
                    self.append(submodule.full_path() + "::" + ident + "::")
                else:
                    self.append(ident + "::")

            # class.attr
            elif cl:  # XXX merge above?
                ident = cl.ident
                if isinstance(node.value, ast.Attribute):
                    submodule = python.lookup_module(
                        node.value.value, infer.inode(self.gx, node).mv
                    )
                    assert submodule
                    self.append(submodule.full_path() + "::" + cl.ident + "::")
                else:
                    self.append(ident + "::")

            # obj.attr
            else:
                checkcls: List["python.Class"] = []  # XXX better to just inherit vars?

                for t in self.mergeinh[node.value]:
                    if isinstance(t[0], python.Class):
                        checkcls.extend(t[0].ancestors(True))
                for cl in checkcls:
                    if (
                        node.attr not in t[0].funcs and node.attr in cl.parent.vars
                    ):  # XXX
                        error.error(
                            "class attribute '"
                            + node.attr
                            + "' accessed without using class name",
                            self.gx,
                            node,
                            warning=True,
                            mv=self.mv,
                        )
                        break

                    if node not in self.gx.called and [
                        cl for cl in checkcls if node.attr in cl.funcs
                    ]:
                        error.error(
                            "method passing is not supported",
                            self.gx,
                            node,
                            warning=True,
                            mv=self.mv,
                        )

                else:
                    if not self.mergeinh[node.value] and not node.attr.startswith(
                        "__"
                    ):  # XXX
                        error.error(
                            "expression has no type",
                            self.gx,
                            node,
                            warning=True,
                            mv=self.mv,
                        )
                    elif (
                        not self.mergeinh[node]
                        and not [cl for cl in checkcls if node.attr in cl.funcs]
                        and not node.attr.startswith("__")
                    ):  # XXX
                        error.error(
                            "expression has no type",
                            self.gx,
                            node,
                            warning=True,
                            mv=self.mv,
                        )

                if not isinstance(node.value, ast.Name):
                    self.append("(")
                if isinstance(node.value, ast.Name) and not python.lookup_var(
                    node.value.id, func, self.mv
                ):  # XXX XXX
                    self.append(node.value.id)
                else:
                    self.visit(node.value, func)
                if not isinstance(node.value, (ast.Name)):
                    self.append(")")

                self.append(self.connector(node.value, func))

            ident = node.attr

            # property
            lcp = typestr.lowest_common_parents(
                typestr.polymorphic_t(self.gx, self.mergeinh[node.value])
            )
            if len(lcp) == 1 and node.attr in lcp[0].properties:
                self.append(self.cpp_name(lcp[0].properties[node.attr][0]) + "()")
                return

            # getfast
            if ident == "__getitem__" and self.one_class(
                node.value, ("list", "str_", "tuple")
            ):
                ident = "__getfast__"
            elif (
                ident == "__getitem__" and len(lcp) == 1 and lcp[0].ident == "array"
            ):  # XXX merge into above
                ident = "__getfast__"

            if module:
                if module.builtin:
                    cppname = self.namer.nokeywords(ident)
                else:
                    cppname = self.cpp_name(ident)
            else:
                cppname = self.attr_var_ref(node, ident)
            self.append(cppname)

        elif isinstance(node.ctx, ast.Del):
            error.error(
                "'del' has no effect without refcounting",
                self.gx,
                node,
                warning=True,
                mv=self.mv,
            )
        elif isinstance(node.ctx, ast.Store):
            cl, module = python.lookup_class_module(
                node.value, infer.inode(self.gx, node).mv, func
            )

            # module.attr
            if module:
                self.append(module.full_path() + "::")

            # class.attr
            elif cl:
                if isinstance(node.value, ast.Attribute):
                    submodule = python.lookup_module(
                        node.value.value, infer.inode(self.gx, node).mv
                    )
                    assert submodule
                    self.append(submodule.full_path() + "::" + cl.ident + "::")
                else:
                    self.append(cl.ident + "::")

            # obj.attr
            else:
                if isinstance(node.value, ast.Name) and not python.lookup_var(
                    node.value.id, func, self.mv
                ):  # XXX
                    self.append(node.value.id)
                else:
                    self.visit(node.value, func)
                self.append(self.connector(node.value, func))  # XXX '->'

            self.append(self.attr_var_ref(node, node.attr))
        else:
            error.error(
                "unknown ctx type for ast.Attribute, " + str(type(node.ctx)),
                self.gx,
                node,
                mv=self.mv,
            )

    def visit_Subscript(
        self, node: ast.Subscript, func: Optional["python.Function"] = None
    ) -> None:
        """Generate a subscript operation"""
        if isinstance(node.ctx, (ast.Load, ast.Store)):
            fakefunc = infer.inode(self.gx, node.value).fakefunc
            assert fakefunc
            self.visit_Call(fakefunc, func)
        elif isinstance(node.ctx, ast.Del):
            fakefunc = infer.inode(self.gx, node.value).fakefunc
            assert fakefunc
            self.start()
            if isinstance(node.slice, ast.Slice):
                self.visit_Call(fakefunc, func)
            else:
                self.visit_Call(fakefunc, func)
            self.eol()
        else:
            error.error(
                "unknown ctx type for ast.Subscript, " + str(type(node.ctx)),
                self.gx,
                node,
                mv=self.mv,
            )

    def visit_Name(
        self,
        node: ast.Name,
        func: Optional["python.Function"] = None,
        add_cl: bool = True,
    ) -> None:
        """Generate a reference to a variable"""
        if isinstance(node.ctx, ast.Del):
            error.error(
                "'del' has no effect without refcounting",
                self.gx,
                node,
                warning=True,
                mv=self.mv,
            )
        elif type(node.ctx) in (ast.Store, ast.Param):
            self.append(self.cpp_name(node.id))
        elif type(node.ctx) in (ast.Load,):
            map = {"True": "True", "False": "False"}
            if node in self.mv.lwrapper:
                self.append(self.mv.lwrapper[node])
            elif node.id == "None":  # py2
                self.append("NULL")
            elif node.id == "self":
                lcp = typestr.lowest_common_parents(
                    typestr.polymorphic_t(self.gx, self.mergeinh[node])
                )
                if (
                    not func
                    or func.listcomp
                    or not isinstance(func.parent, python.Class)
                ) or (
                    func and func.parent and func.isGenerator
                ):  # XXX python.lookup_var?
                    self.append("self")
                elif len(lcp) == 1 and not (
                    lcp[0] is func.parent or lcp[0] in func.parent.ancestors()
                ):  # see test 160
                    self.mv.module.prop_includes.add(lcp[0].module)  # XXX generalize
                    self.append("((" + self.namer.namespace_class(lcp[0]) + " *)this)")
                else:
                    self.append("this")
            elif node.id in map:
                self.append(map[node.id])

            else:  # XXX clean up
                if (
                    not self.mergeinh[node]
                    and infer.inode(self.gx, node).parent
                    not in self.gx.inheritance_relations
                ):
                    error.error(
                        "variable '" + node.id + "' has no type",
                        self.gx,
                        node,
                        warning=True,
                        mv=self.mv,
                    )
                    self.append(node.id)
                elif typestr.singletype(self.gx, node, python.Module):
                    self.append(
                        "__"
                        + typestr.singletype(self.gx, node, python.Module).ident
                        + "__"
                    )
                else:
                    if (python.def_class(self.gx, "class_"), 0) in self.mergeinh[
                        node
                    ] or (
                        add_cl
                        and [
                            t
                            for t in self.mergeinh[node]
                            if isinstance(t[0], python.StaticClass)
                        ]
                    ):
                        cl = python.lookup_class(node, self.mv)
                        if cl:
                            self.append(self.namer.namespace_class(cl, add_cl="cl_"))
                        else:
                            self.append(self.cpp_name(node.id))
                    else:
                        if (
                            isinstance(func, python.Class)
                            and node.id in func.parent.vars
                        ):  # XXX
                            self.append(func.ident + "::")
                        var = python.smart_lookup_var(node.id, func, self.mv)
                        if var:
                            if var.is_global:
                                self.append(self.module.full_path() + "::")
                            self.append(self.cpp_name(var.var))
                        else:
                            self.append(node.id)  # XXX
        else:
            error.error(
                "unknown ctx type for Name, " + str(type(node.ctx)),
                self.gx,
                node,
                mv=self.mv,
            )

    def visit_Constant(
        self, node: ast.Constant, func: Optional["python.Function"] = None
    ) -> None:
        """Generate a constant value"""
        value = node.value

        if isinstance(value, bool):
            self.append(str(value))

        elif value is None:
            self.append("NULL")

        elif value.__class__.__name__ in ("int", "long"):  # isinstance(value, int):
            self.append("__ss_int(")
            self.append(str(value))
            if self.gx.int64 or self.gx.int128:
                self.append("LL")
            self.append(")")

        elif isinstance(value, float):
            self.append("__ss_float(")
            if str(value) in ["inf", "1.#INF", "Infinity"]:
                self.append("INFINITY")
            elif str(value) in ["-inf", "-1.#INF", "-Infinity"]:
                self.append("-INFINITY")
            else:
                self.append(str(value))
            self.append(")")

        elif isinstance(value, complex):
            self.append("mcomplex(%s, %s)" % (value.real, value.imag))

        elif isinstance(value, str):
            if not self.filling_consts:
                const = self.get_constant(node)
                assert const
                self.append(const)
            else:
                self.append('new str("%s"' % self.expand_special_chars(value))
                if "\0" in value:
                    self.append(", %d" % len(value))
                self.append(")")

        elif isinstance(value, bytes):  # TODO merge with str above
            if not self.filling_consts:
                const = self.get_constant(node)
                assert const
                self.append(const)
            else:
                self.append('new bytes("%s"' % self.expand_special_chars(value))
                if b"\0" in value:
                    self.append(", %d" % len(value))
                self.append(")")

        else:
            assert False

    def visit_List(
        self,
        node: ast.List,
        func: Optional["python.Function"] = None,
        argtypes: Optional[Types] = None,
    ) -> None:
        """Visit a list node"""

        if isinstance(node.ctx, ast.Load):
            self.visit_tuple_list(node, func, argtypes)
        elif isinstance(node.ctx, ast.Store):
            assert False
        elif isinstance(node.ctx, ast.Del):
            assert False
        else:
            error.error(
                "unknown ctx type for ast.List, " + str(type(node.ctx)),
                self.gx,
                node,
                mv=self.mv,
            )

    def visit_Tuple(
        self,
        node: ast.Tuple,
        func: Optional["python.Function"] = None,
        argtypes: Optional[Types] = None,
    ) -> None:
        """Visit a tuple node"""
        if isinstance(node.ctx, ast.Load):
            if len(node.elts) > 2:
                types = set()
                for child in node.elts:
                    types.update(self.mergeinh[child])
            self.visit_tuple_list(node, func, argtypes)

        elif isinstance(node.ctx, ast.Store):
            assert False
        elif isinstance(node.ctx, ast.Del):
            assert False
        else:
            error.error(
                "unknown ctx type for Tuple, " + str(type(node.ctx)),
                self.gx,
                node,
                mv=self.mv,
            )

    def visit_Set(
        self,
        node: ast.Set,
        func: Optional["python.Function"] = None,
        argtypes: Optional[Types] = None,
    ) -> None:
        """Visit a set node"""
        self.visit_tuple_list(node, func, argtypes)

    def visit_Dict(
        self,
        node: ast.Dict,
        func: Optional["python.Function"] = None,
        argtypes: Optional[Types] = None,
    ) -> None:
        """Visit a dictionary node"""
        argtypes = self.instance_new(node, argtypes)
        if node.keys:
            self.append(str(len(node.keys)) + ", ")
        ts_key = typestr.typestr(self.gx, self.subtypes(argtypes, "unit"), mv=self.mv)
        ts_value = typestr.typestr(
            self.gx, self.subtypes(argtypes, "value"), mv=self.mv
        )
        items = list(zip(node.keys, node.values))
        for key, value in items:
            assert key  # TODO when None?
            if ts_key == ts_value:
                self.visitm("(new tuple<%s>(2," % ts_key, func)
            else:
                self.visitm("(new tuple2<%s, %s>(2," % (ts_key, ts_value), func)
            type_child = self.subtypes(argtypes, "unit")
            self.impl_visit_conv(key, type_child, func)
            self.append(",")
            type_child = self.subtypes(argtypes, "value")
            self.impl_visit_conv(value, type_child, func)
            self.append("))")
            if (key, value) != items[-1]:
                self.append(",")
        self.append("))")

    def visit_tuple_list(
        self,
        node: Union[ast.Tuple, ast.List, ast.Set],
        func: Optional["python.Function"] = None,
        argtypes: Optional[Types] = None,
    ) -> None:
        """Visit a tuple, list, or set node"""
        if isinstance(func, python.Class):  # XXX
            func = None
        argtypes = self.instance_new(node, argtypes)
        children = list(node.elts)
        if children:
            self.append(str(len(children)) + ",")
        if len(children) >= 2 and self.bin_tuple(argtypes):  # XXX >=2?
            type_child = self.subtypes(argtypes, "first")
            self.impl_visit_conv(children[0], type_child, func)
            self.append(",")
            type_child = self.subtypes(argtypes, "second")
            self.impl_visit_conv(children[1], type_child, func)
        else:
            for child in children:
                type_child = self.subtypes(argtypes, "unit")
                self.impl_visit_conv(child, type_child, func)
                if child != children[-1]:
                    self.append(",")
        self.append("))")

    def visit_ListComp(
        self, node: ast.ListComp, func: Optional["python.Function"] = None
    ) -> None:
        """Generate a list comprehension"""
        lcfunc, _ = self.listcomps[node]
        args = []
        temp = self.line

        for name in lcfunc.misses:
            var = python.lookup_var(name, func, self.mv)
            if var and var.parent:
                if name == "self" and not (func and func.listcomp):
                    args.append("this")
                else:
                    args.append(self.cpp_name(var))

        self.line = temp
        if node in self.gx.genexp_to_lc.values():
            self.append("new ")
        self.append(lcfunc.ident + "(" + ", ".join(args) + ")")

    def visit_SetComp(
        self, node: ast.SetComp, func: Optional["python.Function"] = None
    ) -> None:
        """Generate a set comprehension"""
        self.visit(self.gx.setcomp_to_lc[node], func)

    def visit_DictComp(
        self, node: ast.DictComp, func: Optional["python.Function"] = None
    ) -> None:
        """Generate a dict comprehension"""
        self.visit(self.gx.dictcomp_to_lc[node], func)

    def visit_GeneratorExp(
        self, node: ast.GeneratorExp, func: Optional["python.Function"] = None
    ) -> None:
        """Generate a generator expression"""
        self.visit(self.gx.genexp_to_lc[node], func)

    def visit_Lambda(self, node: ast.Lambda, parent: Optional[Parent] = None) -> None:
        """Visit a lambda node"""
        self.append(self.mv.lambdaname[node])

    def visit_JoinedStr(
        self, node: ast.JoinedStr, func: Optional["python.Function"] = None
    ) -> None:
        """Generate a joined string"""
        self.append("__add_strs(%d, " % len(node.values))
        for i, value in enumerate(node.values):
            if isinstance(value, ast.FormattedValue):
                value = value.value
            self.visitm("__str(", value, ")", func)
            if i != len(node.values) - 1:
                self.append(", ")
        self.append(")")

    def visit_Slice(
        self, node: ast.Slice, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a slice node"""
        assert False

    def visit_Yield(self, node: ast.Yield, func: "python.Function") -> None:
        """Generate a yield statement"""
        self.output("__last_yield = %d;" % func.yieldNodes.index(node))
        self.start("__result = ")
        assert node.value  # added in graph.py
        self.impl_visit_conv(node.value, self.mergeinh[func.yieldnode.thing], func)
        self.eol()
        self.output("return __result;")
        self.output("__after_yield_%d:;" % func.yieldNodes.index(node))
        self.start()

