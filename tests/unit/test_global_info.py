"""Unit tests for refactored GlobalInfo class."""

import argparse
from pathlib import Path
from unittest import mock

import pytest

from shedskin.config import GlobalInfo
from shedskin.compiler_config import CompilerOptions, CompilerPaths, CompilerState


class TestGlobalInfoInitialization:
    """Test GlobalInfo initialization with refactored components."""

    def test_creates_compiler_components(self):
        """Test that GlobalInfo creates all three components."""
        ns = argparse.Namespace(
            wrap_around_check=True,
            bounds_checking=False,
            int64=True,
        )

        gx = GlobalInfo(ns)

        assert isinstance(gx.compiler_options, CompilerOptions)
        assert isinstance(gx.compiler_paths, CompilerPaths)
        assert isinstance(gx.compiler_state, CompilerState)
        assert gx.options is ns

    def test_loads_cpp_keywords(self):
        """Test that cpp_keywords are loaded from illegal.txt."""
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Should have loaded C++ keywords
        assert len(gx.compiler_state.cpp_keywords) > 0
        # Check for some common C++ keywords
        assert any(kw in gx.compiler_state.cpp_keywords for kw in ['class', 'template', 'namespace'])

    def test_compiler_options_from_namespace(self):
        """Test that compiler options are correctly created from namespace."""
        ns = argparse.Namespace(
            wrap_around_check=False,
            bounds_checking=True,
            int64=True,
            float32=True,
            nogc=True,
            backtrace=False,
        )

        gx = GlobalInfo(ns)

        assert gx.compiler_options.wrap_around_check is False
        assert gx.compiler_options.bounds_checking is True
        assert gx.compiler_options.int64 is True
        assert gx.compiler_options.float32 is True
        assert gx.compiler_options.nogc is True


class TestBackwardCompatibility:
    """Test backward compatibility via attribute delegation."""

    def test_can_access_state_attributes(self):
        """Test accessing compiler_state attributes directly."""
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Should be able to access state attributes directly
        assert gx.constraints == set()
        assert gx.templates == 0
        assert gx.iterations == 0
        assert gx.ss_prefix == "__ss_"
        assert isinstance(gx.modules, dict)

    def test_can_access_options_attributes(self):
        """Test accessing compiler_options attributes directly."""
        ns = argparse.Namespace(
            wrap_around_check=False,
            int64=True,
        )
        gx = GlobalInfo(ns)

        # Should be able to access option attributes directly
        assert gx.wrap_around_check is False
        assert gx.int64 is True
        assert gx.bounds_checking is True  # default value

    def test_can_access_paths_attributes(self):
        """Test accessing compiler_paths attributes directly."""
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Should be able to access path attributes directly
        assert isinstance(gx.shedskin_lib, Path)
        assert isinstance(gx.sysdir, str)
        assert isinstance(gx.libdirs, list)
        assert len(gx.libdirs) > 0

    def test_can_modify_state_attributes(self):
        """Test modifying compiler_state attributes."""
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Should be able to modify state attributes
        gx.iterations = 5
        assert gx.compiler_state.iterations == 5
        assert gx.iterations == 5

        gx.templates = 10
        assert gx.compiler_state.templates == 10

    def test_can_modify_options_attributes_creates_new_instance(self):
        """Test that modifying compiler_options creates a new frozen instance."""
        ns = argparse.Namespace(wrap_around_check=True)
        gx = GlobalInfo(ns)

        # Get the original options instance
        original_options = gx.compiler_options

        # Modify an option attribute
        gx.wrap_around_check = False

        # Should have created a new CompilerOptions instance
        assert gx.compiler_options is not original_options
        assert gx.wrap_around_check is False
        assert gx.compiler_options.wrap_around_check is False
        # Original instance unchanged
        assert original_options.wrap_around_check is True

    def test_attribute_not_found_raises(self):
        """Test that accessing non-existent attributes raises AttributeError."""
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        with pytest.raises(AttributeError) as exc_info:
            _ = gx.nonexistent_attribute

        assert "nonexistent_attribute" in str(exc_info.value)

    def test_can_set_new_attributes_to_state(self):
        """Test that new attributes are added to compiler_state."""
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Should be able to add new attributes (go to state)
        gx.custom_attribute = "test_value"
        assert gx.compiler_state.custom_attribute == "test_value"
        assert gx.custom_attribute == "test_value"


class TestGetStats:
    """Test get_stats method."""

    def test_get_stats_returns_dict(self):
        """Test that get_stats returns a dictionary."""
        ns = argparse.Namespace(
            wrap_around_check=True,
            int64=True,
        )
        gx = GlobalInfo(ns)

        stats = gx.get_stats()

        assert isinstance(stats, dict)
        assert 'n_constraints' in stats
        assert 'n_modules' in stats
        assert 'wrap_around_check' in stats
        assert 'int64' in stats

    def test_get_stats_reflects_state(self):
        """Test that get_stats reflects current state."""
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Modify some state
        gx.iterations = 5
        gx.total_iterations = 10
        gx.templates = 3

        stats = gx.get_stats()

        assert stats['n_iterations'] == 5
        assert stats['total_iterations'] == 10
        assert stats['n_templates'] == 3

    def test_get_stats_includes_options(self):
        """Test that get_stats includes compiler options."""
        ns = argparse.Namespace(
            wrap_around_check=False,
            bounds_checking=True,
            int64=True,
            float32=True,
            nogc=True,
        )
        gx = GlobalInfo(ns)

        stats = gx.get_stats()

        assert stats['wrap_around_check'] is False
        assert stats['bounds_checking'] is True
        assert stats['int64'] is True
        assert stats['float32'] is True
        assert stats['nogc'] is True


class TestIntegration:
    """Integration tests for GlobalInfo."""

    def test_full_workflow(self):
        """Test a full compilation workflow using GlobalInfo."""
        # Create with options
        ns = argparse.Namespace(
            wrap_around_check=True,
            bounds_checking=False,
            int64=True,
        )
        gx = GlobalInfo(ns)

        # Access options
        assert gx.int64 is True
        assert gx.bounds_checking is False

        # Access paths
        assert gx.shedskin_lib.exists()

        # Modify state
        gx.iterations = 1
        gx.templates = 5

        # Access state
        assert len(gx.constraints) == 0
        assert len(gx.modules) == 0

        # Get stats
        stats = gx.get_stats()
        assert stats['n_iterations'] == 1
        assert stats['n_templates'] == 5
        assert stats['int64'] is True

    def test_init_directories_is_noop(self):
        """Test that init_directories is now a no-op."""
        ns = argparse.Namespace()
        gx = GlobalInfo(ns)

        # Call deprecated method - should not raise
        gx.init_directories()

        # Paths should still be available
        assert gx.shedskin_lib is not None
        assert gx.sysdir is not None
