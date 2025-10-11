# SHED SKIN Python-to-C++ Compiler
# Copyright 2005-2024 Mark Dufour and contributors; GNU GPL version 3 (See LICENSE)
"""shedskin.config: contains the main shedskin global configuration class

`GlobalInfo` which is referred to in shedskin as `gx`.

This module is transitioning to use the refactored compiler_config module
for better separation of concerns. The GlobalInfo class now composes:
- CompilerOptions (immutable configuration)
- CompilerPaths (file system paths)
- CompilerState (mutable runtime state)
"""

import argparse
import platform
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .compiler_config import (
    CompilerOptions,
    CompilerPaths,
    CompilerState,
    get_pkg_path,
    get_user_cache_dir,
)

if TYPE_CHECKING:
    from .utils import ProgressBar

# constants
PLATFORM = platform.system()


# classes
class GlobalInfo:
    """Global configuration and state for the shedskin compiler.

    This class is being refactored to separate concerns. It now composes:
    - options: CompilerOptions (immutable configuration)
    - paths: CompilerPaths (file system paths)
    - state: CompilerState (mutable runtime state)

    For backward compatibility, all attributes are accessible directly
    on the GlobalInfo instance via property delegation.
    """

    def __init__(self, options: argparse.Namespace):
        """Initialize GlobalInfo with refactored components.

        Args:
            options: Parsed command-line arguments
        """
        # Store original options namespace for compatibility
        self.options = options

        # Create immutable compiler options from namespace
        self.compiler_options = CompilerOptions.from_namespace(options)

        # Create compiler paths (discovers shedskin installation)
        self.compiler_paths = CompilerPaths.from_installation()

        # Create mutable compiler state
        self.compiler_state = CompilerState()

        # Initialize cpp_keywords from illegal.txt
        self.compiler_state.cpp_keywords = self.compiler_paths.get_illegal_keywords()

        # Set module_path if provided in options
        if hasattr(options, 'module_path') and options.module_path:
            self.compiler_paths = CompilerPaths(
                shedskin_lib=self.compiler_paths.shedskin_lib,
                sysdir=self.compiler_paths.sysdir,
                libdirs=self.compiler_paths.libdirs,
                module_path=Path(options.module_path),
            )

    def get_stats(self) -> dict[str, Any]:
        """Get compilation statistics.

        Returns:
            Dictionary with compilation stats and configuration
        """
        state = self.compiler_state
        opts = self.compiler_options

        pyfile = Path(self.compiler_paths.module_path) if self.compiler_paths.module_path else Path("unknown")

        return {
            "name": pyfile.stem,
            "filename": str(pyfile),
            "n_words": 0,
            "sloc": 0,
            "prebuild_secs": 0.0,
            "build_secs": 0.0,
            "run_secs": 0.0,
            "n_constraints": len(state.constraints),
            "n_vars": len(state.allvars),
            "n_funcs": len(state.allfuncs),
            "n_classes": len(state.allclasses),
            "n_cnodes": len(state.cnode.keys()),
            "n_types": len(state.types.keys()),
            "n_orig_types": len(state.orig_types.keys()),
            "n_modules": len(state.modules.keys()),
            "n_templates": state.templates,
            "n_inheritance_relations": len(state.inheritance_relations.keys()),
            "n_inheritance_temp_vars": len(state.inheritance_temp_vars.keys()),
            "n_parent_nodes": len(state.parent_nodes.keys()),
            "n_inherited": len(state.inherited),
            "n_assign_target": len(state.assign_target.keys()),
            "n_alloc_info": len(state.alloc_info.keys()),
            "n_new_alloc_info": len(state.new_alloc_info.keys()),
            "n_iterations": state.iterations,
            "total_iterations": state.total_iterations,
            "n_called": len(state.called),
            "added_allocs": state.added_allocs,
            "added_funcs": state.added_funcs,
            "cpa_limit": state.cpa_limit,
            # commandline-options
            "wrap_around_check": opts.wrap_around_check,
            "bounds_checking": opts.bounds_checking,
            "assertions": opts.assertions,
            "executable_product": opts.executable_product,
            "pyextension_product": opts.pyextension_product,
            "int32": opts.int32,
            "int64": opts.int64,
            "int128": opts.int128,
            "float32": opts.float32,
            "float64": opts.float64,
            "silent": opts.silent,
            "nogc": opts.nogc,
            "backtrace": opts.backtrace,
        }

    def init_directories(self) -> None:
        """Initialize directory paths.

        Deprecated: This method is now handled by CompilerPaths.from_installation().
        Kept for backward compatibility.
        """
        # This is now a no-op as paths are initialized in __init__
        pass

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to composed components for backward compatibility.

        This allows existing code to access attributes like gx.constraints or
        gx.wrap_around_check directly, even though they're now in separate
        components.

        Args:
            name: Attribute name

        Returns:
            Value from compiler_state, compiler_options, or compiler_paths

        Raises:
            AttributeError: If attribute doesn't exist in any component
        """
        # Try compiler_state first (most common case)
        if hasattr(self.compiler_state, name):
            return getattr(self.compiler_state, name)

        # Try compiler_options
        if hasattr(self.compiler_options, name):
            return getattr(self.compiler_options, name)

        # Try compiler_paths
        if hasattr(self.compiler_paths, name):
            return getattr(self.compiler_paths, name)

        # Not found in any component
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    def __setattr__(self, name: str, value: Any) -> None:
        """Delegate attribute setting to composed components for backward compatibility.

        Args:
            name: Attribute name
            value: Value to set
        """
        # Allow setting the core components and options during __init__
        if name in ('options', 'compiler_options', 'compiler_paths', 'compiler_state'):
            object.__setattr__(self, name, value)
            return

        # Once initialized, delegate to appropriate component
        if hasattr(self, 'compiler_state') and hasattr(self.compiler_state, name):
            setattr(self.compiler_state, name, value)
        elif hasattr(self, 'compiler_paths') and hasattr(self.compiler_paths, name):
            # CompilerPaths attributes (except module_path which is mutable)
            if name == 'module_path':
                self.compiler_paths.module_path = value
            else:
                object.__setattr__(self.compiler_paths, name, value)
        elif hasattr(self, 'compiler_options') and hasattr(self.compiler_options, name):
            # CompilerOptions is frozen, but we need backward compatibility
            # Work around frozen dataclass by creating a new instance with the updated value
            from dataclasses import replace
            new_options = replace(self.compiler_options, **{name: value})
            object.__setattr__(self, 'compiler_options', new_options)
        else:
            # New attribute - add to compiler_state
            if hasattr(self, 'compiler_state'):
                setattr(self.compiler_state, name, value)
            else:
                object.__setattr__(self, name, value)


# Exports
__all__ = ['GlobalInfo', 'get_pkg_path', 'get_user_cache_dir', 'PLATFORM']
