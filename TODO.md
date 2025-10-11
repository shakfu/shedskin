# Next Steps - Options:

## Option A: Complete Phase 2 Items (Medium Priority)

From the 9.2 section, there are still some items that were marked as
"partial":

1. [x] Expand Test Coverage
  - Add unit tests for error.py module
  - Add integration tests for compilation pipeline
  - Current: 87 unit tests, could expand to ~150+
2. [ ] Continue Type Hints
  - Add types to error.py (currently no type hints)
  - Add types to more core modules
  - Gradually enable mypy strict mode for existing modules
3. [ ] Address Remaining Technical Debt
  - Review and resolve 80+ TODO/XXX comments in cpp.py
  - Refactor large methods
  - Extract duplicated code

## Option B: Phase 3 - Long-term Enhancements (9.3)

1. Split cpp.py into Focused Modules (HIGH IMPACT)
  - cpp.py is 4,389 lines - unmaintainable
  - Split into: generator.py, types.py, functions.py, classes.py,
expressions.py, statements.py, templates.py
  - Estimated: 2-3 days
2. Improve C++ Template System
  - Replace macros with template aliases in builtin.hpp
  - Use C++20 concepts for better error messages
  - Estimated: 1-2 days
3. Documentation
  - Document CPA/IFA algorithms
  - Create architecture decision records (ADRs)
  - Add developer contribution guide
  - Estimated: 1 week

## Option C: Quick Wins

1. Add mypy to CI/test workflow (30 min)
2. Run and fix any mypy issues in new modules (1 hour)
3. Add docstrings to undocumented functions (2-3 hours)

## My Recommendation

Since comprehensive tests are running, I'd suggest:

Start with Option A.1 - Add unit tests for error.py:
- It's the error handling module we refactored
- Should have test coverage to prevent regressions
- Relatively quick (~1-2 hours)
- High value for code quality

Then either:
- Option A.2 - Continue type hints (good incremental progress)
- Option B.1 - Split cpp.py (highest technical debt item, biggest impact)

What would you prefer to tackle next?
