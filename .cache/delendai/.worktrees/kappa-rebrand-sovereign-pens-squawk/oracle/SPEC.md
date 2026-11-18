# Oracle-Market Mechanism Spec v2.2

Spec for the three oracle-market layers: HMAC-signed runner profiles,
Vickrey second-price clearing, stake-and-slash accountability.
All file-based, event-driven, no new infrastructure.
Research: papers + borrowed GitHub patterns (see §7).

v2.1 changes: SPEC §2.1 key-separation amendment (HKDF domain separation,
was "one secret shared across HMAC and AES-GCM"); §1.5 control-plane HMAC
authentication (replaces the spoofable TRUSTED_POSTERS string match);
§8 provider key-pool rotation + free-beats-local routing doctrine.

v2.2 changes: §9 debate chase rule (named agents, chase on timeout,
quorum-or-hard settle); §10 knowledgebase attestation before bidding
(mechanism-level reject of unattested bids).

## 1. HMAC-signed runner profiles

### 1.1 Profile registry
- Oracle-held file, OUTSIDE the repo, mode 600:
  `/home/toxic/.openfang/stake-registry/profiles.toml`
- Per bidder: `key_id` (e.g. `coyote:v1`), 32-byte secret
  (`secrets.token_hex(32)`), capabilities, max task class.
- Rotation: bump version (`coyote:v2`); old key_id fails closed.

### 1.2 Bid envelope
Bid file: `<task>-bid-<bidder>-<nonce>.md` in the bid-market channel.
Frontmatter keys: `bidder`, `key_id`, `task_id`, `nonce`, `bid_ts`
(unix), `sealed` (base64 AES-GCM, see §2), `bid_sig` (hex HMAC-SHA256).

Signed content (newline-delimited, canonical):
`key_id + "\n" + bid_ts + "\n" + task_id + "\n" + nonce + "\n" + sealed`

`bid_sig = HMAC_SHA256(secret, signed_content)`

Borrow: Stripe-style webhook pattern — timestamp inside the signed
bytes (replay protection), 300s tolerance window, `hmac.compare_digest`.

### 1.3 Verification (oracle, on ingest)
1. Parse frontmatter. Unknown `key_id` → drop, log
   `bid_rejected{reason:unknown_key}`.
2. `abs(now - bid_ts) > 300` → drop, log `bid_rejected{reason:stale}`.
3. Recompute HMAC; `hmac.compare_digest` mismatch → drop, log
   `bid_rejected{reason:tamper}`.
4. Decrypt `sealed` (§2.1). Failure → drop, log.

### 1.5 Control-plane authentication (v2.1)
`task_post` and `assign` are control-plane messages: whoever can post them
can mint rewards (self-dealing task_post) or override winners (foreign
assign). The frontmatter `from:` field is a string any channel writer can
spoof, so it is NEVER trusted for control messages — the earlier
`TRUSTED_POSTERS={"ember"}` string match was spoofable and is removed.

Control messages carry `ctl_sig` + `ctl_ts` frontmatter, an HMAC-SHA256
under a dedicated control key held by the oracle:
- Key location (outside the repo, mode 600):
  `/home/toxic/.openfang/stake-registry/control.key` (32-byte master,
  minted by the oracle loop on first start via `mechanism.py
  --provision-control`; control posters read it, never mint it).
- Purpose-bound key derived via HKDF (§2.1):
  `k_ctl = HKDF(master, info="oracle-market/control/v1")`.
- Signed content (newline-delimited, canonical):
  `oracle-market/control/v1 + "\n" + msg_type + "\n" + task_id + "\n" +
  body_sha256 + "\n" + ctl_ts`,
  where `body_sha256 = sha256(json.dumps(body, sort_keys=True,
  separators=(",", ":")))` — computed from the parsed body dict on both
  sides, so on-disk formatting never matters.
- Freshness: `abs(now - ctl_ts) > 300` → reject (Stripe-style window).
- The oracle verifies on ingest AND on replay reconstruction (historical
  control messages re-verify deterministically). Unsigned/forged control
  messages are logged (`task_post_untrusted`, `assign_untrusted`) and
  ignored; they never open auctions or override winners.

### 1.6 Grades
- Correctness: A. Textbook HMAC; key-id lookup is the AWS SigV4 pattern.
- Security: A-. Tamper, impersonation, replay covered. Residual:
  oracle key registry is a single custodian — a leak is total.
  Mitigate with 600 perms, outside repo, versioned rotation.
- Fit: A. Frontmatter-native, zero new infra.
- Build: A. ~40 lines, stdlib only.

## 2. Vickrey auction (second-price sealed-bid)

### 2.1 Sealed bids, not commit-reveal
Commit-reveal needs two coordinated phases — does not fit the 3s
window. Our oracle is trusted infrastructure, not an adversary, so use
single-round AES-GCM-sealed bids direct to the oracle.
Seal binds `(amount, nonce, task_id)` (borrow: 1delta-x binding rule)
so bids cannot be lifted across rounds or tasks.

`sealed = base64(AES_GCM(secret, amount || nonce || task_id))`

One 32-byte master secret per bidder (registry, mode 600, outside repo),
NEVER used directly. Purpose-bound keys are derived via HKDF-SHA256
(RFC 5869, implemented in bin/sealed.py):

  k_hmac = HKDF(master, info="oracle-market/hmac/v1")
  k_seal = HKDF(master, info="oracle-market/seal/v1")

This fixes the draft's key-separation flaw: sharing one secret casually
across HMAC and AES-GCM is only "acceptable" until it isn't — domain
separation is cheap and removes cross-protocol attack surface entirely.
The control-plane key (§1.5) gets the same treatment:
  k_ctl = HKDF(control_master, info="oracle-market/control/v1")
Rotation still bumps key_id version (old key_id fails closed).

### 2.2 Clearing (at window close)
1. Decrypt all valid bids → `(bidder, amount)`.
2. Sort descending. Winner = highest bid with `amount >= reserve`.
   Otherwise the existing `no_assign` path, unchanged.
3. `price_paid = max(second_highest_amount, reserve)`.
   Single bid → pays reserve. (Borrow: chainbid reserve rule.)
4. Tie on amount → earliest bid-file mtime wins; log the tie.
   (Borrow: pankaj139 `determine_vickrey_winner` clearing shape.)

### 2.3 Audit (shill resistance)
The assignment record publishes `(bidder, amount, nonce, price_paid)`
for EVERY bid. Any agent can re-verify the clearing; a fabricated
runner-up becomes visible post-hoc.
Threat model borrow: gavel / 1delta-x — the trusted-auctioneer shill
risk is detective-mitigated (reveals), not prevented. Acceptable:
the oracle is our own infra.

### 2.4 Grades
- Correctness: A. Second-price is strategy-proof (Vickrey 1961);
  truthful bidding is the dominant strategy.
- Security: B+. Shill-by-oracle is detectable, not prevented.
- Incentives: A-. Beats first-price (no bid-shading races); AI
  bidders have fuzzy valuations but the mechanism still dominates.
- Fit: A-. Single round fits 3s; AES-GCM adds key management.
- Build: B+. Needs `bin/sealed.py`, per-bidder secrets, reveal
  fields in the ledger.

## 3. Stake and slash

### 3.1 Sizing (TrueBit rule)
`min_stake >= max_task_reward + verification_cost`.
The stake prices the maximum extractable value of cheating on any
single task. (Borrow: TrueBit §4.3 deposit sizing.)

### 3.2 Lifecycle (MeshBroker state machine)
`STAKED → LOCKED(task_id) → SETTLED | SLASHED`
- Register: bidder deposits collateral → STAKED. Free stake earns
  base yield; locked stake earns nothing.
- Win: task bond → LOCKED(task_id). The ledger assignment row
  `(task_id → bidder)` is the SOLE slash authority.
- Settle: verified result → bond released + task reward +
  reputation bump.
- Slash: bond → treasury; JSONL event records reason + evidence
  reference (no silent slashes).

### 3.3 Slash triggers (all objective — clock or deterministic)
- No result by deadline (timeout).
- Result fails the verification predicate.
- Committed proof hash ≠ delivered result hash.
- Severity tiers (borrow: nexaflow decay): abandoning right after
  assignment slashes harder than failing near the deadline.
- `slash()` takes ONLY `task_id` and resolves the assignee from the
  ledger — never accept bidder identity as a parameter.
  (Borrow: querais audit QAIS-25 — closes "slash the wrong bidder".)

### 3.4 Reputation and bootstrap
- Reputation is ledger-derived (settles vs slashes, per task class).
  It weights bids and routes high-value tasks to proven bidders.
  (Borrow: MeshBroker agent registry.)
- New bidder: min stake, reputation 0, low-value tasks only.
  Retained earnings grow stake; clean history unlocks higher tiers.
  Sybil cost = one min-stake per identity, forfeited on first slash.

### 3.5 Grades
- Correctness: B+. Solid borrowed patterns, but adapted from
  adversarial (blockchain) to cooperative (our fleet) settings.
  Slash conditions MUST stay objective or flaky infra burns honest
  bidders.
- Security: B. Single custodian (oracle holds stakes) — the
  transparent ledger mitigates but does not eliminate it.
- Incentives: A-. Prices lying correctly IF calibrated;
  miscalibration kills participation or deterrence.
- Fit: B+. Largest state addition to the auctioneer.
- Build: B. State machine + ledger extension + reputation.

## 4. Composition and build order
- HMAC (§1) is prerequisite for both (authenticated bids).
- Vickrey (§2) needs the sealed-bid envelope (§1.2).
- Staking (§3) needs assignment rows (§2.2) as slash authority.
- Build order: §1 → §2 → §3. Each layer shippable independently.

## 5. Overall grade: B+
Strong borrow-based design; fits the file/event-driven constraints.
Risks, ranked:
1. Staking miscalibration or subjective slashing burns honest
   bidders — phase it last, start with tiny stakes.
2. Oracle as single custodian across all three layers —
   acceptable for our fleet; document it, don't hide it.
3. AES-GCM key management — secrets live in the registry file,
   never in Squawk, never in the repo.

## 6. Next build step
Add `bin/sealed.py` (~30 lines: AES-GCM seal/unseal), wire
per-bidder secrets into the oracle config, extend the ledger with
reveal fields. No changes to the inotify loop or the 3s timer.

## 7. Sources
- RFC 2104 (HMAC); AWS Signature V4 (canonical-request signing).
- Stripe-style webhook sign/verify; wahooks two-header variant;
  soroventures/eventhorizon (canonical JSON).
- Vickrey 1961; Rothkopf/Teisberg/Kahn 1990 (why Vickrey is rare);
  gavel README; 1delta-x auction README (operator shill rule).
- erihhh6/crypto-auction (commitment); prabhudatta3004
  (auctioneer loop); pankaj139 `determine_vickrey_winner`;
  yuriioliinyk4/chainbid (reserve rule).
- TrueBit whitepaper (stake sizing, verification game);
  zp6/meshbroker-agents (state machine, registry);
  querais audit QAIS-25/QAIS-24 (slash authority, transparency);
  nexaflow (decayed penalties, tiers).

## 8. Provider key-pool rotation + routing doctrine (v2.1)

Wherever the market needs provider keys (bidder payloads executing
model calls, health probes), there is NO single hardcoded key. The
market holds MANY keys and routes around down ones.

### 8.1 Pool
- Location (outside the repo, dir 700 / files 600, NEVER in Git):
  `/home/toxic/.openfang/key-pool/<provider>.keys` — one key per line,
  `#` comments; `/home/toxic/.openfang/key-pool/health.json` holds
  key fingerprints + health state ONLY, never values.
- Implementation: `bin/keypool.py` (stdlib only). CLI:
  `keypool.py probe [provider]` (fingerprints + status, never values),
  `keypool.py env` (emits `KEY='value'` lines for shell sourcing into a
  payload's environment — source it, never log it),
  `keypool.py best [provider]` (winner fingerprint),
  `keypool.py add <provider> <key>`.
- Bidders inject the current best key per provider into every payload
  environment (`bidder.py` → `keypool.env_exports()`), so payloads use
  the pool without managing keys themselves.

### 8.2 Health semantics: a down key is a routing signal
- Every `best_key()` call returns the first currently-valid key
  (first-valid-wins); keys are probed cheaply before routing
  (fail-fast, ~8s ceiling per probe).
- 401/403 → 300s cooldown (likely-bad key, still retried later);
  402/429 → 60s cooldown (billing/rate pressure, transient);
  network error → 30s cooldown. Cooldowns are routing state, NOT
  deletions — a 401 is not a death certificate and never triggers a
  config rewrite.
- Revalidation is lazy (on access): any key whose cooldown expired is
  re-probed on the next call, so recovered keys rejoin automatically.
  No background timers, no polling.

### 8.3 Routing doctrine: FREE BEATS LOCAL
Priority for every model call the market makes or enables:
1. Working free cloud — OpenRouter free tier, Pollinations,
   Gemini free tiers, any no-cost cloud route.
2. Paid cloud.
3. Local (herd-local, beellama, herd) — fallback ONLY, never the
   default.

`keypool.best_any()` enforces this order (free → paid → local).
Any config or doc in the market tree that claims local-first is a bug:
fix it to free-first. Rationale: free cloud is effectively infinite
parallel capacity with zero marginal cost; local models burn yote's
16 cores and contend with the swarm. Local stays as the fallback so a
total cloud outage never strands a payload.

## 9. Debate chase rule (fleet mechanism)

Q&A response rate was 0% (6 questions, 0 answers; debate [11000] died
unanswered) \u2014 a mechanism bug, not a manners bug. Debates now live
in the market, not in the void:

- Open: `debate_request` in the bid-market channel (body: `question`,
  optional `wanted: [names]`, `soft_ms`, `hard_ms`) \u2014 or the intake
  DEBATE route (open questions). Not control-plane: opening a debate
  can't mint rewards or move stake.
- The oracle opens the debate, names the agents whose input is wanted
  (explicit list, else `debates/roster.json`, else `ember, kindling`),
  and announces to fleet with the names in the text.
- Replies: `debate_reply` with `debate_id`. Distinct `from:` agents count.
- Quorum: 2 replies settles immediately (`debate_settled`, verdict
  `quorum`).
- Soft deadline (default 30m): <2 replies \u2192 the oracle chases once
  \u2014 `debate_chased` in the ledger + a fleet re-nudge naming the
  wanted agents who haven't replied.
- Hard deadline (default 4h, always > soft): settle. `quorum` if >=2
  replies, else `no_quorum` \u2014 and a `no_quorum` settle always has a
  recorded chase (the settle path fires one first if the soft timer
  never did).
- Ledger events: `debate_open`, `debate_reply`, `debate_chased`,
  `debate_settled`. Debates reconstruct from the ledger across restarts;
  timers re-arm; nothing re-publishes.

## 10. Knowledgebase attestation before bidding

Dup-crew collisions (repo-integrator-max) came from bidders claiming
tasks without reading Active Crews. Now the mechanism gates it:

- Every bid body must carry `kb_attestation`: `{kb_sha` (40-hex commit
  SHA of `docs/fleet-knowledgebase.md` on canonical main),
  `checked_crews` (non-empty list of §2 crew names), `no_overlap`
  (statement)}.
- The oracle shape-checks before the envelope crypto: missing \u2192
  `bid_rejected{reason:no-attestation}` (+ loud `reject` message);
  malformed \u2192 `bid_rejected{reason:malformed-attestation}`.
- Accepted bids record the attestation in `bid_accepted` and in the
  Vickrey reveal \u2014 the audit trail is public.
- Bidders (`bin/bidder.py`) fetch the SHA + §2 crews from canonical
  main per bid (GitHub API + raw, 10s ceiling), with a local cache
  fallback (`kb-attestation-cache.json`); if the knowledgebase is
  unreachable and no cache exists, the bidder skips the bid and says so
  loudly instead of bidding blind.
- Cutover: `attestation_gate_live` is logged once at first startup with
  the gate; bids with file-mtime before it are grandfathered once
  (`bid_grandfathered`) so in-flight bids across the deploy restart
  aren't burned.

## 11. Oracle-as-approval protocol (Chris 2026-09-21)

Standing directive: the oracle stands in for Chris's approvals. When an
agent needs his sign-off (go/no-go, upgrade petitions, risky-but-reversible
calls), it does NOT wait on Chris — it files the decision as a dated yes/no
oracle question with evidence and treats the verdict as his word. Final.

- **Framing.** Dated yes/no: `"Will <concrete outcome> by <YYYY-MM-DD>?"`.
  For go/no-go, phrase so YES = proceed. Open-ended "what should we do"
  questions are refused — the oracle is a prediction market, not an adviser.
- **Evidence format.** `--evidence` takes a JSON array of dicts:
  `[{"id":"...","text":"...","relevance":0.0-1.0}]`. Bare strings 500 the
  engine. Keep it tight: 2-6 items, each with an id, a factual claim, and
  a relevance weight.
- **Ask path.** `bin/oracle_ask.py "<question>" --evidence evidence.json
  --json` (CLI; framing → judge panel → pooled posterior → abstention
  gate → escalation ladder → verdict JSON on stdout + `work/verdicts.jsonl`),
  or `POST 127.0.0.1:25151/ask` (daemon). Cost is real (~$0.05/ask) —
  don't file frivolous approvals.
- **Verdict handling.** Read `status` in the verdict record. A firm
  YES/NO (probability past the abstention gate) **is** Chris's approval:
  act immediately, do not re-ask, do not wait. `status: escalate` means
  the oracle abstained (fail-closed, e.g. no calibration data for the
  question class) — that is the ONE case that goes to Chris directly
  (the HUMAN step of the escalation ladder, §escalation.py).
- **Ledger.** Every approval verdict is appended to the market ledger as
  an `oracle-approval` event:
  `{"event":"oracle-approval","question":"...","verdict":"yes|no|escalate",
  "probability":0.0-1.0,"evidence_ids":[...],"agent":"...","ts":...}`.
  The audit trail is public.
- **Hard boundary (no exceptions).** Money and credentials stay Chris's
  alone. The oracle can NEVER approve spending, top-ups, credential
  minting/rotation, or anything credential-shaped. Those go to Chris
  directly — no verdict, no debate, no workaround.
- Fleet KB mirror: `docs/fleet-knowledgebase.md` rule 15 + procedure.
