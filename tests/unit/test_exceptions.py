"""Unit tests for shedskin.exceptions module."""

import ast

import pytest

from shedskin.exceptions import (
    ShedskinException,
    CompilationError,
    ParseError,
    TypeInferenceError,
    CodeGenerationError,
    UnsupportedFeatureError,
    InvalidInputError,
    BuildError,
    CompilationFailed,
)


class TestShedskinException:
    """Test base ShedskinException class."""

    def test_is_exception(self):
        """Test that ShedskinException is a proper Exception."""
        exc = ShedskinException("test message")
        assert isinstance(exc, Exception)
        assert str(exc) == "test message"

    def test_inheritance(self):
        """Test that all exceptions inherit from ShedskinException."""
        exceptions = [
            CompilationError("test"),
            ParseError("test"),
            TypeInferenceError("test"),
            CodeGenerationError("test"),
            UnsupportedFeatureError("test"),
            InvalidInputError("test"),
            BuildError("test"),
        ]

        for exc in exceptions:
            assert isinstance(exc, ShedskinException)
            assert isinstance(exc, Exception)


class TestCompilationError:
    """Test CompilationError and its subclasses."""

    def test_init_without_node(self):
        """Test CompilationError without AST node."""
        error = CompilationError("syntax error")

        assert error.message == "syntax error"
        assert error.node is None
        assert str(error) == "syntax error"

    def test_init_with_node(self):
        """Test CompilationError with AST node."""
        node = ast.parse("x = 1").body[0]
        error = CompilationError("type mismatch", node)

        assert error.message == "type mismatch"
        assert error.node == node
        assert isinstance(error.node, ast.AST)

    def test_parse_error(self):
        """Test ParseError subclass."""
        node = ast.parse("def foo(): pass").body[0]
        error = ParseError("invalid syntax", node)

        assert isinstance(error, CompilationError)
        assert error.message == "invalid syntax"
        assert error.node == node

    def test_type_inference_error(self):
        """Test TypeInferenceError subclass."""
        error = TypeInferenceError("cannot infer type")

        assert isinstance(error, CompilationError)
        assert "cannot infer type" in str(error)

    def test_code_generation_error(self):
        """Test CodeGenerationError subclass."""
        error = CodeGenerationError("failed to generate C++")

        assert isinstance(error, CompilationError)
        assert "failed to generate C++" in str(error)

    def test_unsupported_feature_error(self):
        """Test UnsupportedFeatureError subclass."""
        node = ast.parse("async def foo(): pass").body[0]
        error = UnsupportedFeatureError("async not supported", node)

        assert isinstance(error, CompilationError)
        assert error.message == "async not supported"


class TestInvalidInputError:
    """Test InvalidInputError."""

    def test_invalid_input_error(self):
        """Test InvalidInputError for bad user input."""
        error = InvalidInputError("invalid file path")

        assert isinstance(error, ShedskinException)
        assert not isinstance(error, CompilationError)
        assert str(error) == "invalid file path"


class TestBuildError:
    """Test BuildError class."""

    def test_build_error_without_returncode(self):
        """Test BuildError without return code."""
        error = BuildError("cmake failed")

        assert isinstance(error, ShedskinException)
        assert error.returncode is None
        assert str(error) == "cmake failed"

    def test_build_error_with_returncode(self):
        """Test BuildError with return code."""
        error = BuildError("build failed", returncode=1)

        assert error.returncode == 1
        assert "build failed" in str(error)

    def test_build_error_not_compilation_error(self):
        """Test that BuildError is not a CompilationError."""
        error = BuildError("test")

        assert isinstance(error, ShedskinException)
        assert not isinstance(error, CompilationError)


class TestCompilationFailed:
    """Test CompilationFailed exception."""

    def test_single_error(self):
        """Test CompilationFailed with single error."""
        error1 = CompilationError("type error")
        failed = CompilationFailed([error1])

        assert len(failed.errors) == 1
        assert failed.errors[0] == error1
        assert "1 error" in str(failed)
        assert "type error" in str(failed)

    def test_multiple_errors(self):
        """Test CompilationFailed with multiple errors."""
        error1 = CompilationError("type error")
        error2 = ParseError("syntax error")
        error3 = CodeGenerationError("codegen failed")

        failed = CompilationFailed([error1, error2, error3])

        assert len(failed.errors) == 3
        assert "3 error" in str(failed)
        assert "type error" in str(failed)
        assert "syntax error" in str(failed)
        assert "codegen failed" in str(failed)

    def test_empty_error_list(self):
        """Test CompilationFailed with empty error list."""
        failed = CompilationFailed([])

        assert len(failed.errors) == 0
        assert "0 error" in str(failed)

    def test_errors_accessible(self):
        """Test that individual errors are accessible."""
        error1 = CompilationError("error 1")
        error2 = CompilationError("error 2")
        failed = CompilationFailed([error1, error2])

        assert failed.errors[0].message == "error 1"
        assert failed.errors[1].message == "error 2"


class TestErrorHierarchy:
    """Test the exception hierarchy structure."""

    def test_compilation_error_hierarchy(self):
        """Test CompilationError subclass hierarchy."""
        # All should inherit from CompilationError
        compilation_errors = [
            ParseError("test"),
            TypeInferenceError("test"),
            CodeGenerationError("test"),
            UnsupportedFeatureError("test"),
        ]

        for error in compilation_errors:
            assert isinstance(error, CompilationError)
            assert isinstance(error, ShedskinException)
            assert isinstance(error, Exception)

    def test_non_compilation_errors(self):
        """Test that some exceptions are not CompilationErrors."""
        non_compilation = [
            InvalidInputError("test"),
            BuildError("test"),
            CompilationFailed([]),
        ]

        for error in non_compilation:
            assert isinstance(error, ShedskinException)
            assert not isinstance(error, CompilationError)

    def test_catchable_by_base_class(self):
        """Test that all exceptions can be caught by base class."""
        exceptions = [
            ParseError("test"),
            BuildError("test"),
            CompilationFailed([]),
        ]

        for exc in exceptions:
            try:
                raise exc
            except ShedskinException:
                pass  # Successfully caught
            else:
                pytest.fail(f"{exc.__class__.__name__} not caught by ShedskinException")


class TestExceptionUsage:
    """Test practical exception usage patterns."""

    def test_raising_and_catching_compilation_error(self):
        """Test raising and catching CompilationError."""
        with pytest.raises(CompilationError) as exc_info:
            raise CompilationError("test error")

        assert exc_info.value.message == "test error"

    def test_raising_specific_error_type(self):
        """Test raising specific error types."""
        with pytest.raises(TypeInferenceError):
            raise TypeInferenceError("cannot infer")

        with pytest.raises(BuildError):
            raise BuildError("build failed")

    def test_catching_by_base_class(self):
        """Test catching specific errors by base class."""
        try:
            raise ParseError("parse failed")
        except CompilationError as e:
            assert "parse failed" in str(e)
        else:
            pytest.fail("Should have caught ParseError as CompilationError")

    def test_error_with_node_location(self):
        """Test that node information is preserved."""
        source = "x = 1\ny = 2"
        tree = ast.parse(source)
        node = tree.body[0]  # First statement

        error = CompilationError("error at x = 1", node)

        assert error.node is not None
        assert hasattr(error.node, 'lineno')
        assert error.node.lineno == 1

    def test_compilation_failed_aggregation(self):
        """Test aggregating multiple errors."""
        errors = []

        # Collect multiple errors
        try:
            raise TypeInferenceError("type error 1")
        except CompilationError as e:
            errors.append(e)

        try:
            raise ParseError("parse error")
        except CompilationError as e:
            errors.append(e)

        # Raise aggregated errors
        with pytest.raises(CompilationFailed) as exc_info:
            raise CompilationFailed(errors)

        assert len(exc_info.value.errors) == 2
        assert any("type error 1" in e.message for e in exc_info.value.errors)
        assert any("parse error" in e.message for e in exc_info.value.errors)
