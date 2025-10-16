# SHED SKIN Python-to-C++ Compiler
# Copyright 2005-2024 Mark Dufour and contributors; GNU GPL version 3 (See LICENSE)
"""shedskin.cpp.declarations - Declaration and header generation

This module contains methods for generating C++ declarations and definitions:
- Header file generation (module_hpp, class_hpp)
- Implementation file generation (module_cpp, class_cpp)
- Function declarations (gen_declare_defs, declare_defs, func_header)
- Generator function handling
- List comprehension classes
"""

import ast
from typing import TYPE_CHECKING, Any, Iterator, List, Optional, Tuple, TypeAlias

from .. import ast_utils, infer, python, typestr, virtual

if TYPE_CHECKING:
    pass

Types: TypeAlias = set[Tuple["python.Class", int]]


class DeclarationMixin:
    """Mixin for declaration and header generation methods"""

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
    ) -> List["python.Module"]:
        """Find all (indirect) dependencies recursively.

        Note: Despite the name and comment, this uses an iterative algorithm
        with a work queue instead of recursion. This is intentional because:
        1. Iterative approach avoids stack overflow on deep dependency chains
        2. Easier to detect and break circular dependencies
        3. More efficient for large dependency graphs
        The name 'includes_rec' is kept for API compatibility.
        """
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

    def local_defs(self, func: "python.Function") -> None:
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

