# SHED SKIN Python-to-C++ Compiler
# Copyright 2005-2024 Mark Dufour and contributors; GNU GPL version 3 (See LICENSE)
"""shedskin.cpp.output - Output buffer and formatting management

This module provides output management functionality for C++ code generation,
including file handling, indentation, and line buffering.
"""

import ast
import io
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .. import infer


class OutputMixin:
    """Mixin class for output management in code generation

    This class provides methods for managing C++ code output, including:
    - File handle management
    - Line buffering and formatting
    - Indentation control
    - Constant insertion

    Classes using this mixin should provide:
    - self.gx (config.GlobalInfo)
    - self.module (python.Module)
    - self.analyze (bool)
    - self.output_base (Path)
    - self.consts (dict)
    - self.filling_consts (bool)
    - self.mergeinh (dict)
    """

    def get_output_file(self, ext: str = ".cpp", mode: str = "w") -> IO[Any]:
        """Get an output file for writing C++ code"""
        if self.analyze:  # type: ignore[attr-defined]
            return io.StringIO()
        output_file = Path(self.output_base.with_suffix(ext))  # type: ignore[attr-defined]
        assert self.gx.module_path  # type: ignore[attr-defined]
        module_path = Path(self.gx.module_path)  # type: ignore[attr-defined]
        if self.gx.outputdir:  # type: ignore[attr-defined]
            outputdir = Path(self.gx.outputdir)  # type: ignore[attr-defined]
            output_file = outputdir / output_file.relative_to(module_path.parent)
            output_file.parent.mkdir(exist_ok=True)
        return open(output_file, mode)

    def insert_consts(self, declare: bool) -> None:  # XXX ugly
        """Insert constant declarations into the output file"""
        if not self.consts:  # type: ignore[attr-defined]
            return
        self.filling_consts = True  # type: ignore[attr-defined]

        if declare:
            suffix = ".hpp"
        else:
            suffix = ".cpp"

        with self.get_output_file(ext=suffix, mode="r") as f:
            lines = f.readlines()
        newlines = []
        j = -1
        for i, line in enumerate(lines):
            if line.startswith("namespace ") and "XXX" not in line:  # XXX
                j = i + 1
            newlines.append(line)

            if i == j:
                pairs = []
                done = set()
                for node, name in self.consts.items():  # type: ignore[attr-defined]
                    if (
                        name not in done
                        and node in self.mergeinh  # type: ignore[attr-defined]
                        and self.mergeinh[node]  # type: ignore[attr-defined]
                    ):  # XXX
                        from .. import infer, typestr
                        ts = typestr.nodetypestr(
                            self.gx, node, infer.inode(self.gx, node).parent, mv=self.mv  # type: ignore[attr-defined]
                        )
                        if declare:
                            ts = "extern " + ts
                        pairs.append((ts, name))
                        done.add(name)

                newlines.extend(self.group_declarations(pairs))  # type: ignore[attr-defined]
                newlines.append("\n")

        newlines2 = []
        j = -1
        for i, line in enumerate(newlines):
            if line.startswith("void __init() {"):
                j = i
            newlines2.append(line)

            if i == j:
                todo = {}
                for node, name in self.consts.items():  # type: ignore[attr-defined]
                    if name not in todo:
                        todo[int(name[6:])] = node
                todolist = list(todo)
                todolist.sort()
                for number in todolist:
                    if self.mergeinh[todo[number]]:  # XXX  # type: ignore[attr-defined,index]
                        name = "const_" + str(number)
                        self.start("    " + name + " = ")  # type: ignore[attr-defined]
                        if (
                            isinstance(todo[number], ast.Str)
                            and len(todo[number].s.encode("utf-8")) == 1
                        ):
                            self.append("__char_cache[%d]" % ord(todo[number].s))  # type: ignore[attr-defined]
                        elif (
                            isinstance(todo[number], ast.Bytes)
                            and len(todo[number].s) == 1
                        ):
                            self.append("__byte_cache[%d]" % ord(todo[number].s))  # type: ignore[attr-defined]
                        else:
                            from .. import infer
                            self.visit(  # type: ignore[attr-defined]
                                todo[number], infer.inode(self.gx, todo[number]).parent  # type: ignore[attr-defined]
                            )
                        newlines2.append(self.line + ";\n")  # type: ignore[attr-defined]

                newlines2.append("\n")

        with self.get_output_file(ext=suffix, mode="w") as f:
            f.writelines(newlines2)
        self.filling_consts = False  # type: ignore[attr-defined]

    def insert_extras(self, suffix: str) -> None:
        """Insert extra lines into the output file"""
        with self.get_output_file(ext=suffix, mode="r") as f:
            lines = f.readlines()
        newlines = []
        for line in lines:
            newlines.append(line)
            if suffix == ".cpp" and line.startswith("#include"):
                newlines.extend(self.include_files())  # type: ignore[attr-defined]
            elif suffix == ".hpp" and line.startswith("using namespace"):
                newlines.extend(self.fwd_class_refs())  # type: ignore[attr-defined]
        with self.get_output_file(ext=suffix, mode="w") as f:
            f.writelines(newlines)

    def print(self, text: Optional[str] = None) -> None:
        """Print text to the output file"""
        if text is not None:
            print(text, file=self.out)  # type: ignore[attr-defined]
        else:
            print(file=self.out)  # type: ignore[attr-defined]

    def output(self, text: str) -> None:
        """Output text to the output file"""
        if text:
            self.print(self.indentation + text)  # type: ignore[attr-defined]

    def start(self, text: Optional[str] = None) -> None:
        """Start a new line in the output file"""
        self.line = self.indentation  # type: ignore[attr-defined]
        if text:
            self.line += text  # type: ignore[attr-defined]

    def append(self, text: str) -> None:
        """Append text to the current line in the output file"""
        self.line += text  # type: ignore[attr-defined]

    def eol(self, text: Optional[str] = None) -> None:
        """End the current line in the output file"""
        if text:
            self.append(text)
        if self.line.strip():  # type: ignore[attr-defined]
            self.print(self.line + ";")  # type: ignore[attr-defined]

    def indent(self) -> None:
        """Indent the current line in the output file"""
        self.indentation += 4 * " "  # type: ignore[attr-defined]

    def deindent(self) -> None:
        """Deindent the current line in the output file"""
        self.indentation = self.indentation[:-4]  # type: ignore[attr-defined]
