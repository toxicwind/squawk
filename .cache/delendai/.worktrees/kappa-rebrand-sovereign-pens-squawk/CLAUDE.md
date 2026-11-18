# CLAUDE.md - agent-chat-plugin

# Agent Collaboration

## Quick reference

- Repo: `n24q02m/agent-chat-plugin`
- Description: Peer AI agents coordinate through markdown messages in shared channel folders — no orchestrator, autonomous zero-token waiting, cross-platform.
- License: Apache-2.0
- Design goal: dependency-free Python stdlib CLI (`chat.py` plus `agent_chat/`).

## Build & Test

Run `mise install` for repository-pinned Python and Ruff. A complete checkout
runs without a build; the installed CLI also requires the `agent_chat/` package.

```sh
mise run lint    # ruff check .
mise run smoke   # python chat.py --help
python -m unittest discover -s tests -p "test_*.py" -v
```

Use a temporary `--root` for send/read and task claim/done behavior checks;
`--help` alone does not exercise the structured stores. For package checks,
install with `python -m pip install .` in an isolated virtual environment and
run `agent-chat` outside the checkout. PyPI does not install skills or hooks.

## Runtime and guidance

- `chat.py`: CLI, channels, messages, cursors, wait and capability/status events.
- `agent_chat/`: task models/stores, leases, path locks and derived state.
- `hooks/`: read-only inbox notices; Claude Code lifecycle registration is in
  `hooks/hooks.json`. Other hosts need explicit lifecycle/output adaptation.
- Root `SKILL.md` is the standalone skill; `skills/agent-chat/SKILL.md` and
  `commands/agent-chat.md` are plugin guidance. Keep their commands and README
  aligned, and keep CLAUDE.md as this guidance's mirror.
- Task/path mutation locks are OS advisory locks, not stale-mtime directories.
  Their regular lock files persist after release; recovery of expired domain
  leases and crash transaction markers remains explicit.
- No MCP transport, LLM/completion, embedding, rerank, graph-service or relay
  calls exist here. Capability events do not execute agents; state/compact
  derive local records without calling a model.
- Separate home/company roots are not synchronized by this package. Preserve
  user-owned host configuration; a portable CLI is not automatic hook wiring.

## Release

Manual `workflow_dispatch` on `cd.yml` (choose `beta` or `stable`).
python-semantic-release handles the version bump, CHANGELOG, tag, GitHub Release,
and PyPI publish (via Trusted Publishing / OIDC).

## Conventions

- Commits: only `feat:` and `fix:` prefixes.
- Keep it dependency-free (Python stdlib only).
- No secrets — this CLI has none (local filesystem only, no credentials).
