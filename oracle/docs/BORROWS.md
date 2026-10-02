# Borrows — attribution for the fused Oracle

The Oracle is a *novel combination*, not novel parts. Every borrowed
mechanism is listed here with its source and license; the combination —
deterministic engine owning the number, calibrated panel advising,
asymmetric evidence, CP-gated abstention, Kelly firewall — is ours.

| # | Mechanism | Source | License | Where it lives |
|---|---|---|---|---|
| 1 | Deterministic log-odds core: LLR ≤ 2 nats, p ∈ [0.01, 0.99], atomic claims, cluster discounting, fabrication guard, continuity invariant, reflection clamp, credibility caps | `Alchemist-X/predict-raven` (Raven-Agent, arXiv:2607.03015) | MIT | `bin/bayes.py`, `bin/evidence.py` |
| 2 | Cross-fitted calibration, refusal gates, inner/outer calibration loops, label-budget allocation, datasheets | `cimo-labs/cje` (research file identifies MIT; calibrator source fetched 2026-09-20) | MIT | `bin/calibration.py` |
| 3 | Bias-adjusted judge-reporting estimator θ̂ = (p+q0−1)/(q0+q1−1) with test+calibration uncertainty in the CI | LLM-judge-reporting paper (see research-2026-09.md) | paper math (no code) | `bin/calibration.py`, `bin/engine.py` |
| 4 | Wang Transform pricing p_mkt = Φ(Φ⁻¹(p*) + λ), λ̂ = 0.183 global + hierarchical covariate model; probability-axiom invariant strategies; Kelly/risk firewall and killswitch patterns | `YichengYang-Ethan/oracle3` | Apache-2.0 | `bin/sizing.py` |
| 5 | Vote-then-debate routing doctrine: parallel judgment first, debate as escalation tier; deliberative consensus degrades accuracy (~76%) | arXiv:2605.30802 | paper finding | `bin/escalation.py` |
| 6 | Product-of-posteriors combination (Blackwell bound) for judge posteriors | arXiv:2605.06028 | paper math | `bin/engine.py` |
| 7 | Confidence from disagreement STRUCTURE (evidence overlap, stance divergence), never vote margins | DiscoUQ, arXiv:2603.20975 | paper finding | `bin/engine.py` |
| 8 | Designed information asymmetry: shared public + disjoint private evidence subsets per judge | InfoDelphi, arXiv:2607.01661 | paper finding | `bin/evidence.py` |
| 9 | D3 MORE-style debate: k parallel anonymized advocates/side, budgeted stopping, convergence checks, correction-biased updates | arXiv:2410.04663 | paper pattern | `bin/escalation.py` |
| 10 | Finite-sample abstention with Clopper–Pearson guarantees (abstain/escalate on a principled threshold) | arXiv:2608.17994 | paper pattern | `bin/engine.py` |
| 11 | PROCTOR: engine-owned acceptance checks outranking judges; canary questions as gaming tripwires | arXiv:2609.02246 | paper pattern | `bin/engine.py` |
| 12 | Debate as martingale over belief trajectories (why debate is never the default) | arXiv:2508.17536 | paper finding | `bin/escalation.py` |

Full research synthesis: [research-2026-09.md](research-2026-09.md).
