# Fleet todo: bin contract — symlink github-search bins per manifest

## Origin
tau followup phase: "bin contract: symlink github-search bins per manifest".

## Recon findings
- Bin contract SSOT: `/home/toxic/pens/barn/estate-ops/bin-verify.sh` pins `~/.local/bin` symlinks to `pens/` targets. Checked: the file does **not exist** on disk (path absent). No manifest to sync against.
- `~/.local/bin` currently holds: `ghq`, `ghas-mcp`, `ghas-mcp-stdio.sh`, `kappa-hindsight`, `github-mcp-cli`, `git-credential-gh`, `delend-gh`. No `github-search`, `blackbird`, or `ghas-search` bin present.
- GHAS (`/home/toxic/pens/ranch/products/github-search`) is a Bun workspace product — no compiled bin to symlink; it runs via `bun apps/api/src/server.ts` manually (not pitchfork-supervised; no pitchfork stanza for :25112 found).

## Status
NO-OP — no manifest exists and no bin candidate needs symlinking. If the architect wants a github-search entry point, add one under `apps/api/bin/` + a `~/.local/bin/github-search` symlink per bin-contract convention (target into `pens/ranch/products/github-search/`).
