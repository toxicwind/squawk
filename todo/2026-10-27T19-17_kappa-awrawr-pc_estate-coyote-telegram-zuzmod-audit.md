# Estate Coyote / ZUZMOD Telegram audit — kappa (awrawr-pc) — 2026-10-27T19:17

## Verdict so far: the ZUZMOD spam is NOT from this box

- **Only Telegram-connected process on the box is the desktop app** (pid 1834457, `ss -tnp` → 91.108.56.179/149.154.175.57). No local bot poller is alive.
- **yote (the Telegram bot) has been DOWN with an invalid token since 2026-10-08** — `pens/ranch/yote/logs/yote.log` ends in endless `poll tg: Unauthorized: invalid token specified`. Daemon `estate/yote` is `available` (stopped), not running.
- Therefore the "Estate Coyote" that replied to Pup Trix with `t.me/ZUZMOD` spam is **not this estate's bot** — it is a Telegram-side impersonation/compromised bot using the same display name. Do NOT click t.me/ZUZMOD; report/block it in-app.
- yote bot token in keyring (`TELEGRAM_BOT_TOKEN`) could not be validated end-to-end yet: `secretsmith get TELEGRAM_BOT_TOKEN` returns a whole search dump (269 chars, `label: SIGMA...`) instead of the secret — same class as anomaly #16 (secretsmith get/env semantics). `secretsmith env --app yote` gave no `TELEGRAM_BOT_TOKEN=` line either (token len 0). getMe with empty token → `{ok:false}`.

## Remaining jobs (in order)

1. **Fix the secretsmith key-extraction path** so the yote token resolves (anomaly #16 follow-up: `get` returning search-dump; `env --app yote` missing the var). Then `getMe` to confirm the real bot's username.
2. **Confirm impersonation definitively**: compare the Telegram-side "Estate Coyote" chat/bot ID Pup Trix was talking to against the estate bot's `getMe` id. If different → 100% impostor; write it in the anomaly dossier.
3. **Fix yote itself**: token has been invalid since Oct 8 — re-issue/rotate via @BotFather (or secretsmith update), then `pitchfork start yote` and verify health :25102 + a real poll line.
4. **Anomaly dossier**: add this to `estate/docs/anomalies/2026-10-27/` (impersonation + dead-bot-since-Oct-8 + secretsmith get regression). Anomaly #16 fix (`await ReadAlias`) apparently doesn't cover `get` on this entry — re-verify.
5. **Extensions note (unrelated thread from this session)**: Bitwarden passkey failure on Google = upstream bitwarden/clients#23311 / PM-43909; workaround = type username first. Update extension 2026.9.0 → 2026.10.0.

## Evidence pointers

- `ss -tnp | grep -E '149\.154|91\.108'` → only `Telegram` desktop pid 1834457.
- `pitchfork list` → `estate/yote available`, `estate/campfire running`.
- `/home/toxic/pens/ranch/yote/logs/yote.log` → last real activity 2026-10-08/09, all `Unauthorized`.
- yote source: `pens/ranch/yote/src/telegram.rs` (Bot API long-poll), `src/yote.ts:868` (`estate_coyote_bot`).
- squawk/estate/yote sources grepped: **zero** `zuzmod` hits anywhere on the box.
