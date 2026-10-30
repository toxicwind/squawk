---
agent: tau
status: pending
---

# LG fleet: find the failed chat and recover

**Priority:** HIGH - architect order 2026-10-29 ("target lg fleet find the
failed chat").

**Background:**
- lg-webos was orphaned into pens/estate/products/estate-orphans/devices/lg-webos
  during the estate single-truth cutover (pairs source map:
  devices/lg-webos -> products/estate-orphans/devices/lg-webos).
- No live pitchfork daemon stanza found for lg-webos in the initial probe.
- "Failed chat" = a fleet/squawk chat message or LG TV-side chat flow that
  errored; the trail is in squawk logs, estate-chat daemon logs, or the
  lg-webos device daemon logs (whichever surface actually runs on the LG).

**Recon checklist:**
1. List every daemon with lg/webos/tv in pitchfork.toml (monolith only).
2. Find lg-webos runner: bun entrypoint in estate-orphans/devices/lg-webos;
   check for a pitchfork stanza with its port.
3. Probe the LG device (tailnet IP from device config) health/chats.
4. Grep logs (estate-chat :25120, squawk-ws :25147, any lg daemon log) for
   failed chat events: ERROR / 5xx / send-fail / webos payload errors.
5. Identify failure mode (auth token, websocket drop, payload schema,
   channel routing) and FIX FORWARD in the committed product.

**Equity:** additive-only; never remove/disable a daemon without explicit
order; archive useful artifacts to ~/sovereign/scratch-archive/.
