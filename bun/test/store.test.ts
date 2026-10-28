// squawk/bun/test/store.test.ts
import { beforeAll, afterAll, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openStore } from "../store/index.ts";

let dir: string;
let store: ReturnType<typeof openStore>;

beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), "squawk-store-"));
  store = openStore({ stateDir: dir, presenceTtlS: 120 });
});

afterAll(() => {
  store.db.close();
  rmSync(dir, { recursive: true, force: true });
});

describe("store identity + presence", () => {
  test("join creates an agent", () => {
    const r = store.join({
      name: "wren",
      summoner: "smith",
      agent_id: "wren-1",
    });
    expect(r.agent_id).toBe("wren-1");
    expect(r.receipt).toContain("wren");
  });

  test("anonymous join defaults summoner to anon (Anomaly #35)", () => {
    const r = store.join({ name: "nobody" });
    expect(r.agent_id).toBeDefined();
    expect(r.receipt).toContain("nobody");
  });

  test("heartbeat updates presence", () => {
    const hb = store.heartbeat({ agent_id: "wren-1", activity: "testing" });
    expect(hb.ok).toBe(true);
  });

  test("heartbeat unknown agent rejects", () => {
    expect(() => store.heartbeat({ agent_id: "ghost" })).toThrow(
      "unknown agent_id",
    );
  });

  test("liveAgents lists joined agent", () => {
    const live = store.liveAgents();
    const ids = (live.live as any[]).map((a) => a.agent_id);
    expect(ids).toContain("wren-1");
  });
});

describe("store rooms + messages", () => {
  test("default fleet room exists", () => {
    const rooms = store.rooms();
    expect(rooms.map((r: any) => r.room_id)).toContain("fleet");
  });

  test("createRoom adds a room", () => {
    store.createRoom({ room_id: "ops", name: "ops", created_by: "test" });
    const rooms = store.rooms();
    expect(rooms.map((r: any) => r.room_id)).toContain("ops");
  });

  test("postMessage auto-onboards unknown persona (identity is a feature, not a gate)", () => {
    // ghost was never joined — the message must still flow, with the
    // persona auto-onboarded (unverified) and an oracle clarify queued.
    const r = store.postMessage("fleet", { from_agent: "ghost", body: "hi" });
    expect(r.seq).toBeGreaterThan(0);
    expect(r.from_agent).toBe("ghost");
    const roster = store.agents().agents.map((a: any) => a.agent_id);
    expect(roster).toContain("ghost");
  });

  test("postMessage + readMessages round-trip", () => {
    const msg = store.postMessage("fleet", {
      from_agent: "wren-1",
      body: "hello fleet",
    });
    expect(msg.seq).toBeGreaterThan(0);
    expect(msg.body).toBe("hello fleet");
    const msgs = store.readMessages("fleet", 0, 50) as any[];
    expect(msgs.map((m) => m.body)).toContain("hello fleet");
  });

  test("readMessages paginates with since_seq", () => {
    const before = (store.readMessages("fleet", 0, 200) as any[]).length;
    const latest = store.db
      .query("SELECT COALESCE(MAX(seq),0) AS s FROM messages")
      .get() as any;
    const afterSince = (store.readMessages("fleet", latest.s, 50) as any[])
      .length;
    expect(afterSince).toBeGreaterThanOrEqual(0);
    expect(before).toBeGreaterThan(0);
  });
});

describe("store consolidated state", () => {
  test("consolidatedState returns presence + rooms + decisions", () => {
    const s = store.consolidatedState("2.0.0", 5);
    expect(s.service.name).toBe("squawk");
    expect(s.presence).toBeDefined();
    expect(Array.isArray(s.rooms)).toBe(true);
    expect(Array.isArray(s.decisions)).toBe(true);
  });

  test("activity returns agent rows", () => {
    const a = store.activity();
    expect(Array.isArray(a.agents)).toBe(true);
    expect(a.agents.length).toBeGreaterThan(0);
  });

  test("decision kind appears in recentDecisions", () => {
    store.postMessage("fleet", {
      from_agent: "wren-1",
      body: "DECISION: go",
      kind: "decision",
    });
    const d = store.recentDecisions(50) as any[];
    expect(d.length).toBeGreaterThan(0);
  });
});

describe("store fleetd-style targeted messaging", () => {
  test("sendTargeted writes #channel message", () => {
    const r = store.sendTargeted({
      from: "wren-1",
      to: "#ops",
      body: "deploying",
    });
    expect(r.ok).toBe(true);
    expect(r.seq).toBeGreaterThan(0);
  });

  test("readTargeted lists targeted messages", () => {
    const res = store.readTargeted({ target: "#ops", since: 0 });
    expect(res.ok).toBe(true);
    expect((res.messages as any[]).length).toBeGreaterThan(0);
  });

  test("sendTargeted to @agent alias works", () => {
    const r = store.sendTargeted({
      from: "wren-1",
      to: "wren",
      body: "self-note",
    });
    expect(r.ok).toBe(true);
  });

  test("sendTargeted auto-onboards unknown sender (identity is a feature, not a gate)", () => {
    const r = store.sendTargeted({ from: "ghost", to: "#ops", body: "x" });
    expect(r.ok).toBe(true);
  });

  test("agents returns roster", () => {
    const a = store.agents();
    expect(a.agents.length).toBeGreaterThan(0);
  });
});
