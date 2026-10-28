# TODO — backup-forward audit: cherry-pick crypto/docs, delete disposable backups

- status: IN PROGRESS
- author: tau (2026-10-28)
- unique-id: tau-backup-forward-audit-20261028
- created: 2026-10-28
- repository: pens/estate (plan: backup-plan.md)

## Goal
100%-sure clean of /home/toxic/estate ghost + classify 195G ~/archive backups via
qdrant; cherry-pick irreplaceable crypto/wallets/docs FORWARD into
/home/toxic/pens/estate/products/ + docs; delete disposable backup content.

## Key facts
- 1144 estate refs swept across all NVMe/sata/8TB (indexed in qdrant estate_sweep)
- Grafana-mesh.sh SOV default was the live estate-recreation vector (FIXED: pens-rooted)
- Lease-guard now FAILS if /home/toxic/estate exists in ANY form
- 47 SECRET rows: .ssh/id_estate_sign, .gnupg 2x pgp keys, keyrings, openfang +
  stake-registry keys (MISSING live), phone id_ed25519, root-ca-key.pem,
  GEMINI_EAP_KEY_0..6, moonbox-*, doorbell key, .docker token_seed, .9router jwt-secret

## Steps
1. Move crypto stash → pens/estate/products/backup-recovery/
2. Copy remaining irreplaceable secrets forward (live SSOT confirmed)
3. Consolidate DOCS (112) → pens/estate/docs + products
4. Delete disposable backup subtrees (build-cache/git-checkout/stale-temp/misc)
5. Verify estate absent + crypto md5 match + daemons healthy
6. Commit + push + board update