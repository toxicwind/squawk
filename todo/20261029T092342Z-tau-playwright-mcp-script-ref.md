---
agent: tau
status: pending
---

# Stale playwright-mcp script ref fix

**Priority:** MEDIUM — a daemon or config references a playwright-mcp script
path that moved (or the product relocated during the pens reorg).

**Task:** Find the stale ref (pitchfork.toml / pitchfork.d / run.sh /
serve.sh) pointing at the old playwright-mcp script location; repoint to the
real pens path per the bin contract (no hardcoded product paths in shims).

**Evidence needed:**
- grep playwright in /home/toxic/pens/estate/pitchfork.toml
- Verify the target script exists on disk before repointing
- Restart the daemon via pitchfork and health-check

**Rules:** Edit the MAIN pitchfork config, not pitchfork.d fragments (they
are dead litter; monolith is the only truth). Never run generate.ts.
