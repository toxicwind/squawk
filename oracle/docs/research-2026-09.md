# Oracle Research — September 2026

**Author:** oracle-research (worker under oracle-max / Ember)
**Date:** 2026-09-20
**Scope:** Paper-first research + cutting-edge repo harvest for the maximal Oracle upgrade: fusing the debate-oracle concept, the bid marketplace, judge ensembles, and calibration into one decision engine in OpenFang. SPEC.md §7 (HMAC, Vickrey, stake/slash, TrueBit, querais) is taken as read — nothing here duplicates it.

**Method:** 6 paper-search races (arXiv + alphaXiv, 48 papers), 15 full abstracts via arXiv API, GitHub code-search harvest (6 queries, 47 unique repos, recency-weighted ranking), date-filtered repo search, deep file-level reads of the top ~8 repos (READMEs, module trees, core source files).

---

## Executive summary: the 7 findings that change the design

1. **Vote first, debate rarely.** Majority voting alone accounts for most of multi-agent-debate gains; debate alone is a martingale over belief trajectories — it does not improve expected correctness (Debate-or-Vote, arXiv:2508.17536). One oracle-resolution study found deliberative consensus *degraded* accuracy to ~76%, below every single-model baseline, because confidently-wrong models flip correct ones (arXiv:2605.30802).
2. **Information asymmetry is the whole game.** Give all agents identical evidence and deliberation collapses into herding. Designed asymmetry (shared public + disjoint private evidence) cut inter-agent error correlation and improved Brier scores 12–18% (InfoDelphi, arXiv:2607.01661).
3. **Ensemble gain is capped by the co-failure rate.** For any policy whose output is one member's answer, accuracy ≤ 1 − β, where β = fraction of queries where *every* model is wrong. "Gains come from models failing on different questions, not from adding more models" (arXiv:2606.27288). Select proposers for *complementarity*, not raw accuracy (arXiv:2605.24048).
4. **The aggregation ceiling is the Bayesian pooled posterior.** Voting and debate are provably no more informative than the pooled private information; product-of-posteriors approximation beat SOTA debate and voting on 6 benchmarks (arXiv:2605.06028). Simple vote-counting is leaving accuracy on the table.
5. **Calibrate the judges, don't curate them.** Keeping the full judge panel beats accuracy-ranked top-k selection; even below-chance judges help when biases are learnable and signals non-redundant — halved NLL on RewardBench2 (arXiv:2605.09702). Judge panels need bias correction + confidence intervals as standard output (arXiv:2511.21140), fail-closed calibration gates (JudgeGauge), and refusal-to-claim gates (CJE).
6. **The engine owns the number.** The winning production pattern (Raven-Agent, live on Polymarket, arXiv:2607.03015): agents emit structured evidence (signed per-claim log-likelihood ratios); a deterministic engine dedupes, discounts clusters, verifies citations against the search trace, and computes the probability. Agents never set the final number. This is the same structural lesson as PROCTOR's "judge demoted from oracle to advisor" (arXiv:2609.02246).
7. **Auto-resolve the easy, escalate the rest.** Unanimous high-confidence questions auto-resolve at 97.87% accuracy (47% of volume); inter-agent disagreement is the flag for human review — i.e., the bid-marketplace's expensive tiers (debate, human arbitration) should trigger on *disagreement*, not run by default (arXiv:2605.30802).

---

## (a) Paper findings — mechanisms to steal

### 1. Debate-or-Vote (NeurIPS 2025 Spotlight, arXiv:2508.17536)
- **Claim:** "Majority Voting alone accounts for most of the performance gains typically attributed to MAD… debate alone does not improve expected correctness" (martingale over belief trajectories).
- **Steal:** Oracle's default verdict path = parallel independent judgments + majority vote (cheap, reliable). Full debate becomes an *escalation tier*, triggered by disagreement or low agreement margin. When debate runs, apply their intervention class: "targeted interventions, by biasing the belief update toward correction, can meaningfully enhance debate effectiveness" — i.e., instruct debaters to update *toward correction*, not to defend.
- Code: https://github.com/deeplearning-wisc/debate-or-vote

### 2. Multi-Agent AI Oracle Systems for Prediction Market Resolution (arXiv:2605.30802)
- **Claim:** On 1,189 resolved KalshiBench questions: independent aggregation + confidence-weighted voting = 83.43% (best); deliberative consensus ≈ 76% (below every single baseline); error correlations 0.529–0.689 cap ensembles; "auto-resolving only unanimous, high-confidence questions yields 97.87% accuracy on 47% of the dataset, with inter-agent disagreement flagging the remainder for human review."
- **Steal:** the **routing doctrine** — unanimity + high confidence → auto-resolve; any disagreement → escalate (debate tier / human). Never default to deliberation. KalshiBench dataset: https://github.com/LukasNel/kalshibench (evaluation benchmark for our resolution accuracy).

### 3. InfoDelphi — Diverse Evidence, Better Forecasts (arXiv:2607.01661)
- **Claim:** "When all agents are given identical evidence, deliberation collapses into herding rather than genuine belief revision, leaving multi-agent systems little better than a single agent… removing information asymmetry eliminates most deliberation gains."
- **Steal:** **designed information asymmetry** in the bid marketplace: partition evidence into shared-public + disjoint-private subsets per bidder/judge (relevance-aware evidence routing). Agents with exclusive knowledge can only influence others through deliberation. This is the single highest-leverage structural change to any multi-agent oracle.

### 4. Co-Failure Ceiling (arXiv:2606.27288)
- **Claim:** Accuracy of routing/voting/MoA ≤ 1 − β (all-wrong rate); "At matched quality, low-rho heterogeneous ensembles beat high-rho Self-MoA… combining models rarely beats the single best model without a strong query-level routing signal. Gains come from models failing on different questions, not from adding more models."
- **Steal:** Track per-question **co-failure rate** as the Oracle's ensemble health metric (Clopper–Pearson bound gives a finite-sample certificate of max achievable gain). Bidder/judge *selection* should optimize for low error correlation, not individual strength. A beta certificate tells Chris when adding more judges is pointless.

### 5. Mixture of Complementary Agents (arXiv:2605.24048)
- **Claim:** Proposer selection reframed as combinatorial (feature-selection-like) optimization; "the value of an LLM lies in its complementarity with others"; greedy complementarity selection on a small labeled set achieves best performance-cost trade-offs.
- **Steal:** The marketplace's bidder-selection rule: score candidate judges/proposers by *marginal complementarity* to the seated panel (measured on a small labeled probe set), not by solo accuracy. This directly informs bid weighting.

### 6. Blackwell's Informativeness — pooled posterior bound (arXiv:2605.06028)
- **Claim:** "Voting and debate induce information structures that are no more informative than the pooled private information of all agents… Bayesian pooled posterior maximisation as an information-theoretic upper-bound decision rule." Practical method: estimate each agent's posterior, approximate pooled posterior via **product-of-posteriors**; beat SOTA debate/voting on six QA benchmarks.
- **Steal:** Replace raw majority voting in the aggregation layer with a **pooled-posterior estimator**: each judge reports a posterior (not just a vote); the engine multiplies (with calibration weights). This is the mathematically principled upgrade over the current market's Vickrey-only clearing for the *verdict* path.

### 7. Calibrate, Don't Curate (arXiv:2605.09702)
- **Claim:** "Retaining all judges achieves NLL 0.006 versus 0.013 under top-5 selection, halving the calibration error… even below-chance judges can be useful when their biases are learnable and their signals are non-redundant."
- **Steal:** **Never discard weak judges by accuracy.** The Oracle judge pool keeps everyone parseable/non-redundant; calibration (Platt/isotonic on a labeled set) absorbs their biases. Feed each judge's bias profile into the pooled-posterior weights instead of a binary keep/drop.

### 8. LLM-as-a-Judge Is Not an Oracle (arXiv:2609.02246, 2026-09-02 — freshest paper in the set)
- **Claim:** "The judge should be demoted from oracle to advisor: its verdict becomes one input among several, and every change is gated instead by a deterministic verification layer the judge cannot override." PROCTOR: stateful orchestrator holds all tool access; stateless subagents propose; Teacher grades under five deterministic guardrails — hermetic sandboxes, capability-disjoint roles, **acceptance checks that outrank the Teacher**, frozen holdouts, canary cases where a perfect score is evidence of cheating.
- **Steal:** The Oracle's **constitutional doctrine**: the deterministic aggregation/market layer outranks every LLM judge. Judges advise; the engine decides. Steal the canary pattern too: seeded questions with known answers where a perfect-but-wrong-pattern score exposes gaming (relevant to stake-and-slash design in SPEC §3).

### 9. Judge, Retrieve, or Abstain (arXiv:2608.17994)
- **Claim:** Calibrate uncertainty thresholds on a held-out set so the false discovery rate among *accepted* verdicts stays below user-specified α "with high probability, using finite-sample Clopper–Pearson intervals"; low-confidence instances route to a retrieval-augmented mode under a second calibrated threshold.
- **Steal:** The Oracle's **abstention gate** with a formal guarantee: verdicts below the calibrated threshold are not emitted — they escalate (debate tier / human). Finite-sample, no asymptotic hand-waving. This is the principled version of SPEC's slash conditions for judges.

### 10. VERDI — single-call confidence from the reasoning trace (arXiv:2605.11334)
- **Claim:** Logprobs "saturate above 0.999 with structured JSON output" and are anti-calibrated on several models; VERDI decomposes verification into sub-checks and derives three structural signals (Step-Verdict Alignment, Claim-Level Margin, Evidence Grounding Score) combined with Platt scaling — AUROC 0.72–0.91, zero extra inference calls.
- **Steal:** Judge confidence should come from the **reasoning trace**, not token logprobs. Zero marginal cost (judges already produce traces). Vendor this as the confidence module.

### 11. Rethinking Verbalized Confidence (arXiv:2609.10996, 2026-09-10)
- **Claim:** "Compatibility shift": on post-2025 proprietary models, verbalized confidence is now the more robust soft-scoring mechanism than logprobs; + overconfidence advisory + self-debate improves calibration, score spread, robustness to subjectivity.
- **Steal:** For current-generation judge models, ask for **verbalized confidence** as the soft signal feeding the pooled posterior — do not use logprobs (they saturate). Add the overconfidence-advisory prompt ingredient.

### 12. Judge Datasheet (arXiv:2606.15610)
- **Claim:** Treat each judge "as a measurement instrument": measure dark current under true-vacuum inputs, positional false preference, target sensitivity on a controlled quality ladder, criterion induced by tie instructions. "Prompting moves the criterion, not the resolution."
- **Steal:** **Datasheets for the judge pool**: each runner profile (already HMAC-signed per SPEC §1) gains a psychometric datasheet — dark current, position bias, tie criterion. A strict tie criterion "eliminates Delta0 false preference." This slots directly into runner profiles + bid weighting.

### 13. DiscoUQ — structured disagreement for uncertainty (arXiv:2603.20975)
- **Claim:** Don't use shallow vote statistics; extract disagreement *structure* — evidence overlap, argument strength, divergence depth, embedding geometry — for calibrated confidence. AUROC 0.802, ECE 0.036 vs 0.098 baseline; biggest wins in the "weak disagreement" tier where vote counting fails.
- **Steal:** The Oracle's confidence number should be computed from **disagreement structure**, not vote margins. When the panel weakly disagrees, that's exactly where naive aggregation is most overconfident.

### 14. D3 — Debate, Deliberate, Decide (arXiv:2410.04663)
- **Claim:** Cost-aware adversarial framework with two protocols: MORE (k parallel advocates per answer — parallel advocacy provably increases score separation) and SAMRE (single advocate, multi-round, budgeted stopping with convergence checks). Probabilistic model of score gaps; anonymization + role diversification reduce positional/verbosity bias.
- **Steal:** The **escalation-tier debate protocol**: parallel advocates (k per side, anonymized) + budgeted stopping + convergence checks. The "budgeted stopping" is the cost-control answer for debate rounds in the marketplace.

### 15. Raven-Agent — the Belief-to-Trade layer (arXiv:2607.03015)
- **Claim:** "Trading requires more than forecasting"; calibrated probability ≠ trading result. Raven-Agent achieved the only positive risk-adjusted return among tested policies.
- **Steal (from its open repo, below):** the architectural separation — forecasting engine produces a calibrated probability; a distinct trade layer turns edge into action. The Oracle's market layer needs the same firewall: verdict probability ≠ bid/stake size; a sizing layer (Kelly-style) sits between.

### 16. LLM-judge-reporting (arXiv:2511.21140)
- **Claim:** Plug-in bias correction θ̂ = (p + q0 − 1)/(q0 + q1 − 1) with CIs reflecting *both* test and calibration uncertainty + adaptive calibration-sample allocation.
- **Steal:** The ~3.5KB math module to vendor directly into the Oracle for bias-corrected judge reporting.

---

## (b) Concrete borrow list

Ranked by recency × relevance (operator ranking). All URLs verified live 2026-09-20.

### Tier 1 — steal the mechanism, soonest

**1. cimo-labs/cje** — https://github.com/cimo-labs/cje (MIT, pip: `cje-eval`, active)
Causal Judge Evaluation: calibrate LLM-as-judge scores against a small oracle-labeled sample, with refusal gates and valid uncertainty. arXiv:2512.11150.
- `cje/calibration/flexible_calibrator.py` + `judge.py` — judge→oracle mapping with uncertainty
- `cje/diagnostics/gates.py` — **refusal gates**: never let an unchecked assumption pass silently (`residual transport NOT_CHECKED` until a held-out probe audit grades it)
- `cje/diagnostics/transport.py` — transport audit protocol (PASS/FAIL/INCONCLUSIVE with predeclared practical margins, ≥20 effective clusters)
- `cje/diagnostics/planning.py` — **label budgeting**: variance model → square-root allocation law for how many oracle labels to buy
- `cje/estimators/direct_method.py` — calibrated direct estimator
- `cje/interface/analysis.py` + `cli.py` — `analyze_dataset()` + pairwise comparisons with paired influence-function SE and Benjamini–Hochberg for sweeps
- `PLAYBOOK.md` — the operational runbook: inner calibration loop / outer monitoring loop, drift response, post-audit correction protocol. **Steal the whole loop.**
- `skills/cje/SKILL.md` — agent-native skill teaching the calibration workflow (pattern for Oracle's own agent skill)
- *Why:* This is the closest thing to a production "judge calibration department" in open source. The Oracle's judge panel should run the CJE loop verbatim: calibrate → precision gate → deploy → monitor → drift gate → refit.

**2. Alchemist-X/predict-raven** — https://github.com/Alchemist-X/predict-raven (live on Polymarket, pushed 2026-09-18 — freshest repo in the set)
First autonomous continuously-running prediction-market trading agent. arXiv:2607.03015.
- `packages/forecast-engine/src/engine.ts` — the round loop: prior-aware prompt → agent → validate → claim/source verification → claim dedupe → Bayesian update → persist
- `packages/forecast-engine/src/bayes.ts` — logit/invLogit/applyLlrs with per-claim attribution, clamps (LLR ≤ 2 nats, p ∈ [1%,99%])
- `packages/forecast-engine/src/claims.ts` — source ranking, claim quality scoring, cross-check weights, cluster discounting
- `packages/forecast-engine/src/framing.ts` — **Round 0**: normalize prompt → binary question + resolution criteria + date + settlement source; refuse vague questions (fail-closed)
- `packages/forecast-engine/src/types.ts` — agent round-output contract (structured JSON, validated fail-closed)
- `packages/forecast-engine/EXAMPLE-ROUND-IO.md` + `DIAGRAM.md` — the worked example and state machine (framing → open → converged/no_new_info/max_rounds/aborted → summary)
- `packages/market-intelligence/` (`intelligence_enricher.py`, `tag_library.py`, `worldmonitor_client.py`) — market data enrichment pipeline
- `services/orchestrator/` — service orchestration pattern
- *Why:* The **template for the Oracle's deterministic aggregation core**. Steal these invariants verbatim: (i) the engine owns the number — agents emit signed per-claim LLRs only; (ii) continuity invariant (round n prior = round n−1 posterior); (iii) one atomic claim = one update, extra sources only change verification quality (kills page-counting bias); (iv) fabrication guard — reconcile every cited URL against the actual search trace; (v) reflection entries can revise prior claims but only with new citations and clamped magnitude.

**3. YichengYang-Ethan/oracle3** — https://github.com/YichengYang-Ethan/oracle3 (255★, JOSS paper 2026-05-07, 633 tests)
Autonomous prediction-market trading agent with a calibrated pricing engine.
- `oracle3/pricing/` — **Wang Transform** p_mkt = Φ(Φ⁻¹(p*) + λ), λ̂=0.183 global + hierarchical covariate model λᵢ = 0.259 − 0.072·ln(1+V) + 0.143·ln(1+D) − 0.477·|p−0.5|, calibrated by MLE on **291,309 resolved contracts**; online recalibrator = batch MLE + streaming EWMA + category shrinkage
- `oracle3/strategy/` — eight **constraint-based strategies** enforcing probability-axiom invariants (cross-market identity, exclusivity P(A)+P(B)≤1, implication monotonicity, conditional bounds, event-sum unity) + fair-value divergence + premium-decay lifecycle + stat-arb (cointegration, lead-lag)
- `oracle3/core/` + `oracle3/trader/` — async event loop, SpreadExecutor with atomic multi-leg posting and LIFO unwind (no naked legs), dual-layer risk manager (local limits + pre-flight checks), Kelly/model-Greek-driven sizing
- CLI killswitch via Unix-socket control plane (`run_full_simulation.py`, `demo_server.py`)
- *Why:* The Oracle's **market layer** needs a fair-value engine and axiom-invariant violation detectors, not just Vickrey clearing. The Wang Transform is the only open calibrated pricing model for binary contracts at this scale — it corrects the favorite-longshot bias (a 50% contract trades ~57¢). Steal the invariant-strategy pattern for policing the bid marketplace.

### Tier 2 — steal the pattern

**4. UW-Madison-Lee-Lab/LLM-judge-reporting** — https://github.com/UW-Madison-Lee-Lab/LLM-judge-reporting (arXiv:2511.21140)
- `llm_judge_reporting/calibration.py` — `point_estimator()` (bias-adjusted θ̂) + `confidence_interval()` (test + calibration uncertainty)
- `llm_judge_reporting/allocation.py` — `allocate_calibration_sample()` — optimal split of calibration budget between specificity/sensitivity samples
- *Why:* ~3.5KB of math to vendor directly. Every judge-panel verdict the Oracle emits should carry a bias-corrected point estimate and CI, not a raw mean.

**5. DaBestCode/JudgeGauge** — https://github.com/DaBestCode/JudgeGauge (Apache-2.0, inspired by arXiv:2609.04198)
- `src/judgegauge/calibration.py` + `suites.py` — **fail-closed smoke gate**: 9 requests measuring same-window repeat ranking, candidate-order sensitivity, invalid readouts; exit codes 0/1/2 (unparseable = fail closed)
- `providers.py` — OpenAI-compatible adapter (pattern for herd-router adapter)
- `reporting.py` — JSON/SARIF/HTML/Markdown reports
- *Why:* The pre-flight gate for the Oracle's judge pool: before any expensive verdict run, smoke-test the seated judges for stability. A model name is not a frozen measurement instrument (their audit: same-window repeat ranking Spearman 0.400 vs required 0.90).

**6. deeplearning-wisc/debate-or-vote** — https://github.com/deeplearning-wisc/debate-or-vote (NeurIPS 2025 Spotlight code)
- `src/main.py` — MAD harness with decentralized/centralized/sparse topologies, multi-persona agents, vote-vs-debate solver switch
- `src/evaluator.py` — the **alpha correction-bias intervention** (bias belief updates toward correction)
- `scripts/heterogeneous.sh` — heterogeneous-model runs (ties to the co-failure finding)
- *Why:* The reference implementation for the escalation-tier debate: only debate with correction-biasing and heterogeneous models.

**7. ZhangYiqun018/agent-for-debate** — https://github.com/ZhangYiqun018/agent-for-debate (ICASSP 2026, Agent4Debate)
- `src/agent/`, `src/app/`, `main.py`, `prompt/` — dynamic multi-agent debate framework
- *Why:* Newest published debate framework implementation; candidate scaffold for the deliberation tier if D3's protocol needs a runtime.

### Tier 3 — data, catalogs, scaffolds

**8. LukasNel/kalshibench** — https://github.com/LukasNel/kalshibench — the 1,189 resolved prediction-market questions from arXiv:2605.30802. *Use as the Oracle's resolution-accuracy benchmark.*

**9. Multi-Agent-LLMs/mallm** — https://github.com/Multi-Agent-LLMs/mallm — multi-agent LLM conversational task-solving framework. *Fallback MAS scaffold.*

**10. komako-workshop/digital-oracle** — https://github.com/komako-workshop/digital-oracle — macro-question oracle agent skill mining 13 sources (Polymarket, Kalshi, CFTC, SEC…). *Borrow the evidence-source catalog for the Oracle's research layer.*

---

## (c) Design recommendations — the fused Oracle

**Architecture: four layers, one constitutional rule.**

*Constitutional rule (from PROCTOR + Raven): the deterministic engine owns every number it emits — verdicts, probabilities, confidence, payouts. LLM judges and debaters are advisors producing structured, attributable inputs (votes, posteriors, per-claim LLRs). No LLM output ever bypasses the engine. The engine's acceptance checks outrank every judge.*

**Layer 1 — Framing (fail-closed).** Raven's Round 0, verbatim: every Oracle question is normalized to a binary (or n-ary) question + explicit resolution criteria + resolution date + settlement source + a base-rate prior. Vague questions are refused with a clarification request — never answered with false precision. Framing output is HMAC-signed into the question record (extends SPEC §1 runner profiles to question profiles).

**Layer 2 — Evidence (parallel, asymmetric).** Independent researcher/judge agents run in parallel (cheap — the workhorse), each receiving a *designed-asymmetric* evidence partition: shared public core + disjoint private subsets (InfoDelphi). Evidence unit = **atomic factual claim** (Raven): one claim, one Bayesian update; multiple sources on the same claim only adjust verification quality, with cluster discounting. Every claim carries stance, signed LLR (clamped), cluster_id, rationale, and URLs reconciled against the actual retrieval trace (fabrication guard). Per-round continuity invariant. The Vickrey bid marketplace from SPEC §2 stays, but **bids are weighted by calibrated judge confidence**, and bidder selection optimizes **marginal complementarity** (2605.24048) with a tracked **co-failure rate β** (2606.27288) as the panel health metric.

**Layer 3 — Aggregation (pooled posterior, calibrated).** Replace raw majority vote with **product-of-posteriors pooled estimation** (Blackwell bound), where each judge's contribution is: posterior × calibration weight (Platt/isotonic on labeled set) × datasheet reliability (dark current, position bias, tie criterion per 2606.15610). Confidence comes from **disagreement structure** (DiscoUQ features), not vote margins. Every verdict ships with: bias-corrected point estimate + CI (judge-reporting math), and a limitations line (CJE-style: which assumptions are NOT_CHECKED). Keep all judges — calibrate, don't curate.

**Layer 4 — Market & accountability (Vickrey + invariants + gates).** SPEC's Vickrey clearing and stake-and-slash remain, extended with: (i) **probability-axiom invariant strategies** (oracle3) policing the market — exclusivity, event-sum unity, implication monotonicity violations emit signals/slashes; (ii) **Wang-Transform fair-value engine** as the reference price for binary questions; (iii) **Kelly-style sizing** between verdict probability and stake (Raven's belief-to-trade firewall); (iv) **JudgeGauge smoke gate** before every verdict run — unstable judges are seated out, fail-closed; (v) **abstention gate** with Clopper–Pearson FDR control — below-threshold verdicts escalate instead of emitting.

**Escalation ladder (the routing doctrine).** Default: Layer 2 parallel + Layer 3 aggregate → verdict. Escalate to **structured debate** (D3 MORE/SAMRE: k parallel anonymized advocates per side, budgeted stopping, correction-biased updates) only on: disagreement above margin, below-threshold confidence, or invariant violation. Escalate to **human arbitration** on persistent disagreement. Auto-resolve unanimous high-confidence questions (97.87% precedent). Debate is a cost center, never the default.

**Calibration ops (CJE playbook, adapted).** The Oracle runs a permanent two-loop calibration operation: inner loop (sample judge scores + oracle labels → fit judge→oracle map → precision gate → deploy) and outer loop (monitor with fresh oracle labels → residual-equivalence drift gate → refit/escalate). Label budget allocated by the square-root law. Canary questions (known answers, PROCTOR-style) continuously probe for judge gaming and feed stake-and-slash.

**Evaluation.** KalshiBench (1,189 resolved questions) as the standing resolution benchmark; Brier score + calibration curves + co-failure rate as the standing metrics. Report per the judge-reporting framework (bias-corrected, CIs).

---

## (d) What NOT to build

1. **A bespoke calibration library.** CJE (`cje-eval` on PyPI) + the 3.5KB judge-reporting module + JudgeGauge cover bias correction, CIs, refusal gates, transport audits, and label budgeting. Vendor and adapt; do not re-derive.
2. **Debate-as-default.** Two independent 2025–2026 results say deliberation adds little (martingale) or actively hurts (76% vs 83.43%). The "debate oracle" concept must be demoted to an escalation tier behind vote-first aggregation.
3. **Logprob-based confidence.** Saturates above 0.999 on structured JSON; anti-calibrated on several current models. Use verbalized confidence (compatibility shift) and VERDI trace-decomposition instead.
4. **A from-scratch forecasting engine.** Raven's `forecast-engine` (engine/bayes/claims/framing/types + the state machine) is the proven template — port its invariants, don't redesign.
5. **A from-scratch pricing model.** The Wang Transform on 291K contracts is the calibrated reference; oracle3's invariant strategies are the market-policing pattern.
6. **Judge curation by accuracy.** "Calibrate, Don't Curate" reverses this: weak judges are signal once calibrated. Build the calibrator, not the filter.
7. **New debate topologies from first principles.** D3 (MORE/SAMRE + budgeted stopping) and Agent4Debate are the current published protocols; adopt one for the escalation tier.
8. **Trust in judge stability.** A model name is not a frozen measurement instrument (Spearman 0.400 same-window repeat ranking in the JudgeGauge-cited audit). The smoke gate is mandatory, not optional.

---

## Appendix: search log

- Paper races (arXiv + alphaXiv via `/home/toxic/estate/skills/paper-search/bin/paper-search`, 8 results each): "LLM debate architecture decision oracle", "mixture-of-agents ensemble LLM", "LLM-as-judge methodology evaluation", "prediction markets for AI agents", "confidence calibration LLM judges", "ensemble verdict aggregation multi-agent debate" → 48 papers, 45 unique arXiv IDs.
- Full abstracts pulled for 15 highest-signal papers via arXiv API.
- GitHub code search (6 queries × 8 hits → 47 unique repos, recency-weighted rank: 0.45·recency + 0.20·tests + 0.15·multi-query + 0.10·log(stars) + 0.10·log(forks)) + date-filtered repo searches ("prediction market oracle", "llm judge calibration", "multi-agent debate framework").
- Deep file reads: cje (README, PLAYBOOK, module trees), LLM-judge-reporting (README, calibration.py, allocation.py), JudgeGauge (README, package tree), debate-or-vote (main.py), predict-raven (forecast-engine README, EXAMPLE-ROUND-IO, DIAGRAM, module trees), oracle3 (paper.md, module trees), agent-for-debate (tree).

**Read-only work only.** No commits, no pushes, no process changes on yote. No credentials touched (GitHub API via the broker surrogate through the github skill; arXiv unauthenticated).
