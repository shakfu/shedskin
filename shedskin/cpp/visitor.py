# SHED SKIN Python-to-C++ Compiler
# Copyright 2005-2024 Mark Dufour and contributors; GNU GPL version 3 (See LICENSE)
"""shedskin.cpp.visitor - GenerateVisitor and base visitor methods

This module contains the GenerateVisitor class, which is the main entry point
for C++ code generation. It composes all the mixin classes from the cpp package
to provide a complete visitor for translating Python AST to C++ code.

GenerateVisitor
===============

The GenerateVisitor class inherits from multiple mixins:
- TemplateMixin: Type checking and casting utilities
- DeclarationMixin: Header and declaration generation
- HelperMixin: Specialized code generators (loops, comparisons, lambdas)
- StatementVisitorMixin: Statement visitor methods (for, if, assign, etc.)
- ExpressionVisitorMixin: Expression visitor methods (call, binop, name, etc.)
- OutputMixin: Output buffer management
- BaseNodeVisitor: Base AST visitor pattern

Base Methods
============

This module also contains base visitor methods that don't fit into
specific categories:
- visitm(): Visit multiple nodes
- connector(): Get connector string (:: or -> or .)
- get_constant(): Get constant name
- rich_comparison(): Generate rich comparison functions
- module_cpp(): Generate module implementation file
- impl_visit_conv(): Convert/cast nodes
- impl_visit_and_or(): Handle and/or operations
- impl_visit_bitop(): Handle bitwise operations
- impl_visit_binary(): Handle binary operations
- impl_visit_mod(): Handle modulo operations
- power(): Handle power operations
- visit2(): Generic visit with type info
- library_func(): Check if function is from library
- add_args_arg(): Add arguments to call
- bool_test(): Generate boolean test
- tuple_assign(): Generate tuple assignment
- subs_assign(): Generate subscript assignment
- struct_unpack_cpp(): Generate struct unpacking
- assign_pair(): Generate assignment pair
- get_selector(): Get selector for tuple/list item
- rec_string_addition(): Recursively handle string addition
- attr_var_ref(): Generate attribute variable reference
- expand_special_chars(): Expand special characters in strings
"""

import ast
import functools
import io
import string
import struct
import textwrap
from pathlib import Path
from typing import (IO, TYPE_CHECKING, Any, Dict, Iterator, List, Optional,
                    Tuple, TypeAlias, Union)

from .. import (ast_utils, error, extmod, infer, makefile, python, typestr,
                virtual)
from . import CPPNamer, OutputMixin, ExpressionVisitorMixin, StatementVisitorMixin, HelperMixin, DeclarationMixin, TemplateMixin

if TYPE_CHECKING:
    from .. import config

Types: TypeAlias = set[Tuple["python.Class", int]]
Parent: TypeAlias = Union["python.Class", "python.Function"]
AllParent: TypeAlias = Union["python.Class", "python.Function", "python.StaticClass"]


# CPPNamer has been moved to cpp/namer.py (Phase 1 of cpp.py refactoring)
    # Expression visitor methods moved to cpp/expressions.py (Phase 3)
    # Statement visitor methods moved to cpp/statements.py (Phase 4)
    # Helper methods moved to cpp/helpers.py (Phase 5)
    # Declaration methods moved to cpp/declarations.py (Phase 5)
    # Template/type methods moved to cpp/templates.py (Phase 5)







# --- code generation visitor; use type information


class GenerateVisitor(TemplateMixin, DeclarationMixin, HelperMixin, StatementVisitorMixin, ExpressionVisitorMixin, OutputMixin, ast_utils.BaseNodeVisitor):
    """Visitor for generating C++ code from Python ASTs"""

    def __init__(
        self, gx: "config.GlobalInfo", module: "python.Module", analyze: bool = False
    ):
        self.gx = gx
        self.module = module
        self.analyze = analyze
        self.output_base = module.filename.with_suffix("")
        self.out = self.get_output_file(ext=".cpp")
        self.indentation = ""
        self.consts: dict[ast.Constant, str] = {}
        self.mergeinh = self.gx.merged_inh
        self.mv = module.mv
        self.name = module.ident
        self.filling_consts = False
        self.with_count = 0
        self.bool_wrapper: dict["ast.AST", bool] = {}
        self.namer = CPPNamer(self.gx, self)
        self.extmod = extmod.ExtensionModule(self.gx, self)
        self.done: set[ast.AST]

    def cpp_name(self, obj: Any) -> str:
        """Generate a C++ name for an object"""
        return self.namer.name(obj)

    # Output methods (get_output_file, insert_consts, insert_extras) moved to cpp/output.py

    def visitm(self, *args: Any) -> None:
        """Visit multiple nodes in the output file"""
        func = None
        if args and isinstance(args[-1], (python.Function, python.Class)):
            func = args[-1]
        for arg in args[:-1]:
            if isinstance(arg, str):
                self.append(arg)
            else:
                self.visit(arg, func)

    # TODO func unused
    def connector(self, node: ast.AST, func: Optional["python.Function"]) -> str:
        """Generate a connector for a node"""
        if typestr.singletype(self.gx, node, python.Module):
            return "::"
        elif typestr.unboxable(self.gx, self.mergeinh[node]):
            return "."
        else:
            return "->"

    def get_constant(self, node: ast.Constant) -> Optional[str]:
        """Get a constant name for a node"""
        parent: Optional[AllParent] = infer.inode(self.gx, node).parent
        while isinstance(parent, python.Function) and parent.listcomp:  # XXX
            parent = parent.parent
        if isinstance(parent, python.Function) and (
            parent.inherited or not self.inhcpa(parent)
        ):  # XXX
            return None
        for other in self.consts:  # XXX use mapping
            if node.s == other.s:
                return self.consts[other]
        self.consts[node] = "const_" + str(len(self.consts))
        return self.consts[node]

    def rich_comparison(self) -> None:
        """Generate rich comparison functions"""
        cmp_cls, lt_cls, gt_cls, le_cls, ge_cls = [], [], [], [], []
        for cl in self.mv.classes.values():
            if "__cmp__" not in cl.funcs and [
                f for f in ("__eq__", "__lt__", "__gt__") if f in cl.funcs
            ]:
                cmp_cls.append(cl)
            if "__lt__" not in cl.funcs and "__gt__" in cl.funcs:
                lt_cls.append(cl)
            if "__gt__" not in cl.funcs and "__lt__" in cl.funcs:
                gt_cls.append(cl)
            if "__le__" not in cl.funcs and "__ge__" in cl.funcs:
                le_cls.append(cl)
            if "__ge__" not in cl.funcs and "__le__" in cl.funcs:
                ge_cls.append(cl)
        if cmp_cls or lt_cls or gt_cls or le_cls or ge_cls:
            self.print("namespace __shedskin__ { /* XXX */")
            for cl in cmp_cls:
                t = "__%s__::%s *" % (self.mv.module.ident, self.cpp_name(cl))
                self.print("template<> inline __ss_int __cmp(%sa, %sb) {" % (t, t))
                self.print("    if (!a) return -1;")
                if "__eq__" in cl.funcs:
                    self.print("    if(a->__eq__(b)) return 0;")
                if "__lt__" in cl.funcs:
                    self.print("    return (a->__lt__(b))?-1:1;")
                elif "__gt__" in cl.funcs:
                    self.print("    return (a->__gt__(b))?1:-1;")
                else:
                    self.print("    return __cmp<void *>(a, b);")
                self.print("}")
            self.rich_compare(lt_cls, "lt", "gt")
            self.rich_compare(gt_cls, "gt", "lt")
            self.rich_compare(le_cls, "le", "ge")
            self.rich_compare(ge_cls, "ge", "le")
            self.print("}")

    def rich_compare(
        self, cls: List["python.Class"], msg: "str", fallback_msg: "str"
    ) -> None:
        """Generate rich comparison functions for a list of classes"""
        for cl in cls:
            t = "__%s__::%s *" % (self.mv.module.ident, self.cpp_name(cl))
            self.print("template<> inline __ss_bool __%s(%sa, %sb) {" % (msg, t, t))
            # print >>self.out, '    if (!a) return -1;' # XXX check
            self.print("    return b->__%s__(a);" % fallback_msg)
            self.print("}")

    def module_cpp(self, node: ast.Module) -> None:
        """Generate the source file for a module"""
        self.print('#include "builtin.hpp"\n')

        # --- comments
        doc = ast.get_docstring(node)
        if doc:
            self.do_comment(doc)
            self.print()

        # --- namespace fun
        for n in self.module.name_list:
            self.print("namespace __" + n + "__ {")
        self.print()

        for child in node.body:
            if isinstance(child, ast.ImportFrom) and child.module not in (
                "__future__",
                "typing",
            ):
                module = self.gx.from_module[child]
                using = "using " + module.full_path() + "::"
                for name, pseudonym in [(n.name, n.asname) for n in child.names]:
                    pseudonym = pseudonym or name
                    if name == "*":
                        for func in module.mv.funcs.values():
                            if func.cp or module.builtin:
                                self.print(using + self.cpp_name(func) + ";")
                        for cl in module.mv.classes.values():
                            self.print(using + self.cpp_name(cl) + ";")
                    elif pseudonym not in self.module.mv.globals:
                        if name in module.mv.funcs:
                            func = module.mv.funcs[name]
                            if func.cp or module.builtin:
                                self.print(using + self.cpp_name(func) + ";")
                        else:
                            self.print(using + self.namer.nokeywords(name) + ";")
        self.print()

        # --- globals
        defs = self.declare_defs(list(self.mv.globals.items()), declare=False)
        if defs:
            self.output(defs)
            self.print()

        # --- defaults
        for type_, number in self.gen_defaults():
            self.print(f"{type_} default_{number};")

        # --- declarations
        self.listcomps = {}
        for listcomp, lcfunc, func2 in self.mv.listcomps:
            self.listcomps[listcomp] = (lcfunc, func2)
        self.do_listcomps(True)
        self.do_lambdas(True)
        self.print()

        # --- definitions
        self.do_listcomps(False)
        self.do_lambdas(False)
        for child in node.body:
            if isinstance(child, ast.ClassDef):
                self.class_cpp(child)
            elif isinstance(child, ast.FunctionDef):
                self.do_comments(child)
                self.visit(child)

        # --- __init
        self.output("void __init() {")
        self.indent()
        if self.module == self.gx.main_module and not self.gx.pyextension_product:
            self.output('__name__ = new str("__main__");\n')
        else:
            self.output('__name__ = new str("%s");\n' % self.module.ident)

        for child in node.body:
            if isinstance(child, ast.FunctionDef):
                self.init_defaults(child)
            elif isinstance(child, ast.ClassDef):
                for child2 in child.body:
                    if isinstance(child2, ast.FunctionDef):
                        self.init_defaults(child2)
                if child.name in self.mv.classes:
                    cl = self.mv.classes[child.name]
                    self.output("cl_" + cl.ident + ' = new class_("%s");' % (cl.ident))
                    if cl.parent.static_nodes:
                        self.output("%s::__static__();" % self.cpp_name(cl))

            elif isinstance(child, ast.ImportFrom) and child.module not in (
                "__future__",
                "typing",
            ):
                module = self.gx.from_module[child]
                for name, pseudonym in [(n.name, n.asname) for n in child.names]:
                    pseudonym = pseudonym or name
                    if name == "*":
                        for var in module.mv.globals.values():
                            if (
                                not var.invisible
                                and not var.imported
                                and not var.name.startswith("__")
                                and infer.var_types(self.gx, var)
                            ):
                                self.start(
                                    self.namer.nokeywords(var.name)
                                    + " = "
                                    + module.full_path()
                                    + "::"
                                    + self.namer.nokeywords(var.name)
                                )
                                self.eol()
                    elif pseudonym in self.module.mv.globals and not [
                        t
                        for t in infer.var_types(
                            self.gx, self.module.mv.globals[pseudonym]
                        )
                        if isinstance(t[0], python.Module)
                    ]:
                        self.start(
                            self.namer.nokeywords(pseudonym)
                            + " = "
                            + module.full_path()
                            + "::"
                            + self.namer.nokeywords(name)
                        )
                        self.eol()

            else:
                self.do_comments(child)
                self.visit(child)

        self.deindent()
        self.output("}\n")

        # --- close namespace
        for n in self.module.name_list:
            self.print("} // module namespace")
        self.print()

        # --- c++ main/extension module setup
        if self.gx.pyextension_product:
            self.extmod.do_extmod()
        if self.module == self.gx.main_module:
            self.do_main()

    def impl_visit_temp(self, node: ast.AST, func: Optional["python.Function"]) -> None:
        """Visit a temporary variable"""
        if node in self.mv.tempcount:
            self.append(self.mv.tempcount[node])
        else:
            self.visit(node, func)

    def impl_visit_conv(
        self,
        node: ast.AST,
        argtypes: Types,
        func: Optional["python.Function"],
        check_temp: bool = True,
    ) -> None:
        """Convert/cast a node to the type it is assigned to"""
        actualtypes = self.mergeinh[node]
        if check_temp and node in self.mv.tempcount:  # XXX
            self.append(self.mv.tempcount[node])
        elif isinstance(node, ast.Dict):
            self.visit_Dict(node, func, argtypes=argtypes)
        elif isinstance(node, ast.Tuple):
            self.visit_Tuple(node, func, argtypes=argtypes)
        elif isinstance(node, ast.List):
            self.visit_List(node, func, argtypes=argtypes)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("list", "tuple", "dict", "set")
        ):
            self.visit_Call(node, func, argtypes=argtypes)
        elif ast_utils.is_none(node):
            self.visit(node, func)
        else:  # XXX messy
            cast = ""
            if (
                actualtypes
                and argtypes
                and typestr.typestr(self.gx, actualtypes, mv=self.mv)
                != typestr.typestr(self.gx, argtypes, mv=self.mv)
                and typestr.typestr(self.gx, actualtypes, mv=self.mv)
                not in ("str *", "bytes *")
            ):  # XXX
                if typestr.incompatible_assignment_rec(self.gx, actualtypes, argtypes):
                    error.error(
                        "incompatible types", self.gx, node, warning=True, mv=self.mv
                    )
                else:
                    cast = (
                        "("
                        + typestr.typestr(self.gx, argtypes, mv=self.mv).strip()
                        + ")"
                    )
                    if cast == "(complex)":
                        cast = "mcomplex"
            if cast:
                self.append("(" + cast + "(")
            self.visit(node, func)
            if cast:
                self.append("))")

    def impl_visit_and_or(
        self,
        node: ast.BoolOp,
        nodes: List[ast.expr],
        op: str,
        mix: str,
        func: Optional["python.Function"] = None,
    ) -> None:
        """Generate an and or operation"""
        if node in self.gx.bool_test_only:
            self.append("(")
            for n in nodes:
                self.bool_test(n, func)
                if n != node.values[-1]:
                    self.append(" " + mix + " ")
            self.append(")")
        else:
            child = nodes[0]
            if len(nodes) > 1:
                self.append(op + "(")
            self.impl_visit_conv(child, self.mergeinh[node], func, check_temp=False)
            if len(nodes) > 1:
                self.append(", ")
                self.impl_visit_and_or(node, nodes[1:], op, mix, func)
                self.append(", " + self.mv.tempcount[child][2:] + ")")

    def rec_string_addition(self, node: ast.AST) -> List[ast.AST]:
        """Recursively find string addition nodes"""
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = (
                self.rec_string_addition(node.left),
                self.rec_string_addition(node.right),
            )
            if left and right:
                return left + right
        elif self.mergeinh[node] == set([(python.def_class(self.gx, "str_"), 0)]):
            return [node]
        return []

    def impl_visit_bitop(
        self,
        node: ast.BinOp,
        msg: str,
        inline: str,
        func: Optional["python.Function"] = None,
    ) -> None:
        """Generate a bitwise operation"""
        ltypes = self.mergeinh[node.left]
        ul = typestr.unboxable(self.gx, ltypes)
        self.append("(")
        self.append("(")
        self.visit(node.left, func)
        self.append(")")
        if ul:
            self.append(inline)
        else:
            self.append("->" + msg)
        self.append("(")
        self.visit(node.right, func)
        self.append(")")
        self.append(")")

    def power(
        self,
        left: ast.AST,
        right: ast.AST,
        mod: Optional[ast.AST],
        func: Optional["python.Function"] = None,
    ) -> None:
        """Generate a power operation"""
        inttype = set([(python.def_class(self.gx, "int_"), 0)])  # XXX merge
        if self.mergeinh[left] == inttype and self.mergeinh[right] == inttype:
            if not isinstance(right, ast.Num) or (
                isinstance(right.n, (int, float)) and right.n < 0
            ):
                error.error(
                    "pow(int, int) returns int after compilation",
                    self.gx,
                    left,
                    warning=True,
                    mv=self.mv,
                )
        if mod:
            self.visitm("__power(", left, ", ", right, ", ", mod, ")", func)
        else:
            self.visitm("__power(", left, ", ", right, ")", func)

    # XXX cleanup please
    def impl_visit_binary(
        self,
        left: ast.AST,
        right: ast.AST,
        middle: str,
        inline: str,
        func: Optional["python.Function"] = None,
    ) -> None:
        """Generate a binary operation"""
        ltypes = self.mergeinh[left]
        rtypes = self.mergeinh[right]
        ul, ur = typestr.unboxable(self.gx, ltypes), typestr.unboxable(self.gx, rtypes)

        inttype = set([(python.def_class(self.gx, "int_"), 0)])  # XXX new type?
        floattype = set([(python.def_class(self.gx, "float_"), 0)])  # XXX new type?

        # --- inline mod/div
        # XXX C++ knows %, /, so we can overload?
        if floattype.intersection(ltypes) or inttype.intersection(ltypes):
            if inline in ["%"] or (
                inline in ["/"]
                and not (
                    floattype.intersection(ltypes) or floattype.intersection(rtypes)
                )
            ):
                if python.def_class(self.gx, "complex") not in (
                    t[0] for t in rtypes
                ):  # XXX
                    self.append({"%": "__mods", "/": "__divs"}[inline] + "(")
                    self.visit(left, func)
                    self.append(", ")
                    self.visit(right, func)
                    self.append(")")
                    return

        # --- inline floordiv
        if (inline and ul and ur) and inline in ["//"]:
            self.append({"//": "__floordiv"}[inline] + "(")
            self.visit(left, func)
            self.append(",")
            self.visit(right, func)
            self.append(")")
            return

        # --- beauty fix for '1 +- nj' notation
        if (
            inline in ["+", "-"]
            and isinstance(right, ast.Num)
            and isinstance(right.n, complex)
        ):
            if floattype.intersection(ltypes) or inttype.intersection(ltypes):
                self.append("mcomplex(")
                self.visit(left, func)
                self.append(
                    ", " + {"+": "", "-": "-"}[inline] + str(right.n.imag) + ")"
                )
                return

        # --- inline other
        if inline and (
            (ul and ur)
            or not middle
            or ast_utils.is_none(left)
            or ast_utils.is_none(right)
        ):  # XXX not middle, cleanup?
            self.append("(")
            self.visit(left, func)
            self.append(inline)
            self.visit(right, func)
            self.append(")")
            return

        # --- 'a.__mul__(b)': use template to call to b.__mul__(a), while maintaining evaluation order
        if inline in ["+", "*", "-", "/"] and ul and not ur:
            self.append(
                "__" + {"+": "add", "*": "mul", "-": "sub", "/": "div"}[inline] + "2("
            )
            self.visit(left, func)
            self.append(", ")
            self.visit(right, func)
            self.append(")")
            return

        # --- optimize: list + [element]
        if (
            middle == "__add__"
            and self.one_class(left, ("list",))
            and isinstance(right, ast.List)
            and len(right.elts) == 1
        ):
            self.append("__add_list_elt(")
            self.visit(left, func)
            self.append(", ")
            self.visit(right.elts[0], func)
            self.append(")")
            return

        # --- default: left, connector, middle, right
        argtypes = ltypes | rtypes
        self.append("(")
        if middle == "__add__":
            self.impl_visit_conv(left, argtypes, func)
        else:
            self.visit(left, func)
        self.append(")")
        self.append(self.connector(left, func) + middle + "(")
        if middle == "__add__":
            self.impl_visit_conv(right, argtypes, func)
        else:
            self.visit(right, func)
        self.append(")")

    def visit2(
        self,
        node: ast.AST,
        argtypes: Types,
        middle: Optional[str],
        func: Optional["python.Function"],
    ) -> None:  # XXX use temp vars in comparisons, e.g. (t1=fun())
        """Visit a node to get its temporary variable"""
        if node in self.mv.tempcount:
            if node in self.done:
                self.append(self.mv.tempcount[node])
            else:
                self.visitm("(" + self.mv.tempcount[node] + "=", node, ")", func)
                self.done.add(node)
        elif middle == "__contains__":
            self.visit(node, func)
        else:
            self.impl_visit_conv(node, argtypes, func)

    def library_func(
        self,
        funcs: List["python.Function"],
        modname: str,
        clname: Optional[str],
        funcname: str,
    ) -> bool:
        """Check if a function is a library function"""
        for func in funcs:
            if not func.mv.module.builtin or func.mv.module.ident != modname:
                continue
            if clname is not None:
                if not func.parent or func.parent.ident != clname:
                    continue
            return func.ident == funcname
        return False

    def add_args_arg(self, node: ast.Call, funcs: List["python.Function"]) -> None:
        """append argument that describes which formals are actually filled in"""
        if self.library_func(funcs, "datetime", "time", "replace") or self.library_func(
            funcs, "datetime", "datetime", "replace"
        ):
            # formals = funcs[0].formals[1:]  # skip self UNUSED
            # formal_pos = dict((v, k) for k, v in enumerate(formals)) # UNUSED
            positions = []

            for i, arg in enumerate(node.args):
                if isinstance(arg, ast.keyword):
                    assert False
                #                    positions.append(formal_pos[arg.name])
                else:
                    positions.append(i)

            if positions:
                self.append(
                    str(
                        functools.reduce(
                            lambda a, b: a | b, ((1 << x) for x in positions)
                        )
                    )
                    + ", "
                )
            else:
                self.append("0, ")

    def bool_test(
        self,
        node: ast.AST,
        func: Optional["python.Function"],
        always_wrap: bool = False,
    ) -> None:
        """Generate a boolean test"""
        wrapper = always_wrap or not self.only_classes(node, ("int_", "bool_"))
        if node in self.gx.bool_test_only:
            self.visit(node, func)
        elif wrapper:
            self.append("___bool(")
            self.visit(node, func)
            is_func = bool(
                [1 for t in self.mergeinh[node] if isinstance(t[0], python.Function)]
            )
            self.append(("", "!=NULL")[is_func] + ")")  # XXX
        else:
            self.bool_wrapper[node] = True
            self.visit(node, func)

    def tuple_assign(
        self,
        lvalue: Union[ast.List, ast.Tuple],
        rvalue: Union[ast.AST, str],
        func: Optional["python.Function"],
    ) -> None:
        """Generate a tuple assignment"""
        temp = self.mv.tempcount[lvalue]

        nodes: List[ast.expr]
        if isinstance(lvalue, tuple):
            nodes = list(lvalue)
        else:
            nodes = lvalue.elts

        # --- nested unpacking assignment: a, (b,c) = d, e
        if [item for item in nodes if not isinstance(item, ast.Name)]:
            self.start(temp + " = ")
            if isinstance(rvalue, str):
                self.append(rvalue)
            else:
                self.visit(rvalue, func)
            self.eol()

            for i, item in enumerate(nodes):
                selector = self.get_selector(temp, item, i)
                if isinstance(item, ast.Name):
                    self.output("%s = %s;" % (item.id, selector))
                elif ast_utils.is_assign_list_or_tuple(item):  # recursion
                    assert isinstance(item, (ast.List, ast.Tuple))
                    self.tuple_assign(item, selector, func)
                elif isinstance(item, ast.Subscript):
                    self.assign_pair(item, selector, func)
                elif ast_utils.is_assign_attribute(item):
                    self.assign_pair(item, selector, func)
                    self.eol(" = " + selector)

        # --- non-nested unpacking assignment: a,b,c = d
        else:
            self.start()
            self.visitm(temp, " = ", rvalue, func)
            self.eol()

            for i, item in enumerate(lvalue.elts):
                rvalue_node = self.gx.item_rvalue[item]
                if i == 0:
                    if self.one_class(
                        rvalue_node, ("list", "str_", "bytes_", "tuple", "tuple2")
                    ):
                        self.output(
                            "__unpack_check(%s, %d);" % (temp, len(lvalue.elts))
                        )
                    else:
                        rtypes = self.mergeinh[rvalue_node]
                        ts = typestr.typestr(
                            self.gx, self.subtypes(rtypes, "unit"), mv=self.mv
                        )
                        self.output(
                            "list<%s> *%s_list = new list<%s>(%s);"
                            % (ts, temp, ts, temp)
                        )
                        temp = temp + "_list"
                        self.output(
                            "__unpack_check(%s, %d);" % (temp, len(lvalue.elts))
                        )

                self.start()
                self.visitm(item, " = ", self.get_selector(temp, item, i), func)
                self.eol()

    def get_selector(self, temp: str, item: ast.AST, i: int) -> str:
        """Get the selector for an item in a tuple or list"""
        rvalue_node = self.gx.item_rvalue[item]
        sel = "__getitem__(%d)" % i
        if i < 2 and self.only_classes(rvalue_node, ("tuple2",)):
            sel = ["__getfirst__()", "__getsecond__()"][i]
        elif self.one_class(rvalue_node, ("list", "str_", "tuple")):
            sel = "__getfast__(%d)" % i
        return "%s->%s" % (temp, sel)

    def subs_assign(
        self, lvalue: ast.Subscript, func: Optional["python.Function"]
    ) -> None:
        """Generate a subscript assignment"""
        if isinstance(lvalue.slice, ast.Index):
            assert False
        #            subs = lvalue.slice.value
        else:
            subs = lvalue.slice
        self.visitm(
            lvalue.value,
            self.connector(lvalue.value, func),
            "__setitem__(",
            subs,
            ", ",
            func,
        )

    def struct_unpack_cpp(
        self, node: ast.Assign, func: Optional["python.Function"]
    ) -> bool:
        """Generate a struct unpack operation"""
        struct_unpack = self.gx.struct_unpack.get(node)
        if struct_unpack:
            sinfo, tvar, tvar_pos = struct_unpack
            self.start()
            assert isinstance(node.value, ast.Call)
            self.visitm(tvar, " = ", node.value.args[1], func)
            self.eol()
            if len(node.value.args) > 2:  # TODO unpack_from: nicer check
                self.start()
                self.visitm(
                    tvar_pos, " = __wrap(", tvar, ", ", node.value.args[2], ")", func
                )
                self.eol()
            else:
                self.output("%s = 0;" % tvar_pos)

            hop = 0
            for o, c, t, d in sinfo:
                self.start()
                expr = "__struct__::unpack_%s('%c', '%c', %d, %s, &%s)" % (
                    t,
                    o,
                    c,
                    d,
                    tvar,
                    tvar_pos,
                )
                if c == "x" or (d == 0 and c != "s"):
                    self.visitm(expr, func)
                else:
                    assert isinstance(node.targets[0], (ast.List, ast.Tuple))
                    n = list(node.targets[0].elts)[hop]
                    hop += 1
                    if isinstance(n, ast.Subscript):  # XXX merge
                        self.subs_assign(n, func)
                        self.visitm(expr, ")", func)
                    elif isinstance(n, ast.Name):
                        self.visitm(n, " = ", expr, func)
                    elif ast_utils.is_assign_attribute(n):
                        assert isinstance(n, ast.Attribute)
                        self.visit_Attribute(n, func)
                        self.visitm(" = ", expr, func)
                self.eol()
            return True
        return False

    def assign_pair(
        self,
        lvalue: ast.AST,
        rvalue: Union[ast.AST, str],
        func: Optional["python.Function"],
    ) -> None:
        """Generate an assignment pair"""
        self.start("")

        # expr[expr] = expr
        if isinstance(lvalue, ast.Subscript) and not isinstance(
            lvalue.slice, (ast.Slice, ast.ExtSlice)
        ):
            self.subs_assign(lvalue, func)
            if isinstance(rvalue, str):
                self.append(rvalue)
            elif rvalue in self.mv.tempcount:
                self.append(self.mv.tempcount[rvalue])
            else:
                cast = self.cast_to_builtin2(
                    rvalue, func, lvalue.value, "__setitem__", 2
                )
                if cast:
                    self.append("((%s)" % cast)
                self.visit(rvalue, func)
                if cast:
                    self.append(")")
            self.append(")")
            self.eol()

        # expr.x = expr
        elif ast_utils.is_assign_attribute(lvalue):
            assert isinstance(lvalue, ast.Attribute)
            self.visit_Attribute(lvalue, func)

    def impl_visit_mod(
        self, node: ast.BinOp, func: Optional["python.Function"] = None
    ) -> None:
        """Generate a modulo operation"""
        # --- non-str % ..
        if [
            t
            for t in self.gx.merged_inh[node.left]
            if t[0].ident not in ("str_", "bytes_")
        ]:
            self.impl_visit_binary(node.left, node.right, "__mod__", "%", func)
            return

        # --- str % non-constant tuple
        if (
            not isinstance(node.right, ast.Tuple)
            and node.right in self.gx.merged_inh
            and [
                t
                for t in self.gx.merged_inh[node.right]
                if t[0].ident in ["tuple", "tuple2"]
            ]
        ):
            self.visitm("__modtuple(", node.left, ", ", node.right, ")", func)
            return

        # --- str % constant/non tuple
        if isinstance(node.right, ast.Tuple):
            nodes = node.right.elts
        else:
            nodes = [node.right]

        # --- visit nodes, boxing scalars
        self.visitm("__mod6(", node.left, ", ", str(len(nodes)), func)
        for n in nodes:
            self.visitm(", ", n, func)
        self.append(")")

    def attr_var_ref(
        self, node: ast.Attribute, ident: str
    ) -> str:  # TODO remove, by using convention for var names
        """Generate a reference to an attribute variable"""
        lcp = typestr.lowest_common_parents(
            typestr.polymorphic_t(self.gx, self.mergeinh[node.value])
        )
        if (
            len(lcp) == 1
            and isinstance(lcp[0], python.Class)
            and node.attr in lcp[0].vars
            and node.attr not in lcp[0].funcs
            and node.attr not in lcp[0].virtuals
        ):
            return self.cpp_name(lcp[0].vars[node.attr])
        else:
            return self.cpp_name(ident)

    def expand_special_chars(self, val: Union[str, bytes]) -> str:
        """Expand special characters in a string"""
        if isinstance(val, str):
            val = val.encode("utf-8")  # restriction

        value = [chr(c) for c in val]
        replace = {
            "\\": "\\",
            "\n": "n",
            "\t": "t",
            "\r": "r",
            "\f": "f",
            "\b": "b",
            "\v": "v",
            '"': '"',
        }

        for i in range(len(value)):
            if value[i] in replace:
                value[i] = "\\" + replace[value[i]]
            elif value[i] not in string.printable:
                octval = oct(ord(value[i]))
                if octval.startswith("0o"):  # py3
                    octval = octval[2:]
                value[i] = "\\" + octval.zfill(4)[1:]

        return "".join(value)

