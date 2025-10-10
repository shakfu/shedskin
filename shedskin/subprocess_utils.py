"""Safe subprocess utilities to replace os.system() calls.

This module provides secure subprocess execution functions that prevent
command injection vulnerabilities.
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Union

PathLike = Union[str, Path]


class SubprocessError(Exception):
    """Exception raised when subprocess execution fails."""

    def __init__(self, cmd: Union[str, List[str]], returncode: int, stderr: Optional[str] = None):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr

        if isinstance(cmd, list):
            cmd_str = ' '.join(str(c) for c in cmd)
        else:
            cmd_str = str(cmd)

        msg = f"Command failed with exit code {returncode}: {cmd_str}"
        if stderr:
            msg += f"\nStderr: {stderr}"
        super().__init__(msg)


def run_command(
    cmd: Union[str, List[str]],
    shell: bool = False,
    check: bool = True,
    cwd: Optional[PathLike] = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command safely using subprocess.run().

    Args:
        cmd: Command to run. If a list, will be executed directly.
             If a string and shell=True, will be executed via shell.
        shell: Whether to run command through shell (use sparingly).
        check: Whether to raise exception on non-zero exit code.
        cwd: Working directory for command execution.
        capture_output: Whether to capture stdout/stderr.

    Returns:
        CompletedProcess instance.

    Raises:
        SubprocessError: If check=True and command fails.

    Security Note:
        Prefer passing cmd as a list without shell=True when possible.
        Only use shell=True when you need shell features like pipes or
        environment variable expansion, and ensure cmd is trusted.
    """
    try:
        result = subprocess.run(
            cmd,
            shell=shell,
            check=False,  # We'll handle checking ourselves
            cwd=cwd,
            capture_output=capture_output,
            text=True if capture_output else False,
        )

        if check and result.returncode != 0:
            stderr = result.stderr if capture_output else None
            raise SubprocessError(cmd, result.returncode, stderr)

        return result

    except FileNotFoundError as e:
        if check:
            raise SubprocessError(cmd, -1, str(e)) from e
        raise


def run_executable(executable: PathLike, check: bool = True) -> int:
    """Run an executable file safely.

    Args:
        executable: Path to the executable to run.
        check: Whether to raise exception on non-zero exit code.

    Returns:
        Exit code of the executable.

    Raises:
        SubprocessError: If check=True and executable fails.
    """
    executable = Path(executable)

    if not executable.exists():
        if check:
            raise SubprocessError(str(executable), -1, "Executable not found")
        return -1

    result = run_command([str(executable)], shell=False, check=check)
    return result.returncode


def run_shell_command(
    cmd: str,
    check: bool = True,
    cwd: Optional[PathLike] = None,
) -> int:
    """Run a shell command safely.

    WARNING: This function executes commands through the shell, which can
    be a security risk if cmd contains untrusted input. Prefer run_command()
    with a list of arguments when possible.

    Args:
        cmd: Shell command to run.
        check: Whether to raise exception on non-zero exit code.
        cwd: Working directory for command execution.

    Returns:
        Exit code of the command.

    Raises:
        SubprocessError: If check=True and command fails.
    """
    result = run_command(cmd, shell=True, check=check, cwd=cwd)
    return result.returncode


def enable_windows_color_output() -> None:
    """Enable color output for Windows command prompt.

    This is a Windows-specific hack that enables ANSI color codes.
    On Windows 10+, this initializes the console to handle ANSI sequences.
    """
    if sys.platform == 'win32':
        # The old hack was to run os.system("") to initialize the console
        # A more modern approach is to use ctypes or colorama
        try:
            # Try modern approach first (Windows 10+)
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            # Fallback to old hack for older Windows versions
            subprocess.run("", shell=True, check=False)


def assert_command_success(
    cmd: Union[str, List[str]],
    shell: bool = False,
    cwd: Optional[PathLike] = None,
) -> None:
    """Run command and assert it succeeds (exit code 0).

    This is a convenience function for cases where code uses:
        assert os.system(cmd) == 0

    Args:
        cmd: Command to run.
        shell: Whether to run through shell.
        cwd: Working directory.

    Raises:
        SubprocessError: If command returns non-zero exit code.
    """
    run_command(cmd, shell=shell, check=True, cwd=cwd)
