# CPP Module Refactoring Plan

**Date**: 2025-10-11
**Status**: Design Phase
**Priority**: HIGH - Addresses critical technical debt (CODE_REVIEW.md Section 9.3)

## Executive Summary

The `shedskin/cpp.py` module is **4,389 lines** with **145 methods** in a single `GenerateVisitor` class. This is unmaintainable and represents the highest-priority technical debt in the codebase. This document outlines a plan to split it into focused, maintainable modules.

---

## Current State Analysis

### File Statistics
- **Total Lines**: 4,389
- **Classes**: 2 (`CPPNamer`, `GenerateVisitor`)
- **Methods in GenerateVisitor**: 145
- **Complexity**: Extremely high - single class handles entire AST traversal and code generation

### Method Categories

| Category | Count | Purpose |
|----------|-------|---------|
| `visit_*` methods | 46 | AST node handlers (visitor pattern) |
| `do_*` methods | 12 | Specialized code generation helpers |
| `gen_*` methods | 2 | Declaration/definition generation |
| Other methods | 84 | Utilities, output, templates, type handling |
| **Total** | **145** | |

### Key Methods by Category

**AST Visitors (46 methods)**:
- Expressions: `visit_Call`, `visit_BinOp`, `visit_Attribute`, `visit_Subscript`, etc.
- Statements: `visit_Assign`, `visit_For`, `visit_If`, `visit_Try`, etc.
- Definitions: `visit_FunctionDef`, `visit_ClassDef`, `visit_Module`
- Others: `visit_Lambda`, `visit_ListComp`, `visit_DictComp`, etc.

**Helper Methods (12 do_* methods)**:
- `do_fastfor` - Optimized for loop generation
- `do_compare` - Comparison operator handling
- `do_lambdas` - Lambda function generation
- `do_listcomps` - List comprehension generation
- etc.

**Other Key Methods**:
- Output management: `print`, `append`, `start`, `eol`, `indent`, `deindent`
- Naming: `cpp_name`, `get_constant`, `connector`
- Declarations: `gen_declare_defs`, `declare_defs`, `header_file`
- Templates: Various template specialization methods

---

## Proposed Architecture

### 📦 New Package Structure: `shedskin/cpp/`

```
shedskin/cpp/
├── __init__.py          # Public API, exports generate_code()
├── namer.py            # CPPNamer class (C++ naming, keywords)
├── output.py           # Output buffer management (print, append, indent)
├── visitor_base.py     # Base GenerateVisitor class + common utilities
├── expressions.py      # Expression visitors (visit_Call, visit_BinOp, etc.)
├── statements.py       # Statement visitors (visit_Assign, visit_For, etc.)
├── declarations.py     # Declaration/definition generation
├── templates.py        # Template specialization logic
└── helpers.py          # do_* helper methods (do_fastfor, do_compare, etc.)
```

### Module Responsibilities

#### 1. `namer.py` (~100 lines)
**Purpose**: C++ naming and keyword conflict resolution

**Contents**:
- `CPPNamer` class
- Methods:
  - `nokeywords()` - Remove C++ reserved keywords
  - `namespace_class()` - Add namespace to class names
  - `name()` - Generate C++ name for Python objects
  - `name_variable()`, `name_function()`, `name_class()`, `name_str()`

**Dependencies**:
- `config.GlobalInfo`
- `python` module (for Class, Function, Variable types)

---

#### 2. `output.py` (~200 lines)
**Purpose**: Output buffer and formatting management

**Contents**:
- Output buffer class/mixin
- Methods:
  - `print()` - Print to file
  - `output()` - Return output as string
  - `start()` - Start line buffer
  - `append()` - Append to line buffer
  - `eol()` - End of line
  - `indent()` - Increase indentation
  - `deindent()` - Decrease indentation
  - `get_output_file()` - Get output file handle
  - `insert_consts()` - Insert constants

**Dependencies**: Minimal (I/O operations)

---

#### 3. `visitor_base.py` (~500 lines)
**Purpose**: Base visitor class with shared functionality

**Contents**:
- `GenerateVisitor` base class (inherits from `ast_utils.BaseNodeVisitor`)
- `__init__()` method
- Common utilities:
  - `visitm()` - Visit with mode
  - `connector()` - Get connector string
  - `get_constant()` - Get constant value
  - `cpp_name()` - Get C++ name
  - Type checking utilities
  - Template utilities
- Shared state management

**Dependencies**:
- All other cpp/* modules (mixins/composition)
- `ast_utils`, `config`, `python`, `infer`

---

#### 4. `expressions.py` (~1,200 lines)
**Purpose**: Handle Python expression AST nodes

**Contents** (20+ visitor methods):
- `visit_BinOp` - Binary operations (+, -, *, /, etc.)
- `visit_BoolOp` - Boolean operations (and, or)
- `visit_Call` - Function calls
- `visit_callfunc_args` - Function call arguments
- `visit_Attribute` - Attribute access (obj.attr)
- `visit_Subscript` - Subscript access (obj[key])
- `visit_Name` - Variable names
- `visit_Constant` - Literal constants
- `visit_Compare` - Comparison operators
- `visit_IfExp` - Ternary expressions (a if b else c)
- `visit_Lambda` - Lambda functions
- `visit_List`, `visit_Set`, `visit_Dict` - Literal collections
- `visit_ListComp`, `visit_SetComp`, `visit_DictComp` - Comprehensions
- `visit_GeneratorExp` - Generator expressions
- `visit_JoinedStr` - f-strings
- `visit_Slice` - Slice objects
- etc.

**Dependencies**:
- `visitor_base.GenerateVisitor` (inherits/extends)
- `helpers` (for do_* methods)

---

#### 5. `statements.py` (~1,000 lines)
**Purpose**: Handle Python statement AST nodes

**Contents** (20+ visitor methods):
- `visit_Module` - Module root
- `visit_FunctionDef` - Function definitions
- `visit_Assign` - Assignment statements
- `visit_AugAssign` - Augmented assignment (+=, -=, etc.)
- `visit_AnnAssign` - Annotated assignment
- `visit_For` - For loops
- `visit_While` - While loops
- `visit_If` - If statements
- `visit_Try` - Try/except blocks
- `visit_Raise` - Raise exceptions
- `visit_Return` - Return statements
- `visit_Break`, `visit_Continue` - Loop control
- `visit_Pass` - Pass statements
- `visit_Assert` - Assertions
- `visit_Delete` - Delete statements
- `visit_Global` - Global declarations
- `visit_Import`, `visit_ImportFrom` - Import statements
- `visit_Expr` - Expression statements
- `visit_NamedExpr` - Walrus operator (:=)

**Dependencies**:
- `visitor_base.GenerateVisitor` (inherits/extends)
- `helpers` (for do_* methods)
- `declarations` (for function/class definitions)

---

#### 6. `declarations.py` (~600 lines)
**Purpose**: Generate C++ declarations and definitions

**Contents**:
- `gen_declare_defs()` - Generate declarations/definitions
- `declare_defs()` - Declare definitions
- `gen_defaults()` - Generate default values
- Header file generation:
  - `header_file()` - Generate header file
  - `include_files()` - Generate includes
  - `includes_rec()` - Recursive includes
  - `fwd_class_refs()` - Forward class references
  - `group_declarations()` - Group declarations
  - `insert_extras()` - Insert extra code
- Class/function declaration helpers

**Dependencies**:
- `visitor_base.GenerateVisitor`
- `templates` (for template specializations)

---

#### 7. `templates.py` (~500 lines)
**Purpose**: Template specialization and type expression handling

**Contents**:
- Template type expression generation
- Template specialization logic
- Type string formatting
- Template instantiation
- Polymorphic type handling
- Virtual method table generation helpers

**Dependencies**:
- `typestr` module
- `python` module

---

#### 8. `helpers.py` (~300 lines)
**Purpose**: Specialized code generation helpers

**Contents** (12 do_* methods):
- `do_main()` - Generate main function
- `do_init_modules()` - Generate module initialization
- `do_comment()`, `do_comments()` - Comment generation
- `do_fastfor()` - Optimized for loop
- `do_fastzip2()`, `do_fastzip2_one()` - Optimized zip
- `do_fastenumerate()` - Optimized enumerate
- `do_fastdictiter()` - Optimized dict iteration
- `do_compare()` - Comparison operators
- `do_lambdas()` - Lambda functions
- `do_listcomps()` - List comprehensions

**Dependencies**:
- `visitor_base.GenerateVisitor`

---

#### 9. `__init__.py` (~50 lines)
**Purpose**: Public API and backward compatibility

**Contents**:
```python
"""shedskin.cpp package - C++ code generation

Refactored from monolithic cpp.py (4,389 lines) into focused modules.
"""

from .namer import CPPNamer
from .visitor_base import GenerateVisitor

# Main entry point (backward compatible)
def generate_code(gx, analyze=False):
    """Generate C++ code from analyzed Python AST"""
    from . import expressions, statements, declarations, templates, helpers
    # Implementation...

__all__ = ['CPPNamer', 'GenerateVisitor', 'generate_code']
```

**Dependencies**: All cpp/* modules

---

## Implementation Approaches

### Option A: Full Split (2-3 days)
**Timeline**: 2-3 days
**Risk**: HIGH
**Reward**: Complete solution

**Steps**:
1. Create `shedskin/cpp/` package structure
2. Extract all modules simultaneously
3. Refactor interdependencies
4. Update imports across codebase
5. Run full test suite

**Pros**:
- Complete solution in one go
- Cleaner final architecture
- No intermediate states

**Cons**:
- High risk of breaking changes
- Harder to debug if issues arise
- All-or-nothing approach

---

### Option B: Incremental (Safer) ✅ **RECOMMENDED**
**Timeline**: 4-5 days
**Risk**: LOW-MEDIUM
**Reward**: Same as Option A, but safer

**Phase 1: Extract CPPNamer** (2 hours)
- Create `cpp/` package
- Move `CPPNamer` to `cpp/namer.py`
- Update imports in `cpp.py`
- Test: Run unit tests + basic compilation

**Phase 2: Extract Output Management** (3 hours)
- Create `cpp/output.py`
- Move output methods (print, append, indent, etc.)
- Use mixin or composition pattern
- Test: Run unit tests + basic compilation

**Phase 3: Split Visitor - Expressions** (1 day)
- Create `cpp/expressions.py`
- Move expression visitor methods
- Keep references working via inheritance/delegation
- Test: Run unit tests + compile several test files

**Phase 4: Split Visitor - Statements** (1 day)
- Create `cpp/statements.py`
- Move statement visitor methods
- Test: Run unit tests + compile several test files

**Phase 5: Extract Remaining Modules** (1 day)
- Create `cpp/declarations.py`, `cpp/templates.py`, `cpp/helpers.py`
- Move remaining methods
- Test: Full test suite (118+ tests)

**Phase 6: Final Integration** (4 hours)
- Clean up `cpp/__init__.py`
- Update documentation
- Final testing and verification

**Pros**:
- Testable after each phase
- Easy to debug and rollback
- Gradual migration reduces risk
- Can pause/adjust strategy if issues arise

**Cons**:
- Takes longer
- More intermediate commits
- Some temporary complexity during migration

---

## Challenges & Mitigation Strategies

### 1. High Interdependency
**Challenge**: Methods extensively reference each other

**Mitigation**:
- Use mixins/multiple inheritance for shared functionality
- Keep `visitor_base.py` as common base
- Use composition where appropriate
- Careful ordering of imports

### 2. Shared State
**Challenge**: Many methods access `self.gx`, `self.module`, etc.

**Mitigation**:
- Keep shared state in base class
- Pass context objects where needed
- Use property accessors for common state

### 3. Circular Imports
**Challenge**: Visitor methods may call each other across modules

**Mitigation**:
- Use `TYPE_CHECKING` for type hints
- Import at function level when needed
- Structure inheritance to avoid cycles
- Use forward declarations

### 4. Test Coverage
**Challenge**: Need to verify 118+ test cases still pass

**Mitigation**:
- Run tests after each phase
- Focus on compilation tests (test_*.py)
- Use `shedskin test -x` for executable tests
- Monitor for any behavioral changes

---

## Success Criteria

### Code Quality Metrics
- ✅ No single module > 1,500 lines
- ✅ Clear separation of concerns
- ✅ Reduced cyclomatic complexity
- ✅ Better testability (can mock/test individual components)

### Functional Requirements
- ✅ All 118+ tests pass
- ✅ Zero behavioral changes
- ✅ Backward compatible imports (`from shedskin.cpp import generate_code`)
- ✅ Generated C++ code identical to before (or provably equivalent)

### Developer Experience
- ✅ Easier to understand code flow
- ✅ Faster to locate bugs
- ✅ Simpler to add new AST node support
- ✅ Better IDE navigation

---

## Migration Plan

### Pre-Migration
- [x] Analyze current structure
- [x] Design module architecture
- [x] Document plan
- [ ] Get stakeholder approval
- [ ] Create feature branch: `refactor/split-cpp-module`

### Migration (Incremental Approach)
- [x] **Phase 1**: Extract CPPNamer (2 hours) ✅ COMPLETE
  - Created cpp/ package structure
  - Extracted CPPNamer to cpp/namer.py (86 lines)
  - Reduced cpp.py from 4,389 to 4,323 lines (66 lines extracted)
  - All 114 unit tests pass
  - Basic and complex compilation tests pass
  - Committed: 91402372
- [x] **Phase 2**: Extract Output Management (3 hours) ✅ COMPLETE
  - Created cpp/output.py with OutputMixin (193 lines)
  - Extracted output methods: get_output_file, insert_consts, insert_extras
  - Extracted buffer methods: print, output, start, append, eol, indent, deindent
  - GenerateVisitor now inherits from OutputMixin
  - Reduced cpp.py from 4,323 to 4,182 lines (141 lines extracted)
  - All 114 unit tests pass
  - Basic and complex compilation tests pass
  - Committed: ede504cf
- [x] **Phase 3**: Split Visitor - Expressions (1 day) ✅ COMPLETE
  - Created cpp/expressions.py with ExpressionVisitorMixin (1,236 lines)
  - Extracted 24 expression visitor methods (~1,223 lines)
  - Methods include: BinOp, UnaryOp, Call, Attribute, Name, Constant, comprehensions, etc.
  - GenerateVisitor now inherits from ExpressionVisitorMixin
  - Reduced cpp.py from 4,182 to 2,959 lines (1,223 lines extracted)
  - All 114 unit tests pass
  - Basic and complex compilation tests pass
  - Committed: 6881c98b
- [x] **Phase 4**: Split Visitor - Statements (1 day) ✅ COMPLETE
  - Created cpp/statements.py with StatementVisitorMixin (646 lines)
  - Extracted 22 statement visitor methods (633 lines)
  - Methods include: For, While, If, Try, Assign, FunctionDef, Module, etc.
  - GenerateVisitor now inherits from StatementVisitorMixin
  - Reduced cpp.py from 2,959 to 2,326 lines (633 lines extracted)
  - All 114 unit tests pass
  - Basic and complex compilation tests pass
  - Committed: 74c304d6
- [x] **Phase 5**: Extract Remaining Modules (1 day) ✅ COMPLETE
  - Created cpp/helpers.py with HelperMixin (426 lines)
    - Extracted 18 helper methods (404 lines): do_* methods and optimization helpers
    - Methods include: do_main, do_init_modules, do_fastfor, do_compare, fastfor, fastenumerate, etc.
  - Created cpp/declarations.py with DeclarationMixin (875 lines)
    - Extracted 27 declaration methods (851 lines): header/implementation generation
    - Methods include: module_hpp, class_hpp, func_header, generator_class, listcomp methods, etc.
  - Created cpp/templates.py with TemplateMixin (153 lines)
    - Extracted 9 type/template methods (131 lines): type checking and casting
    - Methods include: nothing, inhcpa, subtypes, cast_to_builtin, only_classes, etc.
  - GenerateVisitor now inherits from all mixins: TemplateMixin, DeclarationMixin, HelperMixin, StatementVisitorMixin, ExpressionVisitorMixin, OutputMixin
  - Reduced cpp.py from 2,326 to 946 lines (1,386 lines extracted in Phase 5)
  - Total extracted across all phases: 3,449 lines (79% reduction from original 4,389 lines)
  - All 114 unit tests pass
  - Basic compilation tests pass
  - Committed: 35edee29
- [ ] **Phase 6**: Final Integration (4 hours)

### Post-Migration
- [ ] Update documentation (README, CODE_REVIEW.md)
- [ ] Add module-level docstrings
- [ ] Consider adding type hints to new modules
- [ ] Update IMPLEMENTATION_SUMMARY.md

---

## Testing Strategy

### After Each Phase
1. Run unit tests: `pytest tests/unit/ -v`
2. Run basic compilation: `shedskin build test`
3. Run test suite: `shedskin test --target test_func_basic`

### Before Merge
1. Full test suite: `shedskin test -x` (all executables)
2. Extension module tests: `shedskin test -e` (all extensions)
3. Error message tests: `shedskin test --run-errs`
4. Verify no warnings: Check compilation output

### Regression Testing
- Compare generated C++ for key test files
- Ensure identical output (or document deliberate changes)
- Performance benchmarks (if available)

---

## Rollback Plan

If issues arise during migration:

1. **Per-Phase Rollback**: Revert to previous phase commit
2. **Full Rollback**: Merge `master` back into feature branch
3. **Adjust Strategy**: Switch from incremental to different approach
4. **Document Issues**: Record problems for future attempts

---

## Related Documentation

- **CODE_REVIEW.md** - Section 3.1, 6.1.1 (Monolithic Modules)
- **IMPLEMENTATION_9.2_SUMMARY.md** - Previous refactoring work
- **TODO.md** - Option B.1 (this task)

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-10-11 | Use incremental approach (Option B) | Lower risk, testable phases, easier debugging |
| 2025-10-11 | 8-module split architecture | Balanced granularity vs. complexity |
| 2025-10-11 | Keep `generate_code()` as main entry | Backward compatibility |

---

## Next Steps

1. **Get approval** for this refactoring plan
2. **Create feature branch**: `git checkout -b refactor/split-cpp-module`
3. **Start Phase 1**: Extract CPPNamer to `cpp/namer.py`
4. **Iterate** through remaining phases
5. **Document** progress in this file

---

**Author**: Claude (with human oversight)
**Last Updated**: 2025-10-11
**Status**: 🚀 In Progress - Phase 5 Complete (83% done - major refactoring complete!)
