"""Unit tests for shedskin.subprocess_utils module."""

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from shedskin.subprocess_utils import (
    SubprocessError,
    run_command,
    run_executable,
    run_shell_command,
    enable_windows_color_output,
    assert_command_success,
)


class TestSubprocessError:
    """Test SubprocessError exception class."""

    def test_init_with_list_command(self):
        """Test SubprocessError initialization with list command."""
        cmd = ["echo", "hello"]
        error = SubprocessError(cmd, 1, "error message")

        assert error.returncode == 1
        assert error.stderr == "error message"
        assert "echo hello" in str(error)
        assert "exit code 1" in str(error)

    def test_init_with_string_command(self):
        """Test SubprocessError initialization with string command."""
        cmd = "echo hello"
        error = SubprocessError(cmd, 127)

        assert error.returncode == 127
        assert error.stderr is None
        assert cmd in str(error)

    def test_init_with_stderr(self):
        """Test SubprocessError includes stderr in message."""
        error = SubprocessError("test", 1, "stderr output")

        assert "stderr output" in str(error)


class TestRunCommand:
    """Test run_command function."""

    def test_successful_command_list(self):
        """Test running a successful command as list."""
        result = run_command(["echo", "test"], capture_output=True)

        assert result.returncode == 0
        assert "test" in result.stdout

    def test_successful_command_shell(self):
        """Test running a successful shell command."""
        result = run_command("echo test", shell=True, capture_output=True)

        assert result.returncode == 0
        assert "test" in result.stdout

    def test_failed_command_with_check(self):
        """Test that failed command raises SubprocessError when check=True."""
        with pytest.raises(SubprocessError) as exc_info:
            run_command(["false"], check=True)

        assert exc_info.value.returncode != 0

    def test_failed_command_without_check(self):
        """Test that failed command returns result when check=False."""
        result = run_command(["false"], check=False)

        assert result.returncode != 0

    def test_command_with_cwd(self, tmp_path):
        """Test running command in specific directory."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        if sys.platform == 'win32':
            cmd = ["cmd", "/c", "dir"]
        else:
            cmd = ["ls"]

        result = run_command(cmd, cwd=tmp_path, capture_output=True)
        assert result.returncode == 0

    def test_command_not_found(self):
        """Test FileNotFoundError for non-existent command."""
        with pytest.raises((SubprocessError, FileNotFoundError)):
            run_command(["nonexistent_command_xyz"], check=True)

    def test_capture_output(self):
        """Test capturing command output."""
        result = run_command(
            ["echo", "captured"],
            capture_output=True
        )

        assert "captured" in result.stdout
        assert result.stderr is not None  # Should be empty string


class TestRunExecutable:
    """Test run_executable function."""

    def test_executable_not_found_with_check(self, tmp_path):
        """Test running non-existent executable with check=True."""
        nonexistent = tmp_path / "nonexistent"

        with pytest.raises(SubprocessError) as exc_info:
            run_executable(nonexistent, check=True)

        assert "not found" in str(exc_info.value).lower()

    def test_executable_not_found_without_check(self, tmp_path):
        """Test running non-existent executable with check=False."""
        nonexistent = tmp_path / "nonexistent"

        returncode = run_executable(nonexistent, check=False)

        assert returncode == -1

    @pytest.mark.skipif(sys.platform == 'win32', reason="Unix-specific test")
    def test_executable_success(self, tmp_path):
        """Test running a successful executable."""
        # Create a simple shell script
        script = tmp_path / "test_script.sh"
        script.write_text("#!/bin/sh\necho 'success'\nexit 0")
        script.chmod(0o755)

        returncode = run_executable(script, check=True)

        assert returncode == 0


class TestRunShellCommand:
    """Test run_shell_command function."""

    def test_successful_shell_command(self):
        """Test running a successful shell command."""
        returncode = run_shell_command("echo test", check=False)

        assert returncode == 0

    def test_failed_shell_command_with_check(self):
        """Test failed shell command raises exception with check=True."""
        with pytest.raises(SubprocessError):
            run_shell_command("exit 1", check=True)

    def test_shell_command_with_cwd(self, tmp_path):
        """Test shell command in specific directory."""
        test_file = tmp_path / "marker.txt"
        test_file.write_text("marker")

        if sys.platform == 'win32':
            cmd = "dir"
        else:
            cmd = "ls"

        returncode = run_shell_command(cmd, check=True, cwd=tmp_path)

        assert returncode == 0


class TestEnableWindowsColorOutput:
    """Test enable_windows_color_output function."""

    @mock.patch('sys.platform', 'win32')
    @mock.patch('shedskin.subprocess_utils.subprocess.run')
    def test_windows_fallback(self, mock_run):
        """Test Windows color output fallback when ctypes fails."""
        # Mock ctypes to fail
        with mock.patch.dict('sys.modules', {'ctypes': None}):
            enable_windows_color_output()

        # Should fall back to subprocess.run
        mock_run.assert_called_once()

    @mock.patch('sys.platform', 'darwin')
    def test_non_windows_does_nothing(self):
        """Test that non-Windows platforms do nothing."""
        # Should not raise any exceptions
        enable_windows_color_output()


class TestAssertCommandSuccess:
    """Test assert_command_success function."""

    def test_successful_command(self):
        """Test assert with successful command."""
        # Should not raise
        assert_command_success(["echo", "test"], shell=False)

    def test_failed_command(self):
        """Test assert with failed command."""
        with pytest.raises(SubprocessError):
            assert_command_success(["false"], shell=False)

    def test_shell_command_success(self):
        """Test assert with successful shell command."""
        assert_command_success("echo test", shell=True)

    def test_with_cwd(self, tmp_path):
        """Test assert with working directory."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        if sys.platform == 'win32':
            cmd = "dir"
        else:
            cmd = "ls"

        # Should not raise
        assert_command_success(cmd, shell=True, cwd=tmp_path)


class TestIntegration:
    """Integration tests for subprocess utilities."""

    def test_command_chain(self, tmp_path):
        """Test chaining multiple commands."""
        # Create a test file
        test_file = tmp_path / "test.txt"

        # Write to file
        if sys.platform == 'win32':
            run_shell_command(
                f'echo test > "{test_file}"',
                shell=True,
                check=True
            )
        else:
            run_command(
                ["sh", "-c", f"echo test > {test_file}"],
                check=True
            )

        # Verify file exists
        assert test_file.exists()
        assert "test" in test_file.read_text()

    def test_error_propagation(self):
        """Test that errors propagate correctly through the call stack."""
        def inner():
            run_command(["false"], check=True)

        def outer():
            inner()

        with pytest.raises(SubprocessError) as exc_info:
            outer()

        # Should have meaningful error message
        assert "exit code" in str(exc_info.value).lower()
