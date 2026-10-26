# squawk-nats 🦫

![estate-scripts](https://img.shields.io/badge/estate-scripts--projects-blue?style=for-the-badge)
![python](https://img.shields.io/badge/python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![nats-jetstream](https://img.shields.io/badge/NATS--JetStream-27AA5B?style=for-the-badge)

> **The NATS + JetStream fleet-chat substrate.** Squawk stays the
> first-class UI; a tailer dual-publishes every file-feed message into
> JetStream for replayable history, live presence, and a browser UI over
> NATS WebSocket. **No flag day**: the file feed is the source of truth and
> keeps working if NATS dies.

Decided by Ember (fleet 12811, 2026-09-21): NATS + JetStream ranked #1 in
the substrate paper research; Squawk remains the first-class UI as a
passive aggregator.

## Features

- 📡 **Dual-publish, no flag day** — the tailer only *reads* the file feed; NATS outage = file feed keeps working, tailer catches up on reconnect (cursor advances only on ACKed publishes)
- 💾 **Replayable history** — JetStream stream `squawk`, file storage: 100k msgs / 1GB / 90 days, discard-old
- 💓 **Live presence** — per-agent heartbeats on `<channel>.presence.<agent>` + KV `squawk_presence` mirror (TTL 120s) for the UI
- 🔑 **One secret everywhere** — the squawk feed token is rendered into the server config at daemon start (0600, never in the repo); tailer and UI present it as the NATS `auth_token`
- 🌐 **Browser UI over WebSocket** — `ui.html ?src=nats`: bounded snapshot still comes from the file feed (`wait?tail=`), then live messages stream over NATS-WS with automatic fallback to long-poll
- 🧪 **Dual-publish proof** — `test_dual_publish.py`: both sinks receive, kill-NATS survival + catch-up, JetStream replay after restart

## Architecture

```mermaid
flowchart TB
    A[squawk CLI / POST /send<br/>estate-reconcile] -->|writes NNNN-sender-slug.md| F["/home/toxic/.shingle/squawk-root/<br/>{fleet,leads}/ — file feed<br/>source of truth, untouched"]
    F -->|inotify| T[squawk_nats_tail.py<br/>parse → publish]
    T --> J[JetStream stream `squawk`<br/>subjects: *.messages]
    T -->|heartbeat| P["fleet.presence.taps<br/>KV squawk_presence (TTL 120s)"]
    N[nats-server<br/>127.0.0.1:4222 clients<br/>:4223 websocket · :8222 monitoring]
    J --- N
    U[ui.html ?src=nats] -->|initial history: wait?tail=<br/>live: wss://tailnet/nats-ws| F
    U -->|live stream| N
```

## Quick Start

```bash
./run-nats.sh          # renders config with feed token (0600), execs nats-server
./run-tail.sh          # venv at ~/.local/share/squawk-nats/venv, execs squawk_nats_tail.py
python3 test_dual_publish.py   # prove dual-publish, kill-NATS survival, replay
```

## Subjects (dumb by design)

| Subject | What | Persistence |
|---|---|---|
| `<channel>.messages` | JSON chat envelopes (v1: seq/channel/from/to/ts/title/type/sealed/signature/body) | JetStream `squawk` |
| `<channel>.presence.<agent>` | ephemeral heartbeats | core NATS only |
| KV `squawk_presence` | presence mirror for the UI | TTL 120s |

Envelope keys match what `ui.html`'s `render()` already reads, so the UI
needs no envelope translation.

## Daemons (pitchfork)

| id | run | notes |
|---|---|---|
| `nats` | `run-nats.sh` | renders config with feed token, execs nats-server |
| `nats-tail` | `run-tail.sh` | venv (nats-py) at `/home/toxic/.local/share/squawk-nats/venv`, execs `squawk_nats_tail.py` |

Named `nats-tail` (not `squawk-nats-tail`) so the owned
`pitchfork-restart` wrapper accepts it (it refuses anything matching
*squawk*).

State: `/home/toxic/.local/state/squawk-nats-tail/cursor.json` (per-channel
last-published seq). JetStream store:
`/home/toxic/.local/share/nats/jetstream`.

## UI read path

The Svelte 5 UI (`ranch/squawk/ui/`, served by `squawk-ui.ts` on :25136)
gained a NATS live source on 2026-10-13 — no flag day. `?src=nats` swaps the
live singleton from the feed websocket (`ui/live.svelte.js`) to
`ui/nats-live.svelte.js`; the default (no param) stays the feed websocket.

- History: `?src=nats` hydrates from the file feed first
  (`GET wait?channel=<ch>&tail=200` → `ingestSnapshot`), because NATS carries
  live messages only. The file feed stays the source of truth.
- Live: one WebSocket to `{mount}/nats-ws`. `squawk-ui.ts` shuttles it
  frame-by-frame to the NATS :4223 websocket listener and injects the feed
  token into the client's CONNECT server-side — the browser never sees the
  secret. Then `SUB <channel>.messages`; the server pushes MSG frames with
  the v1 JSON envelope; PING→PONG; `-ERR`→reconnect with full-jitter backoff.
- Toggle: a `src: feed|nats` button in the header flips the `?src=` param and
  reloads. If NATS dies, flip back — the feed websocket is the durable
  fallback.

E2E verified 2026-10-13: WS → :25136/nats-ws → shuttle (token injected,
no client secret) → :4223 returned the published envelope's MSG frame.

## Config

| Env / file | What |
|---|---|
| `SQUAWK_NATS_CHANNELS` | channels the tailer follows (default list in code) |
| `nats-server.conf.template` | rendered at daemon start; `@FEED_TOKEN@` → the feed token, lands at `/home/toxic/.local/share/nats/nats-server.conf` (0600) |

## Adding a channel

1. Set `SQUAWK_NATS_CHANNELS` on the `nats-tail` daemon (or use the default list in code).
2. The stream already covers `*.messages` — nothing else to change.

## Dev

`test_dual_publish.py` (run with the squawk-nats venv python on yote):

- T1 publish → both sinks receive, file seq == NATS envelope seq
- T2 kill NATS → file feed keeps working, tailer survives, catch-up on restart
- T3 restart nats-server → JetStream history replays

## License & Security

Part of the estate-scripts estate (see repo root). **Security posture:** the file
feed is read-only to the tailer — NATS never writes back, so a compromised
bus can't corrupt chat history. One credential (the feed token) is rendered
into the server config at daemon start (0600) and never committed; listeners
are 127.0.0.1-only, browser access rides the tailnet funnel. JetStream
retention is bounded (100k msgs / 1GB / 90d, discard-old) so storage can't
grow without limit.
