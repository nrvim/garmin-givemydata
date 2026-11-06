#!/usr/bin/env bash
# Install graphify into an isolated venv (.graphify-venv/) with hash-pinned
# dependencies and the network/subprocess guard. Does NOT run `graphify install`:
# no skill, no Claude Code hooks, no git hooks, no CLAUDE.md edits.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
VENV="$REPO/.graphify-venv"
PY="${PYTHON:-python3}"

"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || { echo "graphify-safe: Python >= 3.10 required" >&2; exit 1; }

if [ ! -x "$VENV/bin/python" ]; then
  "$PY" -m venv "$VENV"
fi

# --require-hashes: every wheel must match the sha256 in the lockfile.
# --only-binary: never run a setup.py/build backend from a downloaded sdist.
"$VENV/bin/python" -m pip install --quiet --disable-pip-version-check \
  --require-hashes --only-binary=:all: --no-deps \
  -r "$HERE/requirements.lock"

SITE="$("$VENV/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
install -m 0644 "$HERE/_graphify_guard.py" "$SITE/_graphify_guard.py"
echo "import _graphify_guard" > "$SITE/zz_graphify_guard.pth"

"$VENV/bin/python" -c 'import os, sys; sys.exit(0 if os.environ.get("GRAPHIFY_SAFE_GUARD_ACTIVE") == "1" else 1)' \
  || { echo "graphify-safe: guard failed to load" >&2; exit 1; }

echo "graphify-safe: installed $("$VENV/bin/python" -c 'from importlib.metadata import version; print(version("graphifyy"))') in $VENV (guard active)"
echo "Run: tools/graphify/graphify-safe.sh extract ."
