"""Path security utilities for Shedskin.

This module provides secure path handling to prevent path traversal attacks
and other path-related security vulnerabilities.
"""

import os
from pathlib import Path
from typing import Optional, Union

from .exceptions import InvalidInputError


PathLike = Union[str, Path]


def validate_output_path(
    user_path: PathLike,
    base_dir: Optional[PathLike] = None,
    allow_absolute: bool = False
) -> Path:
    """Validate and normalize an output directory path.

    Args:
        user_path: User-provided path to validate
        base_dir: Expected base directory (defaults to current working directory)
        allow_absolute: Whether to allow absolute paths outside base_dir

    Returns:
        Validated and resolved Path object

    Raises:
        InvalidInputError: If path attempts traversal or is invalid

    Security:
        - Prevents path traversal attacks (../)
        - Validates against expected base directory
        - Resolves symlinks
        - Normalizes path separators

    Examples:
        >>> validate_output_path("output")  # OK
        Path('/current/dir/output')

        >>> validate_output_path("../etc/passwd")  # ERROR
        InvalidInputError: Path traversal detected

        >>> validate_output_path("/tmp/output", allow_absolute=True)  # OK
        Path('/tmp/output')
    """
    if base_dir is None:
        base_dir = Path.cwd()
    else:
        base_dir = Path(base_dir).resolve()

    user_path = Path(user_path)

    # Check for absolute path
    if user_path.is_absolute():
        resolved = user_path.resolve()

        # Check for sensitive system directories (even if allow_absolute is True)
        sensitive_dirs = [
            Path('/etc'),
            Path('/private/etc'),  # macOS resolves /etc to /private/etc
            Path('/boot'),
            Path('/sys'),
            Path('/proc'),
            Path('/dev'),
            Path('/root'),
        ]

        for sensitive in sensitive_dirs:
            try:
                # Check if resolved path is under a sensitive directory
                resolved.relative_to(sensitive)
                raise InvalidInputError(
                    f"Cannot write to sensitive system directory: {resolved}"
                )
            except ValueError:
                # Not under this sensitive directory, continue checking
                pass

        if not allow_absolute:
            raise InvalidInputError(
                f"Absolute path not allowed: {resolved}"
            )

        return resolved

    # For relative paths, resolve against base_dir
    full_path = (base_dir / user_path).resolve()

    # Check for path traversal - ensure resolved path is under base_dir
    # Unless allow_absolute is True, in which case we allow escaping base_dir
    if not allow_absolute:
        try:
            full_path.relative_to(base_dir)
        except ValueError:
            raise InvalidInputError(
                f"Path traversal detected: '{user_path}' resolves outside base directory '{base_dir}'"
            )

    return full_path


def validate_input_file(
    file_path: PathLike,
    must_exist: bool = True,
    allowed_extensions: Optional[list[str]] = None
) -> Path:
    """Validate an input file path.

    Args:
        file_path: Path to input file
        must_exist: Whether file must exist
        allowed_extensions: List of allowed file extensions (e.g., ['.py', '.txt'])

    Returns:
        Validated Path object

    Raises:
        InvalidInputError: If file is invalid or doesn't exist

    Examples:
        >>> validate_input_file("test.py", allowed_extensions=['.py'])
        Path('test.py')

        >>> validate_input_file("../../../etc/passwd")  # ERROR
        InvalidInputError: Path traversal detected
    """
    file_path = Path(file_path).resolve()

    # Check for path traversal to sensitive areas
    sensitive_dirs = [
        Path('/etc'),
        Path('/private/etc'),  # macOS resolves /etc to /private/etc
        Path('/boot'),
        Path('/sys'),
        Path('/proc'),
        Path('/dev'),
    ]

    for sensitive in sensitive_dirs:
        try:
            file_path.relative_to(sensitive)
            raise InvalidInputError(
                f"Cannot read from sensitive system directory: {file_path}"
            )
        except ValueError:
            pass

    # Check existence
    if must_exist and not file_path.exists():
        raise InvalidInputError(f"File not found: {file_path}")

    # Check if it's a file (not directory)
    if must_exist and not file_path.is_file():
        raise InvalidInputError(f"Not a file: {file_path}")

    # Check extension
    if allowed_extensions is not None:
        if file_path.suffix not in allowed_extensions:
            raise InvalidInputError(
                f"Invalid file extension '{file_path.suffix}'. "
                f"Allowed: {', '.join(allowed_extensions)}"
            )

    return file_path


def validate_directory(
    dir_path: PathLike,
    must_exist: bool = False,
    create_if_missing: bool = False
) -> Path:
    """Validate a directory path.

    Args:
        dir_path: Path to directory
        must_exist: Whether directory must exist
        create_if_missing: Whether to create directory if it doesn't exist

    Returns:
        Validated Path object

    Raises:
        InvalidInputError: If directory is invalid

    Examples:
        >>> validate_directory("/tmp/mydir", create_if_missing=True)
        Path('/tmp/mydir')
    """
    dir_path = Path(dir_path).resolve()

    # Check for sensitive system directories
    sensitive_dirs = [
        Path('/etc'),
        Path('/private/etc'),  # macOS resolves /etc to /private/etc
        Path('/boot'),
        Path('/sys'),
        Path('/proc'),
        Path('/dev'),
        Path('/root'),
    ]

    for sensitive in sensitive_dirs:
        try:
            dir_path.relative_to(sensitive)
            raise InvalidInputError(
                f"Cannot use sensitive system directory: {dir_path}"
            )
        except ValueError:
            pass

    # Check existence
    if dir_path.exists():
        if not dir_path.is_dir():
            raise InvalidInputError(f"Not a directory: {dir_path}")
    elif must_exist:
        raise InvalidInputError(f"Directory not found: {dir_path}")
    elif create_if_missing:
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise InvalidInputError(f"Cannot create directory '{dir_path}': {e}")

    return dir_path


def safe_join(base: PathLike, *parts: str) -> Path:
    """Safely join path components, preventing traversal attacks.

    Args:
        base: Base directory path
        *parts: Path components to join

    Returns:
        Joined and validated Path

    Raises:
        InvalidInputError: If result would escape base directory

    Examples:
        >>> safe_join("/tmp", "output", "file.txt")
        Path('/tmp/output/file.txt')

        >>> safe_join("/tmp", "../etc/passwd")  # ERROR
        InvalidInputError: Path traversal detected
    """
    base = Path(base).resolve()
    result = base.joinpath(*parts).resolve()

    try:
        result.relative_to(base)
    except ValueError:
        raise InvalidInputError(
            f"Path traversal detected: {'/'.join(parts)} escapes base directory {base}"
        )

    return result
