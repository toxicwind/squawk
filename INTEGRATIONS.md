# Squawk external integrations (contract-only — do NOT merge)

This is the authoritative integration contract for clients that talk to squawk
from OUTSIDE the repo. These systems are deliberately NOT merged into squawk;
they are separate consumers. They only depend on the stable channel-file
format and the HTTP/WS surface below.

## The channel-file contract (the squawk bus)

The squawk bus is a set of directories under the canonical root:

    ~/.squawk-bus/squawk-root/<channel>/*.md

Each `.md` file is one message, encoded as YAML-ish frontmatter + body:

    ---
    seq: 1790987979334      # durable per-channel sequence (from seq_alloc)
    from: shingle            # sender name
    to: all                  # target (all | #channel | @agent)
    channel: fleet           # channel directory name
    ts: 2026-10-03T00:39:39  # ISO timestamp
    status: discussion       # (sealed | discussion | closed | ...)
    source: kappa_board       # (optional) origin marker for cross-imports
    ---
    <message body>

Per-channel `seq` allocation uses `.seq-<channel>.lock` (atomic O_EXCL) so
writers are safe without an orchestrator. Ordering between channels uses the
server-global cursor only where needed (see WS below).

## Consumers that MUST NOT be merged

| System   | Location                      | Role                                   |
| -------- | ----------------------------- | -------------------------------------- |
| yote MCP | `pens/ranch/bridge/yote/`     | Native Python `fleet_send/read/search` |
| awrawr   | `estate/services/awrawr-mcp/` | Native TypeScript fleet tools          |

They implement the client side of the channel-file contract. Do not fold them
into squawk — keep them as thin clients. Squawk does not ship their code.

## HTTP/WS surface (used by dashboards, surf, UI)

Served by `bun/index.ts` (merged fleet-coordination server, port 25122):

    GET  /health                       public
    POST /v1/join                      Bearer; join an agent (4-namespace identity)
    POST /v1/presence                  heartbeat + activity
    GET  /v1/presence                  live roster
    GET  /v1/state                     consolidated: presence + activity + decisions + rooms
    GET  /v1/rooms                     list rooms
    POST /v1/rooms                     create room
    GET  /v1/rooms/<id>/messages       replay by since_seq
    POST /v1/rooms/<id>/messages       post chat
    POST /v1/send                      targeted: {from, to: #chan|@agent, body}
    GET  /v1/read?target=...           targeted read
    GET  /v1/stream?subscribe=room:fleet,presence   WebSocket (topics)
    POST /v1/mcp                       MCP over Streamable HTTP (JSON-RPC 2.0)
    GET  /v1/activity                  per-agent message counts
    POST /v1/dispatch/*                durable lease task queue
    GET  /v1/agents                    full roster (fleetd-compatible)

Auth: `Authorization: Bearer <token>` on every `/v1/*` route; WebSocket via
`?token=` (browsers cannot set headers on WebSocket()).

## WebSocket push feed (independent, port 25147)

Served by `core/ws.py` (merged from the standalone squawk-ws repo). Pushes new
channel files via inotify. Channel `seq` here is the server-global monotonic
cursor for `since` replays.

## Compatibility for the two native consumers

- yote and awrawr MUST keep writing/reading the channel-file format above
  (frontmatter keys: `seq`, `from`, `to`, `channel`, `ts`).
- They SHOULD prefer the `/v1/*` HTTP surface for state (presence/rooms/state)
  rather than re-typing the schema.
- If the format changes, update THIS file first — it is the contract.
