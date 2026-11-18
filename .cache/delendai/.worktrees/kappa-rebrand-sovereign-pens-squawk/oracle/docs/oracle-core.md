# Oracle decision core — design & proven defaults

The maximal fused Oracle: a deterministic aggregation engine that owns
every number, advised by a panel of calibrated LLM judges. This is the
`bin/` decision layer; the work market around it is specified in
[SPEC.md](../SPEC.md) and the research synthesis in
[research-2026-09.md](research-2026-09.md).

## The constitutional rule

**The deterministic engine owns every number it emits** — verdicts,
probabilities, confidence, payouts. LLM judges produce structured,
attributable inputs (posteriors, per-claim LLRs). No LLM output ever
bypasses the engine; the engine's acceptance checks outrank every judge.

## Pipeline

```
question
  → framing.frame_question        fail-closed binary framing; base-rate prior;
                                  resolution criteria/date/source; refusal path
  → evidence.partition_evidence   shared public core + DISJOINT private subsets
                                  (designed information asymmetry)
  → judges (parallel, anonymized)  overconfidence advisory + self-debate prompt;
                                  JSON contract: posterior, verbal confidence,
                                  atomic claims {stance, llr≤2, cluster, urls}
  → calibration.CalibrationLoop   cross-fitted Platt/isotonic per judge,
                                  identity until the precision gate passes
  → engine.pooled_posterior       product-of-posteriors in log-odds
                                  (Blackwell bound); engine decides
  → engine.disagreement_features  confidence from disagreement STRUCTURE
                                  (evidence overlap, stance divergence),
                                  never raw vote margins
  → engine.abstention_gate        Clopper-Pearson lower bound on accepted-set
                                  accuracy ≥ 0.80, else escalate (never emit)
  → escalation.route              AUTO → VOTE → DEBATE → HUMAN
  → sizing.size_stake             Kelly firewall between belief and stake
```

Every verdict ships: probability, bias-corrected agreement point + CI,
structural confidence, per-judge logit contributions, canary flags,
a RefusalGate ledger, and a limitations line (`NOT_CHECKED` items are
explicit — never silent).

## Proven defaults (all values below were measured, not chosen)

| Default | Value | Proven by |
|---|---|---|
| Judge panel (3+1) | router aliases `oracle-judge-a`, `oracle-judge-b`, `oracle-judge-c` (+ `oracle-judge-local` fallback) | 2026-09-20 herd census picked the fastest exact-output free models (489ms / 799ms / 2161ms) across three families -- but model selection lives in `config/herd.yaml` ("Oracle judge panel"), never in Oracle code. Oracle code names only routing roles; `--models` accepts aliases and refuses concrete model IDs |
| LLR clamp | ±2.0 nats/claim | Raven-Agent (arXiv:2607.03015) |
| Probability bounds | [0.01, 0.99] | Raven-Agent; prevents certainty theater |
| Unverified-claim soft clamp | 0.2 nats | Raven fabrication guard |
| Reflection clamp | 1.0 nats | Raven continuity invariant |
| Cluster decay | ×0.5 per repeat | Raven cluster discounting |
| Credibility caps | low 0.25 / medium 0.8 / high 2.0 nats | Raven-Agent |
| Calibration wins | ΔNLL ≈ −0.04 to −0.05 per judge vs raw | `bench/exp_calibration.py`, synthetic miscalibrated judges, held-out labels |
| Pooling vs majority | Brier 0.2303 vs 0.2345 (accuracy within noise) | `bench/exp_pooled_vs_majority.py`, n=500, seeded |
| Abstention bar | CP lower bound ≥ 0.80 on accepted history | `bench/exp_abstention.py`: 19/20 escalates (lo=0.751), 38/40 emits (lo=0.832); cold start withholds (n=0 → bound 0, no unanimity bypass); only genuinely labeled rows count (legacy rows quarantined) |
| Calibration ownership | `engine.build_verdict` applies the calibration loop exactly once per posterior; the ask path never touches posteriors | `bench/test_core.py`: ask-path scan has no CalibrationLoop, engine aggregation deterministic |
| Framing vagueness guard | questions with no resolvable referent (no date/deadline, number, proper noun, or quoted span) are refused -- e.g. "Will this work?" | `bin/framing.py` anchor rule + `bench/test_core.py` regression |
| Tier unanimity bar | structural confidence >= 0.90 AND posterior >= 0.85 (or <= 0.15) routes the TIER ladder (`escalation.route`), never the abstention gate | `bench/exp_default_tuning.py` T1 sweep tunes the tier ladder; the gate has no unanimity parameter since 2026-09-21 |
| Judge return floor | old: 9/15 live, 95% CP lo **0.3596** (5 questions x 3 concrete models, 60s timeout, no retry; 6/15 slots were harness NoneType crashes, not model refusals) | `bench/judge_return.py`, `proof-runs/judge_return_baseline.jsonl` |
| Judge return floor (hardened) | **13/15 live, 95% CP lo 0.6366 one-sided** (same 5 questions x 3 `oracle-judge-*` aliases, 90s slot timeout, bounded retry + local fallback; per-alias a 5/5, b 3/5, c 5/5; 0 harness crashes, 2 honest timeout refusals; elapsed 151.7s). **Note:** 0.6366 is the one-sided bisection from `bench/judge_return.py`; production `calibration.clopper_pearson(13,15,0.05)` (two-sided) gives **0.5954**. Do not conflate. | `bench/judge_return.py`, `proof-runs/judge_return_new.jsonl` |
| Debate budget | k=2 advocates/side, ≤3 rounds, stop at max Δ<0.03 | D3 MORE pattern (arXiv:2410.04663); debate is a cost center |
| Wang λ | 0.183 global; hierarchical covariate form | oracle3, calibrated on 291,309 resolved contracts; verified: true 0.50 → 0.5726 (≈ the paper's ~57c) |
| Kelly | quarter-Kelly, 10% bankroll cap, 2pp min edge | Raven lesson: calibrated p ≠ trading result |
| Escalation margin | spread ≥ 0.25 or low structural confidence → DEBATE | routing doctrine (arXiv:2605.30802) |

## Module map

| File | Owns |
|---|---|
| `bin/bayes.py` | Log-odds core: LLR clamps, stance-signed LLRs, cluster discounting, fabrication soft-clamp, continuity threading |
| `bin/framing.py` | Fail-closed binary framing, base-rate priors, resolution extraction, refusal/clarification |
| `bin/calibration.py` | Platt + isotonic (PAVA), cross-fitting, NLL/Brier, Clopper–Pearson (exact), bias-corrected reporting math, datasheets, refusal gates, √N label budgeting, persistent two-loop state |
| `bin/engine.py` | Pooled posteriors, structural confidence, abstention gate, canary checks, verdict records |
| `bin/evidence.py` | Asymmetric evidence partitioning, atomic-claim pipeline, URL fabrication guard |
| `bin/escalation.py` | AUTO/VOTE/DEBATE/HUMAN ladder, D3-style budgeted debate, human arbitration flags |
| `bin/sizing.py` | Kelly firewall, Wang Transform fair value, probability-axiom invariant checks |
| `bin/oracle_ask.py` | The ask CLI: framing → panel → calibrate → engine → gate → ladder → verdict JSON |
| `bin/oracle_daemon.py` | HTTP front door (`127.0.0.1:25151`, `POST /ask`, `GET /health`), pitchfork-supervised |

## Interfaces

```bash
# ask (human-readable + JSON verdict on stdout)
bin/oracle_ask.py "Will the herd serve 100 models by 2026-12-31?" --json

# canary sweep (gaming tripwires)
bin/oracle_ask.py --canaries

# daemon (pitchfork: sovereign/oracle-core)
curl -s -X POST 127.0.0.1:25151/ask -d '{"question":"..."}'
curl -s 127.0.0.1:25151/health
```

## Calibration state & ledgers (all under `work/`)

- `work/verdicts.jsonl` — every verdict, hash-chained via `verdict_sha256`
- `work/calibration/state.json` — deployed per-judge calibrators (two-loop)
- `work/calibration/accepted_history.jsonl` — resolved outcomes feeding the CP gate
- `work/calibration/datasheets.json` — judge capability datasheets (reliability weights)
- `work/canaries.json` — seeded known-answer tripwires
- `work/escalations/human-*.json` — human arbitration flags
- `work/proof-runs/` — timestamped live proving reports (restart durability proof)

## Limitations (honest)

- Cold start: the abstention gate trusts only unanimous high-confidence
  verdicts until ≥8 labeled accepted outcomes exist.
- Calibrators are identity maps until ≥10 labels/judge and the precision
  gate (cross-fitted NLL must beat raw) passes.
- The drift outer loop reports `NOT_CHECKED` until fresh labels arrive;
  verdicts carry this in their limitations line.
- Debate advocates run in parallel on distinct judge aliases (`oracle-judge-a/b/c/local`), one bounded retry on the next alias, fail-open to the vote prior. Advocate finals re-enter `engine.build_verdict` as half-weight judges -- probability, confidence, gate, tier, contributions, and the verdict hash are all recomputed on the final number; nothing is overwritten in place.
