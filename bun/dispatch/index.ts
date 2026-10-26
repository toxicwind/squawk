// tools/estate-chat/dispatch.ts — fleet dispatch: durable lease-based task queue.
//
// In-process module loaded by chat.ts (estate-chat). The estate-chat
// process is the SINGLE WRITER of dispatch.db (SQLite WAL, co-located with
// chat.db in STATE_DIR). Readers take short-lived handles.
//
// Every protocol transition is recorded four ways:
//   1. dispatch.db (system of record)
//   2. room message (fleet-dispatch / fleet-claims / fleet-dead-letter) —
//      since_seq replay covers dispatch with zero new machinery
//   3. WebSocket broadcast frame (reactive push)
//   4. JSONL mirror line (mirrorDir/lease-ledger.jsonl, dead-letters.jsonl)
//
// Wedge semantics (merged spec §1, BINDING):
//   alive | wedge-suspect (silent 2x cadence, heartbeats fresh)
//   | wedged (silent 3x cadence OR 50% of lease, whichever first)
//   | dead (heartbeats stale past threshold or owner gone)
//   WEDGED is flagged, NEVER auto-requeued. BLOCKED extends the lease, does
//   not expire. expire (reclaim) is allowed only on DEAD-classified claims
//   past lease expiry; a fresh heartbeat vetoes it.

import { Database } from "bun:sqlite";
import { appendFileSync, mkdirSync } from "node:fs";

export interface DispatchDeps {
  stateDir: string;
  mirrorDir: string;
  broadcast: (topic: string, payload: any) => void;
  postRoomMessage: (room_id: string, p: Record<string, any>) => any;
  ensureRoom: (room_id: string, name: string) => void;
  ensureSystemAgent: () => void;
  holderHeartbeat: (agent_id: string) => string | null; // ISO ts or null
  presenceTtlS?: number;
}

const HEARTBEAT_DEAD_S = 300; // holder heartbeat older than this (or absent) => dead
const SYSTEM_AGENT = "dispatch";
export const ROOM_TASKS = "fleet-dispatch";
export const ROOM_CLAIMS = "fleet-claims";
export const ROOM_DEAD = "fleet-dead-letter";

const nowISO = () => new Date().toISOString();

export function tierDefaultLeaseSecs(priority: number): number {
  if (priority >= 10) return 60;
  if (priority >= 1) return 300;
  return 900;
}
export function labelFor(priority: number): string {
  if (priority >= 10) return "urgent";
  if (priority >= 1) return "normal";
  return "batch";
}
function labelToPriority(label: string): number {
  const l = String(label || "").toLowerCase();
  if (l === "urgent") return 10;
  if (l === "batch") return 0;
  return 5; // normal
}

function fail(status: number, message: string): never {
  throw Object.assign(new Error(message), { status });
}

export interface WedgeVerdict { signal: "alive" | "wedge-suspect" | "wedged" | "dead" | "blocked"; basis: string; }

export function createDispatch(deps: DispatchDeps) {
  const { stateDir, mirrorDir, broadcast, postRoomMessage, ensureRoom, ensureSystemAgent, holderHeartbeat } = deps;
  const presenceTtlS = deps.presenceTtlS ?? 120;

  mkdirSync(stateDir, { recursive: true });
  mkdirSync(mirrorDir, { recursive: true });
  const db = new Database(stateDir + "/dispatch.db", { create: true });
  db.exec("PRAGMA journal_mode = WAL;");
  db.exec(`
  CREATE TABLE IF NOT EXISTS dispatch_tasks (
    task_id      TEXT PRIMARY KEY,
    priority     INTEGER NOT NULL,
    label        TEXT NOT NULL,
    payload      TEXT NOT NULL,
    dedup_key    TEXT,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    lease_secs   INTEGER,
    cadence_secs INTEGER NOT NULL DEFAULT 900,
    created_ts   TEXT NOT NULL,
    available_ts TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    attempts     INTEGER NOT NULL DEFAULT 0
  );
  CREATE TABLE IF NOT EXISTS dispatch_leases (
    lease_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id              TEXT NOT NULL,
    attempt              INTEGER NOT NULL,
    claimed_by           TEXT NOT NULL,
    claimed_ts           TEXT NOT NULL,
    lease_expires_ts     TEXT NOT NULL,
    wedge_ts             TEXT NOT NULL,
    state                TEXT NOT NULL DEFAULT 'progressing',
    queue_depth_at_claim INTEGER NOT NULL DEFAULT 0,
    wait_secs            REAL NOT NULL DEFAULT 0,
    lease_secs           INTEGER NOT NULL,
    cadence_secs         INTEGER NOT NULL,
    status               TEXT NOT NULL DEFAULT 'live',
    ended_ts             TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_leases_task ON dispatch_leases(task_id, status);
  CREATE TABLE IF NOT EXISTS dispatch_acks (
    ack_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    lease_id  INTEGER NOT NULL,
    task_id   TEXT NOT NULL,
    acked_ts  TEXT NOT NULL,
    wait_secs REAL NOT NULL,
    exec_secs REAL NOT NULL
  );
  CREATE TABLE IF NOT EXISTS dispatch_dead_letters (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id  TEXT NOT NULL,
    lease_id INTEGER,
    reason   TEXT NOT NULL,
    detail   TEXT,
    ts       TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS dispatch_wedge_signals (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id  TEXT NOT NULL,
    lease_id INTEGER NOT NULL,
    signal   TEXT NOT NULL,
    basis    TEXT NOT NULL,
    ts       TEXT NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_wedge_lease ON dispatch_wedge_signals(lease_id, id);
  CREATE TABLE IF NOT EXISTS dispatch_poison (
    task_id       TEXT NOT NULL,
    agent_id      TEXT NOT NULL,
    blocked_until TEXT NOT NULL,
    PRIMARY KEY (task_id, agent_id)
  );
  CREATE TABLE IF NOT EXISTS dispatch_metrics_min (
    bucket            TEXT PRIMARY KEY,
    claims            INTEGER NOT NULL DEFAULT 0,
    acks              INTEGER NOT NULL DEFAULT 0,
    expires           INTEGER NOT NULL DEFAULT 0,
    dead_letters      INTEGER NOT NULL DEFAULT 0,
    dup_rejected      INTEGER NOT NULL DEFAULT 0,
    wedge_transitions INTEGER NOT NULL DEFAULT 0
  );
  CREATE TABLE IF NOT EXISTS dispatch_counters (
    name TEXT PRIMARY KEY,
    n    INTEGER NOT NULL DEFAULT 0
  );
  `);

  ensureRoom(ROOM_TASKS, "fleet-dispatch");
  ensureRoom(ROOM_CLAIMS, "fleet-claims");
  ensureRoom(ROOM_DEAD, "fleet-dead-letter");
  ensureSystemAgent();

  const q = (sql: string) => db.query(sql);
  const getTask = (task_id: string) =>
    q("SELECT * FROM dispatch_tasks WHERE task_id = ?").get(task_id) as any;
  const getLease = (lease_id: number) =>
    q("SELECT * FROM dispatch_leases WHERE lease_id = ?").get(lease_id) as any;
  const liveLeaseForTask = (task_id: string) =>
    q("SELECT * FROM dispatch_leases WHERE task_id = ? AND status = 'live' ORDER BY lease_id DESC LIMIT 1").get(task_id) as any;

  function bumpCounter(name: string, by = 1) {
    db.prepare("INSERT INTO dispatch_counters (name, n) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET n = n + ?")
      .run(name, by, by);
    const bucket = nowISO().slice(0, 16);
    const col = { claim: "claims", ack: "acks", expire: "expires", dead_letter: "dead_letters", dup_rejected: "dup_rejected", wedge: "wedge_transitions" }[name];
    if (col) {
      db.prepare(`INSERT INTO dispatch_metrics_min (bucket, ${col}) VALUES (?, ?) ON CONFLICT(bucket) DO UPDATE SET ${col} = ${col} + ?`)
        .run(bucket, by, by);
    }
  }

  function mirror(event: string, row: Record<string, any>, deadLetter = false) {
    const line = JSON.stringify({ ts: nowISO(), event, ...row });
    try {
      appendFileSync(mirrorDir + "/lease-ledger.jsonl", line + "\n");
      if (deadLetter) appendFileSync(mirrorDir + "/dead-letters.jsonl", line + "\n");
    } catch (e) {
      console.error("[dispatch] mirror write failed:", String(e));
    }
  }

  function roomMsg(room_id: string, kind: string, body: any) {
    try {
      postRoomMessage(room_id, { from_agent: SYSTEM_AGENT, kind, body: JSON.stringify(body) });
    } catch (e) {
      console.error("[dispatch] room message failed:", String(e));
    }
  }

  // --- wedge classification (canonical; lazy — evaluated on read) -----------
  function classify(lease: any): WedgeVerdict {
    const now = Date.now();
    const state: string = lease.state || "progressing";
    if (state === "blocked" || state.startsWith("blocked:")) {
      return { signal: "blocked", basis: `state=${state}; lease extended, never expires` };
    }
    const hb = holderHeartbeat(lease.claimed_by);
    const hbAgeS = hb ? (now - Date.parse(hb)) / 1000 : Infinity;
    if (!hb || hbAgeS > HEARTBEAT_DEAD_S) {
      return { signal: "dead", basis: !hb ? `holder ${lease.claimed_by} unknown/gone` : `holder heartbeat stale ${Math.round(hbAgeS)}s > ${HEARTBEAT_DEAD_S}s` };
    }
    const silentMs = now - Date.parse(lease.wedge_ts);
    const cadenceMs = lease.cadence_secs * 1000;
    const leaseMs = lease.lease_secs * 1000;
    const wedgedAtMs = Math.min(3 * cadenceMs, 0.5 * leaseMs); // whichever first
    if (silentMs >= wedgedAtMs) {
      return { signal: "wedged", basis: `no progress for ${Math.round(silentMs / 1000)}s (wedged at ${Math.round(wedgedAtMs / 1000)}s = min(3x cadence, 50% lease)); heartbeats fresh` };
    }
    if (silentMs >= 2 * cadenceMs) {
      return { signal: "wedge-suspect", basis: `no progress for ${Math.round(silentMs / 1000)}s >= 2x cadence (${lease.cadence_secs}s); heartbeats fresh` };
    }
    return { signal: "alive", basis: `progress ${Math.round(silentMs / 1000)}s ago within cadence ${lease.cadence_secs}s` };
  }

  function lastSignal(lease_id: number): string | null {
    const r = q("SELECT signal FROM dispatch_wedge_signals WHERE lease_id = ? ORDER BY id DESC LIMIT 1").get(lease_id) as any;
    return r ? r.signal : null;
  }

  // Emit a wedge-signal transition if the classification changed. Returns the
  // verdict; emits the wire frame + durable copy + mirror + room message.
  function emitWedgeIfChanged(lease: any): WedgeVerdict {
    const v = classify(lease);
    const prev = lastSignal(lease.lease_id);
    if (prev !== v.signal) {
      const ts = nowISO();
      db.prepare("INSERT INTO dispatch_wedge_signals (task_id, lease_id, signal, basis, ts) VALUES (?,?,?,?,?)")
        .run(lease.task_id, lease.lease_id, v.signal, v.basis, ts);
      const frame = { type: "wedge-signal", task_id: lease.task_id, lease_id: lease.lease_id, signal: v.signal, basis: v.basis, ts };
      broadcast(ROOM_CLAIMS, frame);
      roomMsg(ROOM_CLAIMS, "wedge-signal", frame);
      mirror("wedge_signal", { task_id: lease.task_id, lease_id: lease.lease_id, signal: v.signal, basis: v.basis });
      bumpCounter("wedge");
    }
    return v;
  }

  function claimEnvelope(lease: any) {
    return {
      task_id: lease.task_id,
      claimed_by: lease.claimed_by,
      lease_expires_ts: lease.lease_expires_ts,
      attempt: lease.attempt,
      wedge_ts: lease.wedge_ts,
      state: lease.state,
      queue_depth_at_claim: lease.queue_depth_at_claim,
      wait_secs: lease.wait_secs,
    };
  }

  // --- protocol -------------------------------------------------------------
  function postTask(p: Record<string, any>) {
    const task_id = String(p.task_id || "").trim();
    if (!task_id) fail(400, "task_id is required");
    if (getTask(task_id)) fail(409, `task ${task_id} already exists`);
    const priority = p.priority !== undefined ? Math.max(0, Math.floor(Number(p.priority))) : labelToPriority(p.label || "normal");
    if (!Number.isFinite(priority)) fail(400, "priority must be numeric or one of urgent|normal|batch");
    const payload = p.payload !== undefined ? (typeof p.payload === "string" ? p.payload : JSON.stringify(p.payload)) : "";
    const ts = nowISO();
    const task = {
      task_id, priority, label: p.label ? String(p.label) : labelFor(priority),
      payload: payload.slice(0, 20000),
      dedup_key: p.dedup_key ? String(p.dedup_key).slice(0, 200) : null,
      max_attempts: p.max_attempts !== undefined ? Math.max(1, Math.floor(Number(p.max_attempts))) : 5,
      lease_secs: p.lease_secs !== undefined ? Math.max(5, Math.floor(Number(p.lease_secs))) : null,
      cadence_secs: p.cadence_secs !== undefined ? Math.max(5, Math.floor(Number(p.cadence_secs))) : 900,
      created_ts: ts, available_ts: ts, status: "pending", attempts: 0,
    };
    db.prepare(`INSERT INTO dispatch_tasks
      (task_id, priority, label, payload, dedup_key, max_attempts, lease_secs, cadence_secs, created_ts, available_ts, status, attempts)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`).run(
      task.task_id, task.priority, task.label, task.payload, task.dedup_key, task.max_attempts,
      task.lease_secs, task.cadence_secs, task.created_ts, task.available_ts, task.status, task.attempts);
    const frame = { type: "task", ...task };
    broadcast(ROOM_TASKS, frame);
    roomMsg(ROOM_TASKS, "task", frame);
    mirror("task_posted", { task_id, priority: task.priority, label: task.label, dedup_key: task.dedup_key });
    return task;
  }

  function listTasks(status?: string) {
    const rows = (status
      ? q("SELECT * FROM dispatch_tasks WHERE status = ? ORDER BY priority DESC, created_ts ASC").all(status)
      : q("SELECT * FROM dispatch_tasks ORDER BY priority DESC, created_ts ASC").all()) as any[];
    return rows.map((t) => {
      const lease = t.status === "claimed" ? liveLeaseForTask(t.task_id) : null;
      return { ...t, live_lease: lease ? claimEnvelope(lease) : null, wedge: lease ? classify(lease) : null };
    });
  }

  function claim(task_id: string, p: Record<string, any>) {
    const task = getTask(task_id);
    if (!task) fail(404, `unknown task ${task_id}`);
    if (task.status !== "pending") fail(409, `task ${task_id} is ${task.status}, not pending`);
    const claimed_by = String(p.claimed_by || "").trim();
    if (!claimed_by) fail(400, "claimed_by is required");
    // anti-poison: original claimant blocked from re-claim for 2x lease_secs
    const poison = q("SELECT blocked_until FROM dispatch_poison WHERE task_id = ? AND agent_id = ?").get(task_id, claimed_by) as any;
    if (poison && poison.blocked_until > nowISO()) {
      bumpCounter("dup_rejected");
      fail(409, `anti-poison: ${claimed_by} may not re-claim ${task_id} until ${poison.blocked_until}`);
    }
    // dedup_key: reject a second live claim for the same key (no state change)
    if (task.dedup_key) {
      const clash = q(`SELECT l.lease_id, l.task_id FROM dispatch_leases l
        JOIN dispatch_tasks t ON t.task_id = l.task_id
        WHERE l.status = 'live' AND t.dedup_key = ? AND t.task_id != ?
        LIMIT 1`).get(task.dedup_key, task_id) as any;
      if (clash) {
        bumpCounter("dup_rejected");
        mirror("claim_rejected_duplicate", { task_id, dedup_key: task.dedup_key, live_lease_id: clash.lease_id, live_task_id: clash.task_id });
        fail(409, `dedup_key ${task.dedup_key} already has live lease ${clash.lease_id} on ${clash.task_id}`);
      }
    }
    const ts = nowISO();
    const attempt = task.attempts + 1;
    const leaseSecs = task.lease_secs || tierDefaultLeaseSecs(task.priority);
    const queueDepth = (q("SELECT COUNT(*) AS c FROM dispatch_tasks WHERE status = 'pending' AND created_ts <= ?").get(task.created_ts) as any).c - 1;
    const waitSecs = Math.max(0, (Date.parse(ts) - Date.parse(task.available_ts)) / 1000);
    const lease = {
      task_id, attempt, claimed_by, claimed_ts: ts,
      lease_expires_ts: new Date(Date.parse(ts) + leaseSecs * 1000).toISOString(),
      wedge_ts: p.wedge_ts ? String(p.wedge_ts) : ts,
      state: p.state ? String(p.state).slice(0, 200) : "progressing",
      queue_depth_at_claim: Math.max(0, queueDepth), wait_secs: waitSecs,
      lease_secs: leaseSecs, cadence_secs: task.cadence_secs,
      status: "live", ended_ts: null,
    };
    const r = db.prepare(`INSERT INTO dispatch_leases
      (task_id, attempt, claimed_by, claimed_ts, lease_expires_ts, wedge_ts, state, queue_depth_at_claim, wait_secs, lease_secs, cadence_secs, status, ended_ts)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(
      lease.task_id, lease.attempt, lease.claimed_by, lease.claimed_ts, lease.lease_expires_ts,
      lease.wedge_ts, lease.state, lease.queue_depth_at_claim, lease.wait_secs,
      lease.lease_secs, lease.cadence_secs, lease.status, lease.ended_ts);
    const lease_id = Number(r.lastInsertRowid);
    db.prepare("UPDATE dispatch_tasks SET status = 'claimed', attempts = ? WHERE task_id = ?").run(attempt, task_id);
    bumpCounter("claim");
    const env = { lease_id, ...claimEnvelope({ ...lease }) };
    const frame = { type: "claim", lease_id, ...env };
    broadcast(ROOM_CLAIMS, frame);
    roomMsg(ROOM_CLAIMS, "claim", frame);
    mirror("claim", { lease_id, task_id, attempt, claimed_by, lease_expires_ts: lease.lease_expires_ts, wait_secs: waitSecs, queue_depth_at_claim: lease.queue_depth_at_claim });
    return env;
  }

  function progress(lease_id: number, p: Record<string, any>) {
    const lease = getLease(lease_id);
    if (!lease) fail(404, `unknown lease ${lease_id}`);
    if (lease.status !== "live") fail(409, `lease ${lease_id} is ${lease.status}, not live`);
    const before = classify(lease);
    const ts = nowISO();
    const state = p.state ? String(p.state).slice(0, 200) : lease.state;
    // BLOCKED extends the lease; it never expires while blocked.
    const lease_expires_ts = (state === "blocked" || state.startsWith("blocked:"))
      ? new Date(Date.parse(ts) + lease.lease_secs * 1000).toISOString()
      : lease.lease_expires_ts;
    db.prepare("UPDATE dispatch_leases SET wedge_ts = ?, state = ?, lease_expires_ts = ? WHERE lease_id = ?")
      .run(p.wedge_ts ? String(p.wedge_ts) : ts, state, lease_expires_ts, lease_id);
    const updated = getLease(lease_id);
    const frame = { type: "progress", lease_id, task_id: lease.task_id, state, wedge_ts: updated.wedge_ts, ts };
    broadcast(ROOM_CLAIMS, frame);
    roomMsg(ROOM_CLAIMS, "progress", frame);
    mirror("progress", { lease_id, task_id: lease.task_id, state });
    // A progress event emits wedge-cleared when the claim was suspect/wedged.
    let cleared: any = null;
    if (before.signal === "wedge-suspect" || before.signal === "wedged") {
      const cts = nowISO();
      db.prepare("INSERT INTO dispatch_wedge_signals (task_id, lease_id, signal, basis, ts) VALUES (?,?,?,?,?)")
        .run(lease.task_id, lease_id, "wedge-cleared", `progress posted after ${before.signal}`, cts);
      cleared = { type: "wedge-signal", task_id: lease.task_id, lease_id, signal: "wedge-cleared", basis: `progress posted after ${before.signal}`, ts: cts };
      broadcast(ROOM_CLAIMS, cleared);
      roomMsg(ROOM_CLAIMS, "wedge-signal", cleared);
      mirror("wedge_signal", { task_id: lease.task_id, lease_id, signal: "wedge-cleared", basis: cleared.basis });
      bumpCounter("wedge");
    }
    return { ok: true, lease_id, state, wedge_ts: updated.wedge_ts, lease_expires_ts, cleared };
  }

  function ack(lease_id: number, p: Record<string, any>) {
    const lease = getLease(lease_id);
    if (!lease) fail(404, `unknown lease ${lease_id}`);
    if (lease.status !== "live") fail(409, `lease ${lease_id} is ${lease.status}, not live`);
    const ts = nowISO();
    const execSecs = Math.max(0, (Date.parse(ts) - Date.parse(lease.claimed_ts)) / 1000);
    db.prepare("INSERT INTO dispatch_acks (lease_id, task_id, acked_ts, wait_secs, exec_secs) VALUES (?,?,?,?,?)")
      .run(lease_id, lease.task_id, ts, lease.wait_secs, execSecs);
    db.prepare("UPDATE dispatch_leases SET status = 'acked', ended_ts = ? WHERE lease_id = ?").run(ts, lease_id);
    db.prepare("UPDATE dispatch_tasks SET status = 'completed' WHERE task_id = ?").run(lease.task_id);
    bumpCounter("ack");
    const frame = { type: "ack", lease_id, task_id: lease.task_id, acked_by: p.by ? String(p.by) : lease.claimed_by, wait_secs: lease.wait_secs, exec_secs: execSecs, ts };
    broadcast(ROOM_CLAIMS, frame);
    roomMsg(ROOM_CLAIMS, "ack", frame);
    mirror("ack", { lease_id, task_id: lease.task_id, wait_secs: lease.wait_secs, exec_secs: execSecs });
    return { ok: true, lease_id, task_id: lease.task_id, wait_secs: lease.wait_secs, exec_secs: execSecs };
  }

  function deadLetter(task_id: string, lease_id: number | null, reason: string, detail: string | null, by: string) {
    const ts = nowISO();
    db.prepare("INSERT INTO dispatch_dead_letters (task_id, lease_id, reason, detail, ts) VALUES (?,?,?,?,?)")
      .run(task_id, lease_id, reason, detail, ts);
    db.prepare("UPDATE dispatch_tasks SET status = 'dead' WHERE task_id = ?").run(task_id);
    if (lease_id) db.prepare("UPDATE dispatch_leases SET status = 'nacked', ended_ts = ? WHERE lease_id = ?").run(ts, lease_id);
    bumpCounter("dead_letter");
    const frame = { type: "dead-letter", task_id, lease_id, reason, detail, by, ts };
    broadcast(ROOM_DEAD, frame);
    roomMsg(ROOM_DEAD, "dead-letter", frame);
    mirror("dead_letter", { task_id, lease_id, reason, detail, by }, true);
    return { ok: true, task_id, reason, ts };
  }

  function expire(lease_id: number, p: Record<string, any>) {
    const lease = getLease(lease_id);
    if (!lease) fail(404, `unknown lease ${lease_id}`);
    if (lease.status !== "live") fail(409, `lease ${lease_id} is ${lease.status}, not live`);
    const ts = nowISO();
    if (lease.lease_expires_ts > ts) fail(409, `lease ${lease_id} not yet expired (expires ${lease.lease_expires_ts})`);
    const verdict = emitWedgeIfChanged(lease); // lazy classification on the reclaim path
    if (verdict.signal !== "dead") {
      fail(409, `lease ${lease_id} classifies ${verdict.signal} (${verdict.basis}) — reclaim allowed only on DEAD claims; WEDGED is flagged, never auto-requeued`);
    }
    const task = getTask(lease.task_id);
    db.prepare("UPDATE dispatch_leases SET status = 'expired', ended_ts = ? WHERE lease_id = ?").run(ts, lease_id);
    // anti-poison: original claimant blocked from re-claim for 2x lease_secs
    const blockedUntil = new Date(Date.parse(ts) + 2 * lease.lease_secs * 1000).toISOString();
    db.prepare("INSERT INTO dispatch_poison (task_id, agent_id, blocked_until) VALUES (?,?,?) ON CONFLICT(task_id, agent_id) DO UPDATE SET blocked_until = excluded.blocked_until")
      .run(lease.task_id, lease.claimed_by, blockedUntil);
    bumpCounter("expire");
    const by = p.by ? String(p.by) : "unknown";
    let outcome: any;
    if (task.attempts >= task.max_attempts) {
      deadLetter(lease.task_id, lease_id, "attempts-exhausted", `attempt ${task.attempts} expired; max_attempts=${task.max_attempts}`, by);
      outcome = { requeued: false, dead: true, reason: "attempts-exhausted" };
    } else {
      const newPriority = task.priority + 1; // starved tasks rise
      db.prepare("UPDATE dispatch_tasks SET status = 'pending', available_ts = ?, priority = ? WHERE task_id = ?")
        .run(ts, newPriority, lease.task_id);
      outcome = { requeued: true, attempt: task.attempts, new_priority: newPriority, poison_until: blockedUntil };
    }
    const frame = { type: "expire", lease_id, task_id: lease.task_id, by, ts, ...outcome };
    broadcast(ROOM_CLAIMS, frame);
    roomMsg(ROOM_CLAIMS, "expire", frame);
    mirror("expire", { lease_id, task_id: lease.task_id, by, ...outcome });
    return { ok: true, lease_id, ...outcome };
  }

  function nack(lease_id: number, p: Record<string, any>) {
    const lease = getLease(lease_id);
    if (!lease) fail(404, `unknown lease ${lease_id}`);
    if (lease.status !== "live") fail(409, `lease ${lease_id} is ${lease.status}, not live`);
    const reason = p.reason ? String(p.reason).slice(0, 300) : "nack";
    return deadLetter(lease.task_id, lease_id, reason, p.detail ? String(p.detail).slice(0, 1000) : null, p.by ? String(p.by) : lease.claimed_by);
  }

  function requeue(task_id: string, p: Record<string, any>) {
    const task = getTask(task_id);
    if (!task) fail(404, `unknown task ${task_id}`);
    if (task.status !== "dead") fail(409, `task ${task_id} is ${task.status}; only dead tasks can be re-queued (human/decider)`);
    const ts = nowISO();
    db.prepare("UPDATE dispatch_tasks SET status = 'pending', available_ts = ? WHERE task_id = ?").run(ts, task_id);
    const frame = { type: "requeue", task_id, by: p.by ? String(p.by) : "unknown", ts };
    broadcast(ROOM_TASKS, frame);
    roomMsg(ROOM_TASKS, "requeue", frame);
    mirror("requeue", { task_id, by: frame.by });
    return { ok: true, task_id, ts };
  }

  function deadLetterTask(p: Record<string, any>) {
    const task_id = String(p.task_id || "").trim();
    if (!task_id) fail(400, "task_id is required");
    const task = getTask(task_id);
    if (!task) fail(404, `unknown task ${task_id}`);
    const lease = liveLeaseForTask(task_id);
    return deadLetter(task_id, lease ? lease.lease_id : null,
      p.reason ? String(p.reason).slice(0, 300) : "manual",
      p.detail ? String(p.detail).slice(0, 1000) : null,
      p.by ? String(p.by) : "unknown");
  }

  function wedgeScan() {
    const leases = q("SELECT * FROM dispatch_leases WHERE status = 'live'").all() as any[];
    const transitions: any[] = [];
    for (const lease of leases) {
      const before = lastSignal(lease.lease_id);
      const v = emitWedgeIfChanged(lease);
      if (before !== v.signal) transitions.push({ lease_id: lease.lease_id, task_id: lease.task_id, from: before, to: v.signal, basis: v.basis });
    }
    return { ok: true, scanned: leases.length, transitions, ts: nowISO() };
  }

  function snapshot() {
    const tasks = listTasks();
    return {
      generated_ts: nowISO(),
      pending: tasks.filter((t) => t.status === "pending"),
      claimed: tasks.filter((t) => t.status === "claimed"),
      counts: {
        pending: tasks.filter((t) => t.status === "pending").length,
        claimed: tasks.filter((t) => t.status === "claimed").length,
        completed: tasks.filter((t) => t.status === "completed").length,
        dead: tasks.filter((t) => t.status === "dead").length,
      },
    };
  }

  function percentile(sorted: number[], p: number): number | null {
    if (!sorted.length) return null;
    const i = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length));
    return sorted[i];
  }

  function metrics() {
    const waits = (q("SELECT wait_secs FROM dispatch_acks ORDER BY wait_secs").all() as any[]).map((r) => r.wait_secs);
    const execs = (q("SELECT exec_secs FROM dispatch_acks ORDER BY exec_secs").all() as any[]).map((r) => r.exec_secs);
    const live = (q("SELECT * FROM dispatch_leases WHERE status = 'live'").all()) as any[];
    let suspect = 0, wedged = 0;
    for (const l of live) {
      const v = classify(l);
      if (v.signal === "wedge-suspect") suspect++;
      if (v.signal === "wedged") wedged++;
    }
    const byKey: Record<string, number> = {};
    for (const l of live) {
      const t = getTask(l.task_id);
      if (t && t.dedup_key) byKey[t.dedup_key] = (byKey[t.dedup_key] || 0) + 1;
    }
    const dupLiveViolations = Object.values(byKey).filter((n) => n > 1).length;
    const expired = (q("SELECT COUNT(*) AS c FROM dispatch_leases WHERE status = 'expired'").get() as any).c;
    const acked = (q("SELECT COUNT(*) AS c FROM dispatch_leases WHERE status = 'acked'").get() as any).c;
    const nacked = (q("SELECT COUNT(*) AS c FROM dispatch_leases WHERE status = 'nacked'").get() as any).c;
    const finished = acked + expired + nacked;
    const counters = Object.fromEntries((q("SELECT name, n FROM dispatch_counters").all() as any[]).map((r) => [r.name, r.n]));
    const deadByReason = (q("SELECT reason, COUNT(*) AS c FROM dispatch_dead_letters GROUP BY reason").all() as any[]);
    // minute-bucket rollup cache, populated on demand
    const bucket = nowISO().slice(0, 16);
    db.prepare("INSERT INTO dispatch_metrics_min (bucket) VALUES (?) ON CONFLICT(bucket) DO NOTHING").run(bucket);
    return {
      ts: nowISO(),
      dispatch_latency_s: { p50: percentile(waits, 50), p95: percentile(waits, 95), n: waits.length },
      exec_s: { p50: percentile(execs, 50), p95: percentile(execs, 95), n: execs.length },
      orphan_rate: finished ? expired / finished : 0,
      duplicate_execution_violations: dupLiveViolations,
      counters,
      dead_letters_by_reason: deadByReason,
      wedge: { suspect, wedged, live_claims: live.length },
      minute_buckets: q("SELECT * FROM dispatch_metrics_min ORDER BY bucket DESC LIMIT 60").all(),
    };
  }

  return {
    postTask, listTasks, claim, progress, ack, expire, nack, requeue,
    deadLetterTask, wedgeScan, snapshot, metrics, classify, db,
  };
}

export type Dispatch = ReturnType<typeof createDispatch>;
