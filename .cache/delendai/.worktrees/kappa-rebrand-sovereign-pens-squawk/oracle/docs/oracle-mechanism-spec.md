# Oracle-Market Mechanism Spec v1

Spec for the three oracle-market layers: HMAC-signed runner profiles,
Vickrey second-price clearing, stake-and-slash accountability.
All file-based, event-driven, no new infrastructure.
Research: papers + borrowed GitHub patterns (see §7).

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

### 1.4 Grades
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

One 32-byte pre-shared secret per bidder serves both HMAC (§1) and
seal (different primitives; acceptable for our threat model).

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
