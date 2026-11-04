// squawk/bun/routes — HTTP routing for the merged squawk chat.
// Table-driven (table.ts): every /v1 route is one row; handleFetch matches,
// applies auth, reads the body, and dispatches. MCP (mcp.ts) and the ws
// upgrade stay special-cased — they need the raw Request/server.

import type { Store } from "../store/index.ts";
import type { Dispatch } from "../dispatch/index.ts";
import { handleMcp } from "./mcp.ts";
import { matchRoute, type RouteHandlerArgs } from "./table.ts";

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

  // MCP over Streamable HTTP (JSON-RPC — own contract, not the route table)
  if (path === "/v1/mcp" && req.method === "POST") {
    if (!authorized(req, url, token))
      return json({ ok: false, error: "unauthorized" }, 401);
    try {
      return await handleMcp(store, version, req);
    } catch (e: any) {
      return err(e);
    }
  }

  // websocket stream (needs the raw server for the upgrade)
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

  const matched = matchRoute(req.method, path);

  if (!matched) {
    // non-/v1 paths → plain 404; unmatched /v1 paths → noop broadcast + 404
    if (path.startsWith("/v1/"))
      hub.broadcast("*", { type: "noop", path });
    return json({ ok: false, error: "not found" }, 404);
  }

  if (matched.route.auth && !authorized(req, url, token))
    return json({ ok: false, error: "unauthorized" }, 401);

  try {
    const body =
      req.method === "POST" || req.method === "PUT" ? await readBody(req) : {};
    const args: RouteHandlerArgs = {
      ctx,
      req,
      url,
      body,
      params: matched.params,
      server,
    };
    return await matched.route.handler(args);
  } catch (e) {
    return err(e);
  }
}

// keep the todo helpers importable for callers that used them from here
export { handleAdd, handleBlock, handleDone, handleList, handleUpdate } from "../todo/index.ts";
