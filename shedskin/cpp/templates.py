# SHED SKIN Python-to-C++ Compiler
# Copyright 2005-2024 Mark Dufour and contributors; GNU GPL version 3 (See LICENSE)
"""shedskin.cpp.templates - Type and template handling

This module contains methods for type checking and template handling:
- Type checking (only_classes, one_class, bin_tuple)
- Type casting (cast_to_builtin, cast_to_builtin2)
- Template utilities (nothing, inhcpa, subtypes, instance_new)
"""

import ast
from typing import TYPE_CHECKING, Any, Optional, Tuple, TypeAlias

from .. import infer, python, typestr

if TYPE_CHECKING:
    pass

Types: TypeAlias = set[Tuple["python.Class", int]]


class TemplateMixin:
    """Mixin for type and template handling methods"""

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

    def only_classes(self, node: ast.AST, names: Tuple[str, ...]) -> bool:
        """Check if a node is only classes"""
        if node not in self.mergeinh:
            return False
        classes = [python.def_class(self.gx, name, mv=self.mv) for name in names] + [
            python.def_class(self.gx, "none")
        ]
        return not [t for t in self.mergeinh[node] if t[0] not in classes]

    def one_class(self, node: ast.AST, names: Tuple[str, ...]) -> bool:
        """Check if a node is a single class"""
        for clname in names:
            if self.only_classes(node, (clname,)):
                return True
        return False

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

