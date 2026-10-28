# TODO — backup-forward audit + 195G cleanup (tau, 2026-10-28)

status: NOT STARTED
author: tau (session 2026-10-28)
unique-id: tau-backup-forward-audit
created: 2026-10-28

# Goal
Complete the backup-forward audit: classify the 195G in ~/archive/* (home-dirs-2026 130G, detached-2026 18G, estate-clone-20261028 42G, root 4.9G), cherry-pick irreplaceable crypto/docs forward into pens/estate, then delete the disposable backup content.

# Done this session
- Full-disk estate-reference sweep (1144 refs across all mounts), qdrant-indexed into `estate_sweep` + `backup-inventory` collections (2794 rows classified).
- Discovered + fixed the live recreation vector: grafana-mesh.sh defaulted `ESTATE_ROOT=/home/toxic/estate` and its GF_PATHS_DATA recreated /home/toxic/estate on every start → repointed ALL 12 scripts to pens/estate via perl mass-replace; lease-guard now fails if /home/toxic/estate exists in ANY form. /home/toxic/estate ABSENT.
- Migrated ~/.openfang state (fleet agents, stake-registry, key-pool, 13 newer workspaces) into ~/.rig (the rig binary's real home); retired ~/.openfang (archived to ~/archive/retired-openfang-home-20261028). estate/rig daemon started (:25196 api/agents = 200, 56 agents).
- Consolidated rig repo: reconstructed main from scratch (52→2 clean commits), force-pushed; archived empty openfang + openfang-join repos; folded openfang-join into rig/docs; retired estate-scripts ghost (kernel test fixtures → ~/.rig).
- Started qdrant (ports 25133/25134 untouched, test_freeinference collection intact).
- Consolidated irreplaceable crypto/wallets into pens/estate/products/backup-recovery/ (53 files, 544K) — KEPT LOCAL-ONLY, NOT committed to GitHub (push-protection correctly blocked GCP EAP keys).
- Consolidated 30 estate docs forward into docs/backup-consolidated-20261028/.
- Wrote anomaly dossiers #48-#52 + AGENTS.md table + fleet knowledgebase entry; pushed estate main (merge-forward per rule 4).

# Remaining
- Classify remaining backup trees via qdrant semantic queries; cherry-pick any surviving irreplaceable items into pens/estate; then DELETE the disposable backup trees (~/.archive/home-dirs-2026/.local/share 76G build caches etc.) to reclaim ~195G.
- Verify /home/toxic/estate still absent (lease-guard) after deletion; no daemon recreates it.

# References
- anomaly dossiers: pens/estate/docs/anomalies/2026-10-28/ (estate-dual-truth.md, grafana-recreation.md, rig-openfang-consolidation.md, estate-scripts-ghost.md, qdrant-monolith-fragment-two-truth.md)
- backup inventory: /tmp/backup-inventory.tsv; qdrant collection `estate_sweep`
- AGENTS.md lease: /home/toxic/estate must NOT exist; bin-contract-audit enforces.
