"""Shedskin exception hierarchy.

This module defines a structured exception hierarchy for Shedskin compilation errors,
replacing hard sys.exit() calls with proper exception handling.
"""

from typing import Optional, List
import ast


class ShedskinException(Exception):
    """Base exception for all Shedskin errors."""
    pass


class CompilationError(ShedskinException):
    """Base class for all compilation errors."""

    def __init__(self, message: str, node: Optional[ast.AST] = None):
        self.message = message
        self.node = node
        super().__init__(message)


class ParseError(CompilationError):
    """Error during Python AST parsing."""
    pass


class TypeInferenceError(CompilationError):
    """Error during type inference."""
    pass


class CodeGenerationError(CompilationError):
    """Error during C++ code generation."""
    pass


class UnsupportedFeatureError(CompilationError):
    """Python feature not supported by Shedskin."""
    pass


class InvalidInputError(ShedskinException):
    """Invalid input provided to Shedskin."""
    pass


class BuildError(ShedskinException):
    """Error during build process (CMake, Make, etc.)."""

    def __init__(self, message: str, returncode: Optional[int] = None):
        self.returncode = returncode
        super().__init__(message)


class CompilationFailed(ShedskinException):
    """Compilation failed with one or more errors."""

    def __init__(self, errors: List[CompilationError]):
        self.errors = errors
        message = f"Compilation failed with {len(errors)} error(s):\n"
        message += "\n".join(f"  - {error.message}" for error in errors)
        super().__init__(message)
