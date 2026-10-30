---
agent: tau
status: pending
---

# Recon: /home/toxic/estate resurrection source (lease violation)

**Priority:** HIGH — the estate single-truth lease (2026-10-28) forbids
/home/toxic/estate in ANY form (symlink, dir, file). Lease-guard
`364b68ddf9` fails if it appears.

**Task:** Find what keeps recreating /home/toxic/estate (daemons, grafana,
scripts with hardcoded paths, ghost configs) and eliminate the source.

**Evidence needed:**
- `ls -la /home/toxic/estate` (current state)
- Audit pitchfork daemons + grafana provisioning for hardcoded paths
- Fix-forward: point every writer at /home/toxic/pens/estate
- Verify lease-guard passes

**Rules:** Never `git reset --hard`/`checkout -- .`/`clean -f`. Additive-only.
---

## Recon findings (2026-10-29, tau)

**Current state:** /home/toxic/estate does NOT exist (lease OK right now).

**Resurrection sources found (5 systemd units + 2 live configs):**
- /etc/systemd/system/hw-audit.service
  - ExecStart=/home/toxic/estate/ranch/yote/ops/hw-audit/hw-audit.sh
  - ExecStart=/home/toxic/estate/ranch/yote/ops/hw-audit/hw-watchdog.py
- ~/.config/systemd/user/skills-watch.service -> /home/toxic/estate/skills/lib/skills-watch.sh
- ~/.config/systemd/user/arrival-classifier.service ->
  /home/toxic/estate/ranch/android-fleet/phone-backup/arrival-classifier.ts
- ~/.config/systemd/user/depend-refire.service -> /home/toxic/estate/tools/fleet-ops/depend-refire.py
- ~/.config/systemd/user/gemini-sdk-refresh.service ->
  /home/toxic/estate/ranch/barn/gemini-mcp/ops/refresh-sdk.sh
- pens/estate/config/projects.env line 287: sovereign=/home/toxic/estate
- pens/estate/config/bornite.yaml.bak-20260929 (backup only, not live)

**Assessment:** all units currently ENOENT-fail (absent target) — they cannot
resurrect /home/toxic/estate by themselves; the lease-guard would trip only if
some OTHER writer recreates the dir (e.g. a script mkdir -p before ExecStart,
grafana provisioning, or an active checkout). Repointing requires explicit
architect order per rule 2 (never modify a peer/daemon without an order).
Held pending that order.
