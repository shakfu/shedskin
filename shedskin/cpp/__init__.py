# SHED SKIN Python-to-C++ Compiler
# Copyright 2005-2024 Mark Dufour and contributors; GNU GPL version 3 (See LICENSE)
"""shedskin.cpp package - C++ code generation

Refactored from monolithic cpp.py (4,389 lines) into focused modules.

Phase 1: Extracted CPPNamer to cpp/namer.py
Phase 2: Extracted OutputMixin to cpp/output.py
"""

from .namer import CPPNamer
from .output import OutputMixin
from .expressions import ExpressionVisitorMixin
from .statements import StatementVisitorMixin

__all__ = ['CPPNamer', 'OutputMixin', 'ExpressionVisitorMixin', 'StatementVisitorMixin']
