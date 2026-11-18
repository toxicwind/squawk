# agent-chat vs prior art (honest comparison)

Verified 2026-07-17 against each project's primary sources (repo files / arXiv). Star
counts and maturity drift; this is a mid-2026 snapshot of a young space. Claude Code's
native cross-session messaging was verified against its official documentation and
v2.1.224 release notes on 2026-08-11.

## Where each one sits

| Dimension | **agent-chat** | Turnfile | tap | TICK.md | planning-with-files |
|---|---|---|---|---|---|
| Topology | **peer, no required arbiter** | peer + **mandatory human maintainer** | peer transport | human + agents | single-agent |
| Transport | folder of md messages, **multi-channel** | governance files (TURNFILE.yaml + MAILBOX.md + WORKLOG.md) | `.tap-comms/` file messages (Node) | single `TICK.md` kanban | 3 planning files |
| Wait-for-reply | **autonomous sleep-poll, 0 tokens, cross-platform** | human-on-the-loop + notification protocol | notification (live delivery experimental) | pull-before-write | n/a |
| Human required? | **no** (governance is opt-in) | **yes** — merge/veto/conflict are maintainer-only | no (but setup-heavy) | optional | n/a |
| Windows | **yes** (polling; no inotify needed) | n/a (protocol docs) | Node >= 22.6 | git-based | any |
| Setup | **1 Python file, stdlib** | protocol docs + validation tooling | npm + guarded `.mcp.json` | CLI + MCP server | `SKILL.md` |
| Audit trail | git-committable md folder | `WORKLOG.md` + git | delivery evidence | every change = a commit | files on disk |
| License | Apache-2.0 | Apache-2.0 | permissive | MIT | MIT |
| Maturity | v0 | 7 stars | 19 stars (0.6.x preview) | ~28 stars | 25.4k stars |

## The one-line difference from each

- **vs Turnfile** — Turnfile's whole point is a **human maintainer as arbiter** with
  merge and veto authority (SPEC section 3; `docs/HUMAN_GOVERNANCE.md`: "human-on-the-loop,
  not human-in-the-loop", maintainer holds merge authority and tie-breaking). agent-chat
  is **peers with no required boss**; a human-arbiter band is opt-in, not the core.
- **vs tap** — tap is a **Node CLI message-transport** between heterogeneous runtimes,
  setup-heavy (`.mcp.json`, profiles), 1:1-leaning, live delivery still experimental.
  agent-chat is **one stdlib file + a folder**, group-chat native, autonomous wait built in.
- **vs TICK.md** — TICK genuinely delivers git-as-live+audit, but as a **single-file
  kanban**. agent-chat is a **folder of message files across multiple channels** (a chat,
  not a board).
- **vs planning-with-files** — proves the `SKILL.md` distribution path (60+ agents) but
  is **single-agent** persistence; "multi-agent shared state" is an unelaborated tagline.

## What agent-chat reuses (deliberately, not reinvented)

- Message-with-metadata files -> aligned with tap.
- Atomic claim + git-as-audit -> the pattern TICK.md proved.
- `SKILL.md` cross-tool distribution -> the path planning-with-files proved.
- Optional human governance bands -> the model Turnfile formalizes (here opt-in).

## Claude Code native cross-session messaging

Claude Code `v2.1.224+` adds **Cross-session messaging**, using `ListAgents` for discovery
and `SendMessage` for direct text delivery between Claude Code sessions. It is a real
overlap in peer-session messaging, but it is not the same product surface:

| Dimension | agent-chat | Claude Code native |
|---|---|---|
| Scope | Claude Code, Codex, Cursor, OpenCode; mixed tools | Claude Code sessions only |
| Transport | Markdown files in shared folders and channels | Native session messaging |
| Platform | Windows, WSL, Linux | macOS/Linux/WSL2; not native Windows |
| Workflow | Cursors, atomic claims, replayable audit trail, zero-token `wait` | Direct session delivery; no file-backed protocol |

The native feature makes the Claude-specific unread-notification hook layer partially
redundant on supported platforms. It does not subsume this repository's cross-tool,
Windows, file/audit, multi-channel, claim/cursor, or zero-token-wait scope.

## The unsolved combination agent-chat targets

**Peer (no required arbiter) + a folder of messages across multiple channels +
autonomous cross-platform token-free wait.** No verified prior-art project, including
Claude Code's native path, delivers all three together. The riskiest unproven primitive
across the whole space is a
battle-tested Windows-compatible wait-without-token-burn — agent-chat's sleep-poll is
the conservative, working baseline.

## Sources

Turnfile: github.com/snapsynapse/turnfile (SPEC.md, docs/HUMAN_GOVERNANCE.md) ·
tap: github.com/HUA-Labs/tap (README.md), arXiv:2606.14445 ·
TICK.md: github.com/Purple-Horizons/tick-md ·
planning-with-files: github.com/othmanadi/planning-with-files
