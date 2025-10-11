"""Refactored compiler configuration - separating options from state.

This module provides a cleaner separation between:
- CompilerOptions: Immutable configuration from command-line/environment
- CompilerState: Mutable state during compilation
- CompilerPaths: File system paths and directories

This refactoring addresses CODE_REVIEW.md Section 9.2 recommendation to split
GlobalInfo into focused, maintainable components.
"""

import argparse
import ast
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional, Set, Tuple, TypeAlias, Union

if TYPE_CHECKING:
    from . import infer, python
    from .utils import ProgressBar

# Type aliases
CartesianProduct: TypeAlias = Tuple[Tuple["python.Class", int], ...]


@dataclass(frozen=True)
class CompilerOptions:
    """Immutable compiler configuration options.

    These options are set from command-line arguments or environment
    and should not change during compilation.
    """

    # Code generation options
    wrap_around_check: bool = True
    bounds_checking: bool = True
    assertions: bool = True
    executable_product: bool = True
    pyextension_product: bool = False

    # Numeric type options
    int32: bool = False
    int64: bool = False
    int128: bool = False
    float32: bool = False
    float64: bool = False

    # Build options
    flags: Optional[Path] = None
    silent: bool = False
    nogc: bool = False
    backtrace: bool = False
    makefile_name: str = "Makefile"
    nomakefile: bool = False
    generate_cmakefile: bool = False

    # Output options
    outputdir: Optional[str] = None
    debug_level: int = 0

    @classmethod
    def from_namespace(cls, options: argparse.Namespace) -> "CompilerOptions":
        """Create CompilerOptions from argparse Namespace.

        Args:
            options: Parsed command-line arguments

        Returns:
            CompilerOptions instance with values from namespace
        """
        # Extract relevant fields from namespace
        kwargs = {}
        for field_name in cls.__dataclass_fields__:
            if hasattr(options, field_name):
                kwargs[field_name] = getattr(options, field_name)

        return cls(**kwargs)

    def get_numeric_type_flags(self) -> list[str]:
        """Get compiler flags for numeric type configuration.

        Returns:
            List of compiler flags like ['-D__SS_INT64', '-D__SS_FLOAT32']
        """
        flags = []
        if self.int32:
            flags.append('-D__SS_INT32')
        elif self.int64:
            flags.append('-D__SS_INT64')
        elif self.int128:
            flags.append('-D__SS_INT128')

        if self.float32:
            flags.append('-D__SS_FLOAT32')

        if self.backtrace:
            flags.append('-D__SS_BACKTRACE')

        return flags


@dataclass
class CompilerPaths:
    """File system paths used by the compiler.

    These paths are determined during initialization and point to
    Shedskin installation directories and user directories.
    """

    # Shedskin installation paths
    shedskin_lib: Path
    sysdir: str
    libdirs: list[str] = field(default_factory=list)

    # Resource directories
    shedskin_resources: Path = field(init=False)
    shedskin_cmake: Path = field(init=False)
    shedskin_conan: Path = field(init=False)
    shedskin_flags: Path = field(init=False)
    shedskin_illegal: Path = field(init=False)

    # Current working directory
    cwd: Path = field(default_factory=Path.cwd)

    # Module being compiled
    module_path: Optional[Path] = None

    def __post_init__(self) -> None:
        """Initialize resource subdirectories."""
        shedskin_dir = Path(self.sysdir)
        self.shedskin_resources = shedskin_dir / "resources"
        self.shedskin_cmake = self.shedskin_resources / "cmake" / "modular"
        self.shedskin_conan = self.shedskin_resources / "conan"
        self.shedskin_flags = self.shedskin_resources / "flags"
        self.shedskin_illegal = self.shedskin_resources / "illegal"

    @classmethod
    def from_installation(cls) -> "CompilerPaths":
        """Discover Shedskin installation paths.

        Returns:
            CompilerPaths instance with discovered paths

        Raises:
            SystemExit: If lib directory cannot be found
        """
        # Discover shedskin directory
        abspath = os.path.abspath(__file__)
        shedskin_directory = os.sep.join(abspath.split(os.sep)[:-1])

        for dirname in sys.path:
            candidate = os.path.join(dirname, shedskin_directory)
            if os.path.exists(candidate):
                shedskin_directory = candidate
                break

        shedskin_libdir = os.path.join(shedskin_directory, "lib")
        system_libdir = "/usr/share/shedskin/lib"

        # Determine library directories
        if os.path.isdir(shedskin_libdir):
            libdirs = [shedskin_libdir]
        elif os.path.isdir(system_libdir):
            libdirs = [system_libdir]
        else:
            print(
                f"*ERROR* Could not find lib directory in {shedskin_libdir} "
                f"or {system_libdir}.\n"
            )
            sys.exit(1)

        return cls(
            shedskin_lib=Path(shedskin_libdir),
            sysdir=shedskin_directory,
            libdirs=libdirs,
        )

    def get_illegal_keywords(self) -> set[str]:
        """Load C++ reserved keywords from illegal.txt.

        Returns:
            Set of C++ keywords that cannot be used as identifiers
        """
        illegal_file_path = self.shedskin_illegal / "illegal.txt"
        with open(illegal_file_path) as f:
            return {line.strip() for line in f}


@dataclass
class CompilerState:
    """Mutable state during compilation.

    This class holds all the runtime state that changes during
    the compilation process, including type inference data, discovered
    entities, and code generation state.
    """

    # Type inference data
    constraints: Set[Tuple["infer.CNode", "infer.CNode"]] = field(default_factory=set)
    cnode: dict[Tuple[Any, int, int], "infer.CNode"] = field(default_factory=dict)
    types: dict["infer.CNode", Set[Tuple[Any, int]]] = field(default_factory=dict)
    orig_types: dict["infer.CNode", Set[Tuple[Any, int]]] = field(default_factory=dict)

    # Discovered entities
    allvars: Set["python.Variable"] = field(default_factory=set)
    allfuncs: Set["python.Function"] = field(default_factory=set)
    allclasses: Set["python.Class"] = field(default_factory=set)

    # Module tracking
    modules: dict[str, "python.Module"] = field(default_factory=dict)
    main_module: Optional["python.Module"] = None
    module: Optional["python.Module"] = None

    # AST relationships and tracking
    inheritance_relations: dict[
        Union["python.Function", ast.AST],
        List[Union["python.Function", ast.AST]]
    ] = field(default_factory=dict)
    inheritance_temp_vars: dict["python.Variable", List["python.Variable"]] = field(
        default_factory=dict
    )
    parent_nodes: dict[ast.AST, ast.AST] = field(default_factory=dict)
    inherited: Set[ast.AST] = field(default_factory=set)
    assign_target: dict[ast.AST, ast.AST] = field(default_factory=dict)
    from_module: dict[ast.AST, "python.Module"] = field(default_factory=dict)

    # Allocation site tracking
    alloc_info: dict[
        Tuple[str, CartesianProduct, ast.AST], Tuple["python.Class", int]
    ] = field(default_factory=dict)
    new_alloc_info: dict[
        Tuple[str, CartesianProduct, ast.AST], Tuple["python.Class", int]
    ] = field(default_factory=dict)

    # Code generation state
    templates: int = 0
    lambdawrapper: dict[Any, str] = field(default_factory=dict)
    cpp_keywords: Set[str] = field(default_factory=set)
    ss_prefix: str = "__ss_"
    list_types: dict[Tuple[int, ast.AST], int] = field(default_factory=dict)
    tempcount: dict[Any, str] = field(default_factory=dict)

    # AST transformation tracking
    item_rvalue: dict[ast.AST, ast.AST] = field(default_factory=dict)
    genexp_to_lc: dict[ast.GeneratorExp, ast.ListComp] = field(default_factory=dict)
    setcomp_to_lc: dict[ast.SetComp, ast.ListComp] = field(default_factory=dict)
    dictcomp_to_lc: dict[ast.DictComp, ast.ListComp] = field(default_factory=dict)
    bool_test_only: Set[ast.AST] = field(default_factory=set)
    called: Set[ast.Attribute] = field(default_factory=set)
    struct_unpack: dict[
        ast.Assign, Tuple[List[Tuple[str, str, str, int]], str, str]
    ] = field(default_factory=dict)
    augment: Set[ast.AST] = field(default_factory=set)

    # Compilation progress tracking
    iterations: int = 0
    total_iterations: int = 0
    import_order: int = 0
    class_def_order: int = 0

    # Type inference algorithm state (from infer.py)
    added_allocs: int = 0
    added_allocs_set: Set[Any] = field(default_factory=set)
    added_funcs: int = 0
    added_funcs_set: Set["python.Function"] = field(default_factory=set)
    cpa_clean: bool = False
    cpa_limit: int = 0
    cpa_limited: bool = False
    merged_inh: dict[Any, Set[Tuple[Any, int]]] = field(default_factory=dict)

    # Control flow tracking
    loopstack: List[Union[ast.While, ast.For]] = field(default_factory=list)

    # Built-in types (immutable list used during compilation)
    builtins: List[str] = field(default_factory=lambda: [
        "none", "str_", "bytes_", "float_", "int_", "class_",
        "list", "tuple", "tuple2", "dict", "set", "frozenset", "bool_"
    ])

    # UI and progress tracking
    maxhits: int = 0
    terminal: Optional[Any] = None
    progressbar: Optional["ProgressBar"] = None


def get_pkg_path() -> Path:
    """Return the path to the shedskin package.

    Returns:
        Path to shedskin package directory
    """
    pkg_path = Path(__file__).parent
    assert pkg_path.name == "shedskin"
    return pkg_path


def get_user_cache_dir() -> Path:
    """Get user cache directory depending on platform.

    Returns:
        Platform-specific cache directory path

    Raises:
        SystemExit: If platform is unsupported or Windows USERPROFILE not set
    """
    import platform

    system = platform.system()

    if system == "Darwin":
        return Path("~/Library/Caches/shedskin").expanduser()
    elif system == "Linux":
        return Path("~/.cache/shedskin").expanduser()
    elif system == "Windows":
        profile = os.getenv("USERPROFILE")
        if not profile:
            raise SystemExit("USERPROFILE environment variable not set on Windows")
        return Path(profile) / "AppData" / "Local" / "shedskin" / "Cache"
    else:
        raise SystemExit(f"{system} OS not supported")
