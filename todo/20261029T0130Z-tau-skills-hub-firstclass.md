# TODO — skills-hub first-class: tau+kappa plugin integration

- status: DONE (by daemon, 2026-10-28T23:40:56.069Z)
- author: tau (2026-10-29)
- unique-id: tau-skills-hub-firstclass

Recon done: hub = products/estate-skills-hub (repo remote still sovereign-skills-hub.git — RENAME the GitHub repo estate-skills-hub + local remote), loader/router/validator src in JS, 5 tests green-pending, catalog manifest + ontology present. azurite/skills holds the real corpus (9 dirs incl cyoa-router).

1. **Rename**: gh repo rename sovereign-skills-hub -> estate-skills-hub; update local remote URLs
2. **Audit**: run hub tests + fix; reconcile manifest vs azurite corpus (skills_manifest.json vs 9 dirs); dedupe overlap
3. **tau first-class**: tau config.yml skills.paths -> hub/skills (ghost fixed already); verify loader reads depth-1; skill-description compressor contract (config L66 note)
4. **kappa first-class**: implement KAPPA_COMPAT.md contract — kappa_skill_check.py validator wired into kappa skills dir; register hub path in kappa config
5. **Consolidate**: move stray SKILL.md + related .ts (cyoa-router, skill-descriptions.ts ref) into hub skills/<category>/ scheme; azurite keeps serving via symlink or direct path — pick ONE truth
6. **bin contract**: ~/.local/bin/skills-hub -> hub bin/skills-hub.js; manifest.yaml pin
7. **Verify**: end-to-end — tau loads N skills, kappa validates same N; loader router test green
8. **Commit+push**: hub repo + estate pointer + tau/kappa configs

## Done
- marked-by: daemon
- marked-at: 2026-10-28T23:40:56.069Z
