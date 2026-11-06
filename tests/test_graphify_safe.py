"""Tests for the graphify-safe wrapper and its runtime guard (tools/graphify/).

Wrapper allowlist tests need no installation. Guard tests run only when
tools/graphify/install.sh has created .graphify-venv/.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WRAPPER = REPO / "tools" / "graphify" / "graphify-safe.sh"
GUARD = REPO / "tools" / "graphify" / "_graphify_guard.py"
VENV_PY = REPO / ".graphify-venv" / "bin" / "python"

needs_venv = pytest.mark.skipif(not VENV_PY.exists(), reason="graphify-safe not installed")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="bash wrapper")


def _wrapper(*args):
    return subprocess.run(["bash", str(WRAPPER), *args], capture_output=True, text=True, cwd=REPO)


@posix_only
@needs_venv
@pytest.mark.parametrize(
    "args",
    [
        ["install"],
        ["hook", "install"],
        ["add", "https://example.org"],
        ["label", "."],
        ["extract", ".", "--backend", "claude"],
        ["extract", ".", "--backend=claude"],
        ["extract", ".", "--mode", "deep"],
        ["extract", ".", "--model", "x"],
        ["extract", ".", "--dedup-llm"],
        ["extract", ".", "--google-workspace"],
        ["extract", ".", "--no-gitignore"],
        ["extract", ".", "--postgres", "postgres://x"],
        ["extract", ".", "--global"],
        ["cluster-only", ".", "--backend", "claude"],
    ],
)
def test_wrapper_rejects_unsafe_commands(args):
    result = _wrapper(*args)
    assert result.returncode == 2
    assert "graphify-safe:" in result.stderr


def _guarded(code):
    """Run code in a fresh interpreter with the guard loaded first."""
    prog = f"import runpy; runpy.run_path({str(GUARD)!r}); {code}"
    return subprocess.run([sys.executable, "-I", "-c", prog], capture_output=True, text=True)


@pytest.mark.parametrize(
    "code",
    [
        "import urllib.request; urllib.request.urlopen('https://api.anthropic.com')",
        "import socket; socket.create_connection(('example.org', 443))",
        "import subprocess; subprocess.run(['claude', '-p', 'hi'])",
        "import os; os.system('true')",
    ],
)
def test_guard_blocks_network_and_foreign_processes(code):
    result = _guarded(code)
    assert result.returncode != 0
    assert "graphify-safe guard: blocked" in result.stderr


def test_guard_allows_git():
    result = _guarded("import subprocess; subprocess.run(['git', '--version'], check=True)")
    assert result.returncode == 0, result.stderr


@needs_venv
def test_guard_is_autoloaded_in_venv():
    result = subprocess.run(
        [str(VENV_PY), "-c", "import os; print(os.environ.get('GRAPHIFY_SAFE_GUARD_ACTIVE'))"],
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "1"
