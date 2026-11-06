---
name: ponytail-help
description: >
  Quick reference for Ponytail Safe: coding levels, safety levels, features,
  commands and skills. One-shot display. Use for /ponytail-help, "ponytail help",
  "how do I use ponytail safe".
---

# Ponytail Safe Help

Display this reference card when invoked. One-shot: change nothing, write nothing.

## Coding mode (per session)

| Mode | Command | What changes |
|------|---------|--------------|
| **lite** | `/ponytail lite` | Build what was asked, name the smaller option in one line. |
| **full** | `/ponytail` | The smallest complete change, a check where the logic needs one. Default. |
| **ultra** | `/ponytail ultra` | Also questions the request before building. |
| off | `/ponytail off`, "stop ponytail", "normal mode" | Ponytail off. |

`/ponytail default lite|full|ultra|off` sets the mode new sessions start in.

## Safety level (persists)

| Level | Command | Allows |
|-------|---------|--------|
| **safe** | `/ponytail level safe` | Ruleset, subagent ruleset, local cost and token ledger (numbers only). Default. |
| **controlled** | `/ponytail level controlled` | Adds a local audit log; the codebase map after `/ponytail allow map`. |
| **developer** | `/ponytail level developer` | Adds task names (`allow names`) and import of past sessions (`allow import`). |

Every feature beyond safe stays off until you allow it by name. `/ponytail deny <feature>` turns one off.
Only a prompt you type yourself can change a level or a permission.

## Commands and skills

| Command | What it does |
|---------|--------------|
| `/ponytail status` | Dashboard: level, features, cost, tokens and turns per project. |
| `/ponytail import` | Dry run: counts past session transcripts, reads none. `/ponytail import apply` imports. |
| `/ponytail-review` | Quality review of a diff: bugs, security, load, missing tests, what to cut. |
| `/ponytail-audit` | The same review for a whole repo, ranked. |
| `/ponytail-debt` | Collects `shortcut:` comments into a ledger. |
| `/ponytail-gain` | Upstream Ponytail's benchmark scoreboard. |
| `/ponytail-help` | This card. |

## Where data lives

Only on this machine, in `~/.config/ponytail-safe/` (`$XDG_CONFIG_HOME` respected):
`config.json`, `ledger.csv`, `audit.jsonl`, `modes/`, `active`. Delete that folder to reset everything.
