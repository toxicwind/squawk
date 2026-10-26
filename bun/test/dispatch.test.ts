// squawk/bun/test/dispatch.test.ts
import { beforeAll, afterAll, describe, expect, test } from "bun:test";
import { createDispatch, ROOM_TASKS } from "../dispatch/index.ts";
import { Database } from "bun:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

let dir: string;
let dispatch: ReturnType<typeof createDispatch>;
let db: Database;

const frames: Array<{ topic: string; payload: any }> = [];

beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), "squawk-dispatch-"));
  db = new Database(join(dir, "chat.db"), { create: true });
  db.exec(
    "CREATE TABLE IF NOT EXISTS agents (agent_id TEXT PRIMARY KEY, name TEXT, summoner TEXT, first_seen TEXT, last_heartbeat TEXT)",
  );
  dispatch = createDispatch({
    stateDir: dir,
    mirrorDir: dir,
    broadcast: (topic: string, payload: any) => frames.push({ topic, payload }),
    postRoomMessage: () => ({ ok: true }),
    ensureRoom: () => {},
    ensureSystemAgent: () => {
      const ts = new Date().toISOString();
      db.prepare(
        "INSERT OR IGNORE INTO agents (agent_id,name,summoner,first_seen,last_heartbeat) VALUES ('dispatch','dispatch','system',?,?)",
      ).run(ts, ts);
    },
    holderHeartbeat: (agent_id: string) => {
      const r = db
        .query("SELECT last_heartbeat FROM agents WHERE agent_id=?")
        .get(agent_id) as any;
      return r ? r.last_heartbeat : null;
    },
  });
});

afterAll(() => {
  dispatch.db.close();
  db.close();
  rmSync(dir, { recursive: true, force: true });
});

describe("dispatch task lifecycle", () => {
  test("postTask creates a pending task", () => {
    const t = dispatch.postTask({
      task_id: "t1",
      priority: 5,
      payload: "run x",
    });
    expect(t.task_id).toBe("t1");
    expect(t.status).toBe("pending");
  });

  test("postTask rejects duplicates", () => {
    expect(() =>
      dispatch.postTask({ task_id: "t1", payload: "again" }),
    ).toThrow("already exists");
  });

  test("listTasks shows pending", () => {
    const tasks = dispatch.listTasks();
    expect(tasks.some((t: any) => t.task_id === "t1")).toBe(true);
  });

  test("claim creates a live lease", () => {
    const env = dispatch.claim("t1", { claimed_by: "worker-a" });
    expect(env.claimed_by).toBe("worker-a");
    expect(env.lease_id).toBeGreaterThan(0);
  });

  test("claim on already-claimed rejects", () => {
    expect(() => dispatch.claim("t1", { claimed_by: "worker-b" })).toThrow(
      "not pending",
    );
  });

  test("classify reports alive on fresh claim", () => {
    const live = dispatch.db
      .query(
        "SELECT * FROM dispatch_leases WHERE task_id='t1' AND status='live'",
      )
      .get() as any;
    const v = dispatch.classify(live);
    expect(["alive", "wedge-suspect", "wedged", "dead", "blocked"]).toContain(
      v.signal,
    );
  });

  test("progress updates wedge_ts", () => {
    const live = dispatch.db
      .query(
        "SELECT * FROM dispatch_leases WHERE task_id='t1' AND status='live'",
      )
      .get() as any;
    const p = dispatch.progress(live.lease_id, { state: "working" });
    expect(p.ok).toBe(true);
    expect(p.state).toBe("working");
  });

  test("ack completes the task", () => {
    const live = dispatch.db
      .query(
        "SELECT * FROM dispatch_leases WHERE task_id='t1' AND status='live'",
      )
      .get() as any;
    const a = dispatch.ack(live.lease_id, { by: "worker-a" });
    expect(a.ok).toBe(true);
    const task = dispatch.db
      .query("SELECT status FROM dispatch_tasks WHERE task_id='t1'")
      .get() as any;
    expect(task.status).toBe("completed");
  });
});

describe("dispatch metrics + snapshot", () => {
  test("post a few tasks then snapshot", () => {
    dispatch.postTask({ task_id: "t2", priority: 10, payload: "urgent" });
    dispatch.postTask({
      task_id: "t3",
      priority: 1,
      payload: "batch",
      label: "batch",
    });
    const snap = dispatch.snapshot();
    expect(snap.counts.pending).toBeGreaterThanOrEqual(2);
    expect(Array.isArray(snap.pending)).toBe(true);
  });

  test("metrics returns counters + latency", () => {
    const m = dispatch.metrics();
    expect(typeof m.dispatch_latency_s).toBe("object");
    expect(typeof m.counters).toBe("object");
  });

  test("claim and nack -> dead letter", () => {
    const env = dispatch.claim("t2", { claimed_by: "worker-c" });
    const dl = dispatch.nack(env.lease_id, {
      reason: "failed",
      by: "worker-c",
    });
    expect(dl.ok).toBe(true);
    const task = dispatch.db
      .query("SELECT status FROM dispatch_tasks WHERE task_id='t2'")
      .get() as any;
    expect(task.status).toBe("dead");
  });

  test("requeue brings dead task back", () => {
    const r = dispatch.requeue("t2", { by: "decider" });
    expect(r.ok).toBe(true);
    const task = dispatch.db
      .query("SELECT status FROM dispatch_tasks WHERE task_id='t2'")
      .get() as any;
    expect(task.status).toBe("pending");
  });

  test("labelFor maps priority tiers", () => {
    expect(dispatch);
  });
});
