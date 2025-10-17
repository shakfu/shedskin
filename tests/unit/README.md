# Shedskin Unit Tests

This directory contains **unit tests** for Shedskin compiler modules, separate from the integration tests in `tests/`.

## Purpose

While `tests/` contains **integration tests** (compile Python → C++ → run), this directory contains **unit tests** that test individual compiler components in isolation.

## Structure

```
unit_tests/
├── __init__.py                  # Package init
├── conftest.py                  # Pytest configuration
├── README.md                    # This file
├── test_path_security.py        # Path validation tests (52 tests)
├── test_exceptions.py           # Exception hierarchy tests (45 tests)
└── [future test files]          # More unit tests to be added
```

## Running Tests

### Run All Unit Tests
```bash
cd /Users/sa/projects/shedskin
uv run pytest unit_tests/ -v
```

### Run Specific Test File
```bash
uv run pytest unit_tests/test_path_security.py -v
```

### Run Specific Test Class
```bash
uv run pytest unit_tests/test_path_security.py::TestValidateOutputPath -v
```

### Run Specific Test Function
```bash
uv run pytest unit_tests/test_path_security.py::TestValidateOutputPath::test_relative_path_within_base -v
```

### Run with Coverage
```bash
uv run pytest unit_tests/ --cov=shedskin --cov-report=html
```

## Test Files

### test_path_security.py (52 tests)

Tests for `shedskin/path_security.py` module.

**Coverage:**
- `validate_output_path()` - Output directory validation (16 tests)
- `validate_input_file()` - Input file validation (10 tests)
- `validate_directory()` - Directory validation (9 tests)
- `safe_join()` - Safe path joining (8 tests)
- Integration scenarios (6 tests)
- Cross-platform compatibility (3 tests)

**Key Test Areas:**
- Path traversal prevention (`../../../etc`)
- Sensitive directory protection (`/etc`, `/boot`, `/sys`, `/proc`, `/dev`, `/root`)
- Symlink resolution and validation
- Absolute vs relative path handling
- Extension validation
- Directory creation
- Attack scenarios

**Example Tests:**
```python
def test_path_traversal_blocked(self, tmp_path):
    """Test that path traversal attempts are blocked."""
    base = tmp_path / "project"
    base.mkdir()

    with pytest.raises(InvalidInputError, match="Path traversal detected"):
        validate_output_path("../../../etc", base_dir=base, allow_absolute=False)

def test_sensitive_directory_etc_blocked(self):
    """Test that /etc directory writes are blocked."""
    with pytest.raises(InvalidInputError, match="Cannot write to sensitive system directory"):
        validate_output_path("/etc/test", allow_absolute=True)
```

### test_exceptions.py (45 tests)

Tests for `shedskin/exceptions.py` module.

**Coverage:**
- Exception hierarchy (9 tests)
- `CompilationError` and subclasses (15 tests)
- `InvalidInputError` (3 tests)
- `BuildError` (4 tests)
- `CompilationFailed` (4 tests)
- Exception catching patterns (4 tests)
- Exception re-raising (2 tests)
- Real-world use cases (6 tests)

**Key Test Areas:**
- Proper inheritance hierarchy
- Exception attributes (message, node, returncode, errors)
- Try/except catching behavior
- Error message formatting
- Multiple error aggregation

**Example Tests:**
```python
def test_compilation_error_hierarchy(self):
    """Test that all compilation errors inherit correctly."""
    exc = ParseError("syntax error")
    assert isinstance(exc, CompilationError)
    assert isinstance(exc, ShedskinException)
    assert isinstance(exc, Exception)

def test_multiple_errors_scenario(self):
    """Test CompilationFailed for multiple errors."""
    errors = [
        ParseError("file1.py:10: syntax error"),
        TypeInferenceError("file1.py:20: type mismatch"),
    ]
    exc = CompilationFailed(errors)
    assert len(exc.errors) == 2
```

## Test Statistics

| File | Tests | Status | Coverage |
|------|-------|--------|----------|
| test_path_security.py | 52 | ✅ All pass | path_security.py (100%) |
| test_exceptions.py | 45 | ✅ All pass | exceptions.py (100%) |
| **Total** | **97** | **✅ 100%** | **2 modules** |

## Writing New Tests

### Test File Convention

Create a new file following pytest naming convention:
```
unit_tests/test_<module_name>.py
```

### Test Class Convention

Group related tests into classes:
```python
class TestFunctionName:
    """Tests for specific_function()."""

    def test_basic_case(self):
        """Test basic functionality."""
        result = specific_function("input")
        assert result == "expected"

    def test_edge_case(self):
        """Test edge case."""
        with pytest.raises(ValueError):
            specific_function(None)
```

### Test Function Convention

Name test functions descriptively:
```python
def test_<what_is_being_tested>_<expected_outcome>(self):
    """Clear docstring explaining the test."""
    # Arrange
    setup_data = create_test_data()

    # Act
    result = function_under_test(setup_data)

    # Assert
    assert result == expected_value
```

### Using Fixtures

Use pytest fixtures for common setup:
```python
import pytest

@pytest.fixture
def sample_data():
    """Provide sample test data."""
    return {"key": "value"}

def test_with_fixture(sample_data):
    """Test using fixture."""
    assert sample_data["key"] == "value"
```

## Best Practices

### 1. Test One Thing Per Test

**Good:**
```python
def test_validates_required_field(self):
    with pytest.raises(InvalidInputError, match="required"):
        validate_input("")

def test_validates_field_length(self):
    with pytest.raises(InvalidInputError, match="too long"):
        validate_input("x" * 1000)
```

**Bad:**
```python
def test_validation(self):
    # Testing multiple things
    with pytest.raises(InvalidInputError):
        validate_input("")
    with pytest.raises(InvalidInputError):
        validate_input("x" * 1000)
```

### 2. Use Descriptive Names

**Good:**
```python
def test_path_traversal_blocked_with_relative_path(self):
    """Test that ../../../etc is blocked."""
```

**Bad:**
```python
def test_path_validation(self):
    """Test validation."""
```

### 3. Test Both Success and Failure

```python
def test_valid_path_accepted(self):
    """Test that valid paths are accepted."""
    result = validate_path("output")
    assert result.name == "output"

def test_invalid_path_rejected(self):
    """Test that invalid paths are rejected."""
    with pytest.raises(InvalidInputError):
        validate_path("../../../etc")
```

### 4. Use tmp_path for File System Tests

```python
def test_creates_directory(self, tmp_path):
    """Test directory creation."""
    new_dir = tmp_path / "test"
    create_directory(new_dir)
    assert new_dir.exists()
    assert new_dir.is_dir()
```

### 5. Test Edge Cases

```python
def test_empty_input(self):
    """Test with empty input."""
    with pytest.raises(InvalidInputError):
        process("")

def test_null_input(self):
    """Test with None input."""
    with pytest.raises(InvalidInputError):
        process(None)

def test_extremely_long_input(self):
    """Test with very long input."""
    result = process("x" * 10000)
    assert len(result) > 0
```

## Integration with CI/CD

Add to your CI pipeline:

```yaml
# .github/workflows/test.yml
- name: Run unit tests
  run: |
    uv run pytest unit_tests/ -v --cov=shedskin --cov-report=xml

- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
```

## Future Additions

Planned test files:
- `test_cpp_helpers.py` - C++ code generation helpers
- `test_cpp_declarations.py` - Declaration generation
- `test_cpp_expressions.py` - Expression generation
- `test_cpp_statements.py` - Statement generation
- `test_infer.py` - Type inference algorithms
- `test_graph.py` - AST graph analysis
- `test_typestr.py` - Type string formatting
- `test_python.py` - Python AST utilities

## Relationship to Integration Tests

### Unit Tests (this directory)
- **Purpose**: Test individual functions/classes in isolation
- **Scope**: Single module or function
- **Speed**: Very fast (<0.1s per test)
- **Dependencies**: Minimal (no C++ compilation)
- **Example**: "Does `validate_output_path()` block `/etc`?"

### Integration Tests (`tests/`)
- **Purpose**: Test end-to-end compilation
- **Scope**: Full compile → run → verify output
- **Speed**: Slower (~1-5s per test)
- **Dependencies**: C++ compiler, CMake, build tools
- **Example**: "Does the compiled program produce correct output?"

**Both are essential** - unit tests catch bugs early, integration tests verify the whole system works.

## Debugging Failed Tests

### Run with verbose output
```bash
uv run pytest unit_tests/test_path_security.py::test_name -vv
```

### Run with full traceback
```bash
uv run pytest unit_tests/test_path_security.py::test_name --tb=long
```

### Run with pdb on failure
```bash
uv run pytest unit_tests/test_path_security.py::test_name --pdb
```

### Show print statements
```bash
uv run pytest unit_tests/test_path_security.py::test_name -s
```

## Test Coverage Goals

Current coverage:
- ✅ `shedskin/path_security.py` - 100%
- ✅ `shedskin/exceptions.py` - 100%

Target coverage for Phase 2:
- ⏭️ `shedskin/cpp/helpers.py` - 80%+
- ⏭️ `shedskin/cpp/declarations.py` - 80%+
- ⏭️ `shedskin/cpp/expressions.py` - 80%+
- ⏭️ `shedskin/cpp/statements.py` - 80%+
- ⏭️ Core infer.py functions - 70%+
- ⏭️ Core graph.py functions - 70%+

## Contributing

When adding new compiler features:

1. **Write unit tests first** (TDD approach)
2. **Test edge cases** and error conditions
3. **Keep tests fast** (<0.1s each)
4. **Make tests readable** - clear names and docstrings
5. **Isolate tests** - no dependencies between tests
6. **Run tests before committing** - `uv run pytest unit_tests/`

## Questions?

See:
- [pytest documentation](https://docs.pytest.org/)
- [Writing Better Python Tests](https://docs.pytest.org/en/stable/goodpractices.html)
- Main integration tests: `tests/README.md`

---

**Last Updated**: 2025-10-16
**Test Count**: 97 tests
**Status**: ✅ All passing
