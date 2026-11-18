// fleet-feed: roster + history + live WS feed for the squawk fleet.
//
// This is the TypeScript of rust_algo_web/src/agents.rs, ported 2026-10-02.
// The Rust daemon had no Cargo.toml left in the tree, so
// stack/services/rust-web.sh could only ever fall into `cargo build` and fail;
// the fleet UI had no working backend. Bun gives the same three surfaces --
// HTTP roster, per-agent history, and an event-driven WS feed -- in one file.
//
// Behaviour is carried over exactly:
//   * messages are the squawk fleet spool files (YAML frontmatter + markdown)
//   * mtime is the activity timestamp, not the frontmatter `ts`
//   * status thresholds: active <5m, idle <30m, quiet <2h, else stale
//   * no polling anywhere: fs.watch drives the feed, and a WS client only wakes
//     on a frame or a socket event
//
// Port it further and the differences from the Rust original are:
//   * `seen` (seq -> best completeness) is bounded by construction; the
//     original needed an approximate eviction because seqs rise forever
//   * Completeness upgrades still happen, so a file that raises Create before
//     its first write does not broadcast an empty message.

import { readFileSync, readdirSync, statSync, watch } from "node:fs";
import { join } from "node:path";

const FLEET_DIRS = [
  process.env.SQUAWK_ROOT ?? "/home/toxic/.fleet-bus/squawk-root",
  "/home/toxic/shingle/squawk-root",
];

export interface FleetMsg {
  seq: number;
  from: string;
  to: string;
  ts: string;
  title: string;
  body: string;
  unix: number;
}

export interface AgentCard {
  name: string;
  messages: number;
  last_unix: number;
  last_ts: string;
  status: "active" | "idle" | "quiet" | "stale";
  last_title: string;
  last_seq: number;
}

function fleetDir(): string {
  for (const dir of FLEET_DIRS) {
    try {
      if (statSync(join(dir, "fleet")).isDirectory()) return join(dir, "fleet");
    } catch {
      /* try the next candidate */
    }
  }
  return join(FLEET_DIRS[0]!, "fleet");
}

/** Parse one squawk fleet message file. mtime is the arrival timestamp. */
export function parseFleetMsg(path: string): FleetMsg | null {
  const name = path.split("/").pop() ?? "";
  if (!name.endsWith(".md")) return null;
  const fileSeq = Number.parseInt(name.split("-")[0] ?? "", 10);
  if (!Number.isFinite(fileSeq)) return null;

  let content: string;
  let unix: number;
  try {
    content = readFileSync(path, "utf8");
    unix = Math.floor(statSync(path).mtimeMs / 1000);
  } catch {
    return null;
  }

  let seq = fileSeq;
  let from = "";
  let to = "";
  let ts = "";
  let title = "";
  let body = content;

  const lines = content.split("\n");
  if (lines[0]?.trim() === "---") {
    const fm: Record<string, string> = {};
    let inFm = true;
    const rest: string[] = [];
    for (const line of lines.slice(1)) {
      if (inFm) {
        if (line.trim() === "---") {
          inFm = false;
          continue;
        }
        const i = line.indexOf(":");
        if (i > 0) fm[line.slice(0, i).trim()] = line.slice(i + 1).trim();
      } else {
        rest.push(line);
      }
    }
    if (!inFm) {
      if (fm.seq !== undefined) {
        const parsed = Number.parseInt(fm.seq, 10);
        if (Number.isFinite(parsed)) seq = parsed;
      }
      from = fm.from ?? "";
      to = fm.to ?? "";
      ts = fm.ts ?? "";
      title = fm.title ?? "";
      body = rest.join("\n").trim();
    }
  }
  // Fall back to the filename when frontmatter carried no `from`.
  if (!from) {
    const parts = name.replace(/\.md$/, "").split("-");
    if (parts.length >= 3) from = parts[1]!;
  }
  if (!from) return null;
  return { seq, from, to, ts, title, body, unix };
}

function statusFor(lastUnix: number, now: number): AgentCard["status"] {
  const age = now - lastUnix;
  if (age < 300) return "active";
  if (age < 1800) return "idle";
  if (age < 7200) return "quiet";
  return "stale";
}

/** One card per agent, most-recently-active first. */
export function buildRoster(): AgentCard[] {
  const byAgent: Record<string, FleetMsg[]> = {};
  let entries: string[] = [];
  try {
    entries = readdirSync(fleetDir());
  } catch {
    return [];
  }
  for (const entry of entries) {
    if (!entry.endsWith(".md")) continue;
    const msg = parseFleetMsg(join(fleetDir(), entry));
    if (!msg) continue;
    (byAgent[msg.from] ??= []).push(msg);
  }

  const now = Math.floor(Date.now() / 1000);
  const cards: AgentCard[] = Object.entries(byAgent).map(([name, msgs]) => {
    msgs.sort((a, b) => b.unix - a.unix);
    const last = msgs[0]!;
    return {
      name,
      messages: msgs.length,
      last_unix: last.unix,
      last_ts: last.ts,
      status: statusFor(last.unix, now),
      last_title: last.title,
      last_seq: last.seq,
    };
  });
  cards.sort((a, b) => b.last_unix - a.last_unix);
  return cards;
}

export function recentMessages(limit: number): FleetMsg[] {
  const msgs: FleetMsg[] = [];
  let entries: string[] = [];
  try {
    entries = readdirSync(fleetDir());
  } catch {
    return [];
  }
  for (const entry of entries) {
    if (!entry.endsWith(".md")) continue;
    const msg = parseFleetMsg(join(fleetDir(), entry));
    if (msg) msgs.push(msg);
  }
  msgs.sort((a, b) => b.seq - a.seq);
  return msgs.slice(0, limit);
}

// ---------------------------------------------------------------------------
// Event-driven feed. fs.watch is the only trigger; nothing polls.
// ---------------------------------------------------------------------------

type Client = { send: (frame: string) => void; close: () => void };
const clients = new Set<Client>();

function broadcast(frame: string): void {
  for (const client of clients) client.send(frame);
}

// seq -> best completeness (from+title+body bytes) seen so far. A file can
// raise `create` empty, then a write event with the full content; broadcasting
// the most complete parse avoids duplicate frames for identical re-notifies.
const seen = new Map<number, number>();

function onFileEvent(path: string): void {
  // A create event can beat the writer's first write, leaving a 0-byte file.
  // Skip it; the following write event re-triggers this path with content.
  let size: number;
  try {
    size = statSync(path).size;
  } catch {
    return;
  }
  if (size === 0) return;

  const msg = parseFleetMsg(path);
  if (!msg) return;
  const completeness = msg.from.length + msg.title.length + msg.body.length;
  const best = seen.get(msg.seq) ?? 0;
  if (best > 0 && completeness <= best) return;
  seen.set(msg.seq, completeness);
  // Bounded by construction: keep only the 8192 highest seqs.
  if (seen.size > 8192) {
    const cutoff = msg.seq - 8192;
    for (const [seq] of seen) if (seq < cutoff) seen.delete(seq);
  }

  broadcast(JSON.stringify({ type: "squawk", channel: "fleet", message: msg }));
  // Refresh the author's card so the roster grid updates live.
  const card = buildRoster().find((c) => c.name === msg.from);
  if (card) broadcast(JSON.stringify({ type: "agent", agent: card }));
}

export function startFleetFeed(): void {
  const dir = fleetDir();
  try {
    watch(dir, { persistent: true }, (_event, filename) => {
      if (filename && filename.endsWith(".md")) onFileEvent(join(dir, filename));
    });
  } catch (err) {
    console.error(`[fleet-feed] watcher failed: ${String(err)}`);
    return;
  }
  console.log(`[fleet-feed] watching ${dir}`);
}

function addClient(): Client {
  let sock: { send: (d: string) => void; close: () => void } | null = null;
  const client: Client = {
    send: (frame) => sock?.send(frame),
    close: () => sock?.close(),
  };
  clients.add(client);
  return client;
}

const PORT = Number.parseInt(process.env.FLEET_FEED_PORT ?? "", 10) || 25201;

Bun.serve({
  port: PORT,
  idleTimeout: 60,
  async fetch(req, server) {
    const url = new URL(req.url);

    if (url.pathname === "/api/agents/roster") {
      return Response.json(buildRoster());
    }

    if (url.pathname.startsWith("/api/agents/")) {
      const name = decodeURIComponent(url.pathname.slice("/api/agents/".length));
      // agent_ok in the Rust original: bounded, ascii-alphanumeric plus - and _.
      if (!name || name.length > 64 || !/^[A-Za-z0-9_-]+$/.test(name)) {
        return Response.json({ error: "invalid agent name" }, { status: 400 });
      }
      const history = recentMessages(200)
        .filter((m) => m.from === name)
        .sort((a, b) => a.seq - b.seq);
      if (!history.length) {
        return Response.json({ error: "agent not found" }, { status: 404 });
      }
      return Response.json({ name, messages: history });
    }

    if (url.pathname === "/health") {
      return Response.json({ ok: true, clients: clients.size });
    }

    if (url.pathname === "/ws/fleet") {
      if (server.upgrade(req)) return undefined as unknown as Response;
      return new Response("expected websocket", { status: 426 });
    }

    return new Response("not found", { status: 404 });
  },
  websocket: {
    open(sock) {
      const client = addClient();
      // Bind the socket into the client so broadcast can reach it, then send
      // hello + the full snapshot so a new client paints with no HTTP round-trip.
      (sock as unknown as { _client?: Client })._client = client;
      const clientRef = client;
      client.send = (frame) => sock.send(frame);
      client.close = () => sock.close();
      sock.send(
        JSON.stringify({
          type: "hello",
          ts: Math.floor(Date.now() / 1000),
          roster_url: "/api/agents/roster",
        }),
      );
      sock.send(
        JSON.stringify({
          type: "fleet:init",
          roster: buildRoster(),
          messages: recentMessages(50),
        }),
      );
      
    },
    close(sock) {
      const client = (sock as unknown as { _client?: Client })._client;
      if (client) clients.delete(client);
    },
  },
});

startFleetFeed();
console.log(`fleet-feed on :${PORT} (roster + history + ws /ws/fleet)`);