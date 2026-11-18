# agent-chat protocol — vNext specification

Status: vNext baseline. Reference implementation: `chat.py` plus the `agent_chat/` stdlib modules shipped with the package.

The keywords MUST, SHOULD, MAY are used as in RFC 2119.

## 1. Purpose

agent-chat defines a file-based coordination protocol for peer agent sessions.
Multiple sessions coordinate through human-readable, git-committable channel files:
messages, cursors, structured tasks, leases, path locks and a derived state summary.
The protocol is portable across tools that can read/write the shared filesystem.

The filesystem is the source of truth. A derived `state.md` is a convenience summary and
MUST NOT replace authoritative messages, task records, claim records, path locks or cursors.

## 2. Non-goals

agent-chat does NOT:

- execute agents or processes;
- assign models or tools;
- approve permissions or credentials;
- provide a remote coordination service;
- implement an MCP server or ACP/wake bridge;
- manage model memory or run an orchestration workflow.

Those belong to the host runtime or to a separately specified integration.

## 3. Folder layout

```text
<root>/
  <channel>/
    _meta.json
    _seq.lock
    _tasks.lock
    NNNN-<from>-<slug>.md
    .cursors/<agent>.txt
    tasks/<task-id>.json
    claims/<task-id>.<owner>.json
    locks/<lock-id>.json
    state.md
    .lease-transaction.json
    .path-lock-transaction.json
```

- A channel MUST contain `_meta.json`.
- Message files MUST begin with a numeric sequence followed by `-`.
- `tasks/`, `claims/`, `locks/` and transaction markers are protocol metadata and MUST NOT be treated as ordinary messages.
- `state.md` is derived and may be regenerated.
- Transaction markers are retained until the corresponding operation is committed, audited or explicitly recovered.

## 4. Message format

Messages are Markdown files with YAML-style frontmatter:

```text
---
seq: 12
from: alice
to: bob
reply_to: 11
channel: review
ts: 2026-07-17T14:03:22+07:00
status: discussion
title: Converge schema v0.2
---
<markdown body>
```

`seq`, `from`, `to`, `channel`, `ts` and `title` MUST be present. `to: all`, `*` or an omitted recipient means broadcast. A message MUST NOT be edited after writing; replies are new files with `reply_to`.

## 5. Core operations

A conforming implementation MUST provide:

| Operation | Contract |
|---|---|
| `init` | Create a channel and `_meta.json`; fail if the channel already exists. |
| `post` | Allocate the next sequence atomically and write a message. |
| `read` | Return relevant messages after the caller cursor and advance the cursor. |
| `wait` | Sleep in-process until a relevant message arrives or timeout; no model polling. |
| `claim` | Preserve the legacy atomic task-marker claim behavior. |
| `task` | Create/list/show/update/done/block/release structured task records. |
| `lock`/`check`/`unlock`/`recover` | Coordinate normalized workspace-relative paths with owner and stale-recovery rules. |
| `state`/`compact` | Render or atomically write a derived state summary without deleting source records. |
| `event` | Post/read versioned capability/status events through ordinary channel messages. |

A message is relevant to agent `X` when it is broadcast or addressed to `X`, and `from != X`.

## 6. Structured tasks and dependencies

Task records are JSON files under `tasks/` with:

```text
id, channel, title, status, owner, created_by, depends_on, files_hint,
acceptance, lease_expires_at, branch, updated_at
```

Valid statuses are `open`, `in_progress`, `blocked`, `done` and `cancelled`. Task IDs and paths MUST be root-bounded and safe. Dependency references MUST exist and MUST be acyclic.

A task may advance to `in_progress` or `done` only when every dependency has status `done`. Readiness is computed from task JSON, never message text. Same-state transitions are idempotent where the CLI documents them.

`files_hint` values are portable workspace-relative metadata, not file operations.
Both separator styles are recognized on every host; absolute/drive-relative paths,
parent traversal, symlink escapes and colon-bearing names (including Windows
alternate data streams) are rejected with `TASK_PATH_OUTSIDE_WORKSPACE`.

## 7. Leases and claims

Structured task claims are JSON records under `claims/`.

- New claims use exclusive creation or an equivalent atomic primitive.
- Renewal, release, recovery and completion are serialized with task mutation.
- Only the owner may renew, release or complete an unexpired claim.
- Expired claims MUST NOT be silently stolen.
- Recovery requires a new owner and non-empty reason and records the previous owner and expiry.
- Task and claim changes use a durable transaction marker and fail closed after a process interruption.
- Recovery validates task/owner/path identity and rollback payloads before any write.
- Every successful mutation posts a lease audit event.

## 8. Normalized path locks

Path locks are JSON records under `locks/`.

- Inputs are normalized to workspace-relative forward-slash paths.
- Absolute paths, traversal, control characters, malformed Unicode and symlink escapes MUST be rejected.
- Windows comparisons are case-insensitive; POSIX comparisons preserve case.
- File/file and directory/file overlaps conflict.
- Only the owner may unlock an active lock.
- Expired locks require explicit recovery with prior owner, expiry and reason.
- Lock mutations are atomic, auditable and crash-recoverable.

## 9. Derived state and compaction

`state.md` contains deterministic sections for:

- goal/topic;
- decisions;
- open tasks;
- blockers;
- owners and leases;
- path locks;
- verification evidence.

Ordering MUST be stable across repeated renders and platforms. `compact` MUST use an atomic temporary sibling replacement and MUST NOT delete, mutate or truncate authoritative messages, tasks, claims, locks or cursors. The default operation emits a `state.compacted` audit event; `--no-audit` explicitly disables that event.

## 10. Adapter-neutral capability/status events

Events are JSON bodies carried through ordinary messages and validated against `schemas/agent-chat-event.schema.json`.

Required common fields:

```text
schema_version: 1
 event: capability | status
 agent: string
 harness: string
 ts: ISO-8601 timestamp with offset
```

Capability events advertise only these portable primitives:

```text
messages, cursors, wait, tasks, dependencies, leases, path_locks, state_summary
```

Status events use `ready`, `busy`, `idle`, `blocked` or `stopped`, with optional detail. Unknown fields, event types, versions, primitives, identities, timestamps and statuses MUST fail with stable `EVENT_*` errors.

Capability events MUST NOT claim MCP, ACP, wake bridge or agent execution support.

## 11. Concurrency and recovery

- Sequence allocation MUST be atomic across concurrent posters.
- Task/lease/path-lock mutations MUST serialize through channel mutation locks.
- A transaction marker MUST remain when the process cannot prove whether a durable write or audit completed.
- Recovery MUST be explicit and auditable; no stale lock or lease is silently stolen.
- Windows NTFS and POSIX behavior MUST be covered by focused tests where semantics differ.

## 12. Conformance

A live coordination implementation conforms when it passes the focused behavior suites for messages, cursors, wait, tasks, leases, path locks, state, capability events and CLI compatibility. Host-native integrations, MCP wrappers and ACP/wake bridges require separate specifications.

## 13. Relationship to prior art

agent-chat combines peer file-backed coordination, atomic claims/cursors, structured task state, path ownership and cross-platform token-free waiting. It remains deliberately smaller than an agent executor or hosted orchestration platform.
