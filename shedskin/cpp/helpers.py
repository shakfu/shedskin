# SHED SKIN Python-to-C++ Compiler
# Copyright 2005-2024 Mark Dufour and contributors; GNU GPL version 3 (See LICENSE)
"""shedskin.cpp.helpers - Helper methods for code generation

This module contains helper methods including:
- do_* methods for specialized code generation
- Optimization detection for loops (fastfor, fastenumerate, fastzip2, etc.)
- Loop generation helpers
"""

import ast
from typing import TYPE_CHECKING, Any, List, Optional, Tuple, TypeAlias, Union

from .. import ast_utils, python, typestr

if TYPE_CHECKING:
    pass

Types: TypeAlias = set[Tuple["python.Class", int]]


class HelperMixin:
    """Mixin for helper methods"""

    def do_main(self) -> None:
        """Generate the main function"""
        modules = self.gx.modules.values()
        if any(module.builtin and module.ident == "sys" for module in modules):
            self.print("int main(int __ss_argc, char **__ss_argv) {")
        else:
            self.print("int main(int, char **) {")
        self.do_init_modules()
        self.print("    __shedskin__::__start(__%s__::__init);" % self.module.ident)
        self.print("}")

    def do_init_modules(self, extmod: bool = False) -> None:
        """Initialize modules"""
        self.print("    __shedskin__::__init();")
        for module in sorted(self.gx.modules.values(), key=lambda x: x.import_order):
            if module != self.gx.main_module and module.ident != "builtin":
                if module.ident == "sys":
                    if self.gx.pyextension_product:
                        self.print("    __sys__::__init(0, 0);")
                    else:
                        self.print("    __sys__::__init(__ss_argc, __ss_argv);")
                else:
                    if extmod and not module.builtin:
                        self.print(
                            "    "
                            + module.full_path()
                            + "::PyInit_%s();" % "_".join(module.name_list)
                        )
                    self.print("    " + module.full_path() + "::__init();")

    def do_comment(self, s: Optional[str]) -> None:
        """Generate a comment"""
        if not s:
            return
        s = s.encode("ascii", "ignore").decode("ascii")  # TODO
        doc = s.replace("/*", "//").replace("*/", "//").split("\n")
        self.output("/**")
        if doc[0].strip():
            self.output(doc[0])
        rest = textwrap.dedent("\n".join(doc[1:])).splitlines()
        for line in rest:
            self.output(line)
        self.output("*/")

    def do_comments(self, child: ast.AST) -> None:
        """Generate comments for a node"""
        pass

    #        if child in self.gx.comments:
    #            for n in self.gx.comments[child]:
    #                self.do_comment(n)

    def do_fastfor(
        self,
        node: Union[ast.For, ast.ListComp],
        qual: Union[ast.For, ast.comprehension],
        quals: Optional[List[ast.comprehension]],
        iter: str,
        func: Optional["python.Function"],
        genexpr: bool,
    ) -> None:
        """Generate a fast for loop"""
        assert isinstance(qual.iter, ast.Call)
        if len(qual.iter.args) == 3 and not ast_utils.is_literal(qual.iter.args[2]):
            for arg in qual.iter.args:  # XXX simplify
                if arg in self.mv.tempcount:
                    self.start()
                    self.visitm(self.mv.tempcount[arg], " = ", arg, func)
                    self.eol()
        self.fastfor(qual, iter, func)
        self.forbody(node, quals, iter, func, False, genexpr)

    # XXX generalize?
    def do_fastzip2(
        self,
        node: Union[ast.For, ast.comprehension],
        func: Optional["python.Function"],
        genexpr: bool,
    ) -> None:
        """Generate a fast zip2 loop"""
        assert isinstance(node.iter, ast.Call)
        assert isinstance(node.target, (ast.Tuple, ast.List))

        self.start("FOR_IN_ZIP(")
        left, right = node.target.elts
        self.do_fastzip2_one(left, func)
        self.do_fastzip2_one(right, func)
        self.visitm(node.iter.args[0], ",", node.iter.args[1], ",", func)
        tail1 = (
            self.mv.tempcount[(node, 2)][2:]
            + ","
            + self.mv.tempcount[(node, 3)][2:]
            + ","
        )
        tail2 = (
            self.mv.tempcount[(node.iter)][2:] + "," + self.mv.tempcount[(node, 4)][2:]
        )
        self.print(self.line + tail1 + tail2 + ")")
        self.indent()
        if ast_utils.is_assign_list_or_tuple(left):
            assert isinstance(left, (ast.Tuple, ast.List))
            self.tuple_assign(left, self.mv.tempcount[left], func)
        if ast_utils.is_assign_list_or_tuple(right):
            assert isinstance(right, (ast.Tuple, ast.List))
            self.tuple_assign(right, self.mv.tempcount[right], func)

    def do_fastzip2_one(self, node: ast.AST, func: Optional["python.Function"]) -> None:
        """Generate a fast zip2 loop one"""
        if ast_utils.is_assign_list_or_tuple(node):
            self.append(self.mv.tempcount[node])
        else:
            self.visit(node, func)
        self.append(",")

    def do_fastenumerate(
        self,
        node: Union[ast.For, ast.comprehension],
        func: Optional["python.Function"],
        genexpr: bool,
    ) -> None:
        """Generate a fast enumerate loop"""
        assert isinstance(node.iter, ast.Call)
        assert isinstance(node.target, (ast.Tuple, ast.List))
        if self.only_classes(node.iter.args[0], ("tuple", "list")):
            self.start("FOR_IN_ENUMERATE(")
        else:
            self.start("FOR_IN_ENUMERATE_STR(")
        left, right = node.target.elts
        self.do_fastzip2_one(right, func)
        self.visit(node.iter.args[0], func)
        tail = self.mv.tempcount[(node, 2)][2:] + "," + self.mv.tempcount[node.iter][2:]
        self.print(self.line + "," + tail + ")")
        self.indent()
        self.start()
        self.visitm(left, " = " + self.mv.tempcount[node.iter], func)
        self.eol()
        if ast_utils.is_assign_list_or_tuple(right):
            assert isinstance(right, (ast.Tuple, ast.List))
            self.tuple_assign(right, self.mv.tempcount[right], func)

    def do_fastdictiter(
        self,
        node: Union[ast.For, ast.comprehension],
        func: Optional["python.Function"],
        genexpr: bool,
    ) -> None:
        """Generate a fast dict iterator loop"""
        self.start("FOR_IN_DICT(")
        assert isinstance(node.target, (ast.Tuple, ast.List))
        left, right = node.target.elts
        tail = (
            self.mv.tempcount[node, 7][2:]
            + ","
            + self.mv.tempcount[node, 6][2:]
            + ","
            + self.mv.tempcount[node.iter][2:]
        )
        assert isinstance(node.iter, ast.Call)
        assert isinstance(node.iter.func, ast.Attribute)
        self.visit(node.iter.func.value, func)
        self.print(self.line + "," + tail + ")")
        self.indent()
        self.start()
        if left in self.mv.tempcount:  # XXX not for zip, enum..?
            self.visitm(
                "%s = (*%s).first"
                % (self.mv.tempcount[left], self.mv.tempcount[node, 6]),
                func,
            )
        else:
            self.visitm(left, " = (*%s).first" % self.mv.tempcount[node, 6], func)
        self.eol()
        self.start()
        if right in self.mv.tempcount:
            self.visitm(
                "%s = (*%s).second"
                % (self.mv.tempcount[right], self.mv.tempcount[node, 6]),
                func,
            )
        else:
            self.visitm(right, " = (*%s).second" % self.mv.tempcount[node, 6], func)
        self.eol()
        self.output(self.mv.tempcount[node, 6] + "++;")
        if ast_utils.is_assign_list_or_tuple(left):
            assert isinstance(left, (ast.Tuple, ast.List))
            self.tuple_assign(left, self.mv.tempcount[left], func)
        if ast_utils.is_assign_list_or_tuple(right):
            assert isinstance(right, (ast.Tuple, ast.List))
            self.tuple_assign(right, self.mv.tempcount[right], func)

    def do_compare(
        self,
        left: ast.AST,
        right: ast.AST,
        middle: Optional[str],
        inline: Optional[str],
        func: Optional["python.Function"] = None,
        prefix: Optional[str] = None,
    ) -> None:
        """Generate a comparison operation"""
        ltypes = self.mergeinh[left]
        rtypes = self.mergeinh[right]
        argtypes = ltypes | rtypes
        ul, ur = typestr.unboxable(self.gx, ltypes), typestr.unboxable(self.gx, rtypes)

        # expr (not) in [const, ..]/(const, ..)
        if (
            middle == "__contains__"
            and isinstance(left, (ast.Tuple, ast.List))
            and left.elts
            and all([isinstance(elt, ast.Constant) for elt in left.elts])
        ):
            self.append("(")
            for i, elem in enumerate(left.elts):
                if prefix == "!":
                    self.append("!__eq(")  # XXX why does using __ne( fail test 199!?
                else:
                    self.append("__eq(")

                if i == 0:
                    self.visitm(self.mv.tempcount[(left, "cmp")], "=", right, func)
                else:
                    self.visitm(self.mv.tempcount[(left, "cmp")], func)

                self.append(",")
                self.visit(elem, func)
                self.append(")")
                if i != len(left.elts) - 1:
                    if prefix == "!":
                        self.append(" && ")
                    else:
                        self.append(" || ")
            self.append(")")
            return

        # --- inline other
        if inline and (
            (ul and ur)
            or not middle
            or ast_utils.is_none(left)
            or ast_utils.is_none(right)
        ):  # XXX not middle, cleanup?
            self.visit2(left, argtypes, middle, func)
            self.append(inline)
            self.visit2(right, argtypes, middle, func)
            return

        # --- prefix '!'
        postfix = ""
        if prefix:
            self.append("(" + prefix)
            postfix = ")"

        # --- comparison
        if middle in ["__eq__", "__ne__", "__gt__", "__ge__", "__lt__", "__le__"]:
            self.append(middle[:-2] + "(")
            self.visit2(left, argtypes, middle, func)
            self.append(", ")
            self.visit2(right, argtypes, middle, func)
            self.append(")" + postfix)
            return

        # --- default: left, connector, middle, right
        self.append("(")
        self.visit2(left, argtypes, middle, func)
        self.append(")")
        if middle == "==":
            self.append("==(")
        else:
            assert middle
            self.append(self.connector(left, func) + middle + "(")
        self.visit2(right, argtypes, middle, func)
        self.append(")" + postfix)

    def do_lambdas(self, declare: bool) -> None:
        """Generate lambda functions"""
        for lam in self.mv.lambdas.values():
            if lam.ident not in self.mv.funcs:
                assert lam.node
                self.visit_FunctionDef(lam.node, declare=declare)

    def do_listcomps(self, declare: bool) -> None:
        """Generate list comprehensions"""
        for listcomp, lcfunc, func in self.mv.listcomps:  # XXX cleanup
            if lcfunc.mv.module.builtin:
                continue

            parent: Optional[AllParent] = func
            while isinstance(parent, python.Function) and parent.listcomp:
                parent = parent.parent

            if isinstance(parent, python.Function):
                if not self.inhcpa(parent) or parent.inherited:
                    continue

            genexpr = listcomp in self.gx.genexp_to_lc.values()
            if declare:
                self.listcomp_head(listcomp, True, genexpr)
            elif genexpr:
                self.genexpr_class(listcomp, declare)
            else:
                self.listcomp_func(listcomp)

    def fastfor(
        self,
        node: Union[ast.For, ast.comprehension],
        assname: str,
        func: Optional["python.Function"] = None,
    ) -> None:
        """Generate a fast for loop"""
        # --- for i in range(..) -> for( i=l, u=expr; i < u; i++ ) ..
        ivar, evar = self.mv.tempcount[node.target], self.mv.tempcount[node.iter]
        self.start("FAST_FOR(%s," % assname)

        assert isinstance(node.iter, ast.Call)

        if len(node.iter.args) == 1:
            self.append("0,")
            self.impl_visit_temp(node.iter.args[0], func)
            self.append(",")
        else:
            self.impl_visit_temp(node.iter.args[0], func)
            self.append(",")
            self.impl_visit_temp(node.iter.args[1], func)
            self.append(",")

        if len(node.iter.args) != 3:
            self.append("1")
        else:
            self.impl_visit_temp(node.iter.args[2], func)
        self.append(",%s,%s)" % (ivar[2:], evar[2:]))
        self.print(self.line)

    def fastenumerate(self, node: Union[ast.For, ast.comprehension]) -> bool:
        """Check if a node is a fast enumerate loop"""
        return (
            isinstance(node.iter, ast.Call)
            and ast_utils.is_enumerate(node)
            and self.only_classes(node.iter.args[0], ("tuple", "list", "str_"))
        )

    def fastzip2(self, node: Union[ast.For, ast.comprehension]) -> bool:
        """Check if a node is a fast zip2 loop"""
        names = ("tuple", "list")
        return (
            isinstance(node.iter, ast.Call)
            and ast_utils.is_zip2(node)
            and self.only_classes(node.iter.args[0], names)
            and self.only_classes(node.iter.args[1], names)
        )

    def fastdictiter(self, node: Union[ast.For, ast.comprehension]) -> bool:
        """Check if a node is a fast dict iterator loop"""
        return (
            isinstance(node.iter, ast.Call)
            and ast_utils.is_assign_list_or_tuple(node.target)
            and self.only_classes(node.iter.func, ("dict",))
            and isinstance(node.iter.func, ast.Attribute)
            and node.iter.func.attr == "items"
        )

    def forin_preftail(
        self, node: Union[ast.For, ast.comprehension]
    ) -> Tuple[str, str]:
        """Get the prefix and tail for a for in loop"""
        tail = self.mv.tempcount[node][2:] + "," + self.mv.tempcount[node.iter][2:]
        tail += "," + self.mv.tempcount[(node, 5)][2:]
        return "", tail

    def forbody(
        self,
        node: Union[ast.For, ast.ListComp],
        quals: Optional[List[ast.comprehension]],
        iter: str,
        func: Optional["python.Function"],
        skip: bool,
        genexpr: bool,
    ) -> None:
        """Generate the body of a for loop"""
        if quals is not None:
            assert isinstance(node, ast.ListComp)
            assert func
            self.listcompfor_body(node, quals, iter, func, False, genexpr)
            return
        assert isinstance(node, ast.For)
        if not skip:
            self.indent()
            if ast_utils.is_assign_list_or_tuple(node.target):
                assert isinstance(node.target, (ast.List, ast.Tuple))
                self.tuple_assign(node.target, self.mv.tempcount[node.target], func)
        self.gx.loopstack.append(node)
        for child in node.body:
            self.visit(child, func)
        self.gx.loopstack.pop()
        self.deindent()
        self.output("END_FOR")
        if node.orelse:
            self.output("if (!%s) {" % self.mv.tempcount[node.orelse[0]])
            self.indent()
            for child in node.orelse:
                self.visit(child, func)
            self.deindent()
            self.output("}")

