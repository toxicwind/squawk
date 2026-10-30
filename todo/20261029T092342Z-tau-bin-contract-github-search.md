---
agent: tau
status: pending
---

# Bin contract: symlink github-search bins per manifest

**Priority:** MEDIUM — the manifest (`pens/barn/estate-ops/bin-verify.sh`)
pins every symlink in ~/.local/bin to its exact pens target. A broken or
missing link for github-search bins is a FAIL.

**Task:** Ensure github-search/github-advanced-search-mcp entrypoints are
symlinked into ~/.local/bin straight into pens (never a copy, never
/home/toxic/estate). Run bin-verify.sh; fix manifest first, then the link.

**Evidence needed:**
- ls of ~/.local/bin matching ghas
- bin-verify.sh PASS output

**Rules:** Products own their entrypoints; bins only point at them.
