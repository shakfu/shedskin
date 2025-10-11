"""Unit tests for shedskin.error module."""

import argparse
import ast
import logging
from unittest import mock

import pytest

from shedskin import error
from shedskin.config import GlobalInfo
from shedskin.exceptions import CompilationError


class TestErrorFunction:
    """Test the error() function."""

    def setup_method(self):
        """Clear ERRORS set before each test."""
        error.ERRORS.clear()

    def test_error_with_warning_does_not_raise(self):
        """Test that warnings don't raise exceptions."""
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Should not raise
        error.error("test warning", gx, warning=True)

        # Should be in ERRORS set
        assert len(error.ERRORS) == 1

    def test_error_without_warning_raises_compilation_error(self):
        """Test that errors raise CompilationError."""
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        with pytest.raises(CompilationError) as exc_info:
            error.error("test error", gx, warning=False)

        assert "test error" in str(exc_info.value)

    def test_error_adds_to_errors_set(self):
        """Test that errors are added to ERRORS set."""
        error.ERRORS.clear()
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Add a warning (doesn't raise)
        error.error("warning 1", gx, warning=True)
        assert len(error.ERRORS) == 1

        # Add another warning
        error.error("warning 2", gx, warning=True)
        assert len(error.ERRORS) == 2

    def test_error_deduplication(self):
        """Test that duplicate errors are not added twice."""
        error.ERRORS.clear()
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Add same warning twice
        error.error("duplicate warning", gx, warning=True)
        error.error("duplicate warning", gx, warning=True)

        # Should only be added once
        assert len(error.ERRORS) == 1

    def test_error_with_ast_node_with_lineno(self):
        """Test error extraction with AST node that has lineno."""
        error.ERRORS.clear()
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Create AST node with lineno
        node = ast.parse("x = 1").body[0]
        assert hasattr(node, 'lineno')

        # Mock module visitor
        mock_module = mock.Mock()
        mock_module.relative_filename = "test.py"
        mock_mv = mock.Mock()
        mock_mv.module = mock_module

        error.error("test with node", gx, node=node, warning=True, mv=mock_mv)

        # Check that error was recorded with lineno
        assert len(error.ERRORS) == 1
        err = list(error.ERRORS)[0]
        assert err[1] == "test.py"  # filename
        assert err[2] == 1  # lineno
        assert err[3] == "test with node"  # message

    def test_error_with_ast_node_without_lineno(self):
        """Test error extraction with AST node without lineno."""
        error.ERRORS.clear()
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Create AST node without lineno (e.g., Name node)
        node = ast.Name(id='x', ctx=ast.Load())

        # Mock module visitor
        mock_module = mock.Mock()
        mock_module.relative_filename = "test.py"
        mock_mv = mock.Mock()
        mock_mv.module = mock_module

        error.error("test without lineno", gx, node=node, warning=True, mv=mock_mv)

        # Check that error was recorded without lineno
        assert len(error.ERRORS) == 1
        err = list(error.ERRORS)[0]
        assert err[1] == "test.py"  # filename
        assert err[2] is None  # no lineno
        assert err[3] == "test without lineno"  # message

    def test_error_without_node_or_mv(self):
        """Test error without node or module visitor."""
        error.ERRORS.clear()
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        error.error("generic error", gx, warning=True)

        # Should still be recorded
        assert len(error.ERRORS) == 1
        err = list(error.ERRORS)[0]
        assert err[1] == ""  # no filename
        assert err[2] is None  # no lineno
        assert err[3] == "generic error"

    def test_error_raises_with_ast_node(self):
        """Test that CompilationError includes AST node."""
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        node = ast.parse("x = 1").body[0]

        with pytest.raises(CompilationError) as exc_info:
            error.error("test error with node", gx, node=node, warning=False)

        # Exception should have the node
        assert exc_info.value.node is node

    def test_error_raises_without_ast_node_for_variable(self):
        """Test that CompilationError works with non-AST node (e.g., Variable)."""
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Mock a Variable object (not an AST node)
        mock_var = mock.Mock()
        mock_var.__class__.__name__ = 'Variable'

        with pytest.raises(CompilationError) as exc_info:
            error.error("test error with variable", gx, node=mock_var, warning=False)

        # Exception should have None for node (since it's not AST)
        assert exc_info.value.node is None

    def test_error_log_level_warning(self):
        """Test that warnings use WARNING log level."""
        error.ERRORS.clear()
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        error.error("test warning", gx, warning=True)

        err = list(error.ERRORS)[0]
        assert err[0] == logging.WARNING

    def test_error_log_level_error(self):
        """Test that errors use ERROR log level."""
        error.ERRORS.clear()
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        try:
            error.error("test error", gx, warning=False)
        except CompilationError:
            pass

        err = list(error.ERRORS)[0]
        assert err[0] == logging.ERROR


class TestPrintError:
    """Test the print_error() function."""

    def test_print_error_with_filename_and_lineno(self, caplog):
        """Test printing error with filename and line number."""
        err = (logging.ERROR, "test.py", 42, "test message")

        with caplog.at_level(logging.ERROR):
            error.print_error(err)

        assert "test.py:42: test message" in caplog.text

    def test_print_error_with_filename_without_lineno(self, caplog):
        """Test printing error with filename but no line number."""
        err = (logging.ERROR, "test.py", None, "test message")

        with caplog.at_level(logging.ERROR):
            error.print_error(err)

        assert "test.py: test message" in caplog.text

    def test_print_error_without_filename(self, caplog):
        """Test printing error without filename."""
        err = (logging.ERROR, "", None, "test message")

        with caplog.at_level(logging.ERROR):
            error.print_error(err)

        assert "test message" in caplog.text
        # Should not have "filename:lineno:" prefix before the message
        # (logging framework adds its own "module:file.py:line" format)
        # Check that message doesn't start with a file path pattern
        for record in caplog.records:
            if "test message" in record.message:
                # Message should just be "test message", not "file.py:42: test message"
                assert record.message == "test message"

    def test_print_error_warning_level(self, caplog):
        """Test printing warning with WARNING log level."""
        err = (logging.WARNING, "test.py", 10, "warning message")

        with caplog.at_level(logging.WARNING):
            error.print_error(err)

        assert "warning message" in caplog.text


class TestPrintErrors:
    """Test the print_errors() function."""

    def setup_method(self):
        """Clear ERRORS set before each test."""
        error.ERRORS.clear()

    def test_print_errors_empty(self, caplog):
        """Test printing when ERRORS is empty."""
        with caplog.at_level(logging.ERROR):
            error.print_errors()

        # Should not print anything
        assert len(caplog.records) == 0

    def test_print_errors_single(self, caplog):
        """Test printing single error."""
        error.ERRORS.add((logging.ERROR, "test.py", 1, "error message"))

        with caplog.at_level(logging.ERROR):
            error.print_errors()

        assert "test.py:1: error message" in caplog.text

    def test_print_errors_multiple_sorted_by_filename(self, caplog):
        """Test that errors are sorted by filename."""
        error.ERRORS.add((logging.ERROR, "b.py", 1, "error in b"))
        error.ERRORS.add((logging.ERROR, "a.py", 1, "error in a"))
        error.ERRORS.add((logging.ERROR, "c.py", 1, "error in c"))

        with caplog.at_level(logging.ERROR):
            error.print_errors()

        # Extract the order from log output
        records = [r.message for r in caplog.records]
        assert len(records) == 3
        assert "a.py" in records[0]
        assert "b.py" in records[1]
        assert "c.py" in records[2]

    def test_print_errors_multiple_sorted_by_lineno(self, caplog):
        """Test that errors in same file are sorted by line number."""
        error.ERRORS.add((logging.ERROR, "test.py", 30, "error at line 30"))
        error.ERRORS.add((logging.ERROR, "test.py", 10, "error at line 10"))
        error.ERRORS.add((logging.ERROR, "test.py", 20, "error at line 20"))

        with caplog.at_level(logging.ERROR):
            error.print_errors()

        # Extract the order from log output
        records = [r.message for r in caplog.records]
        assert len(records) == 3
        assert "line 10" in records[0]
        assert "line 20" in records[1]
        assert "line 30" in records[2]

    def test_print_errors_handles_none_lineno(self, caplog):
        """Test that None lineno is handled in sorting."""
        error.ERRORS.add((logging.ERROR, "test.py", None, "error without lineno"))
        error.ERRORS.add((logging.ERROR, "test.py", 10, "error at line 10"))

        with caplog.at_level(logging.ERROR):
            error.print_errors()

        # Error without lineno should sort before line 10 (None treated as -1)
        records = [r.message for r in caplog.records]
        assert len(records) == 2
        assert "without lineno" in records[0]
        assert "line 10" in records[1]

    def test_print_errors_handles_empty_filename(self, caplog):
        """Test that empty filename is handled in sorting."""
        error.ERRORS.add((logging.ERROR, "", None, "error without file"))
        error.ERRORS.add((logging.ERROR, "test.py", 1, "error in file"))

        with caplog.at_level(logging.ERROR):
            error.print_errors()

        # Error without filename should sort before named file
        records = [r.message for r in caplog.records]
        assert len(records) == 2
        assert "without file" in records[0]
        assert "error in file" in records[1]


class TestErrorsSet:
    """Test ERRORS module-level set."""

    def setup_method(self):
        """Clear ERRORS set before each test."""
        error.ERRORS.clear()

    def test_errors_set_initially_empty(self):
        """Test that ERRORS set starts empty."""
        assert len(error.ERRORS) == 0
        assert isinstance(error.ERRORS, set)

    def test_errors_set_can_be_cleared(self):
        """Test that ERRORS set can be cleared."""
        error.ERRORS.add((logging.ERROR, "test.py", 1, "test"))
        assert len(error.ERRORS) > 0

        error.ERRORS.clear()
        assert len(error.ERRORS) == 0

    def test_errors_set_stores_tuples(self):
        """Test that ERRORS stores Error tuples."""
        err = (logging.ERROR, "test.py", 1, "test message")
        error.ERRORS.add(err)

        assert err in error.ERRORS
        stored_err = list(error.ERRORS)[0]
        assert stored_err[0] == logging.ERROR
        assert stored_err[1] == "test.py"
        assert stored_err[2] == 1
        assert stored_err[3] == "test message"


class TestIntegration:
    """Integration tests for error module."""

    def setup_method(self):
        """Clear ERRORS set before each test."""
        error.ERRORS.clear()

    def test_full_error_workflow_with_warnings(self, caplog):
        """Test complete workflow with warnings."""
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Create mock module visitor
        mock_module = mock.Mock()
        mock_module.relative_filename = "example.py"
        mock_mv = mock.Mock()
        mock_mv.module = mock_module

        # Create AST node
        node = ast.parse("x = 1 + 2").body[0]

        # Add multiple warnings
        error.error("first warning", gx, node=node, warning=True, mv=mock_mv)
        error.error("second warning", gx, node=node, warning=True, mv=mock_mv)

        assert len(error.ERRORS) == 2

        # Print all errors
        with caplog.at_level(logging.WARNING):
            error.print_errors()

        assert "first warning" in caplog.text
        assert "second warning" in caplog.text

    def test_full_error_workflow_with_errors(self):
        """Test complete workflow with errors."""
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Create mock module visitor
        mock_module = mock.Mock()
        mock_module.relative_filename = "example.py"
        mock_mv = mock.Mock()
        mock_mv.module = mock_module

        # Create AST node
        node = ast.parse("x = 1").body[0]

        # First error should raise
        with pytest.raises(CompilationError) as exc_info:
            error.error("fatal error", gx, node=node, warning=False, mv=mock_mv)

        assert "fatal error" in str(exc_info.value)
        assert len(error.ERRORS) == 1

    def test_mixed_warnings_and_errors(self, caplog):
        """Test workflow with both warnings and errors."""
        error.ERRORS.clear()
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Add warnings first
        error.error("warning 1", gx, warning=True)
        error.error("warning 2", gx, warning=True)

        assert len(error.ERRORS) == 2

        # Try to add error (will raise)
        with pytest.raises(CompilationError):
            error.error("fatal error", gx, warning=False)

        # All three should be in ERRORS
        assert len(error.ERRORS) == 3

        # Print all
        with caplog.at_level(logging.WARNING):
            error.print_errors()

        assert "warning 1" in caplog.text
        assert "warning 2" in caplog.text
        assert "fatal error" in caplog.text
