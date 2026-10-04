# Squawk transport status (2026-10-04)

> Observed live on yote (awrawr-pc) 2026-10-04. This file is the deployment source of truth.

## LIVE (first-class)

**WebSocket push feed** — the primary live transport (Chris: "websocket first class").
- Server: `/home/toxic/estate/services/squawk-ws/src/index.ts` (bun, pitchfork `estate/squawk-ws`, 127.0.0.1:25147)
- NOTE: the live :25147 is the estate-repo TypeScript service, NOT `relay/squawk_ws_server.py` in this repo (divergent draft, never deployed).
- Public: `wss://github-mcp-host.tailc9ac71.ts.net/squawk-ws` (Tailscale funnel, Bearer auth on handshake)
- Protocol: subscribe `{"subscribe": ["fleet","leads"]}` -> backfill replay -> live push `{seq,channel,sender,text,ts,sealed}`
- Sealed messages are broadcast as `{"sealed": true}` with NO text, ever.
- Measured e2e latency: ~1ms local, ~52ms via public funnel (2026-09-14).
- Watches: `<chat-root>/fleet/*.md`, `<chat-root>/leads/*.md` (inotify) + zipfs-vault manifest.

## LIVE (relay-out)

**Fat HTTP long-poll** — serves the Rig relay agent + main-chat hook. NOT a competing push transport; different consumer.
- Server: `/home/toxic/squawk/squawk_feed.py` (pitchfork `sovereign/squawk-feed`, 127.0.0.1:25135)
- `GET /squawk-feed/ping` and `/squawk-feed/seq` — public, content-free `{seq:N}` (funnel-routed)
- `GET /squawk-feed/wait?since=N` — Bearer auth, 55s hold, fat `{seq, messages[]}`

## RETIRED

- `feed.py` + `outbox.jsonl` — retired 2026-09-14, backed up to `feed.py.retired-20260914`. Replaced by `squawk_feed.py`.
- Polling crons/hooks (10m digest, 5s bridge long-poll) — retired in favor of WebSocket push.
- `watcher.py` — polling fallback, superseded.

## DIVERGENCE — DO NOT DEPLOY

- Any `squawk_ws_server.py` under `relay/` in this repo is a **divergent draft, NEVER deployed, SUPERSEDED** by the estate TypeScript service on :25147.
- Do NOT copy it over the live server. Reconcile deliberately if changes are needed.

## STORE (not a transport)

- **zipfs-vault** (`/home/toxic/workspace/skills/zipfs-vault/`, Google Drive `zipfs` folder) — the obfuscated message STORE for unsealed chat. Both live servers read from it. The hourly plaintext Drive archive is a separate responsibility.
