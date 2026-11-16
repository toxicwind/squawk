// squawk/bun/routes/table.ts — table-driven route registry.
// Every /v1 route is one row: method + pattern + auth + handler. The if-chain
// it replaces (routes/index.ts pre-2026-11-04) is gone; handleFetch matches
// against this table. Patterns use :named segments (extracted into params).

import type { RouteCtx } from "./index.ts";
import {
  handleAdd,
  handleBlock,
  handleDone,
  handleList,
  handleUpdate,
} from "../todo/index.ts";

export interface RouteMatch {
  params: Record<string, string>;
}

export interface RouteHandlerArgs {
  ctx: RouteCtx;
  req: Request;
  url: URL;
  body: Record<string, any>;
  params: Record<string, string>;
  server: any;
}

export interface Route {
  method: "GET" | "POST" | "PUT";
  pattern: string;
  auth: boolean;
  handler: (a: RouteHandlerArgs) => Response | Promise<Response>;
  /** Optional extra constraint a matched path must satisfy (e.g. :op enum). */
  match?: (params: Record<string, string>) => boolean;
}

const json = (data: any, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });

/** Match a method+path against one pattern; returns params or null. */
function matchPattern(
  pattern: string,
  path: string,
): Record<string, string> | null {
  const ps = pattern.split("/").filter(Boolean);
  const xs = path.split("/").filter(Boolean);
  if (ps.length !== xs.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < ps.length; i++) {
    if (ps[i].startsWith(":")) params[ps[i].slice(1)] = decodeURIComponent(xs[i]);
    else if (ps[i] !== xs[i]) return null;
  }
  return params;
}

/** Find the route for method+path; null when nothing matches. */
export function matchRoute(
  method: string,
  path: string,
): { route: Route; params: Record<string, string> } | null {
  for (const route of ROUTE_TABLE) {
    if (route.method !== method) continue;
    const params = matchPattern(route.pattern, path);
    if (!params) continue;
    if (route.match && !route.match(params)) continue;
    return { route, params };
  }
  return null;
}

// ── handlers ────────────────────────────────────────────────────────────────

const health = ({ ctx }: RouteHandlerArgs) => {
  const counts = {
    agents: (
      ctx.store.db.query("SELECT COUNT(*) AS c FROM agents").get() as {
        c: number;
      }
    ).c,
    rooms: (
      ctx.store.db.query("SELECT COUNT(*) AS c FROM rooms").get() as { c: number }
    ).c,
    messages: (
      ctx.store.db.query("SELECT COUNT(*) AS c FROM messages").get() as {
        c: number;
      }
    ).c,
  };
  return json({
    ok: true,
    service: "squawk",
    version: ctx.version,
    uptime_s: Math.floor((Date.now() - ctx.bootAt) / 1000),
    counts,
    ts: new Date().toISOString(),
  });
};

// --- identity / presence (Pens-chat) ---
const join = ({ ctx, body }: RouteHandlerArgs) => json({ ok: true, ...ctx.store.join(body) });
const presencePost = ({ ctx, body }: RouteHandlerArgs) => json(ctx.store.heartbeat(body));
const presenceGet = ({ ctx }: RouteHandlerArgs) => json({ ok: true, ...ctx.store.liveAgents() });
const activity = ({ ctx }: RouteHandlerArgs) => json({ ok: true, ...ctx.store.activity() });
const state = ({ ctx }: RouteHandlerArgs) =>
  json({
    ok: true,
    state: ctx.store.consolidatedState(
      ctx.version,
      Math.floor((Date.now() - ctx.bootAt) / 1000),
    ),
  });
const agents = ({ ctx }: RouteHandlerArgs) => json({ ok: true, ...ctx.store.agents() });

// --- rooms (fleet-chat) ---
const roomsGet = ({ ctx }: RouteHandlerArgs) => json({ ok: true, rooms: ctx.store.rooms() });
const roomsPost = ({ ctx, body }: RouteHandlerArgs) => json({ ok: true, room: ctx.store.createRoom(body) });
const roomGet = ({ ctx, params }: RouteHandlerArgs) => {
  const room = ctx.store.room(params.room_id);
  if (!room)
    return json({ ok: false, error: "room not found" }, 404);
  return json({ ok: true, room });
};
const roomMessagesPost = ({ ctx, params, body }: RouteHandlerArgs) =>
  json({ ok: true, message: ctx.store.postMessage(params.room_id, body) });
const roomMessagesGet = ({ ctx, params, url }: RouteHandlerArgs) => {
  const since = parseInt(url.searchParams.get("since_seq") || "0", 10) || 0;
  const limit = parseInt(url.searchParams.get("limit") || "100", 10) || 100;
  return json({
    ok: true,
    room_id: params.room_id,
    messages: ctx.store.readMessages(params.room_id, since, limit),
  });
};

// --- fleetd-style targeted messaging (#channel / @agent) ---
const send = ({ ctx, body }: RouteHandlerArgs) =>
  json({
    ok: true,
    ...ctx.store.sendTargeted({
      from: String(body.from || ""),
      to: String(body.to || ""),
      body: String(body.body || ""),
    }),
  });
const read = ({ ctx, url }: RouteHandlerArgs) =>
  json(ctx.store.readTargeted({ target: url.searchParams.get("target") || "#fleet" }));

// --- fleet todo board (todo/*.md SSOT + TODO.md index) ---
const todoGet = ({ ctx }: RouteHandlerArgs) => json(handleList(ctx.todo));
const todoPost = ({ ctx, body }: RouteHandlerArgs) => {
  // distinguish add (slug+author+content) from update (file+status)
  if (body.slug && body.author && body.content) return json(handleAdd(ctx.todo, body));
  if (body.file) return json(handleUpdate(ctx.todo, body));
  return json(handleAdd(ctx.todo, body));
};
const todoDone = ({ ctx, params, body }: RouteHandlerArgs) =>
  json(
    handleDone(ctx.todo, params.file, {
      by: typeof body?.by === "string" ? body.by : undefined,
      evidence: typeof body?.evidence === "string" ? body.evidence : undefined,
    }),
  );
const todoBlock = ({ ctx, body }: RouteHandlerArgs) =>
  json(
    handleBlock(
      ctx.todo,
      String(body?.file ?? body?.ref ?? ""),
      String(body?.reason ?? ""),
      typeof body?.by === "string" ? body.by : undefined,
    ),
  );

// --- fleet dispatch (Pens-chat) ---
const dispatchTasksPost = ({ ctx, body }: RouteHandlerArgs) => json({ ok: true, task: ctx.dispatch.postTask(body) });
const dispatchTasksGet = ({ ctx, url }: RouteHandlerArgs) =>
  json({ ok: true, tasks: ctx.dispatch.listTasks(url.searchParams.get("status") || undefined) });
const dispatchClaim = ({ ctx, params, body }: RouteHandlerArgs) =>
  json({ ok: true, claim: ctx.dispatch.claim(params.task_id, body) });
const dispatchClaimOp = ({ ctx, params, body }: RouteHandlerArgs) => {
  const id = Number(params.id);
  const op = params.op as "ack" | "progress" | "expire" | "nack";
  return json({ ok: true, result: (ctx.dispatch[op] as any)(id, body) });
};
const dispatchDeadLetter = ({ ctx, body }: RouteHandlerArgs) => json({ ok: true, result: ctx.dispatch.deadLetterTask(body) });
const dispatchRequeue = ({ ctx, body }: RouteHandlerArgs) =>
  json({ ok: true, result: ctx.dispatch.requeue(String(body.task_id || ""), body) });
const dispatchWedgeScan = ({ ctx }: RouteHandlerArgs) => json({ ok: true, ...(ctx.dispatch.wedgeScan() as any) });
const dispatchSnapshot = ({ ctx }: RouteHandlerArgs) => json({ ok: true, snapshot: ctx.dispatch.snapshot() });
const dispatchMetrics = ({ ctx }: RouteHandlerArgs) => json({ ok: true, metrics: ctx.dispatch.metrics() });

// ── the table ───────────────────────────────────────────────────────────────

export const ROUTE_TABLE: Route[] = [
  { method: "GET", pattern: "/health", auth: false, handler: health },
  // identity / presence (Pens-chat)
  { method: "POST", pattern: "/v1/join", auth: true, handler: join },
  { method: "POST", pattern: "/v1/presence", auth: true, handler: presencePost },
  { method: "GET", pattern: "/v1/presence", auth: true, handler: presenceGet },
  { method: "GET", pattern: "/v1/activity", auth: true, handler: activity },
  { method: "GET", pattern: "/v1/state", auth: true, handler: state },
  { method: "GET", pattern: "/v1/agents", auth: true, handler: agents },
  // rooms (fleet-chat)
  { method: "GET", pattern: "/v1/rooms", auth: true, handler: roomsGet },
  { method: "POST", pattern: "/v1/rooms", auth: true, handler: roomsPost },
  { method: "GET", pattern: "/v1/rooms/:room_id", auth: true, handler: roomGet },
  { method: "POST", pattern: "/v1/rooms/:room_id/messages", auth: true, handler: roomMessagesPost },
  { method: "GET", pattern: "/v1/rooms/:room_id/messages", auth: true, handler: roomMessagesGet },
  // fleetd-style targeted messaging (#channel / @agent)
  { method: "POST", pattern: "/v1/send", auth: true, handler: send },
  { method: "GET", pattern: "/v1/read", auth: true, handler: read },
  // fleet todo board (todo/*.md SSOT + TODO.md index)
  { method: "GET", pattern: "/v1/todo", auth: true, handler: todoGet },
  { method: "POST", pattern: "/v1/todo", auth: true, handler: todoPost },
  { method: "POST", pattern: "/v1/todo/:file/done", auth: true, handler: todoDone },
  { method: "POST", pattern: "/v1/todo/block", auth: true, handler: todoBlock },
  // fleet dispatch (Pens-chat)
  { method: "POST", pattern: "/v1/dispatch/tasks", auth: true, handler: dispatchTasksPost },
  { method: "GET", pattern: "/v1/dispatch/tasks", auth: true, handler: dispatchTasksGet },
  { method: "POST", pattern: "/v1/dispatch/tasks/:task_id/claim", auth: true, handler: dispatchClaim },
  {
    method: "POST",
    pattern: "/v1/dispatch/claims/:id/:op",
    auth: true,
    handler: dispatchClaimOp,
    match: (p) => ["ack", "progress", "expire", "nack"].includes(p.op),
  },
  { method: "POST", pattern: "/v1/dispatch/dead-letter", auth: true, handler: dispatchDeadLetter },
  { method: "POST", pattern: "/v1/dispatch/requeue", auth: true, handler: dispatchRequeue },
  { method: "POST", pattern: "/v1/dispatch/wedge-scan", auth: true, handler: dispatchWedgeScan },
  { method: "GET", pattern: "/v1/dispatch/snapshot", auth: true, handler: dispatchSnapshot },
  { method: "GET", pattern: "/v1/dispatch/metrics", auth: true, handler: dispatchMetrics },
];
