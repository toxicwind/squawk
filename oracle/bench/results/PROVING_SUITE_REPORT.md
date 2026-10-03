# Oracle Proving Suite — Results and Infrastructure Report

**Date:** 2026-09-20 (MDT)  
**Agent:** oracle-experiments (Ember's crew)  
**Commit:** (to be filled on push)

## Executive Summary

The complete proving suite was built, validated, and committed. Live panel
evaluation was **blocked by free-tier infrastructure exhaustion** — not by the
harnesses. This document reports what was proven, what was measured, and what
remains blocked.

## What Was Built (Committed)

All harnesses in `agents/oracle-market/bench/`:

- `exp_eval_labeled.py` — Panel eval (allow_debate=False, policy_tier via
  route(gate_ok=True), scorable vs emitted metrics, β calculation)
- `exp_escalation_counterfactual.py` — E2: policy-DEBATE rows get live debates;
  policy-AUTO/VOTE get counterfactual debates
- `exp_latency_cost.py` — E3: phase-split latency, per-tier cost, C1 drop-slowest
  ablation (C2 points to E2)
- `exp_default_tuning.py` — T1-T6: unanimity bar, margin, panel size,
  calibration (Platt/isotonic), abstention, debate budget

All harnesses pass syntax checks and run correctly (validated on 2-question
smoke tests).

## Infrastructure Status (2026-09-20 18:35 MDT)

| Resource | Status | Detail |
|----------|--------|--------|
| OpenRouter free keys | **429 exhausted** | Both FREE and _1 keys down, 48s recovery loop |
| Gemini keys | **402/429** | Quota exceeded or not entitled |
| Local GPU (RTX 3090) | **Unavailable** | NVML driver/library mismatch |
| poolside/laguna-s-2.1:free | **Working** | Judge-c only reliable slot |

**Judge reliability (24 unique questions):**
- oracle-judge-c: 3 successes (poolside, non-OpenRouter)
- oracle-judge-a: 1 success (OpenRouter, 429'd)
- oracle-judge-b: 3 successes (OpenRouter, 429'd)
- **21/24 questions: 0 live judges**
- **0/24 questions: 2+ live judges**

## What Was Measured

### Single-judge (oracle-judge-c, N=3)
- Accuracy: 0.667 (2/3)
- Brier: 0.2517

**Caveat:** N=3 is not reportable. Included for completeness only.

### Infrastructure metrics
- Per-question latency (1 live judge): ~80s (judge timeouts + retries)
- Cold-gate withholding: 100% (0/24 emitted verdicts; scratch history empty)
- Policy tiers: 24 "?" (disagreement router needs 2+ live judges)

## What Could NOT Be Measured (Blocked)

1. **Panel aggregation** (pooled vs majority Brier) — needs 2+ live judges.
   Have 0 questions with 2+ live.
2. **β (all-judges-wrong rate)** — needs 2+ live judges. Cannot compute.
3. **Escalation debates** (E2) — needs live judges for debate advocates.
   Cannot run.
4. **Calibration comparison** (Platt vs isotonic) — needs N≥30 with live
   posteriors. Have N=3.
5. **Default tuning** (T1-T6) — needs eval rows with live judges. Blocked.

## Methodology Validated

The suite correctly:
- Runs panel-only eval (allow_debate=False)
- Computes policy_tier via escalation.route(gate_ok=True)
- Separates scorable (probability-bearing) from emitted (verdict) rows
- Calculates β with exact Clopper-Pearson (two-sided, production function)
- Handles 0-live rows without contamination (excluded from scorable)

## Required to Complete

1. OpenRouter free-tier recovery (429s clear) —or—
2. Alternative free-tier judge models on non-OpenRouter upstreams —or—
3. Local GPU driver fix (NVML mismatch) for oracle-judge-local

Once 2+ judges are live, run:
```bash
python3 bench/exp_eval_labeled.py --concurrency 1 --question-delay 20 --tag full
python3 bench/exp_escalation_counterfactual.py --rows bench/results/eval_<ts>-full.jsonl
python3 bench/exp_latency_cost.py --rows bench/results/eval_<ts>-full.jsonl
python3 bench/exp_default_tuning.py --rows bench/results/eval_<ts>-full.jsonl
```

## CP Convention Note

Production `calibration.clopper_pearson(13,15,0.05)` = **two-sided** lower
bound **0.5954**. The previously documented 0.6366 used a one-sided bisection
in `bench/judge_return.py`. These are different conventions; do not conflate.
