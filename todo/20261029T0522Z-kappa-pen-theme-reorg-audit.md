# TODO — pen theme reorg + shape audit (scaffold maximalization)

- status: NOT-STARTED
- author: kappa (2026-10-29)
- unique-id: kappa-pen-theme-reorg-audit
- priority: high
- collab: OPEN (barn-ops tack, geode/hephaistos rigs — each pen has an owner)

Scaffold audit done (Pens-ops/scaffold): make-pen.ts is post-2026-10-25 safe
(never deletes, --force=metadata), manifest+readme-gen idempotent. Gaps found:
no pitchfork.toml template, no namespace-registration step, no ghost-path
linter, static AGENTS.md stale (~/.openfang retired -> ~/.rig, Pens/agents ->
pens/Pens/agents, missing !docs/), apply.sh only substitutes 3 files, no ssot/
convention, mise template uses invalid `catalog:`, no automated pen audit.
All gaps are now implemented as scaffold/bin/{lint-paths.sh,audit-pen.sh,
register-namespace.ts,reorganize-pen.ts,exec.ts}.

Audit findings by pen:

- olympus: conformant (alias symlinks -> products/*, harmless)
- geode: near-conformant, no LICENSE, 2 root repos
- barn: mixed, flat products at root + products/, no LICENSE
- ranch: **chaos** — no mise.toml, 249 root dirs, ${XDG_RUNTIME_DIR} literal,
  .super-ralph/.retired-* litter, cross-pen symlink kairos->olympus
- Pens: all 7 metadata BUT recursion (olympus/ranch -> pens/* symlinks inside)
  - heavy runtime litter; ghost /home/toxic/pens/Pens resurrected (removed 05:14,
    killed 5 ghost-path procs)

Actions:

1. audit-pen.sh across all 5 -> FAIL list.
2. Fix missing metadata: ranch mise.toml, geode/barn LICENSE.
3. reorganize-pen.ts --apply per pen (git-safety archives first; products/ +
   theme cross-pen moves).
4. Remove Pens recursion symlinks + archive litter (additive-only).
5. exec.ts cross-repo runner wired as the pens `moon run` analog.
