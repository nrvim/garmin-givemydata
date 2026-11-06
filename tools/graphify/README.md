# graphify-safe — code-only, offline knowledge graph

A hardened way to run [graphify](https://github.com/Graphify-Labs/graphify)
(`graphifyy` on PyPI) on this repository. Code is parsed locally with
tree-sitter. Nothing is sent to an LLM provider, and no hooks, skills or MCP
servers are installed.

## Usage

```bash
tools/graphify/install.sh                       # once: isolated venv + guard
tools/graphify/graphify-safe.sh extract .       # build graphify-out/graph.json
tools/graphify/graphify-safe.sh cluster-only .  # GRAPH_REPORT.md + graph.html
tools/graphify/graphify-safe.sh query "garmin login flow"
```

Allowed commands are `extract`, `cluster-only`, `query`, `path` and `explain`.
Everything else is refused, including `install`, `hook`, `add`, `label`, `serve`
and `watch`.

## Protection layers

| Layer | What it does |
|---|---|
| Pinned supply chain | `requirements.lock` pins `graphifyy==0.9.90` and every dependency with sha256 hashes. Install uses `--require-hashes --only-binary=:all:`, so no sdist build code runs. The lock contains no LLM SDKs. |
| Isolated venv | Installed in `.graphify-venv/` (gitignored), not in the system or user site. |
| No integration | `graphify install` is never run, so there is no PreToolUse hook, no skill, no CLAUDE.md edit, no git hooks and no MCP server. |
| Command/flag allowlist | `extract` always gets `--code-only`. `--backend`, `--model`, `--mode`, `--dedup-llm`, `--google-workspace`, `--postgres`, `--cargo`, `--global` and `--no-gitignore` are rejected. `cluster-only` always gets `--no-label`. |
| Clean environment | `env -i`, so no API keys and no proxy variables. `PATH` holds only the venv and `git`, so the `claude` CLI can't be found. `HOME` is a throwaway directory. `GRAPHIFY_NO_AUTO_REFRESH=1`, `GRAPHIFY_QUERY_LOG_DISABLE=1`, `GRAPHIFY_GOOGLE_WORKSPACE=0`, and `GRAPHIFY_BACKEND=none` for newer versions. |
| Runtime guard | `_graphify_guard.py` loads through a `.pth` file in the venv, so it also covers worker processes. It installs a PEP 578 audit hook, which can't be removed. Any socket connect or DNS lookup, any urllib/http.client request, and any subprocess other than `git` or the venv's Python raises `PermissionError`. |
| File excludes | graphify follows `.gitignore`. On top of that, `.graphifyignore` excludes `.env*`, session JSON, `*.db`, FIT files, exports, browser profiles and logs. |
| Output | `graphify-out/` is gitignored, so the map of the code isn't committed. |

## Audit findings (graphifyy 0.9.90)

- `GRAPHIFY_BACKEND` does **not** exist in 0.9.90. It only appears in newer
  releases. On its own it would not have protected this version.
- `extract` with no flags auto-selects an LLM provider from any API key in the
  environment. The order is Gemini, Kimi (Moonshot, China), Claude, OpenAI,
  DeepSeek, Azure, Bedrock (triggered by a bare `AWS_REGION`/`AWS_PROFILE`),
  then Ollama. Docs are then sent to that provider.
- `cluster-only` and `label` name communities with an LLM. With no key set, they
  silently fall back to the `claude` CLI and send node labels to Anthropic. The
  wrapper forces `--no-label`, and the guard blocks the `claude` subprocess
  anyway. The second protection was verified by running `graphify label`
  directly.
- Every invocation "auto-refreshes" installed skill files under `~` and the
  current directory unless `GRAPHIFY_NO_AUTO_REFRESH=1` is set.
- `graphify install` adds a Claude Code PreToolUse hook that fires before every
  Read, Glob, Grep and shell reader. It injects graph text that comes from repo
  content into the agent context, which is a prompt-injection channel.
- `extract` runs only `git ls-files` as a subprocess. There is no telemetry.

## Upgrading

Review the new version's diff first. Look especially at `llm.py`, `cli.py`
(the extract and cluster-only paths), `__main__.py` (auto-refresh) and
`security.py`. Then pin it:

```bash
echo "graphifyy==<new>" > tools/graphify/requirements.in
uv pip compile tools/graphify/requirements.in --universal --python-version 3.10 \
  --generate-hashes -o tools/graphify/requirements.lock
rm -rf .graphify-venv && tools/graphify/install.sh
pytest tests/test_graphify_safe.py
```

## Optional: Claude Code permission rules

To stop Claude Code from calling graphify outside the wrapper, add this to
`.claude/settings.json` yourself:

```json
{
  "permissions": {
    "allow": ["Bash(tools/graphify/graphify-safe.sh *)"],
    "deny": [
      "Bash(graphify *)",
      "Bash(graphify-mcp*)",
      "Bash(.graphify-venv/bin/graphify*)",
      "Bash(uvx graphify*)",
      "Bash(pipx run graphify*)",
      "Bash(pip install graphify*)",
      "Bash(uv tool install graphify*)",
      "Bash(pipx install graphify*)"
    ]
  }
}
```
