# SHED SKIN Python-to-C++ Compiler
# Copyright 2005-2024 Mark Dufour and contributors; GNU GPL version 3 (See LICENSE)
"""shedskin.error: error handling"""

import ast
import logging
import sys
from typing import TYPE_CHECKING, Optional, Tuple, TypeAlias, Union

from .exceptions import CompilationError

if TYPE_CHECKING:
    from . import config, graph, python

Error: TypeAlias = Tuple[int, str, Optional[int], str]

logger = logging.getLogger("shedskin")
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.WARNING)
formatter = logging.Formatter("*%(levelname)s* %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)


ERRORS: set[Error] = set()


def error(
    msg: str,
    gx: "config.GlobalInfo",
    node: Optional[Union[ast.AST, "python.Variable"]] = None,
    warning: bool = False,
    mv: Optional["graph.ModuleVisitor"] = None,
) -> None:
    """Report an error"""
    from . import infer

    if warning:
        kind = logging.WARNING
    else:
        kind = logging.ERROR
    if not mv and node and (node, 0, 0) in gx.cnode:
        mv = infer.inode(gx, node).mv
    filename = lineno = None
    if mv:
        filename = mv.module.relative_filename
        if isinstance(node, ast.AST) and hasattr(node, "lineno"):
            lineno = node.lineno
    result = (kind, str(filename or ""), lineno, msg)
    if result not in ERRORS:
        ERRORS.add(result)
    if not warning:
        print_error(result)
        # Convert node to AST node if needed for exception
        ast_node = node if isinstance(node, ast.AST) else None
        raise CompilationError(msg, ast_node)


def print_error(error: Error) -> None:
    """Print an error"""
    (kind, filename, lineno, msg) = error
    result = ""
    if filename:
        result += str(filename) + ":"
        if lineno is not None:
            result += str(lineno) + ":"
        result += " "
    logger.log(kind, result + msg)


def print_errors() -> None:
    """Print all errors"""
    for error in sorted(
        ERRORS, key=lambda x: (x[1] or "", x[2] if x[2] is not None else -1)
    ):
        print_error(error)
