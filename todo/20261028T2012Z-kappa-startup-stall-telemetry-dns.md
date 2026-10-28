# kappa cold-start: 31s stall to first session open + dead telemetry DNS (ingest.kappasessions.ai)

- **Status:** NOT-STARTED
- **Found:** 2026-10-28T19:06Z, ~/.local/share/kappa/log/dev.log + live session audit

## Evidence

- Boot 19:06:22 → session open 19:06:54 = **31s**, with fetches at +7.7s/+15s/+31s
  (15s-timeout network calls blocking the first turn).
- `getaddrinfo ENOTFOUND ingest.kappasessions.ai` — DNS is DEAD (NXDOMAIN verified via
  getent; freeinference.org resolves fine) yet kappa retries telemetry every ~30s.
- kappa.jsonc line 346: `"share": "disabled"` — but kappasessions bootstrap happens anyway.
  Config-vs-behavior violation = the "pointlessly enforced" complaint.
- `autoupdate: true` → boot-time checkUpgrade RPC (id=0).
- `$schema: https://app.kappa.ai/config.json` — remote schema ref (potential boot fetch).

## Fix direction

1. Honor `share: disabled` fully: skip kappasessions bootstrap + DNS entirely.
2. All boot-time network (checkUpgrade, model catalog refresh) → background, never block
   first turn; 3s per-attempt deadline, offline-first.
3. TUI "Config Warning" toast: notices.ts `duration: 0` sticky → auto-dismiss; single
   benign notices must not render as forced warnings.
4. Re-audit wezterm→bash→BASH_ENV(kairos shim)→kappa chain timing with sudo strace.

## Acceptance

- Fresh kappa in a fresh wezterm tab: first prompt < 2s, zero kappasessions DNS lines,
  no sticky warning toast.
