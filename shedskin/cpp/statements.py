# SHED SKIN Python-to-C++ Compiler
# Copyright 2005-2024 Mark Dufour and contributors; GNU GPL version 3 (See LICENSE)
"""shedskin.cpp.statements - Statement visitor methods

This module contains visitor methods for Python statement AST nodes.
"""

import ast
from typing import TYPE_CHECKING, Any, List, Optional, Tuple, TypeAlias, Union

from .. import error, infer, python, typestr

if TYPE_CHECKING:
    pass

# Type aliases (from cpp.py)
Types: TypeAlias = set[Tuple["python.Class", int]]
Parent: TypeAlias = Union["python.Class", "python.Function"]
AllParent: TypeAlias = Union["python.Class", "python.Function", "python.StaticClass"]


class StatementVisitorMixin:
    """Mixin for statement visitor methods"""

    def visit_Module(self, node: ast.Module, declare: bool = False) -> None:
        """Visit a module node"""
        if declare:
            self.module_hpp(node)
        else:
            self.module_cpp(node)

    def visit_FunctionDef(
        self,
        node: ast.FunctionDef,
        parent: Optional[Parent] = None,
        declare: bool = False,
    ) -> None:
        """Visit a function definition node"""
        # locate right func instance
        if parent and isinstance(parent, python.Class):
            func = parent.funcs[node.name]
        elif node.name in self.mv.funcs:
            func = self.mv.funcs[node.name]
        else:
            func = self.mv.lambdas[node.name]
        if func.invisible or (func.inherited and not func.ident == "__init__"):
            return
        if declare and func.declared:  # XXX
            return

        # check whether function is called at all (possibly via inheritance)
        if not self.inhcpa(func):
            if func.ident in ["__iadd__", "__isub__", "__imul__"]:
                return
            if func.lambdanr is None and not ast.dump(node.body[0]).startswith(
                "Raise(type=Call(func=Name(id='NotImplementedError'"
            ):
                error.error(
                    repr(func) + " not called!", self.gx, node, warning=True, mv=self.mv
                )
            if not (
                declare
                and isinstance(func.parent, python.Class)
                and func.ident in func.parent.virtuals
            ):
                return

        if func.isGenerator and not declare:
            self.generator_class(func)

        self.func_header(func, declare)
        if declare:
            return
        self.indent()

        if func.isGenerator:
            self.generator_body(func)
            return

        # --- local declarations
        self.local_defs(func)

        # --- function body
        for child in node.body:
            self.visit(child, func)
        if func.fakeret:
            self.visit(func.fakeret, func)

        # --- add Return(None) (sort of) if function doesn't already end with a Return
        if node.body:
            lastnode = node.body[-1]
            if (
                not func.ident == "__init__"
                and not func.fakeret
                and not isinstance(lastnode, ast.Return)
            ):
                assert func.retnode
                self.output(
                    "return %s;" % self.nothing(self.mergeinh[func.retnode.thing])
                )

        self.deindent()
        self.output("}\n")

    # XXX merge?
    def visit_For(
        self, node: ast.For, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a for loop node"""
        if isinstance(node.target, ast.Name):
            assname = node.target.id
        elif ast_utils.is_assign_attribute(node.target):
            assert isinstance(node.target, ast.Attribute)
            self.start("")
            self.visit_Attribute(node.target, func)
            assname = self.line.strip()  # XXX yuck
        else:
            assname = self.mv.tempcount[node.target]
        assname = self.cpp_name(assname)
        self.print()
        if node.orelse:
            self.output("%s = 0;" % self.mv.tempcount[node.orelse[0]])
        if ast_utils.is_fastfor(node):
            self.do_fastfor(node, node, None, assname, func, False)
        elif self.fastenumerate(node):
            self.do_fastenumerate(node, func, False)
            self.forbody(node, None, assname, func, True, False)
        elif self.fastzip2(node):
            self.do_fastzip2(node, func, False)
            self.forbody(node, None, assname, func, True, False)
        elif self.fastdictiter(node):
            self.do_fastdictiter(node, func, False)
            self.forbody(node, None, assname, func, True, False)
        else:
            pref, tail = self.forin_preftail(node)
            self.start("FOR_IN%s(%s," % (pref, assname))
            self.visit(node.iter, func)
            self.print(self.line + "," + tail + ")")
            self.forbody(node, None, assname, func, False, False)
        self.print()

    def visit_While(
        self, node: ast.While, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a while node"""
        self.print()
        if node.orelse:
            self.output("%s = 0;" % self.mv.tempcount[node.orelse[0]])

        self.start("while (")
        self.bool_test(node.test, func)
        self.append(") {")
        self.print(self.line)
        self.indent()
        self.gx.loopstack.append(node)
        for child in node.body:
            self.visit(child, func)
        self.gx.loopstack.pop()
        self.deindent()
        self.output("}")

        if node.orelse:
            self.output("if (!%s) {" % self.mv.tempcount[node.orelse[0]])
            self.indent()
            for child in node.orelse:
                self.visit(child, func)
            self.deindent()
            self.output("}")

    def visit_If(
        self,
        node: ast.If,
        func: Optional["python.Function"] = None,
        else_if: int = 0,
        root_if: Optional[ast.If] = None,
    ) -> None:
        """Visit an if statement"""
        # break up long if-elif-elif.. chains (MSVC error C1061, c64/hq2x examples)
        root_if = root_if or node
        if else_if == 0:
            if root_if in self.mv.tempcount:
                self.output(self.mv.tempcount[root_if] + " = (__ss_int)1;")
            self.start()
            self.append("if (")
        else:
            if root_if in self.mv.tempcount and else_if % 100 == 0:
                self.output("else")
                self.output("    " + self.mv.tempcount[root_if] + " = (__ss_int)0;")
                if else_if > 100:
                    self.output("}")
                self.output("if(!" + self.mv.tempcount[root_if] + ") {")
                self.output("    " + self.mv.tempcount[root_if] + " = (__ss_int)1;")
                self.start()
                self.append("if (")
            else:
                self.start()
                self.append("else if (")

        # test condition, body
        self.bool_test(node.test, func)
        self.print(self.line + ") {")
        self.indent()
        for child in node.body:  # TODO used in many places.. can we just visit a list?
            self.visit(child, func)
        self.deindent()
        self.output("}")

        if node.orelse:
            if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                self.visit_If(node.orelse[0], func, else_if + 1, root_if)
            else:
                self.output("else {")
                self.indent()
                for child in node.orelse:
                    self.visit(child, func)
                self.deindent()
                self.output("}")

                if root_if in self.mv.tempcount:
                    self.output("}")
        elif root_if in self.mv.tempcount:
            self.output("}")

    def visit_Try(
        self, node: ast.Try, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a try node"""
        self.start("try {")
        self.print(self.line)
        self.indent()
        if node.orelse:
            self.output("%s = 0;" % self.mv.tempcount[node.orelse[0]])
        for child in node.body:
            self.visit(child, func)
        if node.orelse:
            self.output("%s = 1;" % self.mv.tempcount[node.orelse[0]])
        self.deindent()
        self.start("}")

        # except
        for handler in node.handlers:
            pairs: List[Tuple[Optional[ast.expr], Optional[str], List[ast.stmt]]]
            if isinstance(handler.type, ast.Tuple):
                pairs = [(n, handler.name, handler.body) for n in handler.type.elts]
            else:
                pairs = [(handler.type, handler.name, handler.body)]

            for h0, h1, h2 in pairs:
                if isinstance(h0, ast.Name) and h0.id in [
                    "int",
                    "float",
                    "str",
                    "class",
                ]:
                    continue  # XXX python.lookup_class
                elif h0:
                    cl = python.lookup_class(h0, self.mv)
                    assert cl
                    if cl.mv.module.builtin and cl.ident in [
                        "KeyboardInterrupt",
                        "FloatingPointError",
                        "OverflowError",
                        "ZeroDivisionError",
                        "SystemExit",
                    ]:
                        error.error(
                            "system '%s' is not caught" % cl.ident,
                            self.gx,
                            h0,
                            warning=True,
                            mv=self.mv,
                        )
                    arg = self.namer.namespace_class(cl) + " *"
                else:
                    arg = "Exception *"

                if isinstance(h1, str):
                    arg += h1
                elif isinstance(h1, ast.Name):  # py2
                    arg += h1.id

                self.append(" catch (%s) {" % arg)
                self.print(self.line)
                self.indent()
                for child in h2:
                    self.visit(child, func)
                self.deindent()
                self.start("}")
        self.print(self.line)

        # else
        if node.orelse:
            self.output("if(%s) { // else" % self.mv.tempcount[node.orelse[0]])
            self.indent()
            for child in node.orelse:
                self.visit(child, func)
            self.deindent()
            self.output("}")

    def visit_With(
        self, node: ast.With, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a with node"""

        def handle_with_vars(var: Optional[ast.AST]) -> List[str]:
            if isinstance(var, ast.Name):
                return [var.id]
            elif isinstance(var, (ast.List, ast.Tuple)):
                result = []
                for elt in var.elts:
                    result.extend(handle_with_vars(elt))  # TODO return result??
            return []

        item = node.items[0]
        self.start()
        if item.optional_vars:
            self.visitm("WITH_VAR(", item.context_expr, ",", item.optional_vars, func)
        else:
            self.visitm("WITH(", item.context_expr, func)
        self.append(",%d)" % self.with_count)
        self.with_count += 1
        self.print(self.line)
        self.indent()
        self.mv.current_with_vars.append(handle_with_vars(item.optional_vars))
        for child in node.body:
            self.visit(child, func)
        self.mv.current_with_vars.pop()
        self.deindent()
        self.output("END_WITH")

    def visit_Assign(
        self, node: ast.Assign, func: Optional["python.Function"] = None
    ) -> None:
        """Visit an assignment"""
        if node.value is None:  # skip type annotation
            return

        if self.struct_unpack_cpp(node, func):
            return

        # temp vars
        if len(node.targets) > 1 or isinstance(node.value, ast.Tuple):
            if isinstance(node.value, ast.Tuple):
                if [
                    n for n in node.targets if ast_utils.is_assign_tuple(n)
                ]:  # XXX a,b=d[i,j]=..?
                    for child in node.value.elts:
                        if (
                            child,
                            0,
                            0,
                        ) not in self.gx.cnode:  # (a,b) = (1,2): (1,2) never visited
                            continue
                        if not ast_utils.is_constant(child) and not ast_utils.is_none(
                            child
                        ):
                            # Prevent self-assignment warnings - check if child is a temp variable
                            temp_var = self.mv.tempcount[child]
                            if (isinstance(child, ast.Name) and
                                child.id == temp_var):
                                # Skip self-assignment
                                continue
                            self.start(temp_var + " = ")
                            self.visit(child, func)
                            self.eol()
            elif not ast_utils.is_constant(node.value) and not ast_utils.is_none(
                node.value
            ):
                # Prevent self-assignment warnings
                temp_var = self.mv.tempcount[node.value]
                if (isinstance(node.value, ast.Name) and
                    node.value.id == temp_var):
                    # Skip self-assignment
                    pass
                else:
                    self.start(temp_var + " = ")
                    self.visit(node.value, func)
                    self.eol()

        # a = (b,c) = .. = expr
        for left in node.targets:
            pairs = ast_utils.assign_rec(left, node.value)

            for lvalue, rvalue in pairs:
                self.start("")  # XXX remove?

                # expr[expr] = expr
                if isinstance(lvalue, ast.Subscript) and not isinstance(
                    lvalue.slice, (ast.Slice, ast.ExtSlice)
                ):
                    self.assign_pair(lvalue, rvalue, func)

                # expr.attr = expr
                elif ast_utils.is_assign_attribute(lvalue):
                    assert isinstance(lvalue, ast.Attribute)
                    lcp = typestr.lowest_common_parents(
                        typestr.polymorphic_t(self.gx, self.mergeinh[lvalue.value])
                    )
                    # property
                    if (
                        len(lcp) == 1
                        and isinstance(lcp[0], python.Class)
                        and lvalue.attr in lcp[0].properties
                    ):
                        self.visitm(
                            lvalue.value,
                            "->"
                            + self.cpp_name(lcp[0].properties[lvalue.attr][1])
                            + "(",
                            rvalue,
                            ")",
                            func,
                        )
                    elif lcp and isinstance(lcp[0], python.Class):
                        var = python.lookup_var(lvalue.attr, lcp[0], self.mv)
                        vartypes = set()
                        if var:
                            vartypes = self.mergeinh[var]
                        self.visit(lvalue, func)
                        self.append(" = ")
                        self.impl_visit_conv(rvalue, vartypes, func)
                    else:
                        self.visitm(lvalue, " = ", rvalue, func)
                    self.eol()

                # name = expr
                elif isinstance(lvalue, ast.Name):
                    vartypes = self.mergeinh[
                        python.lookup_var(lvalue.id, func, self.mv)
                    ]
                    self.visit(lvalue, func)
                    self.append(" = ")
                    self.impl_visit_conv(rvalue, vartypes, func)
                    self.eol()

                # (a,(b,c), ..) = expr
                elif ast_utils.is_assign_list_or_tuple(lvalue):
                    assert isinstance(lvalue, (ast.Tuple, ast.List))
                    self.tuple_assign(lvalue, rvalue, func)

                elif isinstance(lvalue, ast.Slice):
                    assert (
                        False
                    ), "ast.Slice shouldn't appear outside ast.Subscript node"

                # expr[a:b] = expr
                # expr[a:b:c] = expr
                elif isinstance(lvalue, ast.Subscript) and isinstance(
                    lvalue.slice, ast.Slice
                ):
                    # XXX let visit_Call(fakefunc) use cast_to_builtin?
                    fakefunc = infer.inode(self.gx, lvalue.value).fakefunc
                    assert fakefunc
                    assert isinstance(fakefunc.func, ast.Attribute)
                    self.visitm(
                        "(",
                        fakefunc.func.value,
                        ")->__setslice__(",
                        fakefunc.args[0],
                        ",",
                        fakefunc.args[1],
                        ",",
                        fakefunc.args[2],
                        ",",
                        fakefunc.args[3],
                        ",",
                        func,
                    )
                    if [
                        t for t in self.mergeinh[lvalue.value] if t[0].ident == "bytes_"
                    ]:  # TODO more general fix
                        self.visit(fakefunc.args[4], func)
                    elif [
                        t
                        for t in self.mergeinh[fakefunc.args[4]]
                        if t[0].ident == "__xrange"
                    ]:
                        self.visit(fakefunc.args[4], func)
                    else:
                        self.impl_visit_conv(
                            fakefunc.args[4], self.mergeinh[lvalue.value], func
                        )
                    self.append(")")
                    self.eol()

    def visit_AugAssign(
        self, node: ast.AugAssign, func: Optional["python.Function"] = None
    ) -> None:
        """Visit an augmented assignment"""
        if isinstance(node.target, ast.Subscript):
            self.start()
            if set(
                [
                    t[0].ident
                    for t in self.mergeinh[node.target.value]
                    if isinstance(t[0], python.Class)
                ]
            ) in [set(["dict"]), set(["defaultdict"])] and isinstance(node.op, ast.Add):
                self.visitm(
                    node.target.value,
                    "->__addtoitem__(",
                    infer.inode(self.gx, node).subs,
                    ", ",
                    node.value,
                    ")",
                    func,
                )
                self.eol()
                return

            self.visitm(
                infer.inode(self.gx, node).temp1 + " = ", node.target.value, func
            )
            self.eol()
            self.start()
            self.visitm(
                infer.inode(self.gx, node).temp2 + " = ",
                infer.inode(self.gx, node).subs,
                func,
            )
            self.eol()
        self.visit(infer.inode(self.gx, node).assignhop, func)

    def visit_AnnAssign(
        self, node: ast.AnnAssign, func: Optional["python.Function"] = None
    ) -> None:
        """Visit an annotated assignment"""
        self.visit(ast.Assign([node.target], node.value), func)

    def visit_Return(
        self, node: ast.Return, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a return statement"""
        if func and func.isGenerator:
            self.output("__stop_iteration = true;")
            assert func.retnode
            func2 = typestr.nodetypestr(self.gx, func.retnode.thing, mv=self.mv)[
                7:-3
            ]  # XXX meugh
            self.output("return __zero<%s>();" % func2)
            return
        self.start("return ")
        assert node.value  # added in graph.py
        assert func
        assert func.retnode
        self.impl_visit_conv(node.value, self.mergeinh[func.retnode.thing], func)
        self.eol()

    def visit_Raise(
        self, node: ast.Raise, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a raise node"""
        exc = node.exc
        assert exc

        cl = None  # XXX sep func
        t = [t[0] for t in self.mergeinh[exc]]
        if len(t) == 1:
            cl = t[0]
        self.start("throw (")

        # --- raise class  # TODO lookup_class?
        if isinstance(exc, ast.Name) and not python.lookup_var(exc.id, func, self.mv):
            self.append("new %s()" % exc.id)

        # --- raise instance
        elif (
            isinstance(cl, python.Class)
            and cl.mv.module.ident == "builtin"
            and not [a for a in cl.ancestors_upto(None) if a.ident == "BaseException"]
        ):
            self.append("new Exception()")
        else:
            self.visit(exc, func)
        self.eol(")")

    def visit_Break(
        self, node: ast.Break, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a break statement"""
        if self.gx.loopstack[-1].orelse:
            orelse_tempcount_id = self.gx.loopstack[-1].orelse[0]
            if orelse_tempcount_id in self.mv.tempcount:
                self.output("%s = 1;" % self.mv.tempcount[orelse_tempcount_id])
        self.output("break;")

    def visit_Continue(
        self, node: ast.Continue, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a continue node"""
        self.output("continue;")

    def visit_Pass(
        self, node: ast.Pass, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a pass statement"""
        pass

    def visit_Delete(
        self, node: ast.Delete, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a delete statement"""
        for child in node.targets:
            self.visit(child, func)

    def visit_Global(
        self, node: ast.Global, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a global statement"""
        pass

    def visit_Import(
        self, node: ast.Import, func: Optional["python.Function"] = None
    ) -> None:
        """Visit an import node"""
        pass

    def visit_ImportFrom(
        self, node: ast.ImportFrom, func: Optional["python.Function"] = None
    ) -> None:
        """Visit an import from node"""
        pass

    def visit_Assert(
        self, node: ast.Assert, func: Optional["python.Function"] = None
    ) -> None:
        """Visit an assert node"""
        self.start("ASSERT(")
        self.visitm(node.test, ", ", func)
        if node.msg:
            if not self.only_classes(node.msg, ("str_",)):
                error.error(
                    "exception with non-str argument",
                    self.gx,
                    node.msg,
                    warning=True,
                    mv=self.mv,
                )
            self.visit(node.msg, func)
        else:
            self.append("0")
        self.eol(")")

    def visit_Expr(
        self, node: ast.Expr, func: Optional["python.Function"] = None
    ) -> None:
        """Visit an expression node"""
        if not isinstance(node.value, ast.Str):
            self.start("")
            self.visit(node.value, func)
            self.eol()

    def visit_NamedExpr(
        self, node: ast.NamedExpr, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a named expression node"""
        assert isinstance(node.target, ast.Name)
        self.visitm("(", node.target.id, "=", node.value, ")", func)

