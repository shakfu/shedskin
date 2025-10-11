# SHED SKIN Python-to-C++ Compiler
# Copyright 2005-2024 Mark Dufour and contributors; GNU GPL version 3 (See LICENSE)
"""shedskin.cpp package - C++ code generation

This package implements the C++ code generation phase of the Shedskin compiler.
It translates Python AST nodes (with inferred type information) into optimized C++ code.

Architecture Overview
=====================

The package uses a **mixin-based architecture** where different aspects of code generation
are separated into focused modules. These mixins are composed together via multiple
inheritance to form the complete GenerateVisitor class.

Module Structure
----------------

    shedskin/cpp/
    ├── __init__.py          # Package exports (this file)
    ├── namer.py             # CPPNamer: C++ naming and keyword handling
    ├── output.py            # OutputMixin: Output buffer management
    ├── expressions.py       # ExpressionVisitorMixin: Expression AST visitors
    ├── statements.py        # StatementVisitorMixin: Statement AST visitors
    ├── helpers.py           # HelperMixin: Helper methods and optimizations
    ├── declarations.py      # DeclarationMixin: Header/declaration generation
    └── templates.py         # TemplateMixin: Type checking and casting

Module Interactions
===================

1. **namer.py (CPPNamer)**
   - Pure utility class (no dependencies on other mixins)
   - Used by: All visitor mixins
   - Purpose: Convert Python names to valid C++ identifiers
   - Example: Handles C++ reserved keywords, adds namespace prefixes

2. **output.py (OutputMixin)**
   - Foundation layer (no dependencies on other mixins)
   - Used by: All visitor mixins
   - Purpose: Manages output buffer, indentation, file I/O
   - Methods: print(), append(), indent(), deindent(), start(), eol()

3. **templates.py (TemplateMixin)**
   - Low-level type utilities (minimal dependencies)
   - Used by: expressions, statements, helpers, declarations
   - Purpose: Type checking, casting, template instantiation
   - Methods: only_classes(), cast_to_builtin(), inhcpa(), subtypes()

4. **helpers.py (HelperMixin)**
   - Mid-level code generation utilities
   - Depends on: output, templates
   - Used by: expressions, statements, declarations
   - Purpose: Specialized code generators (loops, comparisons, lambdas)
   - Methods: do_fastfor(), do_compare(), fastfor(), fastenumerate()

5. **expressions.py (ExpressionVisitorMixin)**
   - High-level AST visitor layer
   - Depends on: output, templates, helpers
   - Purpose: Generate C++ for Python expressions
   - Methods: visit_Call(), visit_BinOp(), visit_Name(), visit_Attribute()
   - Handles: 24 expression types (calls, operations, literals, comprehensions)

6. **statements.py (StatementVisitorMixin)**
   - High-level AST visitor layer
   - Depends on: output, templates, helpers, declarations
   - Purpose: Generate C++ for Python statements
   - Methods: visit_For(), visit_If(), visit_Assign(), visit_FunctionDef()
   - Handles: 22 statement types (control flow, assignments, definitions)

7. **declarations.py (DeclarationMixin)**
   - High-level declaration generator
   - Depends on: output, templates, helpers
   - Purpose: Generate C++ declarations and headers
   - Methods: module_hpp(), class_hpp(), func_header(), generator_class()
   - Handles: Header files, class declarations, function signatures

Composition Pattern
===================

The GenerateVisitor class composes all mixins via multiple inheritance:

    class GenerateVisitor(
        TemplateMixin,          # Type utilities (lowest level)
        DeclarationMixin,       # Declaration generation
        HelperMixin,            # Helper utilities
        StatementVisitorMixin,  # Statement visitors
        ExpressionVisitorMixin, # Expression visitors
        OutputMixin,            # Output management (foundation)
        ast_utils.BaseNodeVisitor  # Base visitor pattern
    ):
        pass

Method Resolution Order (MRO):
    GenerateVisitor → TemplateMixin → DeclarationMixin → HelperMixin →
    StatementVisitorMixin → ExpressionVisitorMixin → OutputMixin →
    BaseNodeVisitor → object

Data Flow
=========

1. **Initialization** (cpp.py)
   - GlobalInfo (gx) contains type inference results
   - Module contains Python AST with type annotations
   - CPPNamer is initialized for name translation

2. **Header Generation** (declarations.py)
   - module_hpp() generates .hpp file
   - Includes forward declarations, class definitions
   - Uses templates.py for type expressions
   - Uses output.py for formatted output

3. **Implementation Generation** (statements.py, expressions.py)
   - visit_Module() entry point
   - Recursively visits AST nodes
   - Statements call expressions for nested expressions
   - Both use helpers.py for specialized patterns
   - All use output.py for code emission

4. **Optimization** (helpers.py)
   - Detects patterns (fastfor, fastenumerate)
   - Generates optimized C++ loops
   - Uses templates.py for type checks

5. **Output** (output.py)
   - Accumulates generated code in buffers
   - Manages indentation levels
   - Writes to .cpp/.hpp files

Usage Example
=============

    from shedskin.cpp import CPPNamer, GenerateVisitor
    from shedskin import config

    # Create global info with type inference results
    gx = config.GlobalInfo()

    # Create visitor
    visitor = GenerateVisitor(gx, module, analyze=False)

    # Generate code (entry point)
    visitor.visit(module.ast)  # Calls visit_Module()

    # Result: .cpp and .hpp files written to output directory

History
=======

Refactored from monolithic cpp.py (4,389 lines) into 7 focused modules (3,615 lines):
- Phase 1: Extracted CPPNamer (86 lines)
- Phase 2: Extracted OutputMixin (193 lines)
- Phase 3: Extracted ExpressionVisitorMixin (1,236 lines)
- Phase 4: Extracted StatementVisitorMixin (646 lines)
- Phase 5: Extracted HelperMixin, DeclarationMixin, TemplateMixin (1,454 lines)

Final cpp.py: 946 lines (79% reduction)

Design Principles
=================

1. **Separation of Concerns**: Each module has a single, well-defined responsibility
2. **Mixin Composition**: Functionality composed via multiple inheritance
3. **Backward Compatibility**: GenerateVisitor interface unchanged
4. **Testability**: Each module can be tested independently
5. **Zero Behavioral Changes**: Generated C++ code identical to original
"""

from typing import TYPE_CHECKING

from .namer import CPPNamer
from .output import OutputMixin
from .expressions import ExpressionVisitorMixin
from .statements import StatementVisitorMixin
from .helpers import HelperMixin
from .declarations import DeclarationMixin
from .templates import TemplateMixin
from .visitor import GenerateVisitor

if TYPE_CHECKING:
    from .. import config

__all__ = [
    'CPPNamer',
    'OutputMixin',
    'ExpressionVisitorMixin',
    'StatementVisitorMixin',
    'HelperMixin',
    'DeclarationMixin',
    'TemplateMixin',
    'GenerateVisitor',
    'generate_code',
]


def generate_code(gx: "config.GlobalInfo", analyze: bool = False) -> None:
    """Generate C++ code for all modules.

    This is the main entry point for C++ code generation. It creates a
    GenerateVisitor for each module and generates both .cpp and .hpp files.

    Args:
        gx: GlobalInfo containing type inference results and modules
        analyze: If True, only analyze without writing files

    Process:
        1. Create GenerateVisitor for each non-builtin module
        2. Visit module AST to generate implementation (.cpp)
        3. Generate header file (.hpp)
        4. Insert constants and extras into both files
    """
    for module in gx.modules.values():
        if not module.builtin:
            gv = GenerateVisitor(gx, module, analyze)
            gv.visit(module.ast)
            gv.out.close()
            gv.header_file()
            gv.out.close()
            gv.insert_consts(declare=False)
            gv.insert_consts(declare=True)
            gv.insert_extras(".hpp")
            gv.insert_extras(".cpp")
