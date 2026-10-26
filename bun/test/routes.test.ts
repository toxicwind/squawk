// squawk/bun/test/routes.test.ts
import { beforeAll, afterAll, describe, expect, test } from "bun:test";
import { openStore } from "../store/index.ts";
import { createDispatch } from "../dispatch/index.ts";
import { handleFetch } from "../routes/index.ts";
import { createWsHub } from "../ws/index.ts";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

let dir: string;
let store: ReturnType<typeof openStore>;
let dispatch: ReturnType<typeof createDispatch>;
let hub: ReturnType<typeof createWsHub>;
let ctx: any;
const TOKEN = "test-token";

function base(url: string) {
  return `http://127.0.0.1${url}`;
}

async function call(method: string, path: string, body?: any, token = TOKEN) {
  const req = new Request(base(path), {
    method,
    headers: {
      "content-type": "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return await handleFetch(ctx, req, null as any);
}

beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), "squawk-routes-"));
  hub = createWsHub(null as any);
  store = openStore({
    stateDir: dir,
    broadcast: (t: string, p: any) => hub.broadcast(t, p),
  });
  dispatch = createDispatch({
    stateDir: dir,
    mirrorDir: dir,
    broadcast: (t: string, p: any) => hub.broadcast(t, p),
    postRoomMessage: (room_id: string, p: any) => store.postMessage(room_id, p),
    ensureRoom: (room_id: string, name: string) =>
      store.createRoom({ room_id, name }),
    ensureSystemAgent: () => {
      const ts = new Date().toISOString();
      store.db
        .prepare(
          "INSERT OR IGNORE INTO agents (agent_id,name,summoner,first_seen,last_heartbeat) VALUES ('dispatch','dispatch','system',?,?)",
        )
        .run(ts, ts);
    },
    holderHeartbeat: (agent_id: string) => {
      const r = store.db
        .query("SELECT last_heartbeat FROM agents WHERE agent_id=?")
        .get(agent_id) as any;
      return r ? r.last_heartbeat : null;
    },
  });
  ctx = {
    store,
    dispatch,
    version: "2.0.0",
    bootAt: Date.now(),
    token: TOKEN,
    hub,
  };
});

afterAll(() => {
  store.db.close();
  dispatch.db.close();
  rmSync(dir, { recursive: true, force: true });
});

const j = async (res: Response) => JSON.parse(await res.text());

describe("routes auth", () => {
  test("/health is public", async () => {
    const res = await call("GET", "/health");
    expect(res.status).toBe(200);
    const d = await j(res);
    expect(d.service).toBe("squawk");
  });

  test("/v1/* without token -> 401", async () => {
    const res = await call("GET", "/v1/rooms", undefined, "");
    expect(res.status).toBe(401);
  });

  test("/v1/* with bad token -> 401", async () => {
    const res = await call("GET", "/v1/rooms", undefined, "wrong");
    expect(res.status).toBe(401);
  });
});

describe("routes identity + presence", () => {
  test("POST /v1/join", async () => {
    const res = await call("POST", "/v1/join", {
      name: "route-bot",
      summoner: "test",
      agent_id: "route-bot",
    });
    expect(res.status).toBe(200);
  });

  test("POST /v1/presence (heartbeat)", async () => {
    const res = await call("POST", "/v1/presence", { agent_id: "route-bot" });
    expect(res.status).toBe(200);
  });

  test("GET /v1/presence", async () => {
    const res = await call("GET", "/v1/presence");
    expect(res.status).toBe(200);
  });

  test("GET /v1/state", async () => {
    const res = await call("GET", "/v1/state");
    expect(res.status).toBe(200);
  });

  test("GET /v1/agents", async () => {
    const res = await call("GET", "/v1/agents");
    expect(res.status).toBe(200);
  });
});

describe("routes rooms + messages", () => {
  test("GET /v1/rooms", async () => {
    const res = await call("GET", "/v1/rooms");
    const d = await j(res);
    expect(d.rooms.map((r: any) => r.room_id)).toContain("fleet");
  });

  test("POST /v1/rooms creates", async () => {
    const res = await call("POST", "/v1/rooms", { room_id: "rt", name: "rt" });
    expect(res.status).toBe(200);
  });

  test("messages post/read", async () => {
    const p = await call("POST", "/v1/rooms/fleet/messages", {
      from_agent: "route-bot",
      body: "route hello",
    });
    expect(p.status).toBe(200);
    const g = await call("GET", "/v1/rooms/fleet/messages");
    const d = await j(g);
    expect((d.messages as any[]).map((m) => m.body)).toContain("route hello");
  });
});

describe("routes targeted messaging", () => {
  test("POST /v1/send to #channel", async () => {
    const res = await call("POST", "/v1/send", {
      from: "route-bot",
      to: "#ops",
      body: "tg",
    });
    expect(res.status).toBe(200);
  });

  test("GET /v1/read", async () => {
    const res = await call("GET", "/v1/read?target=%23ops");
    const d = await j(res);
    expect(d.ok).toBe(true);
  });
});

describe("routes dispatch", () => {
  test("POST/GET /v1/dispatch/tasks", async () => {
    await call("POST", "/v1/dispatch/tasks", { task_id: "rt-1", payload: "x" });
    const res = await call("GET", "/v1/dispatch/tasks");
    expect(res.status).toBe(200);
  });

  test("POST claim + ack", async () => {
    const claim = await call("POST", "/v1/dispatch/tasks/rt-1/claim", {
      claimed_by: "w",
    });
    expect(claim.status).toBe(200);
  });

  test("GET snapshot + metrics", async () => {
    expect((await call("GET", "/v1/dispatch/snapshot")).status).toBe(200);
    expect((await call("GET", "/v1/dispatch/metrics")).status).toBe(200);
  });

  test("POST wedge-scan", async () => {
    expect((await call("POST", "/v1/dispatch/wedge-scan", {})).status).toBe(
      200,
    );
  });

  test("unknown route -> 404", async () => {
    const res = await call("GET", "/v1/nope");
    expect(res.status).toBe(404);
  });
});

describe("routes MCP over HTTP", () => {
  test("/v1/mcp tools/list", async () => {
    const res = await call("POST", "/v1/mcp", {
      jsonrpc: "2.0",
      id: 1,
      method: "tools/list",
    });
    const d = await j(res);
    expect(d.result.tools.length).toBeGreaterThan(0);
  });

  test("/v1/mcp bad request", async () => {
    const res = await call("POST", "/v1/mcp", { nope: true });
    const d = await j(res);
    expect(d.error).toBeDefined();
  });
});

describe("routes ws upgrade + extras", () => {
  test("/v1/stream upgrades via server.upgrade", async () => {
    let upgradeArg: any = null;
    const server = {
      upgrade(req: any, opts: any) {
        upgradeArg = opts;
        return true;
      },
    };
    const req = new Request(
      "http://127.0.0.1/v1/stream?token=test-token&subscribe=room:fleet,presence",
      { method: "GET" },
    );
    const res = await handleFetch(ctx, req, server as any);
    expect(res).toBeUndefined(); // 101 handled by server
    expect(upgradeArg.data.sub.topics.has("room:fleet")).toBe(true);
    expect(upgradeArg.data.sub.topics.has("presence")).toBe(true);
  });

  test("/v1/stream requires auth", async () => {
    const server = { upgrade: () => true };
    const req = new Request("http://127.0.0.1/v1/stream", { method: "GET" });
    const res = await handleFetch(ctx, req, server as any);
    expect(res.status).toBe(401);
  });

  test("/v1/stream 500 when upgrade fails", async () => {
    const server = { upgrade: () => false };
    const req = new Request("http://127.0.0.1/v1/stream?token=test-token", {
      method: "GET",
    });
    const res = await handleFetch(ctx, req, server as any);
    expect(res.status).toBe(500);
  });

  test("GET /v1/activity", async () => {
    const res = await call("GET", "/v1/activity");
    expect(res.status).toBe(200);
  });

  test("GET /v1/recent-decision log present in state", async () => {
    const res = await call("GET", "/v1/state");
    const d = await j(res);
    expect(Array.isArray(d.state.decisions)).toBe(true);
  });
});
