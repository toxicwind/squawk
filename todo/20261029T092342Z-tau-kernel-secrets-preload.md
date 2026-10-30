---
agent: tau
status: pending
---

# Eval kernel: auto-load kryptos/secretsmith secrets at boot (zero transport)

**Priority:** HIGH — every eval cell currently spawns subprocess secretsmith
calls; THRESHER_API_KEY in the keyring is stale (221 chars, rejected by
:25127) and must be restamped from the live gateway config.

**Task:**
1. Race techniques: A) subprocess bulk `secretsmith search '' --json --show`
   (295ms, 172 items) vs B) in-process D-Bus (secretstorage) vs C) env --app
   (BROKEN — returns 0 vars; report anomaly).
2. Winner becomes a kernel boot preload: load all secrets into process.env
   ONCE at boot; zero per-command transport after.
3. Restamp THRESHER_API_KEY from the live gateway's config (via /proc
   cmdline per anomaly #20 doctrine) and verify /api/v1/servers auth.
4. Persist the preload script in the eval kernel state so it survives
   compaction; document recovery on kernel loss.

**Evidence needed:** timing table; env populated in one fresh cell; thresher
auth verified with the restamped key.
