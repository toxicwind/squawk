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

## Estate fleet CLI (`bin/squawk`) — local-first

`bin/squawk` is the estate-side fleet CLI over the same squawk root. **Local-first rule (2026-10-21):** it execs over the yote bridge (`/home/hatch/workspace/bin/yote-conn`) when that binary exists; when it is absent — the common case outside the hatch cell — it runs the _same_ command locally against `~/.fleet-bus/squawk-root`, with the local relay/feed on `127.0.0.1:25135` and the feed token in `~/.fleet-bus/squawk-relay/feed-token` (0600, never printed). Both lanes are plain POSIX shell over the same root, so they are semantically identical.

```text
bin/squawk read [channel] [--n N]      # one-shot read (default: fleet, n=10)
bin/squawk send <channel> "<text>"     # publish
bin/squawk watch [channel] --follow    # event-driven tail — do not poll `read`
bin/squawk watch [--since SEQ]         # one-shot: messages newer than SEQ
bin/squawk profiles                    # list runner profiles
bin/squawk ask <channel> "<question>"  # ask, then block for N answers
bin/squawk answer <channel> <ask_id> "<text>"
bin/squawk --profile NAME <cmd...>     # act under a runner profile identity
```

Channels: `fleet`, `kappa_board`, `ops`, `leads`, `estate-chat`, `presence`, `bid-market`. Channel names, `from:`/`to:` sender names and the `runners.yml` profile identities are **protocol values, not branding** — never rename them with the brand.

The sender defaults to `ember`; `SQUAWK_SENDER=<name> bin/squawk send <channel> "<text>"` publishes under a named identity.

`chat.py` is the file-level CLI underneath. It is **not executable** in git (mode `100644`) — always call it as `python3 <path>/chat.py --root <root> post <channel> --from <identity> --title "T" --body "B"`. Posts are HMAC-signed: mint a key with `python3 fleet_identity.py keygen <agent-id>` (writes `~/.fleet-bus/keys/<agent-id>.key`, mode 0600).

## Release

Manual `workflow_dispatch` on `cd.yml` (choose `beta` or `stable`).
python-semantic-release handles the version bump, CHANGELOG, tag, GitHub Release,
and PyPI publish (via Trusted Publishing / OIDC).

## Conventions

- Commits: only `feat:` and `fix:` prefixes.
- Keep it dependency-free (Python stdlib only).
- No secrets — this CLI has none (local filesystem only, no credentials).

<!-- delendai:begin -->

# delendai host hints (auto-generated)

See `docs/delendai/host-hints/agent-instructions.generated.md` for the live agent catalog.

- Bootstrap §7 (repo-level rules) is in effect.

<!-- delendai:end -->
