# Fix advisor-class model routing: tauvisor + modelRoles advisor family + kappa glm/nvidia misroute (verbose)

## Update 2026-10-28T19:50Z — 53s-thought root cause FOUND + FIXED

The "53s of thought" stall was NOT provider latency alone: `agent/config.yml`
had `defaultThinkingLevel: auto` + `autoThinkingMaxEffort: xhigh`. `auto` runs
a JUDGE classifier model call EVERY turn (classifyDifficulty), and on
freeinference's maxConcurrency:1 lane that judge call queues behind everything
else — each turn paid an extra queued round trip before the real completion.
Fixed in-place: `defaultThinkingLevel: low` (concrete = no judge call) +
`autoThinkingMaxEffort: medium` (bounded residual). Verified: YAML parses,
`tau models ls` loads 0 config failures. Takes effect on new sessions
(this session predates it). Residual: thinking-auto-shim extension
(`config/tau/extensions/thinking-auto-shim.ts`, untracked in estate tree)
is the runtime belt-and-suspenders — wiring it remains part of the
permanence-wire todo.

- **Posted by:** tau (session 01a1838e, /tmp) · 2026-10-28T19:40Z
- **Status:** PARTIALLY DONE — see "completed this session" below; the rest is the remaining work
- **Priority:** HIGH — the freeinference single-lane queue is the estate's choke point; advisor-class traffic made it worse
- **Provenance:** live `ss -tnp` traces + session JSONL forensics 2026-10-28 (this session), architect directive stream

## Why (root-cause chain, evidence-backed)

1. **Single-lane observer effect is real and measured** (anomaly #4, D-2026-10-23): freeinference is a CF-fronted single-server queue (de facto 1 worker). Live evidence this session: `104.21.92.204:443` cert CN=freeinference.org held ESTAB from **both** tau 1165802 (me) and struggling tau 1945778 simultaneously; struggling tau's session `01a183e8` (deepseek-v4-flash) was spam-spawning vibe audit workers (`gemini-402-audit`, `nvidia-slow-audit`) that all funnel through the same lane.
2. **Tauvisor (the advisor agent) was pinned to `freeinference/deepseek-v4-flash:low`** in `~/.tau/agent/TAUVISOR.yml` — every advisor invocation burned a slot on the saturated lane. Architect noticed ("why is tauvisor using freeinference wtf").
3. **The advisor model ROLE is also freeinference**: `~/.tau/config.yml` line 259: `advisor: freeinference/qwen3.6-35b` — and the same model backs `judge`, `memory`, `plan`, `smol`, `tiny`, `verification` roles. Even with Tauvisor rerouted, six other roles still queue on the same lane.
4. **Kappa glm misroute**: a live kappa session runs `glm-5.3` tagged as the "nvidia" provider, bypassing rhodochrosite (:25193, health 4ms). Rhodochrosite currently serves **no** glm/nemotron ids (probed `/v1/models` — absent), so the route contract is violated: model identity chain (anomaly #3) says resolved model must flow catalog → models.yml → overrides → modelRoles → frontmatter; "nvidia" as a provider tag for glm is a phantom lane. NVIDIA direct API is healthy (200 in 91ms) — the fix is routing through rhodochrosite's `secure-nim` pool, not direct.
5. **Bizarre latency**: rhodochrosite `/v1/models` answers in 257ms while `/health` is 4ms — the models-list handler re-resolves providers per call (suspicion, needs probe: anomaly-13-style Schema.TaggedError regeneration or per-request keyring reads). This is the fixable latency the architect flagged.

## Completed this session (2026-10-28)

- [x] `TAUVISOR.yml` advisor moved to `nvidia/nemotron-3.5-super-vl-120b-a12b` (rhodochrosite-routed). NOT banned — queue hygiene, per-model strike doctrine respected. Commit pending tau config push.
- [x] pcap lane verified working: kappa's funnel-keepalive capture live (`/tmp/kappa/funnel-trace/funnel-keepalive.pcap`, ports 25135/25136/25217/25127/25193/25218); my freeinference-specific capture got 0 packets in 8s (filter/net mismatch on CF ranges — `net 2606:4700::/32` too narrow; use `host` per-edge).
- [x] swarm canceled earlier (swarmscout tmux killed, estate/rig stopped).

## Remaining work (do these)

1. **modelRoles advisor family reroute**: change `advisor/judge/memory/plan/smol/tiny/verification` in `~/.tau/config.yml` from `freeinference/qwen3.6-35b` to rhodochrosite-routed alternates (qwen3.6-35b stays FIRST choice for interactive `advisor` if architect wants; the queue-heavy BACKGROUND roles — memory, verification, plan — move first). Save via `.tau config` or direct edit + tau restart contract.
2. **Kappa glm fix**: pin the kappa session's model to `rhodochrosite.secure-nim/z-ai/glm-5.3-flash` (or add glm-5.3-flash to rhodochrosite's served ids via mimetite catalog regen if absent). Verify with a live completion through :25193 ≤300ms.
3. **Rhodochrosite /v1/models latency probe**: instrument whether 257ms is per-request provider re-resolution; if so, cache the models list (60s TTL) — the "bizarre latency" fix.
4. **Contract test**: per anomaly charter — a probe that asserts (a) no tau/kappa config role references bare `freeinference/` for background roles, (b) glm-5.3 resolves through rhodochrosite, (c) /v1/models < 50ms warm.
5. **Docs**: update `pens/CONCEPTS.md` single-lane row + this file as the receipt.

## Files

- `~/.tau/agent/TAUVISOR.yml` (edited this session)
- `~/.tau/config.yml` lines 247–300 (modelRoles — remaining work)
- kappa session: `2026-10-28T19-06-50-592Z_01a183e8` (the struggling one; also spawned the vibe workers)
