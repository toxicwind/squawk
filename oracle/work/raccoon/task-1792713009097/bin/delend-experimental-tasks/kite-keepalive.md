# Task: Kite Keepalive Verification

## Context
The `kite-cli` gateway requires keepalive+reconnect functionality. 
Commit `baedc9e` is cited as landed but not locally reachable. 
This task requires the experimental agent to:
1. Verify if `kite-cli` has a keepalive mechanism.
2. If not, propose a minimal implementation strategy.
3. If yes, verify its robustness under simulated network drop.

## Constraints
- Use `bun` or `node` for testing.
- Do not modify core `kite-cli` unless explicitly authorized by the oracle market.
- Report findings in `reports/kite-keepalive.md`.

## Emergent Directive
If the keepalive is missing, create a `keepalive-proxy.ts` in `ranch/pylae` as a proof-of-concept.
