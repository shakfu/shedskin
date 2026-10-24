# SHED SKIN Python-to-C++ Compiler
# Copyright 2005-2026 Mark Dufour and contributors; GNU GPL version 3 (See LICENSE)
"""Unit tests for scripts/escape_census.py (see docs/dev/type-alloc.md).

The census installs a profiler and keeps module state, so it runs in a
subprocess.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "escape_census.py"

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 13), reason="needs frame.f_locals proxies (3.13+)"
)


def census(*args):
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_selftest():
    assert "selftest ok" in census("--selftest")


def test_program(tmp_path):
    prog = tmp_path / "prog.py"
    prog.write_text(
        "import sys\n"
        "class P:\n"
        "    pass\n"
        "KEEP = []\n"
        "def f():\n"
        "    t = P()\n"
        "    KEEP.append(P())\n"
        "    return P()\n"
        "def main():\n"
        "    for _ in range(int(sys.argv[1])):\n"
        "        f()\n"
    )
    out = census(str(prog), "5")
    rows = {
        line.split()[0]: line.split()[1:]
        for line in out.splitlines()
        if line.startswith(("P ", "total "))
    }
    # per call: t is L0, the returned P is L1, the appended P escapes
    assert rows["P"] == ["5", "5", "0", "5", "15"]
    assert "f, P" in out
