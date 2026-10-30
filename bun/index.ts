// squawk/bun — merged fleet coordination server (squawk chat gateway).
// Modular entry point: wires together identity/store, dispatch, routes, and
// the WebSocket hub. This is NOT a monolith — each concern lives in its own
// module under bun/{identity,store,dispatch,ws,routes,mcp}.
//
// Run:  bun bun/index.ts              (HTTP + WS server, :25122)
//       bun bun/index.ts mcp          (stdio MCP adapter)
//
// Cherry-picks (2026-10-24 consolidation):
//   - estate-chat: 4-namespace identity, presence, consolidated state, dispatch
//   - fleet-chat:  rooms/join/leave/messages/presence/heartbeat REST + SQLite
//   - fleetd:       #channel / @agent targeted messaging + roster

import { Database } from "bun:sqlite";
import { createInterface } from "readline";
import { createDispatch } from "./dispatch/index.ts";
import { openStore, type Store } from "./store/index.ts";
import { createWsHub } from "./ws/index.ts";
import { handleFetch } from "./routes/index.ts";
import { MCP_TOOLS, mcpCallTool } from "./mcp/index.ts";

const VERSION = "2.0.0";
const PORT = parseInt(process.env.SQUAWK_CHAT_PORT || "25120", 10);
const TOKEN_FILE =
  process.env.SQUAWK_CHAT_TOKEN_FILE ||
  `${process.env.HOME || "/home/toxic"}/.config/estate-chat-token`;
const STATE_DIR = process.env.SQUAWK_CHAT_STATE_DIR || "/home/toxic/.squawk";
const MIRROR_DIR = process.env.DISPATCH_MIRROR_DIR || "/home/toxic/.squawk";
const BUS_ROOT =
  process.env.SQUAWK_BUS_ROOT ||
  `${process.env.HOME || ""}/.squawk-bus/squawk-root`;
const BOOT_AT = Date.now();

async function loadToken(): Promise<string> {
  if (!TOKEN_FILE) {
    console.error(
      "FATAL: SQUAWK_CHAT_TOKEN_FILE is not set — refusing to run unauthenticated",
    );
    process.exit(1);
  }
  try {
    return (await Bun.file(TOKEN_FILE).text()).trim();
  } catch {
    console.error("FATAL: cannot read token file " + TOKEN_FILE);
    process.exit(1);
  }
}

async function tailscaleIPv4(): Promise<string | null> {
  try {
    const p = Bun.spawnSync(["tailscale", "ip", "-4"]);
    const out = new TextDecoder()
      .decode(p.stdout)
      .trim()
      .split("\n")[0]
      ?.trim();
    if (out && /^\d+\.\d+\.\d+\.\d+$/.test(out)) return out;
  } catch {
    /* no tailscale CLI */
  }
  return null;
}

// --- stdio MCP adapter ---
async function runMcp(store: Store, token: string) {
  const envToken = (process.env.SQUAWK_CHAT_TOKEN || "").trim();
  if (envToken && envToken !== token) {
    console.error("MCP: bad SQUAWK_CHAT_TOKEN");
    process.exit(1);
  }
  const rl = createInterface({ input: process.stdin, terminal: false });
  const respond = (id: any, result: any) =>
    process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, result }) + "\n");
  const respondErr = (id: any, code: number, message: string) =>
    process.stdout.write(
      JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } }) + "\n",
    );
  for await (const line of rl) {
    const t = line.trim();
    if (!t) continue;
    let msg: any;
    try {
      msg = JSON.parse(t);
    } catch {
      continue;
    }
    try {
      if (msg.method === "initialize") {
        respond(msg.id, {
          protocolVersion: "2024-11-05",
          capabilities: { tools: {} },
          serverInfo: { name: "squawk", version: VERSION },
        });
      } else if (
        msg.method === "notifications/initialized" ||
        msg.method?.startsWith("notifications/")
      ) {
        // ack-only
      } else if (msg.method === "tools/list") {
        respond(msg.id, { tools: MCP_TOOLS });
      } else if (msg.method === "tools/call") {
        const { name, arguments: args } = msg.params || {};
        const out = mcpCallTool(store, name, args || {});
        respond(msg.id, {
          content: [{ type: "text", text: JSON.stringify(out) }],
        });
      } else if (msg.method === "ping") {
        respond(msg.id, {});
      } else {
        respondErr(msg.id, -32601, `method not found: ${msg.method}`);
      }
    } catch (e: any) {
      respondErr(msg.id, -32000, String(e?.message || e));
    }
  }
}

// --- server boot ---
async function main() {
  const token = await loadToken();

  const hub = createWsHub(null as any);
  const store = openStore({
    stateDir: STATE_DIR,
    busRoot: BUS_ROOT,
    broadcast: (topic: string, payload: any) => hub.broadcast(topic, payload),
  });

  // Wire the hub: the store broadcasts through hub topics too.
  const dispatch = createDispatch({
    stateDir: STATE_DIR,
    mirrorDir: MIRROR_DIR,
    broadcast: (topic: string, payload: any) => {
      hub.broadcast(topic, payload);
    },
    postRoomMessage: (room_id: string, p: Record<string, any>) =>
      store.postMessage(room_id, p),
    ensureRoom: (room_id: string, name: string) => {
      store.createRoom({ room_id, name, created_by: "system" });
    },
    ensureSystemAgent: () => {
      const ts = new Date().toISOString();
      store.db
        .prepare(
          "INSERT OR IGNORE INTO agents (agent_id, name, summoner, first_seen, last_heartbeat) VALUES ('dispatch','dispatch','system',?,?)",
        )
        .run(ts, ts);
    },
    holderHeartbeat: (agent_id: string) => {
      const r = store.db
        .query("SELECT last_heartbeat FROM agents WHERE agent_id = ?")
        .get(agent_id) as any;
      return r ? r.last_heartbeat : null;
    },
  });

  const ctx = {
    store,
    dispatch,
    version: VERSION,
    bootAt: BOOT_AT,
    token,
    todo: { todoDir: "/home/toxic/pens/ranch/squawk/todo" },
    hub,
  };

  if (process.argv[2] === "mcp") {
    await runMcp(store, token);
    process.exit(0);
  }

  const tsIP = await tailscaleIPv4();
  const hosts = ["127.0.0.1", ...(tsIP ? [tsIP] : [])];
  const servers = hosts.map((hostname) =>
    Bun.serve({
      port: PORT,
      hostname,
      fetch: (req: Request, srv: any) => handleFetch(ctx, req, srv),
      websocket: {
        open(ws: any) {
          hub.handlers.open(ws);
          ws.send(
            JSON.stringify({
              type: "hello",
              service: "squawk",
              version: VERSION,
              topic: "presence",
            }),
          );
        },
        close(ws: any) {
          hub.handlers.close(ws);
        },
        message(ws: any, message: any) {
          hub.handlers.message(ws, message);
        },
      },
    }),
  );
  console.log(
    `[squawk] v${VERSION} listening on ${hosts.map((h) => `${h}:${PORT}`).join(" and ")} (state: ${STATE_DIR}/chat.db)`,
  );
  // Pre-flight: ensure the shared DB handle stays warm for dispatch readers.
  const _warm = new Database(STATE_DIR + "/chat.db");
  _warm.close();
  return servers;
}

if (process.argv[2] !== "mcp") {
  main().catch((e) => {
    console.error("[squawk] fatal:", e?.message || e);
    process.exit(1);
  });
}
