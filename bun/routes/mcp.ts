// squawk/bun/routes/mcp.ts — MCP over Streamable HTTP (JSON-RPC 2.0).
// Extracted verbatim from the routes if-chain (2026-11-04 refactor).

import type { Store } from "../store/index.ts";
import { mcpCallTool, MCP_TOOLS } from "../mcp/index.ts";

const json = (data: any, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });

export async function handleMcp(
  store: Store,
  version: string,
  req: Request,
): Promise<Response> {
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
