# Code Review Priorities

Phase 2: Architecture Improvements (1 month)

5. [x] Refactor GlobalInfo 🟡 MEDIUM

- Location: config.py
- Issue: 100+ attributes mixing configuration and runtime state
- Fix: Split into immutable CompilerOptions and mutable CompilerState
- Effort: 2-3 days
- Benefits: Better testability, thread safety, clearer state management

6. Add Unit Tests 🟡 MEDIUM

- Current: Good integration tests, lacking unit tests
- Focus: New cpp/ modules, infer.py, graph.py
- Effort: 1 week
- Benefits: Better test coverage, easier debugging, regression prevention

Phase 3: Technical Debt (2-3 months)

7. Address Technical Debt Markers 🟢 LOW-MEDIUM

- Count: 80+ TODO/XXX/FIXME comments in cpp modules
- Action: Resolve, fix, or document why deferred
- Effort: 1-2 weeks
- Examples:
  - Line 2516: Bug workaround without root cause fix
  - Line 3468: Unclear purpose code (# XXX remove?)

8. Improve Type Hints 🟢 LOW-MEDIUM

- Issue: Many functions lack proper type annotations
- Fix: Add complete type annotations, enable mypy strict mode
- Effort: 3-4 days
- Benefits: Better IDE support, catch type errors early

Recommended Prioritization

Immediate (This Week):
1. Fix command injection vulnerability (2 hours) ← DO THIS FIRST
2. Fix C-style casts in C++ templates (4-6 hours)
3. Add path traversal validation (3-4 hours)

Short-term (This Month):
4. Improve error handling (1 day)
5. Refactor GlobalInfo (2-3 days)
6. Add unit tests for cpp/ modules (1 week)

Medium-term (Next Quarter):
7. Address technical debt markers (1-2 weeks)
8. Improve type hints (3-4 days)

Why This Order?

1. Security first: Command injection is a critical vulnerability
2. Type safety: C-style casts are easy wins that improve code quality
3. Architecture: GlobalInfo refactoring enables better testing
4. Testing: Unit tests prevent regressions as we fix technical debt
5. Polish: Type hints and debt cleanup improve maintainability

The cpp.py refactoring you just completed was the biggest maintainability
blocker. These remaining issues are more focused and incremental
improvements.
