# SHED SKIN Python-to-C++ Compiler
# Copyright 2005-2024 Mark Dufour and contributors; GNU GPL version 3 (See LICENSE)
"""shedskin.cpp: C++ Code Generator

This module is responsible for translating Python code into equivalent C++ code,
handling all aspects of code generation including:

Key Components:
- `GenerateVisitor`: Main code generation class that traverses the Python AST
  and outputs corresponding C++ code. Inherits visitor pattern from
  `ast_utils.BaseNodeVisitor` to recursively generate C++ code for each
  syntactical Python construct. 
- `CPPNamer`: Handles C++ identifier naming and keyword conflicts.
- `TypeExpr`: Manages C++ template type expressions.
- `InstanceAllocator`: Handles object allocation and memory management.

Major Features:
- Template-based polymorphism for Python's dynamic typing.
- Virtual method tables for inheritance and method dispatch.
- Reference counting and garbage collection integration.
- Python builtin type implementations
- Exception handling translation
- Module system and import handling
- Standard library implementations

The code generation process:
1. Constraint graph, with inferred types, is first 'merged' back to program
   dimensions (`gx.merged_inh`).
2. AST is traversed to generate C++ declarations and definitions.
3. Template specializations are generated for polymorphic functions.
4. Virtual method tables are created for class hierarchies.
5. Boilerplate code is added for Python integration.

Generated code aims to balance performance with Python semantics,
using C++ features like templates and virtuals where appropriate
while maintaining Python's dynamic behavior.
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

from . import (ast_utils, error, extmod, infer, makefile, python, typestr,
               virtual)
from .cpp import CPPNamer, OutputMixin, ExpressionVisitorMixin

if TYPE_CHECKING:
    from . import config

Types: TypeAlias = set[Tuple["python.Class", int]]
Parent: TypeAlias = Union["python.Class", "python.Function"]
AllParent: TypeAlias = Union["python.Class", "python.Function", "python.StaticClass"]


# CPPNamer has been moved to cpp/namer.py (Phase 1 of cpp.py refactoring)
    # Expression visitor methods moved to cpp/expressions.py (Phase 3)



# --- code generation visitor; use type information


class GenerateVisitor(ExpressionVisitorMixin, OutputMixin, ast_utils.BaseNodeVisitor):
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

    def fwd_class_refs(self) -> list[str]:
        """Forward declare classes from included modules"""
        lines = []
        for _module in self.module.prop_includes:
            if _module.builtin:
                continue
            for name in _module.name_list:
                lines.append("namespace __%s__ { /* XXX */\n" % name)
            for cl in _module.mv.classes.values():
                lines.append("class %s;\n" % self.cpp_name(cl))
            for name in _module.name_list:
                lines.append("}\n")
        if lines:
            lines.insert(0, "\n")
        return lines

    def include_files(self) -> list[str]:
        """Find all (indirect) dependencies"""
        includes = set()
        includes.add(self.module)
        changed = True
        while changed:
            size = len(includes)
            for module in list(includes):
                includes.update(module.prop_includes)
                includes.update(module.mv.imports.values())
                includes.update(module.mv.fake_imports.values())
            changed = size != len(includes)
        includes = set(i for i in includes if i.ident != "builtin")
        # order by cross-file inheritance dependencies
        for include in includes:
            include.deps = set()
        for include in includes:
            for cl in include.mv.classes.values():
                if cl.bases:
                    module = cl.bases[0].mv.module
                    if module.ident != "builtin" and module != include:
                        include.deps.add(module)
        includes1 = [i for i in includes if i.builtin]
        includes2 = [i for i in includes if not i.builtin]
        includes3 = includes1 + self.includes_rec(set(includes2))
        return ['#include "%s"\n' % module.include_path() for module in includes3]

    def includes_rec(
        self, includes: set["python.Module"]
    ) -> List["python.Module"]:  # XXX should be recursive!? ugh
        """Find all (indirect) dependencies recursively"""
        todo = includes.copy()
        result: List["python.Module"] = []
        while todo:
            for include in todo:
                if not include.deps - set(result):
                    todo.remove(include)
                    result.append(include)
                    break
            else:  # XXX circular dependency warning?
                result.append(todo.pop())
        return result

    # --- group pairs of (type, name) declarations, while paying attention to '*'
    def group_declarations(self, pairs: List[Tuple[str, str]]) -> List[str]:
        """Group pairs of (type, name) declarations"""
        group: Dict[str, List[str]] = {}
        for type, name in pairs:
            group.setdefault(type, []).append(name)
        result = []
        for type, names in group.items():
            names.sort()
            if type.endswith("*"):
                result.append(type + (", *".join(names)) + ";\n")
            else:
                result.append(type + (", ".join(names)) + ";\n")
        return result

    def header_file(self) -> None:
        """Generate the header file"""
        self.out = self.get_output_file(ext=".hpp")
        self.visit(self.module.ast, True)
        self.out.close()

    # Output buffer methods (print, output, start, append, eol, indent, deindent) moved to cpp/output.py

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

    def gen_declare_defs(
        self, vars: List[Tuple[str, "python.Variable"]]
    ) -> Iterator[Tuple[str, str]]:
        """Generate declarations and definitions for variables"""
        for name, var in vars:
            if (
                typestr.singletype(self.gx, var, python.Module)
                or var.invisible
                or var.name in {"__exception", "__exception2"}
            ):
                continue
            ts = typestr.nodetypestr(self.gx, var, var.parent, mv=self.mv)
            yield ts, self.cpp_name(var)

    # TODO just pass vars as dict?
    def declare_defs(
        self, vars: List[Tuple[str, "python.Variable"]], declare: bool
    ) -> str:
        """Generate declarations and definitions for variables"""
        pairs = []
        for ts, name in self.gen_declare_defs(vars):
            if declare:
                if "for_in_loop" in ts:  # XXX
                    continue
                ts = "extern " + ts
            pairs.append((ts, name))
        return "".join(self.group_declarations(pairs))

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

    def module_hpp(self, node: ast.Module) -> None:
        """Generate the header file for a module"""
        define = "_".join(self.module.name_list).upper() + "_HPP"
        self.print("#ifndef __" + define)
        self.print("#define __" + define + "\n")

        # --- namespaces
        self.print("using namespace __shedskin__;")
        for n in self.module.name_list:
            self.print("namespace __" + n + "__ {")
        self.print()

        # class declarations
        for child in node.body:
            if isinstance(child, ast.ClassDef):
                cl = python.def_class(self.gx, child.name, mv=self.mv)
                self.print("class " + self.cpp_name(cl) + ";")
        self.print()

        # --- lambda typedefs
        self.func_pointers()

        # globals
        defs = self.declare_defs(list(self.mv.globals.items()), declare=True)
        if defs:
            self.output(defs)
            self.print()

        # --- class definitions
        for child in node.body:
            if isinstance(child, ast.ClassDef):
                self.class_hpp(child)

        # --- defaults
        for type, number in self.gen_defaults():
            self.print("extern %s default_%d;" % (type, number))

        # function declarations
        if self.module != self.gx.main_module:
            self.print("void __init();")
        for child in node.body:
            if isinstance(child, ast.FunctionDef):
                func = self.mv.funcs[child.name]
                if self.inhcpa(func):
                    assert func.node
                    self.visit_FunctionDef(func.node, declare=True)
        self.print()

        if self.gx.pyextension_product:
            self.print('extern "C" {')
            self.extmod.pyinit_func()
            self.print("}")

        for n in self.module.name_list:
            self.print("} // module namespace")

        self.rich_comparison()

        if self.gx.pyextension_product:
            self.extmod.convert_methods2()

        self.print("#endif")

    def gen_defaults(self) -> Iterator[Tuple[str, int]]:
        """Generate default values for functions"""
        for default, (nr, func, func_def_nr) in self.module.mv.defaults.items():
            formal = func.formals[len(func.formals) - len(func.defaults) + func_def_nr]
            var = func.vars[formal]
            yield (
                typestr.typestr(self.gx, self.mergeinh[var], func, mv=self.mv),
                nr,
            )  #  + ' ' + ('default_%d;' % nr)

    def init_defaults(self, func2: ast.FunctionDef) -> None:
        """Initialize default values for function arguments"""
        for default in func2.args.defaults:
            if default in self.mv.defaults:
                nr, func, func_def_nr = self.mv.defaults[default]
                formal = func.formals[
                    len(func.formals) - len(func.defaults) + func_def_nr
                ]
                var = func.vars[formal]
                if self.mergeinh[var]:
                    ts = [
                        t
                        for t in self.mergeinh[default]
                        if isinstance(t[0], python.Function)
                    ]
                    if not ts or [t for t in ts if infer.called(t[0])]:
                        self.start("default_%d = " % nr)
                        self.impl_visit_conv(default, self.mergeinh[var], None)
                        self.eol()

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

    def visit_Module(self, node: ast.Module, declare: bool = False) -> None:
        """Visit a module node"""
        if declare:
            self.module_hpp(node)
        else:
            self.module_cpp(node)

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

    def visit_Continue(
        self, node: ast.Continue, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a continue node"""
        self.output("continue;")

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

    def copy_method(self, cl: "python.Class", name: "str", declare: bool) -> None:
        """Generate a copy method for a class"""
        class_name = self.cpp_name(cl)
        header = class_name + " *"
        if not declare:
            header += class_name + "::"
        header += name + "("
        self.start(header)
        if name == "__deepcopy__":
            self.append("dict<void *, pyobj *> *memo")
        self.append(")")
        if not declare:
            self.print(self.line + " {")
            self.indent()
            self.output(class_name + " *c = new " + class_name + "();")
            if name == "__deepcopy__":
                self.output("memo->__setitem__(this, c);")
            for var in cl.vars.values():
                if (
                    not var.invisible
                    and var in self.gx.merged_inh
                    and self.gx.merged_inh[var]
                ):
                    varname = self.cpp_name(var)
                    if name == "__deepcopy__":
                        self.output("c->%s = __deepcopy(%s);" % (varname, varname))
                    else:
                        self.output("c->%s = %s;" % (varname, varname))
            self.output("return c;")
            self.deindent()
            self.output("}\n")
        else:
            self.eol()

    def copy_methods(self, cl: "python.Class", declare: bool) -> None:
        """Generate copy methods for a class"""
        if cl.has_copy:
            self.copy_method(cl, "__copy__", declare)
        if cl.has_deepcopy:
            self.copy_method(cl, "__deepcopy__", declare)

    def class_hpp(self, node: ast.ClassDef) -> None:
        """Generate a class declaration for a header file"""
        cl = self.mv.classes[node.name]
        self.output("extern class_ *cl_" + cl.ident + ";")

        # --- header
        clnames = [self.namer.namespace_class(b) for b in cl.bases]
        if not clnames:
            clnames = ["pyobj"]
            if "__iter__" in cl.funcs:  # XXX get return type of 'next'
                retnode = cl.funcs["__iter__"].retnode
                assert retnode
                ts = typestr.nodetypestr(self.gx, retnode.thing, mv=self.mv)
                if ts.startswith("__iter<"):
                    ts = ts[ts.find("<") + 1 : ts.find(">")]
                    clnames = ["pyiter<%s>" % ts]  # XXX use iterable interface
            if "__call__" in cl.funcs:
                callfunc = cl.funcs["__call__"]
                retnode = callfunc.retnode
                assert retnode
                r_typestr = typestr.nodetypestr(
                    self.gx, retnode.thing, mv=self.mv
                ).strip()
                nargs = len(callfunc.formals) - 1
                argtypes = [
                    typestr.nodetypestr(
                        self.gx, callfunc.vars[callfunc.formals[i + 1]], mv=self.mv
                    ).strip()
                    for i in range(nargs)
                ]
                clnames = ["pycall%d<%s,%s>" % (nargs, r_typestr, ",".join(argtypes))]
        self.output(
            "class "
            + self.cpp_name(cl)
            + " : "
            + ", ".join(["public " + clname for clname in clnames])
            + " {"
        )
        self.do_comment(ast.get_docstring(node))
        self.output("public:")
        self.indent()
        self.class_variables(cl)

        # --- constructor
        need_init = False
        if "__init__" in cl.funcs:
            initfunc = cl.funcs["__init__"]
            if self.inhcpa(initfunc):
                need_init = True

        # --- default constructor
        if need_init:
            self.output(self.cpp_name(cl) + "() {}")
        else:
            self.output(
                self.cpp_name(cl) + "() { this->__class__ = cl_" + cl.ident + "; }"
            )

        # --- init constructor
        if need_init:
            self.func_header(initfunc, declare=True, is_init=True)
            self.indent()
            self.output("this->__class__ = cl_" + cl.ident + ";")
            self.output(
                "__init__("
                + ", ".join(
                    self.cpp_name(initfunc.vars[f]) for f in initfunc.formals[1:]
                )
                + ");"
            )
            self.deindent()
            self.output("}")

        # --- static code
        if cl.parent.static_nodes:
            self.output("static void __static__();")

        # --- methods
        virtual.virtuals(self, cl, True)
        for func in cl.funcs.values():
            if func.node and not (func.ident == "__init__" and func.inherited):
                self.visit_FunctionDef(func.node, cl, True)
        self.copy_methods(cl, True)
        if self.gx.pyextension_product:
            self.extmod.convert_methods(cl, True)

        self.deindent()
        self.output("};\n")

    def class_cpp(self, node: ast.ClassDef) -> None:
        """Generate a class definition for a source file"""
        cl = self.mv.classes[node.name]
        #        if node in self.gx.comments:
        #            self.do_comments(node)
        #        else:
        self.output("/**\nclass %s\n*/\n" % cl.ident)
        self.output("class_ *cl_" + cl.ident + ";\n")

        # --- methods
        virtual.virtuals(self, cl, False)
        for func in cl.funcs.values():
            if func.node and not (func.ident == "__init__" and func.inherited):
                self.visit_FunctionDef(func.node, cl, False)
        self.copy_methods(cl, False)

        # --- class variable declarations
        if cl.parent.vars:  # XXX merge with visit_Module
            for var in cl.parent.vars.values():
                if var in self.gx.merged_inh and self.gx.merged_inh[var]:
                    self.start(
                        typestr.nodetypestr(self.gx, var, cl.parent, mv=self.mv)
                        + cl.ident
                        + "::"
                        + self.cpp_name(var)
                    )
                    self.eol()
            self.print()

        # --- static init
        if cl.parent.static_nodes:
            self.output("void %s::__static__() {" % self.cpp_name(cl))
            self.indent()
            for node2 in cl.parent.static_nodes:
                self.visit(node2, cl.parent)
            self.deindent()
            self.output("}")
            self.print()

    def class_variables(self, cl: "python.Class") -> None:
        """Generate class variable declarations"""
        if cl.parent.vars:
            for var in cl.parent.vars.values():
                if var in self.gx.merged_inh and self.gx.merged_inh[var]:
                    self.output(
                        "static "
                        + typestr.nodetypestr(self.gx, var, cl.parent, mv=self.mv)
                        + self.cpp_name(var)
                        + ";"
                    )
            self.print()

        # --- instance variables
        for var in cl.vars.values():
            if var.invisible:
                continue  # var.name in cl.virtualvars: continue
            # var is masked by ancestor var
            vars: set[str] = set()
            for ancestor in cl.ancestors():
                vars.update(ancestor.vars)
            if var.name in vars:
                continue
            if var in self.gx.merged_inh and self.gx.merged_inh[var]:
                self.output(
                    typestr.nodetypestr(self.gx, var, cl, mv=self.mv)
                    + self.cpp_name(var)
                    + ";"
                )

        if [v for v in cl.vars if not v.startswith("__")]:
            self.print()

    def nothing(self, types: Types) -> str:
        """Generate a default value for a type"""
        if python.def_class(self.gx, "complex") in (t[0] for t in types):
            return "mcomplex(0.0, 0.0)"
        elif python.def_class(self.gx, "bool_") in (t[0] for t in types):
            return "False"
        else:
            return "0"

    def inhcpa(self, func: "python.Function") -> bool:
        """Check if a function is inherited"""
        return bool(
            infer.called(func)
            or (
                func in self.gx.inheritance_relations
                and [
                    1
                    for f in self.gx.inheritance_relations[func]
                    if isinstance(f, python.Function) and infer.called(f)
                ]
            )
        )

    def subtypes(self, types: Types, varname: Optional[str]) -> Types:
        """Get the subtypes of a type"""
        subtypes = set()
        if varname:
            for t in types:
                if isinstance(t[0], python.Class):
                    var = t[0].vars.get(varname)
                    if var and (var, t[1], 0) in self.gx.cnode:  # XXX yeah?
                        subtypes.update(self.gx.cnode[var, t[1], 0].types())
        return subtypes

    def bin_tuple(self, types: Types) -> bool:
        """Check if a tuple is binary"""
        for t in types:
            if isinstance(t[0], python.Class) and t[0].ident == "tuple2":
                var1 = t[0].vars.get("first")
                var2 = t[0].vars.get("second")
                if var1 and var2:
                    if (var1, t[1], 0) in self.gx.cnode and (
                        var2,
                        t[1],
                        0,
                    ) in self.gx.cnode:
                        if (
                            self.gx.cnode[var1, t[1], 0].types()
                            != self.gx.cnode[var2, t[1], 0].types()
                        ):
                            return True
        return False

    def instance_new(self, node: ast.AST, argtypes: Optional[Types]) -> Types:
        """Get the types for a new instance"""
        if argtypes is None:
            argtypes = self.gx.merged_inh[node]
        ts = typestr.typestr(self.gx, argtypes, mv=self.mv)
        if ts.startswith("pyseq") or ts.startswith("pyiter"):  # XXX
            argtypes = self.gx.merged_inh[node]
        ts = typestr.typestr(self.gx, argtypes, mv=self.mv)
        self.append("(new " + ts[:-2] + "(")
        return argtypes

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
    def impl_visit_temp(self, node: ast.AST, func: Optional["python.Function"]) -> None:
        """Visit a temporary variable"""
        if node in self.mv.tempcount:
            self.append(self.mv.tempcount[node])
        else:
            self.visit(node, func)

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

    def only_classes(self, node: ast.AST, names: Tuple[str, ...]) -> bool:
        """Check if a node is only classes"""
        if node not in self.mergeinh:
            return False
        classes = [python.def_class(self.gx, name, mv=self.mv) for name in names] + [
            python.def_class(self.gx, "none")
        ]
        return not [t for t in self.mergeinh[node] if t[0] not in classes]

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

    def func_pointers(self) -> None:
        """Generate function pointers for lambdas"""
        for func in self.mv.lambdas.values():
            argtypes = [
                typestr.nodetypestr(
                    self.gx, func.vars[formal], func, mv=self.mv
                ).rstrip()
                for formal in func.formals
            ]
            if func.largs is not None:
                argtypes = argtypes[: func.largs]
            assert func.retnode
            rettype = typestr.nodetypestr(self.gx, func.retnode.thing, func, mv=self.mv)
            assert isinstance(func.lambdanr, int)
            self.print(
                "typedef %s(*lambda%d)(" % (rettype, func.lambdanr)
                + ", ".join(argtypes)
                + ");"
            )
        self.print()

    def func_header(
        self, func: "python.Function", declare: bool, is_init: bool = False
    ) -> None:
        """Generate the header for a function or method"""
        method = isinstance(func.parent, python.Class)
        if method:
            formals = [f for f in func.formals if f != "self"]
        else:
            formals = [f for f in func.formals]
        if func.largs is not None:
            formals = formals[: func.largs]

        if is_init:
            ident = self.cpp_name(func.parent)
        else:
            ident = self.cpp_name(func)

        self.start()

        # --- return expression
        header = ""
        if is_init:
            pass
        elif func.ident in ["__hash__"]:
            header += "long "  # XXX __ss_int leads to problem with virtual parent
        elif func.returnexpr:
            assert func.retnode
            header += typestr.nodetypestr(
                self.gx, func.retnode.thing, func, mv=self.mv
            )  # XXX mult
        else:
            header += "void "

        ftypes = [
            typestr.nodetypestr(self.gx, func.vars[f], func, mv=self.mv)
            for f in formals
        ]

        # if arguments type too precise (e.g. virtually called) cast them back
        oldftypes = ftypes
        if func.ftypes:
            ftypes = func.ftypes[1:]

        # --- method header
        if method and not declare:
            header += self.cpp_name(func.parent) + "::"
        header += ident

        # --- cast arguments if necessary (explained above)
        casts = []
        casters = set()
        if func.ftypes:
            for i in range(
                min(len(oldftypes), len(ftypes))
            ):  # XXX this is 'cast on specialize'.. how about generalization?
                if oldftypes[i] != ftypes[i]:
                    casts.append(
                        oldftypes[i]
                        + formals[i]
                        + " = ("
                        + oldftypes[i]
                        + ")__"
                        + formals[i]
                        + ";"
                    )
                    if not declare:
                        casters.add(i)

        formals2 = formals[:]
        for i, f in enumerate(formals2):  # XXX
            formals2[i] = self.cpp_name(func.vars[f])
            if i in casters:
                formals2[i] = "__" + formals2[i]
        formaldecs = [o + f for (o, f) in zip(ftypes, formals2)]
        if (
            declare
            and isinstance(func.parent, python.Class)
            and func.ident in func.parent.staticmethods
        ):
            header = "static " + header
        if is_init and not formaldecs:
            formaldecs = ["int __ss_init"]
        if func.ident.startswith("__lambda"):  # XXX
            header = "static inline " + header

        # --- output
        self.append(header + "(" + ", ".join(formaldecs) + ")")
        if is_init:
            self.print(self.line + " {")
        elif declare:
            self.eol()
        else:
            self.print(self.line + " {")
            self.indent()
            if not declare and func.doc:
                self.do_comment(func.doc)
            for cast in casts:
                self.output(cast)
            self.deindent()

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
    def generator_ident(self, func: "python.Function") -> str:
        if func.parent:
            return func.parent.ident + "_" + func.ident
        return func.ident

    def generator_class(self, func: "python.Function") -> None:
        ident = self.generator_ident(func)
        assert func.retnode
        self.output(
            "class __gen_%s : public %s {"
            % (
                ident,
                typestr.nodetypestr(self.gx, func.retnode.thing, func, mv=self.mv)[:-2],
            )
        )
        self.output("public:")
        self.indent()
        pairs = [
            (
                typestr.nodetypestr(self.gx, func.vars[f], func, mv=self.mv),
                self.cpp_name(func.vars[f]),
            )
            for f in func.vars
        ]
        self.output(self.indentation.join(self.group_declarations(pairs)))
        self.output("int __last_yield;\n")

        args = []
        for f in func.formals:
            args.append(
                typestr.nodetypestr(self.gx, func.vars[f], func, mv=self.mv)
                + self.cpp_name(func.vars[f])
            )
        self.output(("__gen_%s(" % ident) + ",".join(args) + ") {")
        self.indent()
        for f in func.formals:
            self.output(
                "this->%s = %s;"
                % (self.cpp_name(func.vars[f]), self.cpp_name(func.vars[f]))
            )
        self.output("__last_yield = -1;")
        self.deindent()
        self.output("}\n")

        func2 = typestr.nodetypestr(self.gx, func.retnode.thing, func, mv=self.mv)[7:-3]
        self.output("%s __get_next() {" % func2)
        self.indent()
        self.output("switch(__last_yield) {")
        self.indent()
        for i, n in enumerate(func.yieldNodes):
            self.output("case %d: goto __after_yield_%d;" % (i, i))
        self.output("default: break;")
        self.deindent()
        self.output("}")

        assert func.node
        for child in func.node.body:
            self.visit(child, func)

        self.output("__stop_iteration = true;")
        self.output("return __zero<%s>();" % func2)
        self.deindent()
        self.output("}\n")

        self.deindent()
        self.output("};\n")

    def generator_body(self, func: "python.Function") -> None:
        """Generate the body of a generator function"""
        ident = self.generator_ident(func)
        if not (func.isGenerator and func.parent):
            formals = [self.cpp_name(func.vars[f]) for f in func.formals]
        else:
            formals = ["this"] + [
                self.cpp_name(func.vars[f]) for f in func.formals if f != "self"
            ]
        self.output("return new __gen_%s(%s);\n" % (ident, ",".join(formals)))
        self.deindent()
        self.output("}\n")

    def visit_Global(
        self, node: ast.Global, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a global statement"""
        pass

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

    def visit_Break(
        self, node: ast.Break, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a break statement"""
        if self.gx.loopstack[-1].orelse:
            orelse_tempcount_id = self.gx.loopstack[-1].orelse[0]
            if orelse_tempcount_id in self.mv.tempcount:
                self.output("%s = 1;" % self.mv.tempcount[orelse_tempcount_id])
        self.output("break;")

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

    def visit_Pass(
        self, node: ast.Pass, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a pass statement"""
        pass

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

    def cast_to_builtin(
        self,
        arg: ast.AST,
        func: Optional["python.Function"],
        formal: "python.Variable",
        target: "python.Function",
        method_call: bool,
        objexpr: Optional[ast.AST],
    ) -> Optional[Types]:
        """Check if a cast to a builtin type is necessary"""
        # type inference cannot deduce all necessary casts to builtin formals
        vars = {"u": "unit", "v": "value", "o": None}
        if (
            target.mv.module.builtin
            and method_call
            and formal.name in vars
            and isinstance(target.parent, python.Class)
            and target.parent.ident in ("list", "dict", "set")
        ):
            assert objexpr
            subtypes = self.subtypes(self.mergeinh[objexpr], vars[formal.name])
            if typestr.nodetypestr(self.gx, arg, func, mv=self.mv) != typestr.typestr(
                self.gx, subtypes, mv=self.mv
            ):
                return subtypes
        return None

    def cast_to_builtin2(
        self,
        arg: ast.AST,
        func: Optional["python.Function"],
        objexpr: ast.AST,
        msg: str,
        formal_nr: int,
    ) -> Optional[str]:
        """Check if a cast to a builtin type is necessary"""
        # shortcut for outside of visit_Call XXX merge with visit_Call?
        cls = [t[0] for t in self.mergeinh[objexpr] if isinstance(t[0], python.Class)]
        if cls:
            cl = cls.pop()
            if msg in cl.funcs:
                target = cl.funcs[msg]
                if formal_nr < len(target.formals):
                    formal = target.vars[target.formals[formal_nr]]
                    builtin_types = self.cast_to_builtin(
                        arg, func, formal, target, True, objexpr
                    )
                    if builtin_types:
                        return typestr.typestr(self.gx, builtin_types, mv=self.mv)
        return None

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

    def one_class(self, node: ast.AST, names: Tuple[str, ...]) -> bool:
        """Check if a node is a single class"""
        for clname in names:
            if self.only_classes(node, (clname,)):
                return True
        return False

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

    def visit_Delete(
        self, node: ast.Delete, func: Optional["python.Function"] = None
    ) -> None:
        """Visit a delete statement"""
        for child in node.targets:
            self.visit(child, func)

    def visit_AnnAssign(
        self, node: ast.AnnAssign, func: Optional["python.Function"] = None
    ) -> None:
        """Visit an annotated assignment"""
        self.visit(ast.Assign([node.target], node.value), func)

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

    def listcomp_head(self, node: ast.ListComp, declare: bool, genexpr: bool) -> None:
        """Generate the header for a list comprehension"""
        lcfunc, func = self.listcomps[node]
        args = [a + b for a, b in self.lc_args(lcfunc, func)]
        ts = typestr.nodetypestr(self.gx, node, lcfunc, mv=self.mv)
        if not ts.endswith("*"):
            ts += " "
        if genexpr:
            self.genexpr_class(node, declare)
        else:
            self.output(
                "static inline "
                + ts
                + lcfunc.ident
                + "("
                + ", ".join(args)
                + ")"
                + [" {", ";"][declare]
            )

    def lc_args(
        self, lcfunc: "python.Function", func: Optional["python.Function"]
    ) -> List[Tuple[str, str]]:
        """Generate the arguments for a list comprehension"""
        args = []
        for name in lcfunc.misses:
            var = python.lookup_var(name, func, self.mv)
            assert var
            if var.parent:
                arg = self.cpp_name(name)
                if name in lcfunc.misses_by_ref:
                    arg = "&" + arg
                args.append(
                    (
                        typestr.nodetypestr(
                            self.gx,
                            python.lookup_var(name, lcfunc, self.mv),
                            lcfunc,
                            mv=self.mv,
                        ),
                        arg,
                    )
                )
        return args

    def listcomp_func(self, node: ast.ListComp) -> None:
        """Generate a list comprehension function"""
        lcfunc, func = self.listcomps[node]
        self.listcomp_head(node, False, False)
        self.indent()
        self.local_defs(lcfunc)
        self.output(
            typestr.nodetypestr(self.gx, node, lcfunc, mv=self.mv)
            + "__ss_result = new "
            + typestr.nodetypestr(self.gx, node, lcfunc, mv=self.mv)[:-2]
            + "();\n"
        )
        self.listcomp_rec(node, node.generators, lcfunc, False)
        self.output("return __ss_result;")
        self.deindent()
        self.output("}\n")

    def genexpr_class(self, node: ast.ListComp, declare: bool) -> None:
        """Generate a generator expression class"""
        lcfunc, func = self.listcomps[node]
        args = self.lc_args(lcfunc, func)
        func1 = lcfunc.ident + "(" + ", ".join(a + b for a, b in args) + ")"
        func2 = typestr.nodetypestr(self.gx, node, lcfunc, mv=self.mv)[7:-3]
        if declare:
            ts = typestr.nodetypestr(self.gx, node, lcfunc, mv=self.mv)
            if not ts.endswith("*"):
                ts += " "
            self.output("class " + lcfunc.ident + " : public " + ts[:-2] + " {")
            self.output("public:")
            self.indent()
            self.local_defs(lcfunc)
            for a, b in args:
                self.output(a + b + ";")
            self.output("int __last_yield;\n")
            self.output(func1 + ";")
            self.output(func2 + " __get_next();")
            self.deindent()
            self.output("};\n")
        else:
            self.output(lcfunc.ident + "::" + func1 + " {")
            for a, b in args:
                self.output("    this->%s = %s;" % (b, b))
            self.output("    __last_yield = -1;")
            self.output("}\n")
            self.output(func2 + " " + lcfunc.ident + "::__get_next() {")
            self.indent()
            self.output("if(!__last_yield) goto __after_yield_0;")
            self.output("__last_yield = 0;\n")
            self.listcomp_rec(node, node.generators, lcfunc, True)
            self.output("__stop_iteration = true;")
            self.output("return __zero<%s>();" % func2)
            self.deindent()
            self.output("}\n")

    def local_defs(self, func: python.Function) -> None:
        """Generate local definitions for a function"""
        pairs = []
        for name, var in func.vars.items():
            if not var.invisible and (
                not hasattr(func, "formals") or name not in func.formals
            ):  # XXX
                pairs.append(
                    (
                        typestr.nodetypestr(self.gx, var, func, mv=self.mv),
                        self.cpp_name(var),
                    )
                )
        self.output(self.indentation.join(self.group_declarations(pairs)))

    # --- nested for loops: loop headers, if statements
    def listcomp_rec(
        self,
        node: ast.ListComp,
        quals: List[ast.comprehension],
        lcfunc: "python.Function",
        genexpr: bool,
    ) -> None:
        """Generate nested for loops"""
        if not quals:
            if genexpr:
                self.start("__result = ")
                self.visit(node.elt, lcfunc)
                self.eol()
                self.output("return __result;")
                self.start("__after_yield_0:")
            elif node in self.gx.setcomp_to_lc.values():
                self.start("__ss_result->add(")
                self.visit(node.elt, lcfunc)
                self.append(")")
            elif node in self.gx.dictcomp_to_lc.values():
                self.start("__ss_result->__setitem__(")
                self.visit(node.elt[0], lcfunc)
                self.append(",")
                self.visit(node.elt[1], lcfunc)
                self.append(")")
            elif (
                len(node.generators) == 1
                and not ast_utils.is_fastfor(node.generators[0])
                and not self.fastenumerate(node.generators[0])
                and not self.fastzip2(node.generators[0])
                and not node.generators[0].ifs
                and self.one_class(
                    node.generators[0].iter, ("tuple", "list", "str_", "dict", "set")
                )
            ):
                self.start(
                    "__ss_result->units["
                    + self.mv.tempcount[node.generators[0].iter]
                    + "] = "
                )
                self.visit(node.elt, lcfunc)
            else:
                self.start("__ss_result->append(")
                self.visit(node.elt, lcfunc)
                self.append(")")
            self.eol()
            return

        qual = quals[0]

        # iter var
        if isinstance(qual.target, ast.Name):
            var = python.lookup_var(qual.target.id, lcfunc, self.mv)
        else:
            var = python.lookup_var(self.mv.tempcount[qual.target], lcfunc, self.mv)
        iter = self.cpp_name(var)

        if ast_utils.is_fastfor(qual):
            self.do_fastfor(node, qual, quals, iter, lcfunc, genexpr)
        elif self.fastenumerate(qual):
            self.do_fastenumerate(qual, lcfunc, genexpr)
            self.listcompfor_body(node, quals, iter, lcfunc, True, genexpr)
        elif self.fastzip2(qual):
            self.do_fastzip2(qual, lcfunc, genexpr)
            self.listcompfor_body(node, quals, iter, lcfunc, True, genexpr)
        elif self.fastdictiter(qual):
            self.do_fastdictiter(qual, lcfunc, genexpr)
            self.listcompfor_body(node, quals, iter, lcfunc, True, genexpr)
        else:
            if not isinstance(qual.iter, ast.Name):
                itervar = self.mv.tempcount[qual]
                self.start("")
                self.visitm(itervar, " = ", qual.iter, lcfunc)
                self.eol()
            else:
                itervar = self.cpp_name(qual.iter.id)

            pref, tail = self.forin_preftail(qual)

            if (len(node.generators) == 1 and
                not qual.ifs and
                not genexpr and
                not node in self.gx.setcomp_to_lc.values() and
                not node in self.gx.dictcomp_to_lc.values()):
                if self.one_class(qual.iter, ("list", "tuple", "str_", "dict", "set")):
                    self.output("__ss_result->resize(len(" + itervar + "));")

            self.start("FOR_IN" + pref + "(" + iter + "," + itervar + "," + tail)
            self.print(self.line + ")")
            self.listcompfor_body(node, quals, iter, lcfunc, False, genexpr)

    def listcompfor_body(
        self,
        node: ast.ListComp,
        quals: List[ast.comprehension],
        iter: str,
        lcfunc: "python.Function",
        skip: bool,
        genexpr: bool,
    ) -> None:
        """Generate the body of a for loop"""
        qual = quals[0]

        if not skip:
            self.indent()
            if ast_utils.is_assign_list_or_tuple(qual.target):
                assert isinstance(qual.target, (ast.Tuple, ast.List))
                self.tuple_assign(qual.target, iter, lcfunc)

        # if statements
        if qual.ifs:
            self.start("if (")
            self.indent()
            for cond in qual.ifs:
                self.bool_test(cond, lcfunc)
                if cond != qual.ifs[-1]:
                    self.append(" && ")
            self.append(") {")
            self.print(self.line)

        # recurse
        self.listcomp_rec(node, quals[1:], lcfunc, genexpr)

        # --- nested for loops: loop tails
        if qual.ifs:
            self.deindent()
            self.output("}")
        self.deindent()
        self.output("END_FOR\n")

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

