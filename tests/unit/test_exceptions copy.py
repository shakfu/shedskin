"""Unit tests for shedskin.exceptions module.

Tests the exception hierarchy and error handling.
"""

import ast

import pytest

from shedskin.exceptions import (
    BuildError,
    CodeGenerationError,
    CompilationError,
    CompilationFailed,
    InvalidInputError,
    ParseError,
    ShedskinException,
    TypeInferenceError,
    UnsupportedFeatureError,
)


class TestExceptionHierarchy:
    """Tests for exception class hierarchy."""

    def test_base_exception(self):
        """Test ShedskinException is base of all Shedskin exceptions."""
        exc = ShedskinException("test error")
        assert isinstance(exc, Exception)
        assert str(exc) == "test error"

    def test_compilation_error_is_shedskin_exception(self):
        """Test CompilationError inherits from ShedskinException."""
        exc = CompilationError("compilation error")
        assert isinstance(exc, ShedskinException)
        assert isinstance(exc, Exception)

    def test_parse_error_hierarchy(self):
        """Test ParseError inherits correctly."""
        exc = ParseError("parse error")
        assert isinstance(exc, CompilationError)
        assert isinstance(exc, ShedskinException)
        assert isinstance(exc, Exception)

    def test_type_inference_error_hierarchy(self):
        """Test TypeInferenceError inherits correctly."""
        exc = TypeInferenceError("type error")
        assert isinstance(exc, CompilationError)
        assert isinstance(exc, ShedskinException)

    def test_code_generation_error_hierarchy(self):
        """Test CodeGenerationError inherits correctly."""
        exc = CodeGenerationError("codegen error")
        assert isinstance(exc, CompilationError)
        assert isinstance(exc, ShedskinException)

    def test_unsupported_feature_error_hierarchy(self):
        """Test UnsupportedFeatureError inherits correctly."""
        exc = UnsupportedFeatureError("unsupported")
        assert isinstance(exc, CompilationError)
        assert isinstance(exc, ShedskinException)

    def test_invalid_input_error_hierarchy(self):
        """Test InvalidInputError inherits correctly."""
        exc = InvalidInputError("invalid input")
        assert isinstance(exc, ShedskinException)
        assert not isinstance(exc, CompilationError)

    def test_build_error_hierarchy(self):
        """Test BuildError inherits correctly."""
        exc = BuildError("build failed")
        assert isinstance(exc, ShedskinException)
        assert not isinstance(exc, CompilationError)

    def test_compilation_failed_hierarchy(self):
        """Test CompilationFailed inherits correctly."""
        errors = [ParseError("error 1")]
        exc = CompilationFailed(errors)
        assert isinstance(exc, ShedskinException)
        assert not isinstance(exc, CompilationError)


class TestCompilationError:
    """Tests for CompilationError class."""

    def test_simple_message(self):
        """Test CompilationError with simple message."""
        exc = CompilationError("test error")
        assert exc.message == "test error"
        assert str(exc) == "test error"
        assert exc.node is None

    def test_with_ast_node(self):
        """Test CompilationError with AST node."""
        node = ast.parse("x = 1").body[0]
        exc = CompilationError("test error", node=node)
        assert exc.message == "test error"
        assert exc.node is node
        assert isinstance(exc.node, ast.Assign)

    def test_message_attribute(self):
        """Test that message attribute is accessible."""
        exc = CompilationError("error message")
        assert hasattr(exc, "message")
        assert exc.message == "error message"

    def test_node_attribute(self):
        """Test that node attribute is accessible."""
        exc = CompilationError("error")
        assert hasattr(exc, "node")
        assert exc.node is None


class TestParseError:
    """Tests for ParseError class."""

    def test_simple_parse_error(self):
        """Test ParseError with simple message."""
        exc = ParseError("syntax error")
        assert exc.message == "syntax error"
        assert str(exc) == "syntax error"

    def test_parse_error_with_node(self):
        """Test ParseError with AST node."""
        node = ast.parse("def f(): pass").body[0]
        exc = ParseError("invalid syntax", node=node)
        assert exc.message == "invalid syntax"
        assert exc.node is node

    def test_parse_error_formatting(self):
        """Test ParseError message formatting."""
        exc = ParseError("expected ':', got 'EOF'")
        assert "expected ':'" in str(exc)
        assert "got 'EOF'" in str(exc)


class TestTypeInferenceError:
    """Tests for TypeInferenceError class."""

    def test_simple_type_error(self):
        """Test TypeInferenceError with simple message."""
        exc = TypeInferenceError("cannot infer type")
        assert exc.message == "cannot infer type"

    def test_type_error_with_node(self):
        """Test TypeInferenceError with AST node."""
        node = ast.parse("x + y").body[0].value
        exc = TypeInferenceError("incompatible types", node=node)
        assert exc.message == "incompatible types"
        assert exc.node is node


class TestCodeGenerationError:
    """Tests for CodeGenerationError class."""

    def test_simple_codegen_error(self):
        """Test CodeGenerationError with simple message."""
        exc = CodeGenerationError("cannot generate C++")
        assert exc.message == "cannot generate C++"

    def test_codegen_error_with_node(self):
        """Test CodeGenerationError with AST node."""
        node = ast.parse("async def f(): pass").body[0]
        exc = CodeGenerationError("async not supported", node=node)
        assert exc.message == "async not supported"
        assert exc.node is node


class TestUnsupportedFeatureError:
    """Tests for UnsupportedFeatureError class."""

    def test_unsupported_feature(self):
        """Test UnsupportedFeatureError with feature description."""
        exc = UnsupportedFeatureError("metaclasses not supported")
        assert exc.message == "metaclasses not supported"

    def test_unsupported_with_node(self):
        """Test UnsupportedFeatureError with AST node."""
        code = "class Meta(type): pass"
        node = ast.parse(code).body[0]
        exc = UnsupportedFeatureError("metaclasses", node=node)
        assert exc.node is node


class TestInvalidInputError:
    """Tests for InvalidInputError class."""

    def test_simple_invalid_input(self):
        """Test InvalidInputError with simple message."""
        exc = InvalidInputError("file not found")
        assert str(exc) == "file not found"

    def test_invalid_input_no_node(self):
        """Test InvalidInputError doesn't have node attribute."""
        exc = InvalidInputError("invalid argument")
        assert not hasattr(exc, "node")

    def test_path_validation_error(self):
        """Test InvalidInputError for path validation."""
        exc = InvalidInputError("Path traversal detected: ../../../etc")
        assert "Path traversal" in str(exc)
        assert "../../../etc" in str(exc)


class TestBuildError:
    """Tests for BuildError class."""

    def test_simple_build_error(self):
        """Test BuildError with simple message."""
        exc = BuildError("cmake failed")
        assert str(exc) == "cmake failed"
        assert exc.returncode is None

    def test_build_error_with_returncode(self):
        """Test BuildError with return code."""
        exc = BuildError("make failed", returncode=2)
        assert str(exc) == "make failed"
        assert exc.returncode == 2

    def test_returncode_attribute(self):
        """Test that returncode attribute is accessible."""
        exc = BuildError("build failed", returncode=1)
        assert hasattr(exc, "returncode")
        assert exc.returncode == 1

    def test_zero_returncode(self):
        """Test BuildError with zero return code."""
        exc = BuildError("process completed", returncode=0)
        assert exc.returncode == 0


class TestCompilationFailed:
    """Tests for CompilationFailed class."""

    def test_single_error(self):
        """Test CompilationFailed with single error."""
        error = ParseError("syntax error")
        exc = CompilationFailed([error])

        assert exc.errors == [error]
        assert "Compilation failed with 1 error(s)" in str(exc)
        assert "syntax error" in str(exc)

    def test_multiple_errors(self):
        """Test CompilationFailed with multiple errors."""
        errors = [
            ParseError("syntax error at line 1"),
            TypeInferenceError("type mismatch at line 5"),
            CodeGenerationError("cannot generate code")
        ]
        exc = CompilationFailed(errors)

        assert exc.errors == errors
        assert len(exc.errors) == 3
        assert "Compilation failed with 3 error(s)" in str(exc)
        assert "syntax error" in str(exc)
        assert "type mismatch" in str(exc)
        assert "cannot generate" in str(exc)

    def test_errors_attribute(self):
        """Test that errors attribute is accessible."""
        errors = [ParseError("error")]
        exc = CompilationFailed(errors)
        assert hasattr(exc, "errors")
        assert isinstance(exc.errors, list)

    def test_error_message_formatting(self):
        """Test error message formatting."""
        errors = [
            ParseError("error 1"),
            ParseError("error 2")
        ]
        exc = CompilationFailed(errors)
        message = str(exc)

        assert "Compilation failed with 2 error(s)" in message
        assert "error 1" in message
        assert "error 2" in message
        # Check formatting
        assert "  - " in message  # Bullet points


class TestExceptionCatching:
    """Tests for catching exceptions in try/except blocks."""

    def test_catch_shedskin_exception(self):
        """Test catching ShedskinException catches all Shedskin exceptions."""
        exceptions = [
            CompilationError("test"),
            ParseError("test"),
            TypeInferenceError("test"),
            CodeGenerationError("test"),
            UnsupportedFeatureError("test"),
            InvalidInputError("test"),
            BuildError("test"),
            CompilationFailed([ParseError("test")])
        ]

        for exc in exceptions:
            try:
                raise exc
            except ShedskinException as e:
                assert isinstance(e, ShedskinException)
            else:
                pytest.fail(f"Failed to catch {type(exc).__name__}")

    def test_catch_compilation_error(self):
        """Test catching CompilationError catches all compilation errors."""
        exceptions = [
            ParseError("test"),
            TypeInferenceError("test"),
            CodeGenerationError("test"),
            UnsupportedFeatureError("test")
        ]

        for exc in exceptions:
            try:
                raise exc
            except CompilationError as e:
                assert isinstance(e, CompilationError)
            else:
                pytest.fail(f"Failed to catch {type(exc).__name__}")

    def test_catch_specific_error(self):
        """Test catching specific error types."""
        try:
            raise ParseError("syntax error")
        except ParseError as e:
            assert isinstance(e, ParseError)
            assert e.message == "syntax error"
        else:
            pytest.fail("Failed to catch ParseError")

    def test_catch_with_multiple_handlers(self):
        """Test multiple exception handlers."""
        def raise_error(error_type):
            if error_type == "parse":
                raise ParseError("parse error")
            elif error_type == "type":
                raise TypeInferenceError("type error")
            else:
                raise InvalidInputError("input error")

        # Catch ParseError specifically
        try:
            raise_error("parse")
        except ParseError as e:
            assert "parse error" in str(e)

        # Catch TypeInferenceError specifically
        try:
            raise_error("type")
        except TypeInferenceError as e:
            assert "type error" in str(e)

        # Catch InvalidInputError specifically
        try:
            raise_error("input")
        except InvalidInputError as e:
            assert "input error" in str(e)


class TestExceptionReraising:
    """Tests for re-raising exceptions with context."""

    def test_reraise_with_context(self):
        """Test re-raising exception with additional context."""
        try:
            try:
                raise ParseError("original error")
            except ParseError:
                # Could add context here
                raise
        except ParseError as e:
            assert "original error" in str(e)

    def test_chain_exceptions(self):
        """Test chaining exceptions with 'from'."""
        try:
            try:
                raise ParseError("parse failed")
            except ParseError as e:
                raise CompilationFailed([e]) from e
        except CompilationFailed as e:
            assert len(e.errors) == 1
            assert isinstance(e.errors[0], ParseError)


class TestExceptionUseCases:
    """Tests for real-world exception use cases."""

    def test_file_not_found_scenario(self):
        """Test InvalidInputError for missing files."""
        exc = InvalidInputError("no such file: 'program.py'")
        assert "no such file" in str(exc)
        assert "program.py" in str(exc)

    def test_syntax_error_scenario(self):
        """Test ParseError for syntax errors."""
        exc = ParseError("program.py:5: invalid syntax")
        assert "program.py:5" in str(exc)
        assert "invalid syntax" in str(exc)

    def test_type_mismatch_scenario(self):
        """Test TypeInferenceError for type mismatches."""
        exc = TypeInferenceError("cannot add 'str' and 'int'")
        assert "cannot add" in str(exc)
        assert "'str'" in str(exc)
        assert "'int'" in str(exc)

    def test_unsupported_async_scenario(self):
        """Test UnsupportedFeatureError for async/await."""
        exc = UnsupportedFeatureError("async/await not supported")
        assert "async/await" in str(exc)

    def test_cmake_failure_scenario(self):
        """Test BuildError for CMake failures."""
        exc = BuildError("cmake configuration failed", returncode=1)
        assert "cmake" in str(exc)
        assert exc.returncode == 1

    def test_multiple_compilation_errors_scenario(self):
        """Test CompilationFailed for multiple errors."""
        errors = [
            ParseError("file1.py:10: syntax error"),
            TypeInferenceError("file1.py:20: type mismatch"),
            UnsupportedFeatureError("file2.py:5: feature not supported")
        ]
        exc = CompilationFailed(errors)

        assert len(exc.errors) == 3
        message = str(exc)
        assert "3 error(s)" in message
        assert "file1.py:10" in message
        assert "file1.py:20" in message
        assert "file2.py:5" in message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
