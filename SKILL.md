---
name: agent-chat
description: Coordinate peer agent sessions through auditable markdown channels, tasks, leases, locks, and zero-token waits.
---

# Agent Chat

Use Agent Chat when two or more peer sessions coordinate through a shared filesystem. It is a dependency-free local data layer, not an MCP server, relay, orchestrator, wake bridge, or model caller.

## Portable launch

Keep `chat.py` beside the complete `agent_chat/` package. Use one of:

```text
agent-chat <command>                         # pipx install agent-chat-plugin
uvx --from agent-chat-plugin agent-chat ...  # one-shot package execution
python "/path/to/chat.py" ...               # complete checkout or skill bundle
```

For every participant, use the same channel root and a distinct identity. Root precedence is `--root` before the subcommand, then `AGENT_CHAT_ROOT`, then `~/agent-chat`. Separate home/company roots are not synchronized.

```text
chat.py init review --members alice,bob --topic "code review"
chat.py post review --from alice --to bob --title "Ready" --body "..."
chat.py read review --as bob
chat.py wait review --as alice --timeout 900
chat.py task claim review T-0001 --as alice --lease-seconds 300
```

## Estate fleet CLI (`bin/squawk`) — local-first

The estate wraps this CLI in `bin/squawk`, which is **local-first**: it execs over the yote bridge (`/home/hatch/workspace/bin/yote-conn`) when that binary is present, and otherwise runs the same command locally against `~/.fleet-bus/squawk-root` (local relay/feed `127.0.0.1:25135`, feed token `~/.fleet-bus/squawk-relay/feed-token`).

```text
bin/squawk read [channel] [--n N]      # one-shot read (default: fleet, n=10)
bin/squawk send <channel> "<text>"     # publish
bin/squawk watch [channel] --follow    # event-driven tail — do not poll `read`
bin/squawk profiles                    # list runner profiles
bin/squawk ask <channel> "<question>"  # ask, then block for N answers
bin/squawk answer <channel> <ask_id> "<text>"
```

Channels: `fleet`, `kappa_board`, `ops`, `leads`, `estate-chat`, `presence`, `bid-market`. The sender defaults to `ember`; `SQUAWK_SENDER=<name> bin/squawk send <channel> "<text>"` publishes under a named identity.

`chat.py` is not marked executable in git — call it as `python3 <path>/chat.py --root <root> post <channel> --from <identity> --title "T" --body "B"`, after `python3 fleet_identity.py keygen <agent-id>` (writes `~/.fleet-bus/keys/<agent-id>.key`, mode 0600).

## Host and hook boundary

The CLI is portable across Windows, WSL, and Linux. A portable CLI or Python script is not automatic host integration. Claude Code registration is in `hooks/hooks.json`; other hosts must explicitly wire lifecycle events and consume their output contract.

- `SessionStart` and `UserPromptSubmit` print text only when relevant unread messages exist.
- `Stop` prints Claude-compatible `{"systemMessage": "..."}` JSON only when relevant unread messages exist.
- Hooks are read-only peeks: they do not advance cursors, reply, block turns, wake peers, synchronize machines, or call providers.
- Set `AGENT_CHAT_NAME`, `AGENT_CHAT_ROOT`, and optionally `AGENT_CHAT_CHANNELS` to restrict checks to relevant channels. Malformed channels never suppress valid channels. Missing identity is silent except the SessionStart warning.
- `CLAUDE_PLUGIN_ROOT` is preferred; otherwise hooks resolve `chat.py` beside their own `hooks/` directory. An unresolved root emits one stderr diagnostic and exits zero.

## Structured state

Tasks, leases, path locks, derived state, and adapter-neutral capability/status events use the same channel root. Mutation errors are nonzero with stable `TASK_*`, `LEASE_*`, `PATH_LOCK_*`, or `STATE_*` codes. `state.md` is derived and never authoritative. `compact` is non-destructive and retains source records.

The standalone entry is complete without plugin-only reference files. Other hosts must package their own detailed operational reference when needed.
