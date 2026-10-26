// squawk/bun/hindsight-mcp.ts — MCP server exposing Hindsight's shared `estate`
// bank, Bun port of hindsight_mcp_server.py (squawk de-hybridisation).
//
// Lets Kappa (and any MCP client) recall/retain/reflect against the SAME
// Hindsight bank Tau uses (bank_id = "estate") — one coherent long-term memory
// plane across harnesses. Zero third-party deps (global fetch + readline).
//
// Backend : https://freeinference? no — Vectorize Hindsight at HINDSIGHT_API_URL
//           (default http://127.0.0.1:25117).
// Bank    : HINDSIGHT_BANK (default "estate").
// Transport: stdio JSON-RPC (MCP). Run: bun bun/hindsight-mcp.ts
//
// Contract (live probes + OpenAPI):
//   ensure bank : PUT  /v1/default/banks/{bank}
//   recall      : POST /v1/default/banks/{bank}/memories/recall
//   retain      : POST /v1/default/banks/{bank}/memories   body {items:[...]} (+async)
//   reflect     : POST /v1/default/banks/{bank}/reflect
//   list banks  : GET  /v1/default/banks

import { createInterface } from "readline";

const API_URL = (process.env.HINDSIGHT_API_URL || "http://127.0.0.1:25117").replace(/\/$/, "");
const BANK = process.env.HINDSIGHT_BANK || "estate";

async function req(
  method: string,
  path: string,
  body?: unknown,
  timeoutMs = 30000,
): Promise<{ status: number; data: any }> {
  const url = `${API_URL}${path}`;
  try {
    const res = await fetch(url, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
    const text = await res.text();
    let data: any = {};
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { raw: text };
      }
    }
    return { status: res.status, data };
  } catch (err) {
    return { status: 0, data: { error: String((err as Error).message || err) } };
  }
}

async function ensureBank(): Promise<void> {
  // Best-effort crate the estate bank. Hindsight auto-creates on first retain;
  // swallow here (matches the python server's tolerance).
  const { status } = await req("PUT", `/v1/default/banks/${BANK}`);
  // 200/201 created; 404/422 on bare PUT tolerated.
  return;
}

async function recall(
  query = "",
  budget = "mid",
  maxTokens = 1024,
  types: string[] | null = null,
  tags: string[] | null = null,
): Promise<any> {
  const body: Record<string, unknown> = { query, budget, max_tokens: maxTokens };
  if (types) body.types = types;
  if (tags) body.tags = tags;
  const { status, data } = await req("POST", `/v1/default/banks/${BANK}/memories/recall`, body);
  if (status !== 200) return { ok: false, status, error: data };
  const results = data.results ?? data.memories ?? data;
  return { ok: true, results };
}

async function retain(
  content: string,
  context: string | null = null,
  tags: string[] | null = null,
): Promise<any> {
  await ensureBank();
  const item: Record<string, unknown> = { content };
  if (context) item.context = context;
  if (tags) item.tags = tags;
  // /memories expects {items:[...]}; {memories:[...]} -> 422 (body.items required).
  // async=true returns immediately with operation_id (sync runs extraction, >20s).
  const { status, data } = await req(
    "POST",
    `/v1/default/banks/${BANK}/memories`,
    { async: true, items: [item] },
  );
  if (status !== 200 && status !== 201) return { ok: false, status, error: data };
  return { ok: true, ...data };
}

async function reflect(query: string | null = null, budget = "low"): Promise<any> {
  await ensureBank();
  const body: Record<string, unknown> = { budget };
  if (query) body.query = query;
  const { status, data } = await req("POST", `/v1/default/banks/${BANK}/reflect`, body);
  if (status !== 200) return { ok: false, status, error: data };
  return { ok: true, ...data };
}

async function listBanks(): Promise<any> {
  const { status, data } = await req("GET", "/v1/default/banks");
  if (status !== 200) return { ok: false, status, error: data };
  return { ok: true, banks: data.banks ?? [] };
}

const TOOLS = [
  {
    name: "hindsight_recall",
    description: `Recall memories from the shared Hindsight '${BANK}' bank (same bank Tau uses).`,
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Natural-language search query" },
        budget: { type: "string", enum: ["low", "mid", "high"], default: "mid" },
        max_tokens: { type: "integer", default: 1024 },
        types: { type: "array", items: { type: "string" } },
        tags: { type: "array", items: { type: "string" } },
      },
      required: ["query"],
    },
  },
  {
    name: "hindsight_retain",
    description: `Store a durable fact into the shared Hindsight '${BANK}' bank.`,
    inputSchema: {
      type: "object",
      properties: {
        content: { type: "string", description: "Self-contained fact/memory to store" },
        context: { type: "string", description: "Optional provenance" },
        tags: { type: "array", items: { type: "string" } },
      },
      required: ["content"],
    },
  },
  {
    name: "hindsight_reflect",
    description: `Run agentic reflection over the shared Hindsight '${BANK}' bank.`,
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        budget: { type: "string", enum: ["low", "mid", "high"], default: "low" },
      },
    },
  },
  {
    name: "hindsight_list_banks",
    description: "List Hindsight banks (confirm 'estate' exists).",
    inputSchema: { type: "object", properties: {} },
  },
];

const HANDLERS: Record<string, (...a: any[]) => Promise<any>> = {
  hindsight_recall: recall,
  hindsight_retain: retain,
  hindsight_reflect: reflect,
  hindsight_list_banks: listBanks,
};

// Normalise tool arguments into positional order matching the handler signatures.
function argsParsed(args: Record<string, any>, tool: string): any[] {
  switch (tool) {
    case "hindsight_recall":
      return [
        args.query ?? "",
        args.budget ?? "mid",
        args.max_tokens ?? 1024,
        args.types ?? null,
        args.tags ?? null,
      ];
    case "hindsight_retain":
      return [args.content ?? "", args.context ?? null, args.tags ?? null];
    case "hindsight_reflect":
      return [args.query ?? null, args.budget ?? "low"];
    default:
      return [];
  }
}

async function handle(msg: any): Promise<any> {
  const method = msg?.method;
  const id = msg?.id;
  if (method === "initialize") {
    return {
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: "2024-11-05",
        capabilities: { tools: { listChanged: false } },
        serverInfo: { name: "hindsight-mcp", version: "1.1.0" },
      },
    };
  }
  if (method === "notifications/initialized" || method === undefined) return null;
  if (method === "tools/list") {
    return { jsonrpc: "2.0", id, result: { tools: TOOLS } };
  }
  if (method === "tools/call") {
    const tool = msg?.params?.name;
    const args = msg?.params?.arguments ?? {};
    if (tool && tool in HANDLERS) {
      try {
        const res = await HANDLERS[tool](...argsParsed(args, tool));
        return {
          jsonrpc: "2.0",
          id,
          result: { content: [{ type: "text", text: JSON.stringify(res) }] },
        };
      } catch (e) {
        return {
          jsonrpc: "2.0",
          id,
          error: { code: -32603, message: String((e as Error).message || e) },
        };
      }
    }
    return { jsonrpc: "2.0", id, error: { code: -32601, message: `unknown tool ${tool}` } };
  }
  return { jsonrpc: "2.0", id, error: { code: -32601, message: `unknown method ${method}` } };
}

const rl = createInterface({ input: process.stdin, terminal: false });

rl.on("line", async (lineRaw) => {
  const line = lineRaw.trim();
  if (!line) return;
  let msg: any;
  try {
    msg = JSON.parse(line);
  } catch {
    return;
  }
  const out = await handle(msg);
  if (out) process.stdout.write(JSON.stringify(out) + "\n");
});