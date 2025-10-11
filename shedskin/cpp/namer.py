# SHED SKIN Python-to-C++ Compiler
# Copyright 2005-2024 Mark Dufour and contributors; GNU GPL version 3 (See LICENSE)
"""shedskin.cpp.namer - C++ naming and keyword conflict resolution

This module handles the generation of valid C++ identifiers from Python names,
ensuring no conflicts with C++ reserved keywords and proper namespacing.
"""

from typing import TYPE_CHECKING, Any

from .. import python

if TYPE_CHECKING:
    from .. import config


class CPPNamer:
    """Class for naming C++ entities"""

    def __init__(self, gx: "config.GlobalInfo", gv: Any):  # gv is GenerateVisitor
        self.gx = gx
        self.class_names = [cl.ident for cl in self.gx.allclasses]
        self.cpp_keywords = self.gx.cpp_keywords
        self.ss_prefix = self.gx.ss_prefix
        self.name_by_type = {
            str: self.name_str,
            python.Class: self.name_class,
            python.Function: self.name_function,
            python.Variable: self.name_variable,
        }
        self.gv = gv

    def nokeywords(self, name: str) -> str:
        """Remove C++ keywords from a name"""
        if name in self.cpp_keywords:
            return self.ss_prefix + name
        return name

    def namespace_class(self, cl: "python.Class", add_cl: str = "") -> str:
        """Add a namespace to a class name"""
        module = cl.mv.module
        if module.ident != "builtin" and module != self.gv.module and module.name_list:
            return module.full_path() + "::" + add_cl + self.name(cl)
        else:
            return add_cl + self.name(cl)

    def name(self, obj: Any) -> str:
        """Generate a C++ name for an object"""
        if isinstance(obj, str):
            name = self.name_str(obj)
        elif isinstance(obj, python.Class):
            name = self.name_class(obj)
        elif isinstance(obj, python.Function):
            name = self.name_function(obj)
        elif isinstance(obj, python.Variable):
            name = self.name_variable(obj)
        else:
            assert False

        return self.nokeywords(name)

    def name_variable(self, var: python.Variable) -> str:
        """Generate a C++ name for a variable"""
        if var.masks_global():
            return "_" + var.name
        return self.name_str(var.name)

    def name_function(self, func: python.Function) -> str:
        """Generate a C++ name for a function"""
        return self.name_str(func.ident)

    def name_class(self, obj: python.Class) -> str:
        """Generate a C++ name for a class"""
        return obj.ident

    def name_str(self, name: str) -> str:
        """Generate a C++ name for a string"""
        if (
            [x for x in ("init", "add") if name == x + self.gx.main_module.ident]
            or name in self.class_names
            or name + "_" in self.class_names
        ):
            name = "_" + name
        return name
