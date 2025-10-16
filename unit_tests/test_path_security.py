"""Unit tests for shedskin.path_security module.

Tests path validation, traversal prevention, and sensitive directory protection.
"""

import os
import tempfile
from pathlib import Path

import pytest

from shedskin.exceptions import InvalidInputError
from shedskin.path_security import (
    safe_join,
    validate_directory,
    validate_input_file,
    validate_output_path,
)


class TestValidateOutputPath:
    """Tests for validate_output_path function."""

    def test_relative_path_within_base(self, tmp_path):
        """Test that relative paths within base directory are accepted."""
        base = tmp_path
        result = validate_output_path("output", base_dir=base, allow_absolute=False)
        assert result == base / "output"

    def test_relative_path_creates_subdirs(self, tmp_path):
        """Test that relative paths with subdirectories are normalized."""
        base = tmp_path
        result = validate_output_path("foo/bar/baz", base_dir=base, allow_absolute=False)
        assert result == base / "foo" / "bar" / "baz"

    def test_relative_path_traversal_blocked(self, tmp_path):
        """Test that path traversal attempts are blocked."""
        base = tmp_path / "project"
        base.mkdir()

        with pytest.raises(InvalidInputError, match="Path traversal detected"):
            validate_output_path("../../../etc", base_dir=base, allow_absolute=False)

    def test_absolute_path_requires_flag(self, tmp_path):
        """Test that absolute paths require allow_absolute=True."""
        abs_path = tmp_path / "output"

        # Should fail without allow_absolute
        with pytest.raises(InvalidInputError, match="Absolute path not allowed"):
            validate_output_path(abs_path, allow_absolute=False)

        # Should succeed with allow_absolute
        result = validate_output_path(abs_path, allow_absolute=True)
        assert result == abs_path

    def test_sensitive_directory_etc_blocked(self):
        """Test that /etc directory writes are blocked."""
        with pytest.raises(InvalidInputError, match="Cannot write to sensitive system directory"):
            validate_output_path("/etc/test", allow_absolute=True)

    def test_sensitive_directory_boot_blocked(self):
        """Test that /boot directory writes are blocked."""
        with pytest.raises(InvalidInputError, match="Cannot write to sensitive system directory"):
            validate_output_path("/boot/test", allow_absolute=True)

    def test_sensitive_directory_sys_blocked(self):
        """Test that /sys directory writes are blocked."""
        with pytest.raises(InvalidInputError, match="Cannot write to sensitive system directory"):
            validate_output_path("/sys/test", allow_absolute=True)

    def test_sensitive_directory_proc_blocked(self):
        """Test that /proc directory writes are blocked."""
        with pytest.raises(InvalidInputError, match="Cannot write to sensitive system directory"):
            validate_output_path("/proc/test", allow_absolute=True)

    def test_sensitive_directory_dev_blocked(self):
        """Test that /dev directory writes are blocked."""
        with pytest.raises(InvalidInputError, match="Cannot write to sensitive system directory"):
            validate_output_path("/dev/test", allow_absolute=True)

    def test_sensitive_directory_root_blocked(self):
        """Test that /root directory writes are blocked."""
        with pytest.raises(InvalidInputError, match="Cannot write to sensitive system directory"):
            validate_output_path("/root/test", allow_absolute=True)

    def test_tmp_directory_allowed(self):
        """Test that /tmp directory is allowed."""
        result = validate_output_path("/tmp/test", allow_absolute=True)
        # macOS resolves /tmp to /private/tmp
        assert result == Path("/tmp/test").resolve()

    def test_symlink_resolution(self, tmp_path):
        """Test that symlinks are resolved and validated."""
        # Create a directory and a symlink to it
        target = tmp_path / "target"
        target.mkdir()

        link = tmp_path / "link"
        link.symlink_to(target)

        # Validate through symlink
        result = validate_output_path(link, allow_absolute=True)
        assert result == target

    def test_symlink_to_sensitive_blocked(self, tmp_path):
        """Test that symlinks to sensitive directories are blocked."""
        # Create symlink to /etc (if we have permission, otherwise skip)
        link = tmp_path / "etc_link"
        try:
            link.symlink_to("/etc")
        except (OSError, PermissionError):
            pytest.skip("Cannot create symlink to /etc")

        with pytest.raises(InvalidInputError, match="Cannot write to sensitive system directory"):
            validate_output_path(link, allow_absolute=True)

    def test_default_base_dir_is_cwd(self):
        """Test that base_dir defaults to current working directory."""
        cwd = Path.cwd()
        result = validate_output_path("output")
        assert result == cwd / "output"

    def test_path_normalization(self, tmp_path):
        """Test that paths are normalized (removes ./  and resolves ..)."""
        base = tmp_path
        result = validate_output_path("./foo/../bar", base_dir=base, allow_absolute=False)
        assert result == base / "bar"

    def test_allow_absolute_with_relative_path(self, tmp_path):
        """Test that allow_absolute=True allows relative paths to escape base."""
        base = tmp_path / "project"
        base.mkdir()

        # With allow_absolute=True, can escape base directory
        result = validate_output_path("../output", base_dir=base, allow_absolute=True)
        assert result == tmp_path / "output"


class TestValidateInputFile:
    """Tests for validate_input_file function."""

    def test_existing_file_accepted(self, tmp_path):
        """Test that existing files are accepted."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        result = validate_input_file(test_file, must_exist=True)
        assert result == test_file

    def test_missing_file_rejected(self, tmp_path):
        """Test that missing files are rejected when must_exist=True."""
        test_file = tmp_path / "missing.py"

        with pytest.raises(InvalidInputError, match="File not found"):
            validate_input_file(test_file, must_exist=True)

    def test_missing_file_allowed_when_not_required(self, tmp_path):
        """Test that missing files are allowed when must_exist=False."""
        test_file = tmp_path / "missing.py"
        result = validate_input_file(test_file, must_exist=False)
        assert result == test_file

    def test_directory_rejected(self, tmp_path):
        """Test that directories are rejected."""
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()

        with pytest.raises(InvalidInputError, match="Not a file"):
            validate_input_file(test_dir, must_exist=True)

    def test_extension_validation_accepts_valid(self, tmp_path):
        """Test that files with valid extensions are accepted."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        result = validate_input_file(test_file, must_exist=True, allowed_extensions=['.py'])
        assert result == test_file

    def test_extension_validation_rejects_invalid(self, tmp_path):
        """Test that files with invalid extensions are rejected."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        with pytest.raises(InvalidInputError, match="Invalid file extension"):
            validate_input_file(test_file, must_exist=True, allowed_extensions=['.py'])

    def test_extension_validation_multiple_allowed(self, tmp_path):
        """Test that multiple allowed extensions work."""
        test_file = tmp_path / "test.cpp"
        test_file.write_text("// test")

        result = validate_input_file(
            test_file,
            must_exist=True,
            allowed_extensions=['.py', '.cpp', '.hpp']
        )
        assert result == test_file

    def test_sensitive_directory_etc_blocked(self):
        """Test that reading from /etc is blocked."""
        # On macOS, /etc resolves to /private/etc, test both
        etc_path = Path("/etc/passwd").resolve()
        with pytest.raises(InvalidInputError, match="Cannot read from sensitive system directory"):
            validate_input_file(etc_path, must_exist=False)

    def test_sensitive_directory_boot_blocked(self):
        """Test that reading from /boot is blocked."""
        with pytest.raises(InvalidInputError, match="Cannot read from sensitive system directory"):
            validate_input_file("/boot/grub/grub.cfg", must_exist=False)

    def test_symlink_resolution(self, tmp_path):
        """Test that symlinks to files are resolved."""
        target = tmp_path / "target.py"
        target.write_text("# test")

        link = tmp_path / "link.py"
        link.symlink_to(target)

        result = validate_input_file(link, must_exist=True)
        assert result == target


class TestValidateDirectory:
    """Tests for validate_directory function."""

    def test_existing_directory_accepted(self, tmp_path):
        """Test that existing directories are accepted."""
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()

        result = validate_directory(test_dir, must_exist=True)
        assert result == test_dir

    def test_missing_directory_rejected(self, tmp_path):
        """Test that missing directories are rejected when must_exist=True."""
        test_dir = tmp_path / "missing"

        with pytest.raises(InvalidInputError, match="Directory not found"):
            validate_directory(test_dir, must_exist=True)

    def test_missing_directory_allowed(self, tmp_path):
        """Test that missing directories are allowed when must_exist=False."""
        test_dir = tmp_path / "missing"
        result = validate_directory(test_dir, must_exist=False)
        assert result == test_dir

    def test_create_if_missing(self, tmp_path):
        """Test that directories can be created if create_if_missing=True."""
        test_dir = tmp_path / "newdir"
        assert not test_dir.exists()

        result = validate_directory(test_dir, create_if_missing=True)
        assert result == test_dir
        assert test_dir.exists()
        assert test_dir.is_dir()

    def test_create_nested_directories(self, tmp_path):
        """Test that nested directories can be created."""
        test_dir = tmp_path / "a" / "b" / "c"
        assert not test_dir.exists()

        result = validate_directory(test_dir, create_if_missing=True)
        assert result == test_dir
        assert test_dir.exists()
        assert test_dir.is_dir()

    def test_file_not_directory_rejected(self, tmp_path):
        """Test that files are rejected when expecting directory."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("test")

        with pytest.raises(InvalidInputError, match="Not a directory"):
            validate_directory(test_file, must_exist=True)

    def test_sensitive_directory_etc_blocked(self):
        """Test that /etc directory is blocked."""
        # On macOS, /etc resolves to /private/etc
        etc_path = Path("/etc").resolve()
        with pytest.raises(InvalidInputError, match="Cannot use sensitive system directory"):
            validate_directory(etc_path, must_exist=False)

    def test_sensitive_directory_root_blocked(self):
        """Test that /root directory is blocked."""
        with pytest.raises(InvalidInputError, match="Cannot use sensitive system directory"):
            validate_directory("/root", must_exist=False)

    def test_tmp_directory_allowed(self):
        """Test that /tmp directory is allowed."""
        result = validate_directory("/tmp", must_exist=False)
        # macOS resolves /tmp to /private/tmp
        assert result == Path("/tmp").resolve()


class TestSafeJoin:
    """Tests for safe_join function."""

    def test_simple_join(self, tmp_path):
        """Test simple path joining."""
        result = safe_join(tmp_path, "foo", "bar")
        assert result == tmp_path / "foo" / "bar"

    def test_single_component(self, tmp_path):
        """Test joining single component."""
        result = safe_join(tmp_path, "foo")
        assert result == tmp_path / "foo"

    def test_multiple_components(self, tmp_path):
        """Test joining multiple components."""
        result = safe_join(tmp_path, "a", "b", "c", "d")
        assert result == tmp_path / "a" / "b" / "c" / "d"

    def test_path_traversal_blocked(self, tmp_path):
        """Test that path traversal is blocked."""
        with pytest.raises(InvalidInputError, match="Path traversal detected"):
            safe_join(tmp_path, "..", "etc", "passwd")

    def test_path_traversal_in_middle_blocked(self, tmp_path):
        """Test that path traversal in middle of path is blocked."""
        with pytest.raises(InvalidInputError, match="Path traversal detected"):
            safe_join(tmp_path, "foo", "..", "..", "etc")

    def test_absolute_component_escapes(self, tmp_path):
        """Test that absolute path components escape base (and are caught)."""
        # On Unix, absolute paths override the join
        with pytest.raises(InvalidInputError, match="Path traversal detected"):
            safe_join(tmp_path, "/etc/passwd")

    def test_dot_components_allowed(self, tmp_path):
        """Test that . components are allowed (they resolve to same dir)."""
        result = safe_join(tmp_path, ".", "foo", ".", "bar")
        assert result == tmp_path / "foo" / "bar"

    def test_empty_component_handling(self, tmp_path):
        """Test that empty components are handled correctly."""
        result = safe_join(tmp_path, "foo", "", "bar")
        # pathlib normalizes empty components away
        assert result == tmp_path / "foo" / "bar"


class TestPathSecurityIntegration:
    """Integration tests for path security functions."""

    def test_workflow_output_directory(self, tmp_path):
        """Test typical workflow for output directory validation."""
        # User provides output directory
        user_input = "build/output"

        # Validate it
        validated = validate_output_path(
            user_input,
            base_dir=tmp_path,
            allow_absolute=True
        )

        # Create it
        validated.mkdir(parents=True, exist_ok=True)

        # Verify it exists
        assert validated.exists()
        assert validated.is_dir()

    def test_workflow_input_file(self, tmp_path):
        """Test typical workflow for input file validation."""
        # Create test file
        test_file = tmp_path / "program.py"
        test_file.write_text("def main(): pass")

        # Validate it
        validated = validate_input_file(
            str(test_file),
            must_exist=True,
            allowed_extensions=['.py']
        )

        # Read it
        content = validated.read_text()
        assert "def main()" in content

    def test_workflow_library_directory(self, tmp_path):
        """Test typical workflow for library directory validation."""
        # Create library directory
        lib_dir = tmp_path / "mylib"
        lib_dir.mkdir()

        # Validate it
        validated = validate_directory(str(lib_dir), must_exist=True)

        # Use it
        assert validated.exists()
        assert validated.is_dir()

    def test_attack_scenario_path_traversal(self, tmp_path):
        """Test that path traversal attack is blocked."""
        base = tmp_path / "project"
        base.mkdir()

        # Attacker tries to write to parent directory
        malicious_input = "../../../etc/malicious"

        with pytest.raises(InvalidInputError):
            validate_output_path(malicious_input, base_dir=base, allow_absolute=False)

    def test_attack_scenario_absolute_sensitive(self):
        """Test that writing to sensitive directories is blocked."""
        # Attacker tries to write to /etc
        malicious_input = "/etc/backdoor"

        with pytest.raises(InvalidInputError, match="sensitive system directory"):
            validate_output_path(malicious_input, allow_absolute=True)

    def test_attack_scenario_symlink_escape(self, tmp_path):
        """Test that symlink escape attempts are blocked."""
        # Create project directory
        base = tmp_path / "project"
        base.mkdir()

        # Create symlink pointing to parent
        escape_link = base / "escape"
        escape_link.symlink_to(tmp_path)

        # Attacker tries to use symlink to escape
        malicious_input = escape_link / "malicious"

        # This should be blocked (error can be either "Path traversal" or "Absolute path not allowed")
        with pytest.raises(InvalidInputError):
            validate_output_path(malicious_input, base_dir=base, allow_absolute=False)


class TestCrossPlatform:
    """Cross-platform compatibility tests."""

    def test_windows_drive_letter(self, tmp_path):
        """Test handling of Windows drive letters (on all platforms)."""
        # This test verifies Path handles drive letters correctly
        # On Unix, this will be a relative path "C:/test"
        # On Windows, this will be absolute "C:\test"
        result = Path("C:/test").resolve()
        assert isinstance(result, Path)

    def test_backslash_separator(self, tmp_path):
        """Test that backslashes in paths are handled."""
        # Path normalizes separators
        result = Path(str(tmp_path) + "/foo\\bar")
        assert isinstance(result, Path)

    def test_unc_path_handling(self):
        """Test UNC path handling (Windows network paths)."""
        # Path should handle UNC paths gracefully
        # This doesn't validate them, just ensures no crash
        unc_path = Path("//server/share/file")
        assert isinstance(unc_path, Path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
