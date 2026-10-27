// squawk/bun/routes — HTTP route handlers for the merged squawk chat.
// Combines fleet-chat's rooms REST, estate-chat's presence/state/MCP + dispatch
// routes, and fleetd's targeted #channel/@agent endpoints.

import type { Store } from "../store/index.ts";
import type { Dispatch } from "../dispatch/index.ts";
import { mcpCallTool, MCP_TOOLS } from "../mcp/index.ts";
import {
  handleAdd,
  handleDone,
  handleList,
  handleUpdate,
} from "../todo/index.ts";

export interface RouteCtx {
  store: Store;
  dispatch: Dispatch;
  version: string;
  bootAt: number;
  token: string;
  todo: import("../todo/index.ts").TodoDeps;
  hub: { broadcast(topic: string, payload: any): void };
}

const json = (data: any, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
const err = (e: any) =>
  json({ ok: false, error: String(e?.message || e) }, e?.status || 500);

function authorized(req: Request, url: URL, token: string): boolean {
  const h = req.headers.get("authorization");
  if (token && h === `Bearer ${token}`) return true;
  if (token && url.searchParams.get("token") === token) return true;
  return false;
}

async function readBody(req: Request): Promise<Record<string, any>> {
  try {
    return (await req.json()) || {};
  } catch {
    return {};
  }
}

export async function handleFetch(
  ctx: RouteCtx,
  req: Request,
  server: any,
): Promise<Response> {
  const { store, dispatch, version, bootAt, token, hub } = ctx;
  const url = new URL(req.url);
  const path = url.pathname;

  if (path === "/health") {
    const counts = {
      agents: (
        store.db.query("SELECT COUNT(*) AS c FROM agents").get() as {
          c: number;
        }
      ).c,
      rooms: (
        store.db.query("SELECT COUNT(*) AS c FROM rooms").get() as { c: number }
      ).c,
      messages: (
        store.db.query("SELECT COUNT(*) AS c FROM messages").get() as {
          c: number;
        }
      ).c,
    };
    return json({
      ok: true,
      service: "squawk",
      version,
      uptime_s: Math.floor((Date.now() - bootAt) / 1000),
      counts,
      ts: new Date().toISOString(),
    });
  }

  // websocket stream
  if (path === "/v1/stream" && req.method === "GET") {
    if (!authorized(req, url, token))
      return json({ ok: false, error: "unauthorized" }, 401);
    const topics = new Set(
      (url.searchParams.get("subscribe") || "room:fleet,presence")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    );
    const upgraded = server.upgrade(req, { data: { sub: { topics } } });
    if (!upgraded)
      return json({ ok: false, error: "websocket upgrade failed" }, 500);
    return undefined as any;
  }

  // MCP over Streamable HTTP
  if (path === "/v1/mcp" && req.method === "POST") {
    if (!authorized(req, url, token))
      return json({ ok: false, error: "unauthorized" }, 401);
    const rpc = (await req.json().catch(() => null)) as any;
    const okR = (id: any, result: any) => json({ jsonrpc: "2.0", id, result });
    const failR = (id: any, code: number, message: string) =>
      json({ jsonrpc: "2.0", id, error: { code, message } });
    if (!rpc || rpc.jsonrpc !== "2.0" || typeof rpc.method !== "string")
      return failR(rpc?.id ?? null, -32600, "invalid JSON-RPC 2.0 request");
    try {
      if (rpc.method === "initialize")
        return okR(rpc.id, {
          protocolVersion: "2024-11-05",
          capabilities: { tools: {} },
          serverInfo: { name: "squawk", version },
        });
      if (
        rpc.method === "notifications/initialized" ||
        String(rpc.method).startsWith("notifications/")
      )
        return okR(rpc.id, {});
      if (rpc.method === "tools/list") return okR(rpc.id, { tools: MCP_TOOLS });
      if (rpc.method === "tools/call") {
        const { name, arguments: args } = rpc.params || {};
        const out = mcpCallTool(store, name, args || {});
        return okR(rpc.id, {
          content: [{ type: "text", text: JSON.stringify(out) }],
        });
      }
      if (rpc.method === "ping") return okR(rpc.id, {});
      return failR(rpc.id, -32601, "method not found: " + String(rpc.method));
    } catch (e: any) {
      return failR(rpc.id, -32000, String(e?.message || e));
    }
  }

  if (!path.startsWith("/v1/"))
    return json({ ok: false, error: "not found" }, 404);
  if (!authorized(req, url, token))
    return json({ ok: false, error: "unauthorized" }, 401);

  try {
    const body =
      req.method === "POST" || req.method === "PUT" ? await readBody(req) : {};

    // --- identity / presence (estate-chat) ---
    if (path === "/v1/join" && req.method === "POST")
      return json({ ok: true, ...store.join(body) });
    if (path === "/v1/presence" && req.method === "POST")
      return json(store.heartbeat(body));
    if (path === "/v1/presence" && req.method === "GET")
      return json({ ok: true, ...store.liveAgents() });
    if (path === "/v1/activity" && req.method === "GET")
      return json({ ok: true, ...store.activity() });
    if (path === "/v1/state" && req.method === "GET")
      return json({
        ok: true,
        state: store.consolidatedState(
          version,
          Math.floor((Date.now() - bootAt) / 1000),
        ),
      });
    if (path === "/v1/agents" && req.method === "GET")
      return json({ ok: true, ...store.agents() });

    // --- rooms (fleet-chat) ---
    if (path === "/v1/rooms" && req.method === "GET")
      return json({ ok: true, rooms: store.rooms() });
    if (path === "/v1/rooms" && req.method === "POST")
      return json({ ok: true, room: store.createRoom(body) });

    const m = path.match(/^\/v1\/rooms\/([^/]+)\/messages$/);
    if (m) {
      const room_id = decodeURIComponent(m[1]);
      if (req.method === "POST")
        return json({ ok: true, message: store.postMessage(room_id, body) });
      if (req.method === "GET") {
        const since =
          parseInt(url.searchParams.get("since_seq") || "0", 10) || 0;
        const limit =
          parseInt(url.searchParams.get("limit") || "100", 10) || 100;
        return json({
          ok: true,
          room_id,
          messages: store.readMessages(room_id, since, limit),
        });
      }
    }

    // --- fleetd-style targeted messaging (#channel / @agent) ---
    if (path === "/v1/send" && req.method === "POST")
      return json({
        ok: true,
        ...store.sendTargeted({
          from: String(body.from || ""),
          to: String(body.to || ""),
          body: String(body.body || ""),
        }),
      });
    if (path === "/v1/read" && req.method === "GET")
      return json(
        store.readTargeted({
          target: url.searchParams.get("target") || "#fleet",
        }),
      );

    // --- fleet dispatch (estate-chat) ---
    // --- fleet todo board (todo/*.md SSOT + TODO.md index) ---
    if (path === "/v1/todo" && req.method === "GET")
      return json(handleList(ctx.todo));
    if (path === "/v1/todo" && req.method === "POST") {
      // distinguish add (slug+author+content) from update (file+status)
      if (body.slug && body.author && body.content)
        return json(handleAdd(ctx.todo, body));
      if (body.file) return json(handleUpdate(ctx.todo, body as any));
      return json(handleAdd(ctx.todo, body));
    }
    {
      const tm = path.match(/^\/v1\/todo\/([^/]+)\/done$/);
      if (tm && req.method === "POST")
        return json(handleDone(ctx.todo, decodeURIComponent(tm[1])));
    }

    if (path === "/v1/dispatch/tasks" && req.method === "POST")
      return json({ ok: true, task: dispatch.postTask(body) });
    if (path === "/v1/dispatch/tasks" && req.method === "GET")
      return json({
        ok: true,
        tasks: dispatch.listTasks(url.searchParams.get("status") || undefined),
      });
    {
      const dm = path.match(/^\/v1\/dispatch\/tasks\/([^/]+)\/claim$/);
      if (dm && req.method === "POST")
        return json({
          ok: true,
          claim: dispatch.claim(decodeURIComponent(dm[1]), body),
        });
      const cm = path.match(
        /^\/v1\/dispatch\/claims\/(\d+)\/(ack|progress|expire|nack)$/,
      );
      if (cm && req.method === "POST") {
        const id = Number(cm[1]);
        const op = cm[2] as "ack" | "progress" | "expire" | "nack";
        return json({ ok: true, result: (dispatch[op] as any)(id, body) });
      }
    }
    if (path === "/v1/dispatch/dead-letter" && req.method === "POST")
      return json({ ok: true, result: dispatch.deadLetterTask(body) });
    if (path === "/v1/dispatch/requeue" && req.method === "POST")
      return json({
        ok: true,
        result: dispatch.requeue(String(body.task_id || ""), body),
      });
    if (path === "/v1/dispatch/wedge-scan" && req.method === "POST")
      return json({ ok: true, ...(dispatch.wedgeScan() as any) });
    if (path === "/v1/dispatch/snapshot" && req.method === "GET")
      return json({ ok: true, snapshot: dispatch.snapshot() });
    if (path === "/v1/dispatch/metrics" && req.method === "GET")
      return json({ ok: true, metrics: dispatch.metrics() });

    hub.broadcast("*", { type: "noop", path });
    return json({ ok: false, error: "not found" }, 404);
  } catch (e) {
    return err(e);
  }
}
