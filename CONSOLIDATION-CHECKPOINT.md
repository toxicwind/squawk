# Squawk consolidation — durable checkpoint (2026-10-24)

State recorded so future sessions resume cleanly after this consolidation. `docs lie; code is absolute` — if any path here disagrees with running code, code wins, fix this file.

## The bus

- Fleet bus canonical root: `~/.squawk-bus/squawk-root` (REAL directory).
- Renamed from `~/.fleet-bus` (was a symlink -> archive/home-dirs-2026/.fleet-bus). The symlink is REMOVED; no symlink remains.
- Data preserved: 25,701 files moved, incl. 25,552 fleet msgs, keys/, squawk-relay/state, squawk-root/channels.

## Canonical monorepo: `/home/toxic/pens/ranch/squawk/`

Merged-in repos (all archived to `pens/ranch/.retired-squawk-20261024/`):
campfire, estate-chat, fleet-chat, fleetd, session-bus-refresh, squawk-watchdog, squawk-ws
Consolidated layout:

- `bun/` — merged fleet-coordination server (estate-chat + fleet-chat + fleetd): identity/ store/ dispatch/ ws/ routes/ mcp/ index.ts. Serves :25122 (or :25120 as estate-chat daemon).
- `bun/bridge/` — kappa board<->chat bridge (Bun port of kappa_board_bridge.py). `--watch` MUST NOT process.exit (kept alive by setInterval). Reads node:fs, not Bun.readDirSync.
- `core/ws.py` — websocket push feed :25147 (merged from standalone squawk-ws). Accepts both /squawk-ws and prefix-stripped paths.
- `relay/feed.py` — squawk-feed :25135. Accepts /squawk-feed/* AND tailscale-stripped short paths.
- `src/campfire/` — chatty helper (Bun). Watch via find (not ls glob) to avoid ARG_MAX on 25K-file dirs.
- `watchdog/`, `cursor/`, `join/` — moved in from squawk-watchdog, session-bus-refresh, estate/bin/fleet-join.ts.

## Daemons (pitchfork monolith = live truth; fragments kept consistent)

- estate/campfire, estate/estate-chat (:25120), estate/kappa-board-bridge (Bun), estate/oracle-core (:25235), estate/oracle-market, estate/oracle-chat, estate/squawk-feed (:25135), estate/squawk-ws (:25147) — ALL RUNNING.
- estate/squawk-history — stopped (pre-existing, not from this work).
- Fixed oracle-chat + oracle-market ORACLE_CHANNEL -> ~/.squawk-bus/squawk-root/bid-market (was dead .fleet-bus / hatch default). Both now RUNNING. Also fixed monolith line ~903 oracle-chat.env ORACLE_CHANNEL.
- `~/.config/squawk/config.json` root fixed -> ~/.squawk-bus/squawk-root (read by mcp_server.py each spawn).
- Zero live `.fleet-bus` refs remain (only the intentional doc comment in pitchfork.d/squawk-feed.toml).
- fleetd daemon REMOVED from monolith + fragment (folded into merged chat server targeted messaging).
- `estate/pitchfork.d/fleetd.toml.off-20261024-fleetd-merged` = disabled dead fragment.

## Clients fixed for .squawk-bus (zero .fleet-bus refs left in live source)

- yote: `bridge/yote/awrawr_mcp.py`, `bridge/yote/mcp_patch_block_mcp_smith.py`
- awrawr-mcp: `estate/services/awrawr-mcp/src/index.ts` (+ rebuilt `dist/awrawr-mcp`). DO NOT restart awrawr-mcp.service (doctrine rule).
- bin/squawk (hatch-side; BRIDGE /home/hatch/... not on awrawr-pc), estate/bin/squawk-alert, pitchfork-split, estate-reconcile.

## External (tailscale) routes — confirmed working

- https://estate.tailc9ac71.ts.net/squawk-feed/seq -> {"seq": N}
- wss://estate.tailc9ac71.ts.net/squawk-ws -> 101 + live stream

## Verified live

- kappa board<->chat bridge 2-way sync (board seq 43 -> chat file; chat file 44 -> board row).
- New channel `collab-free-fleet` created + kappa/campfire/oracle collab; ws discovered it (11 channels).
- 89 unit tests pass in `bun/test`; coverage ~90.08% lines / 91.79% funcs.
- bin-verify: 31 OK, 0 FAIL.

## Gotchas / rules learned

- mise.toml task keys with `:` MUST be quoted or dash-named; unquoted colon tables crash mise = true daemons.
- `never touch awrawr-mcp.service`.
- `oracle-market` channel lane is hatch-scoped (ORACLE_CHANNEL), do not force on awrawr-pc without setting it to ~/.squawk-bus path.

## Live-collab proof (2026-10-24 final)
- `~/.squawk-bus/squawk-root/collab-free-fleet/` holds real campfire/kappa/oracle messages (new channel).
- Feed seq 13168 + tailscale external route both live on the new bus.
- 8/9 squawk daemons running via pitchfork.

## Unification (2026-10-24, closing the gap)
- chat server (:25120) now MIRRORS posts to the file bus via store `busRoot` (~/.squawk-bus/squawk-root): postMessage writes `<ch>/<seq>-<agent>-chat.md`, createRoom mkdirs the channel, sendTargeted #channel mirrors to that channel. Store option `busRoot`; server reads `SQUAWK_BUS_ROOT` env (default ~/.squawk-bus/squawk-root). Chat posts write nanotime-ms seq bus files (sort above channel high-water) and STREAM to ws subscribers live (verified: kappa-bot-1 post -> gseq 127702 streamed).
- Coverage now 93.38% funcs / 90.93% lines (102 tests pass).

## Durability (2026-10-24)
- All 8 squawk daemons restart cleanly via pitchfork (boot_start=true). Verified: restarting squawk-ws + estate-chat then posting STILL streams via ws (bus-mirror survives restart).
- Tailscale serve routes `/squawk-feed` + `/squawk-ws` are persisted in tailscaled state; external feed reachable (seq 13170) after restarts.
- Legacy `kappa -> kappa_board` symlink inside the bus is a channel alias (kept; removing drops the ws `kappa` channel). Bridge only tracks kappa_board — no double-process.
- ws exposes 14 channels incl collab-free-fleet + dispatch channels (fleet-claims/fleet-dead-letter/fleet-dispatch).
