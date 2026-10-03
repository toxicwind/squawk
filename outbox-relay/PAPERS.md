# squawk-relay: paper research (reliable relay)

Two sources ground the design. Both were read (abstracts + key sections via
web search, 2026-09-20); the mappings below are how the relay implements them.

## 1. Transactional outbox (pattern)

Chris Richardson, *Microservices Patterns* (2018), "Transactional outbox"
pattern (microservices.io). Grounded via ADR writeup:

- https://github.com/mansiverma897993/atlas/blob/HEAD/docs/adr/0006-transactional-outbox.md

Core claim: never dual-write (DB + broker). The event store **is** the
outbox: events are appended in one local transaction and carry a monotonic
`global_seq`; a separate **relay** process tails `global_seq` and publishes;
delivery is **at-least-once**; consumers are **idempotent** (dedup on
`event_id`); poison messages are quarantined, not blocking.

Relay mapping:

| Paper concept | squawk-relay |
|---|---|
| outbox table, same-tx write | `outbox.jsonl`: entry appended with fsync BEFORE the per-channel cursor advances (`sink.append_outbox` + atomic `state.json` commit) |
| monotonic `global_seq` | `seq` — global feed counter, persisted in `state.json` |
| relay process tails seq | `forward.py`: inotify on the relay dir + 30s sweep, ordered by `seq` |
| at-least-once | state committed atomically AFTER each successful post; crash replays <= 1 message by construction |
| idempotent consumer (`event_id`) | deterministic `idempotency_key` per source message + persistent seen-set + startup channel reconciliation |
| poison isolation | `MAX_ATTEMPTS=5` then quarantine; one bad entry never stalls the queue |

## 2. MillWheel: at-least-once + dedup via atomic record-ID write

T. Akidau et al., "MillWheel: Fault-Tolerant Stream Processing at Internet
Scale", Proc. VLDB 2013.

- http://static.googleusercontent.com/media/research.google.com/ru//pubs/archive/41378.pdf

Core claim: the system assigns **unique IDs to all records at production
time**; deliveries are retried until ACKed (at-least-once, so duplicates
happen on crash-before-ACK); duplicates are discarded by **including the
unique ID for the record in the same atomic write as the state
modification**.

Relay mapping:

| Paper concept | squawk-relay |
|---|---|
| unique record ID at production | `relay_common.idempotency_key(channel, msg_seq, author, ts, body_hash)` — deterministic, stable across re-ingests |
| retry until ACK | forwarder blocks the queue on failed post, retries next sweep (order preserved) |
| ID in the same atomic write as state | `mark_seen` + `cursor_seq` advance + `last_key` committed via `atomic_write_json` (tmp + fsync + rename) AFTER the post — the dedup record and the cursor move together, so a crash can only replay, never double-apply |
| duplicate discard | `dup suppressed` path; startup `reconcile_channel_keys()` scans the dest channel so a crash between post and commit can never double-post |

## Incidents that validated the design (2026-09-20, live)

- **Double-post from dual forwarders**: `acquire_lock()` discarded its file
  handle, so CPython GC released the flock at startup and two forwarder
  instances raced one outbox entry (#fleet/10033 + #fleet/10034, same
  `relay_key`). Fixed with per-daemon lock files (`.sink.lock` /
  `.forward.lock`) + process-lifetime handle pinning. The idempotency key
  is what made the double-post *detectable*.
- **Racy manual outbox appends**: an ad-hoc test script appended replays
  with self-computed `seq` values, twice colliding with the sink's own
  sequence (duplicate seqs). The forwarder's cursor logic skipped the
  shadowed entry both times. Lesson: outbox writes must go through the
  sink (or pause it first); `seq` uniqueness is the invariant everything
  else rests on. Safe re-injection procedure: pause via `control.json`,
  append at `max(seq)+1` with the same key, resume — proven 2026-09-20
  (seq 38 re-injection of `relay:leads:8:9793ec989080` suppressed, exactly
  one #fleet post).

## 3. Styx — arXiv:2312.06893 (loop 2)

*Styx: Deterministic Transactional Serverless Functions on Streaming Dataflows.*
Exactly-once function-to-function calls via the streaming dataflow model:
periodic snapshots of operator state to a durable store, deterministic
replay after failure. Mapping: `forward-state.json` (cursor + seen-keys +
counters, atomically written after every post) is the relay's snapshot
store; `reconcile_channel_keys()` (scan #fleet for `relay_key:` on startup)
is deterministic replay — a restarted forwarder converges to exactly the
posted set without double-delivery. Refinement from this loop: none needed
beyond what existed; it validated the snapshot+reconcile design.

## 4. Kafka KIP-98 / EOS: broker-side idempotent producer (loop 2)

The broker assigns each producer a PID; the producer attaches
(PID, epoch, per-partition monotonic seq); the broker keeps the last 5
batches per (PID, partition) and dedups retries — idempotence as a property
of the LOG, not just the consumer. Cross-restart duplicates need
transactional.id fencing. Mapping → refinement implemented in `sink.py`:

- `seed_sink_seen()` + per-sweep dedup: the outbox log itself is the dedup
  authority; a key already in the log is never appended twice, even across
  cursor rewinds (tested: rewind simulation → `sink_dup_suppressed`).
- `sink_dup_suppressed` counter, exposed in `relay-status`.
- Producer fencing analog: per-daemon `flock` files (`.sink.lock`,
  `.forward.lock`), pinned for process lifetime — a stale/zombie forwarder
  can never hold the lock, so two forwarders can never race the same entry
  (this fixed a real double-post found during E2E).

## 5. HFT doctrine → hop telemetry (synthesis)

From the local HFT corpus (squawk-hft-latency.md): push-not-poll, hot
persistent paths, fail-fast ceilings, *measure every hop*. The relay was
already push-driven (inotify); the synthesis added what it lacked:

- `hop_samples` ring (200) in forward-state: `t_msg_to_outbox_s` and
  `t_outbox_to_post_s` per relayed message.
- `relay-status` reports p50/p95/max per hop — the 68s outbox→post outlier
  during the restart storm was caught by this telemetry, not by guessing.
- `relay-out` subprocess timeout 60s → 20s (fail-fast ceiling).
