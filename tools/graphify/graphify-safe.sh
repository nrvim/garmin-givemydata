#!/usr/bin/env bash
# graphify-safe: run graphify in code-only, offline mode.
#
# Layers of protection (each one is enough on its own for the default flow):
#   1. Subcommand + flag allowlist: only local, read-only/graph-building commands.
#   2. `extract` always gets --code-only; `cluster-only` always gets --no-label.
#   3. Clean environment (env -i): no API keys, no proxy settings, no `claude`
#      CLI on PATH, throwaway HOME so nothing is written to ~/.claude or ~/.cache.
#   4. Audit-hook guard inside Python: any network call or non-git subprocess
#      raises PermissionError.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
VENV="$REPO/.graphify-venv"
GRAPHIFY="$VENV/bin/graphify"

die() { echo "graphify-safe: $*" >&2; exit 2; }

[ -x "$GRAPHIFY" ] || die "not installed; run tools/graphify/install.sh first"
[ $# -ge 1 ] || die "usage: graphify-safe.sh {extract|cluster-only|query|path|explain|--version} [args]"

cmd="$1"; shift
args=()

case "$cmd" in
  --version|-V|--help|-h)
    args=("$cmd")
    cmd=""
    ;;
  extract)
    # Only flags that keep processing local. Everything that selects a backend,
    # a model, deep/LLM modes, Google Workspace export, Postgres, cargo, the
    # global graph, or that disables .gitignore is rejected.
    while [ $# -gt 0 ]; do
      case "$1" in
        --code-only|--no-cluster|--no-dedup|--allow-partial|--timing|--force) args+=("$1") ;;
        --out|--output|--max-workers)
          [ $# -ge 2 ] || die "$1 needs a value"; args+=("$1" "$2"); shift ;;
        --out=*|--output=*|--max-workers=*) args+=("$1") ;;
        -*) die "flag not allowed in safe mode: $1" ;;
        *) args+=("$1") ;;
      esac
      shift
    done
    args+=("--code-only")
    ;;
  cluster-only)
    while [ $# -gt 0 ]; do
      case "$1" in
        --no-viz) args+=("$1") ;;
        --no-label) ;;
        -*) die "flag not allowed in safe mode: $1" ;;
        *) args+=("$1") ;;
      esac
      shift
    done
    args+=("--no-label")
    ;;
  query|path|explain)
    # Pure graph lookups on graphify-out/graph.json. Query logging is disabled below.
    args=("$@")
    ;;
  *)
    die "command '$cmd' is blocked in safe mode (only extract, cluster-only, query, path, explain)"
    ;;
esac

# Minimal PATH: the venv and a private dir that exposes only `git`.
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
mkdir -p "$SANDBOX/bin" "$SANDBOX/home"
if GIT_BIN="$(command -v git 2>/dev/null)"; then
  ln -s "$GIT_BIN" "$SANDBOX/bin/git"
fi

run=(env -i
  "PATH=$VENV/bin:$SANDBOX/bin"
  "HOME=$SANDBOX/home"
  "LANG=${LANG:-C.UTF-8}"
  "PYTHONNOUSERSITE=1"
  "GRAPHIFY_BACKEND=none"
  "GRAPHIFY_NO_AUTO_REFRESH=1"
  "GRAPHIFY_QUERY_LOG_DISABLE=1"
  "GRAPHIFY_GOOGLE_WORKSPACE=0"
  "GRAPHIFY_NO_TIPS=1"
  "GRAPHIFY_SKIP_HOOK=1"
)

# Refuse to run if the guard is not active in this interpreter.
"${run[@]}" "$VENV/bin/python" -c \
  'import os, sys; sys.exit(0 if os.environ.get("GRAPHIFY_SAFE_GUARD_ACTIVE") == "1" else 1)' \
  || die "network guard not active; re-run tools/graphify/install.sh"

# No `exec`: the EXIT trap must still remove the sandbox directory.
if [ -n "$cmd" ]; then
  "${run[@]}" "$GRAPHIFY" "$cmd" ${args[@]+"${args[@]}"}
else
  "${run[@]}" "$GRAPHIFY" ${args[@]+"${args[@]}"}
fi
