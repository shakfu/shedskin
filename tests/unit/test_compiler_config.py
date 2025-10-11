"""Unit tests for shedskin.compiler_config module."""

import argparse
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

from shedskin.compiler_config import (
    CompilerOptions,
    CompilerPaths,
    get_pkg_path,
    get_user_cache_dir,
)


class TestCompilerOptions:
    """Test CompilerOptions dataclass."""

    def test_default_options(self):
        """Test default compiler options."""
        options = CompilerOptions()

        assert options.wrap_around_check is True
        assert options.bounds_checking is True
        assert options.assertions is True
        assert options.executable_product is True
        assert options.pyextension_product is False
        assert options.int32 is False
        assert options.int64 is False
        assert options.float32 is False
        assert options.nogc is False
        assert options.backtrace is False

    def test_custom_options(self):
        """Test creating options with custom values."""
        options = CompilerOptions(
            int64=True,
            float32=True,
            bounds_checking=False,
            backtrace=True,
        )

        assert options.int64 is True
        assert options.float32 is True
        assert options.bounds_checking is False
        assert options.backtrace is True

    def test_immutability(self):
        """Test that CompilerOptions is immutable (frozen dataclass)."""
        options = CompilerOptions()

        with pytest.raises(AttributeError):
            options.int64 = True  # type: ignore

    def test_from_namespace(self):
        """Test creating CompilerOptions from argparse Namespace."""
        ns = argparse.Namespace(
            wrap_around_check=False,
            bounds_checking=True,
            int64=True,
            float32=True,
            nogc=True,
            backtrace=False,
            outputdir="/tmp/output",
        )

        options = CompilerOptions.from_namespace(ns)

        assert options.wrap_around_check is False
        assert options.bounds_checking is True
        assert options.int64 is True
        assert options.float32 is True
        assert options.nogc is True
        assert options.outputdir == "/tmp/output"

    def test_from_namespace_partial(self):
        """Test from_namespace with partial Namespace."""
        ns = argparse.Namespace(
            int64=True,
            # Missing other fields - should use defaults
        )

        options = CompilerOptions.from_namespace(ns)

        assert options.int64 is True
        assert options.bounds_checking is True  # Default value

    def test_get_numeric_type_flags_default(self):
        """Test numeric type flags with defaults."""
        options = CompilerOptions()
        flags = options.get_numeric_type_flags()

        assert flags == []

    def test_get_numeric_type_flags_int64(self):
        """Test numeric type flags with int64."""
        options = CompilerOptions(int64=True)
        flags = options.get_numeric_type_flags()

        assert '-D__SS_INT64' in flags

    def test_get_numeric_type_flags_int32(self):
        """Test numeric type flags with int32."""
        options = CompilerOptions(int32=True)
        flags = options.get_numeric_type_flags()

        assert '-D__SS_INT32' in flags

    def test_get_numeric_type_flags_int128(self):
        """Test numeric type flags with int128."""
        options = CompilerOptions(int128=True)
        flags = options.get_numeric_type_flags()

        assert '-D__SS_INT128' in flags

    def test_get_numeric_type_flags_float32(self):
        """Test numeric type flags with float32."""
        options = CompilerOptions(float32=True)
        flags = options.get_numeric_type_flags()

        assert '-D__SS_FLOAT32' in flags

    def test_get_numeric_type_flags_backtrace(self):
        """Test numeric type flags with backtrace."""
        options = CompilerOptions(backtrace=True)
        flags = options.get_numeric_type_flags()

        assert '-D__SS_BACKTRACE' in flags

    def test_get_numeric_type_flags_combined(self):
        """Test numeric type flags with multiple options."""
        options = CompilerOptions(int64=True, float32=True, backtrace=True)
        flags = options.get_numeric_type_flags()

        assert '-D__SS_INT64' in flags
        assert '-D__SS_FLOAT32' in flags
        assert '-D__SS_BACKTRACE' in flags


class TestCompilerPaths:
    """Test CompilerPaths dataclass."""

    def test_post_init_sets_resource_paths(self, tmp_path):
        """Test that __post_init__ sets resource paths."""
        paths = CompilerPaths(
            shedskin_lib=tmp_path / "lib",
            sysdir=str(tmp_path),
            libdirs=[str(tmp_path / "lib")],
        )

        assert paths.shedskin_resources == tmp_path / "resources"
        assert paths.shedskin_cmake == tmp_path / "resources" / "cmake" / "modular"
        assert paths.shedskin_conan == tmp_path / "resources" / "conan"
        assert paths.shedskin_flags == tmp_path / "resources" / "flags"
        assert paths.shedskin_illegal == tmp_path / "resources" / "illegal"

    def test_default_cwd(self):
        """Test that cwd defaults to current directory."""
        paths = CompilerPaths(
            shedskin_lib=Path("/fake/lib"),
            sysdir="/fake",
        )

        assert paths.cwd == Path.cwd()

    def test_from_installation_finds_lib(self, tmp_path, monkeypatch):
        """Test from_installation discovers library paths."""
        # Create mock shedskin structure
        shedskin_dir = tmp_path / "shedskin"
        lib_dir = shedskin_dir / "lib"
        lib_dir.mkdir(parents=True)

        # Mock __file__ to point to our temp directory
        mock_file = str(shedskin_dir / "compiler_config.py")
        monkeypatch.setattr("shedskin.compiler_config.__file__", mock_file)

        # Mock sys.path to include our temp directory
        monkeypatch.setattr("sys.path", [str(tmp_path)])

        paths = CompilerPaths.from_installation()

        assert paths.shedskin_lib == lib_dir
        assert str(lib_dir) in paths.libdirs

    def test_get_illegal_keywords(self, tmp_path):
        """Test loading C++ illegal keywords."""
        # Create mock illegal.txt
        illegal_dir = tmp_path / "resources" / "illegal"
        illegal_dir.mkdir(parents=True)
        illegal_file = illegal_dir / "illegal.txt"
        illegal_file.write_text("class\nstruct\ntemplate\n")

        paths = CompilerPaths(
            shedskin_lib=tmp_path / "lib",
            sysdir=str(tmp_path),
        )

        keywords = paths.get_illegal_keywords()

        assert keywords == {"class", "struct", "template"}


class TestGetPkgPath:
    """Test get_pkg_path function."""

    def test_returns_shedskin_path(self):
        """Test that get_pkg_path returns shedskin directory."""
        path = get_pkg_path()

        assert path.name == "shedskin"
        assert path.is_dir()


class TestGetUserCacheDir:
    """Test get_user_cache_dir function."""

    @mock.patch('platform.system', return_value='Darwin')
    def test_macos_cache_dir(self, mock_system):
        """Test macOS cache directory."""
        cache_dir = get_user_cache_dir()

        expected = Path("~/Library/Caches/shedskin").expanduser()
        assert cache_dir == expected

    @mock.patch('platform.system', return_value='Linux')
    def test_linux_cache_dir(self, mock_system):
        """Test Linux cache directory."""
        cache_dir = get_user_cache_dir()

        expected = Path("~/.cache/shedskin").expanduser()
        assert cache_dir == expected

    @mock.patch('platform.system', return_value='Windows')
    @mock.patch.dict(os.environ, {'USERPROFILE': 'C:\\Users\\TestUser'})
    def test_windows_cache_dir(self, mock_system):
        """Test Windows cache directory."""
        cache_dir = get_user_cache_dir()

        # Check components since path separator may differ
        assert "TestUser" in str(cache_dir)
        assert "AppData" in str(cache_dir)
        assert "Local" in str(cache_dir)
        assert "shedskin" in str(cache_dir)
        assert "Cache" in str(cache_dir)

    @mock.patch('platform.system', return_value='Windows')
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_windows_no_userprofile_raises(self, mock_system):
        """Test Windows raises SystemExit if USERPROFILE not set."""
        with pytest.raises(SystemExit) as exc_info:
            get_user_cache_dir()

        assert "USERPROFILE" in str(exc_info.value)

    @mock.patch('platform.system', return_value='FreeBSD')
    def test_unsupported_platform_raises(self, mock_system):
        """Test unsupported platform raises SystemExit."""
        with pytest.raises(SystemExit) as exc_info:
            get_user_cache_dir()

        assert "FreeBSD" in str(exc_info.value)
        assert "not supported" in str(exc_info.value)


class TestIntegration:
    """Integration tests for compiler configuration."""

    def test_options_and_paths_together(self):
        """Test using CompilerOptions and CompilerPaths together."""
        # Create options
        options = CompilerOptions(
            int64=True,
            bounds_checking=False,
            outputdir="/tmp/output",
        )

        # Get flags
        flags = options.get_numeric_type_flags()

        # Create paths
        paths = get_pkg_path()

        # Should work together
        assert '-D__SS_INT64' in flags
        assert paths.exists()
        assert not options.bounds_checking

    def test_from_namespace_integration(self):
        """Test full integration with argparse namespace."""
        # Simulate parsed arguments
        parser = argparse.ArgumentParser()
        parser.add_argument('--int64', action='store_true')
        parser.add_argument('--bounds-checking', action='store_true')
        parser.add_argument('--outputdir')

        args = parser.parse_args(['--int64', '--outputdir', '/tmp'])

        # Convert to options
        # Fix attribute name (argparse converts - to _)
        args.bounds_checking = args.bounds_checking
        options = CompilerOptions.from_namespace(args)

        assert options.int64 is True
        assert options.outputdir == '/tmp'
