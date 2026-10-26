// squawk/bun/store — SQLite persistence for the merged squawk chat.
// Cherry-picks estate-chat's identity/presence model + fleet-chat's rooms,
// and folds in fleetd's #channel / @agent targeting. This is the single
// writer of state DB files (SQLite WAL).

import { Database } from "bun:sqlite";
import { mkdirSync, existsSync, readdirSync, writeFileSync } from "node:fs";
import { normalizeIdentity, nowISO, type Identity } from "../identity/index.ts";

export interface Store {
  db: Database;
  join(p: Record<string, any>): any;
  heartbeat(p: Record<string, any>): any;
  liveAgents(): any;
  activity(): any;
  recentDecisions(limit?: number): any;
  consolidatedState(version: string, uptimeS: number): any;
  rooms(): any[];
  createRoom(p: Record<string, any>): any;
  postMessage(room_id: string, p: Record<string, any>): any;
  readMessages(room_id: string, since_seq?: number, limit?: number): any;
  /** fleetd-style instant-direct: message to a #channel or @agent. */
  sendTargeted(s: { from: string; to: string; body: string }): any;
  readTargeted(s: { target: string; since?: number; limit?: number }): any;
  agents(): any;
}

export interface StoreOptions {
  stateDir: string;
  seedJsonl?: string;
  presenceTtlS?: number;
  broadcast?: (topic: string, payload: any) => void;
  /** Squawk file-bus root (e.g. ~/.squawk-bus/squawk-root). When set, the
   *  rooms/messages written here are ALSO mirrored as native squawk .md files
   *  so squawk-feed, squawk-ws and campfire see them. Unifies the two surfaces. */
  busRoot?: string;
}

const PRESENCE_TTL_DEFAULT = 120;

export function openStore(opts: StoreOptions): Store {
  mkdirSync(opts.stateDir, { recursive: true });
  const db = new Database(opts.stateDir + "/chat.db", { create: true });
  db.exec("PRAGMA journal_mode = WAL;");
  const presenceTtlS = opts.presenceTtlS ?? PRESENCE_TTL_DEFAULT;
  // Single fan-out path: either injected (server wires the ws hub) or a local
  // no-op default so tests and headless use can work without a socket layer.
  const broadcast: (topic: string, payload: any) => void =
    opts.broadcast ?? (() => {});
  const busRoot = opts.busRoot;

  /** Mirror a chat message into the squawk file bus (native .md format) so
   *  squawk-feed/ws/campfire see it. Returns the file path or null if no bus. */
  function writeBusMessage(
    channel: string,
    from: string,
    body: string,
  ): string | null {
    if (!busRoot) return null;
    if (!/^[A-Za-z0-9_-]{1,32}$/.test(channel)) return null;
    const dir = `${busRoot}/${channel}`;
    try {
      mkdirSync(dir, { recursive: true });
      const now = Date.now();
      const pid = (process as any).pid ?? 0;
      // bus seq = nanotime-ms + pid + rand, matching the fleet channel
      // convention so files sort ABOVE the high-water and stream to ws/feed.
      const seq = `${now}${(pid % 1000).toString().padStart(3, "0")}${Math.floor(
        Math.random() * 100,
      )
        .toString()
        .padStart(2, "0")}`;
      const ts = new Date(now).toISOString().slice(0, 19);
      const slug =
        from
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .slice(0, 20) || "agent";
      const f = `${dir}/${seq}-${slug}-chat.md`;
      const fm =
        `---\nseq: ${seq}\nfrom: ${from}\nto: all\nchannel: ${channel}\n` +
        `ts: ${ts}\nstatus: discussion\n---\n${body}\n`;
      writeFileSync(f, fm, "utf-8");
      return f;
    } catch {
      return null;
    }
  }

  // ── Mirror ingest: file bus → daemon DB ─────────────────────────────
  // The bus is a TWO-WAY mirror: the daemon mirrors DB writes out to .md
  // files (writeBusMessage), and anything that writes a .md directly into
  // the bus (campfire, oracle, an offline laptop) gets ingested back here
  // so the fleet server's DB/WS/feed converge no matter which side a
  // writer used. Our own writes are skipped (seq files we just wrote have
  // our pid embedded; also the from-slug matches a live agent we track).
  function parseBusFile(dir: string, name: string): { channel: string; from: string; body: string; seq: string } | null {
    if (!name.endsWith(".md")) return null;
    try {
      const raw = readFileSync(`${dir}/${name}`, "utf-8");
      const m = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/.exec(raw);
      if (!m) return null;
      const hdr: Record<string, string> = {};
      for (const line of m[1].split("\n")) {
        const kv = /^(\w+):\s*(.*)$/.exec(line);
        if (kv) hdr[kv[1]] = kv[2].trim();
      }
      if (!hdr.from || !hdr.channel) return null;
      return {
        channel: hdr.channel,
        from: hdr.from,
        body: m[2].trimEnd(),
        seq: hdr.seq || name.split("-")[0],
      };
    } catch {
      return null;
    }
  }

  const ingestedBus = new Set<string>();
  let ingestArmed = false;
  function scanBus(): void {
    if (!busRoot || !ingestArmed) return;
    let channels: string[] = [];
    try {
      channels = readdirSync(busRoot).filter((c) => /^[A-Za-z0-9_-]{1,32}$/.test(c));
    } catch {
      return;
    }
    for (const channel of channels) {
      const dir = `${busRoot}/${channel}`;
      let names: string[] = [];
      try {
        names = readdirSync(dir);
      } catch {
        continue;
      }
      for (const name of names) {
        const key = `${channel}/${name}`;
        if (ingestedBus.has(key)) continue;
        ingestedBus.add(key);
        if (ingestedBus.size > 4096) {
          // bounded memory: drop the oldest half (Set preserves insertion order)
          const arr = [...ingestedBus];
          for (const k of arr.slice(0, 2048)) ingestedBus.delete(k);
        }
        const parsed = parseBusFile(dir, name);
        if (!parsed) continue;
        // Skip our own mirror writes: dedupe on body+from+channel (the HTTP
        // path inserted the same body moments before mirroring it out).
        const dupe = db
          .query(
            "SELECT 1 FROM messages WHERE room_id = ? AND from_agent = ? AND body = ? LIMIT 1",
          )
          .get(channel, parsed.from, parsed.body);
        if (dupe) continue;
        try {
          // Unknown persona on the bus: onboard (never drop), queue oracle
          // clarify — identity gates the route, not the message.
          if (
            !db
              .query("SELECT agent_id FROM agents WHERE agent_id = ?")
              .get(parsed.from)
          )
            autoOnboardAgent(parsed.from, { surface: "bus", room_id: channel });
          const msg = postMessageInternal(
            channel,
            parsed.from,
            parsed.body,
            "bus-mirror",
          );
          broadcast(`room:${channel}`, { type: "message", ...msg });
          broadcast("*", { type: "message", ...msg });
        } catch {
          // room validation or insert failure — file stays, no ingest
        }
      }
    }
  }

  /** Shared insert path for HTTP posts and bus ingest. Does NOT write the
   *  file-bus mirror when source is "bus-mirror" (avoid ping-pong). */
  function postMessageInternal(
    room_id: string,
    from: string,
    body: string,
    source: "http" | "bus-mirror",
  ) {
    if (!db.query("SELECT room_id FROM rooms WHERE room_id = ?").get(room_id))
      createRoom({ room_id, name: room_id, created_by: from });
    // Identity as feature: ingest path already auto-onboarded; nothing here
    // rejects on unknown agent — insert proceeds with provenance.
    const ts = nowISO();
    const r = db
      .prepare(
        "INSERT INTO messages (room_id, ts, from_agent, kind, body) VALUES (?,?,?,?,?)",
      )
      .run(room_id, ts, from, "chat", body.slice(0, 20000));
    const msg = {
      seq: Number(r.lastInsertRowid),
      room_id,
      ts,
      from_agent: from,
      kind: "chat",
      body: body.slice(0, 20000),
    };
    if (source === "http") writeBusMessage(room_id, from, body.slice(0, 20000));
    return msg;
  }

  // Unknown persona → auto-onboard with provenance so the message flows;
  // a clarification task is queued for the oracle rig, which can repersona
  // (merge/rename/verify) once a human or the rig confirms identity.
  let oracleSeq = 0;
  function autoOnboardAgent(from: string, p: Record<string, any>): void {
    const ts = nowISO();
    db.prepare(
      "INSERT OR IGNORE INTO agents (agent_id, name, summoner, surface, first_seen, last_heartbeat, activity) VALUES (?,?,?,?,?,?,?)",
    ).run(
      from,
      from,
      "auto-onboard",
      String(p.surface || "bus"),
      ts,
      ts,
      "unverified-persona",
    );
    oracleSeq += 1;
    const task = {
      kind: "persona-clarify",
      agent_id: from,
      room_id: String(p.room_id || "fleet"),
      task_id: `persona-${Date.now()}-${oracleSeq}`,
      ts,
    };
    try {
      writeBusMessage("oracle", "dispatch", JSON.stringify(task));
    } catch {
      // oracle channel unavailable — persona still onboarded, task lost is
      // acceptable: next message from same persona re-queues nothing (it is
      // now known), and the roster shows unverified-persona activity.
    }
    broadcast("presence", { type: "join", agent_id: from, name: from, ts });
  }

  db.exec(`
  CREATE TABLE IF NOT EXISTS agents (
    agent_id        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    chat_id         TEXT,
    host_machine_id TEXT,
    hostname        TEXT,
    hatchling_id    TEXT,
    summoner        TEXT NOT NULL,
    surface         TEXT,
    frame_id        TEXT,
    first_seen      TEXT NOT NULL,
    last_heartbeat  TEXT NOT NULL,
    activity        TEXT,
    counters        TEXT
  );
  CREATE TABLE IF NOT EXISTS rooms (
    room_id    TEXT PRIMARY KEY,
    name       TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT
  );
  CREATE TABLE IF NOT EXISTS messages (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id    TEXT NOT NULL,
    ts         TEXT NOT NULL,
    from_agent TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'chat',
    body       TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS targeted_messages (
    seq     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    sender  TEXT NOT NULL,
    target  TEXT NOT NULL,
    body    TEXT NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_messages_room_seq ON messages(room_id, seq);
  CREATE INDEX IF NOT EXISTS idx_agents_heartbeat ON agents(last_heartbeat);
  CREATE INDEX IF NOT EXISTS idx_targeted_target_seq ON targeted_messages(target, seq);
  `);

  // seed the default room
  db.prepare(
    "INSERT OR IGNORE INTO rooms (room_id, name, created_at, created_by) VALUES ('fleet','fleet',?,'system')",
  ).run(nowISO());

  const store: Store = {
    db,

    join(p: Record<string, any>) {
      const ident = normalizeIdentity(p as any);
      const ts = nowISO();
      db.prepare(
        `INSERT INTO agents
          (agent_id, name, chat_id, host_machine_id, hostname, hatchling_id, summoner, surface, frame_id, first_seen, last_heartbeat, activity, counters)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(agent_id) DO UPDATE SET
            name=excluded.name, chat_id=excluded.chat_id, host_machine_id=excluded.host_machine_id,
            hostname=excluded.hostname, hatchling_id=excluded.hatchling_id, summoner=excluded.summoner,
            surface=excluded.surface, frame_id=excluded.frame_id, last_heartbeat=excluded.last_heartbeat,
            activity=COALESCE(excluded.activity, agents.activity)`,
      ).run(
        ident.agent_id,
        ident.name,
        ident.chat_id,
        ident.host_machine_id,
        ident.hostname,
        ident.hatchling_id,
        ident.summoner,
        ident.surface,
        ident.frame_id,
        ts,
        ts,
        p.activity ? String(p.activity).slice(0, 500) : null,
        p.counters ? JSON.stringify(p.counters).slice(0, 4000) : null,
      );
      broadcast("presence", {
        type: "join",
        agent_id: ident.agent_id,
        name: ident.name,
        ts,
      });
      return {
        agent_id: ident.agent_id,
        name: ident.name,
        room: "fleet",
        ts,
        receipt: `joined fleet as ${ident.name} @ ${ts}`,
      };
    },

    heartbeat(p: Record<string, any>) {
      const agent_id = String(p.agent_id || "").trim();
      if (!agent_id)
        throw Object.assign(new Error("agent_id is required"), { status: 400 });
      const row = db
        .query("SELECT agent_id FROM agents WHERE agent_id = ?")
        .get(agent_id) as any;
      if (!row)
        throw Object.assign(new Error("unknown agent_id — join first"), {
          status: 404,
        });
      const ts = nowISO();
      db.prepare(
        "UPDATE agents SET last_heartbeat = ?, activity = COALESCE(?, activity), counters = COALESCE(?, counters) WHERE agent_id = ?",
      ).run(
        ts,
        p.activity !== undefined ? String(p.activity).slice(0, 500) : null,
        p.counters !== undefined
          ? JSON.stringify(p.counters).slice(0, 4000)
          : null,
        agent_id,
      );
      const live = db
        .query(
          "SELECT agent_id, name, activity, last_heartbeat FROM agents WHERE agent_id = ?",
        )
        .get(agent_id);
      broadcast("presence", { type: "heartbeat", ...(live as object), ts });
      return { ok: true, agent_id, ts };
    },

    liveAgents() {
      const cutoff = new Date(Date.now() - presenceTtlS * 1000).toISOString();
      const live = db
        .query(
          `SELECT agent_id, name, chat_id, host_machine_id, hostname, hatchling_id, summoner, surface, activity, counters, last_heartbeat
           FROM agents WHERE last_heartbeat >= ? ORDER BY last_heartbeat DESC`,
        )
        .all(cutoff);
      const stale = (
        db
          .query("SELECT COUNT(*) AS c FROM agents WHERE last_heartbeat < ?")
          .get(cutoff) as { c: number }
      ).c;
      return {
        live,
        live_count: (live as any[]).length,
        stale_count: stale,
        ttl_s: presenceTtlS,
        ts: nowISO(),
      };
    },

    activity() {
      const rows = db
        .query(
          `SELECT agent_id, name, activity, counters, last_heartbeat,
            (strftime('%s','now') - strftime('%s', last_heartbeat)) AS age_s
           FROM agents ORDER BY last_heartbeat DESC`,
        )
        .all();
      const perAgentMsg = db
        .query(
          "SELECT from_agent AS agent_id, COUNT(*) AS messages_sent, MAX(ts) AS last_message_ts FROM messages GROUP BY from_agent",
        )
        .all();
      return { agents: rows, message_counts: perAgentMsg, ts: nowISO() };
    },

    recentDecisions(limit = 50) {
      limit = Math.min(Math.max(1, limit), 200);
      return db
        .query(
          "SELECT seq, room_id, ts, from_agent, body FROM messages WHERE kind = 'decision' ORDER BY seq DESC LIMIT ?",
        )
        .all(limit);
    },

    consolidatedState(version: string, uptimeS: number) {
      return {
        service: { name: "squawk", version, uptime_s: uptimeS },
        presence: this.liveAgents(),
        activity: this.activity(),
        decisions: this.recentDecisions(50),
        rooms: this.rooms(),
        ts: nowISO(),
      };
    },

    rooms() {
      return db
        .query(
          `SELECT r.*, (SELECT COUNT(*) FROM messages m WHERE m.room_id = r.room_id) AS message_count
           FROM rooms r ORDER BY r.created_at`,
        )
        .all();
    },

    createRoom(p: Record<string, any>) {
      const room_id = p.room_id
        ? String(p.room_id)
        : `room-${crypto.getRandomValues(new Uint8Array(4)).join("").slice(0, 8)}`;
      const ts = nowISO();
      db.prepare(
        "INSERT OR IGNORE INTO rooms (room_id, name, created_at, created_by) VALUES (?,?,?,?)",
      ).run(
        room_id,
        p.name ? String(p.name).slice(0, 120) : room_id,
        ts,
        p.created_by ? String(p.created_by) : null,
      );
      // ensure the bus channel dir exists so feed/ws discover it.
      if (busRoot && /^[A-Za-z0-9_-]{1,32}$/.test(room_id)) {
        try {
          mkdirSync(`${busRoot}/${room_id}`, { recursive: true });
        } catch {
          /* fs unavailable — channel still in chat.db */
        }
      }
      return db.query("SELECT * FROM rooms WHERE room_id = ?").get(room_id);
    },

    postMessage(room_id: string, p: Record<string, any>) {
      const room = db
        .query("SELECT room_id FROM rooms WHERE room_id = ?")
        .get(room_id) as any;
      if (!room)
        throw Object.assign(new Error("unknown room"), { status: 404 });
      const from_agent = String(p.from_agent || "").trim();
      const body = String(p.body || "");
      if (!from_agent)
        throw Object.assign(new Error("from_agent is required"), {
          status: 400,
        });
      if (!body || !body.trim())
        throw Object.assign(new Error("body is required"), { status: 400 });
      // Identity is a FEATURE, not a gate: unknown personas are enriched
      // with auto-onboard (provenance-marked, oracle-clarify task queued),
      // never rejected. Known personas keep their richer routing/telemetry.
      const agent = db
        .query("SELECT agent_id FROM agents WHERE agent_id = ?")
        .get(from_agent) as any;
      if (!agent) autoOnboardAgent(from_agent, { ...p, room_id });
      const ts = nowISO();
      const kind = p.kind ? String(p.kind).slice(0, 32) : "chat";
      const r = db
        .prepare(
          "INSERT INTO messages (room_id, ts, from_agent, kind, body) VALUES (?,?,?,?,?)",
        )
        .run(room_id, ts, from_agent, kind, body.slice(0, 20000));
      const msg = {
        seq: Number(r.lastInsertRowid),
        room_id,
        ts,
        from_agent,
        kind,
        body: body.slice(0, 20000),
      };
      // Mirror into the squawk file bus so feed/ws/campfire/oracle see it.
      writeBusMessage(room_id, from_agent, body.slice(0, 20000));
      broadcast(`room:${room_id}`, { type: "message", ...msg });
      broadcast("*", { type: "message", ...msg });
      return msg;
    },

    readMessages(room_id: string, since_seq = 0, limit = 100) {
      limit = Math.min(Math.max(1, limit), 500);
      return db
        .query(
          "SELECT seq, room_id, ts, from_agent, kind, body FROM messages WHERE room_id = ? AND seq > ? ORDER BY seq ASC LIMIT ?",
        )
        .all(room_id, since_seq, limit);
    },

    sendTargeted(s: { from: string; to: string; body: string }) {
      const to = String(s.to || "").trim();
      const body = String(s.body || "");
      const from = String(s.from || "").trim();
      if (!to || !body || !from)
        throw Object.assign(new Error("from, to and body required"), {
          status: 400,
        });
      const agent = db
        .query("SELECT name FROM agents WHERE agent_id = ?")
        .get(from) as any;
      // Identity is a feature, not a gate: unknown sender auto-onboards.
      if (!agent) autoOnboardAgent(from, { surface: "targeted" });
      const senderName =
        agent?.name ||
        from;
      let target: string;
      if (to.startsWith("#")) target = to.slice(0, 64);
      else target = "@" + to;
      const ts = nowISO();
      const r = db
        .prepare(
          "INSERT INTO targeted_messages (ts, sender, target, body) VALUES (?,?,?,?)",
        )
        .run(ts, senderName, target, body);
      const msg = {
        seq: Number(r.lastInsertRowid),
        ts,
        sender: senderName,
        target,
        body,
      };
      // mirror #channel targets into the bus channel dir too
      if (target.startsWith("#")) {
        writeBusMessage(target.slice(1), senderName, body);
      } else {
        writeBusMessage("fleet", senderName, body);
      }
      broadcast(`target:${target}`, { type: "message", ...msg });
      broadcast("*", { type: "message", ...msg });
      return { ok: true, seq: msg.seq };
    },

    readTargeted(s: { target: string; since?: number; limit?: number }) {
      const target = String(s.target || "#fleet")
        .trim()
        .slice(0, 64);
      const since = Number(s.since || 0) || 0;
      const limit = Math.min(Math.max(1, Number(s.limit || 50) || 50), 200);
      const rows = db
        .query(
          "SELECT seq, ts, sender, target, body FROM targeted_messages WHERE target = ? AND seq > ? ORDER BY seq LIMIT ?",
        )
        .all(target, since, limit) as any[];
      return { ok: true, messages: rows };
    },

    agents() {
      // fleetd-style: full roster with presence TTL
      return {
        agents: db
          .query("SELECT * FROM agents ORDER BY last_heartbeat DESC")
          .all(),
        presence_ttl_s: presenceTtlS,
      };
    },
  };

  // Arm the two-way mirror: bus → DB ingest polls at the fleet grain.
  // Armed only after the full store interface exists (scanBus touches
  // postMessageInternal + autoOnboardAgent, both defined above).
  ingestArmed = true;
  scanBus();
  const ingestTimer = setInterval(scanBus, 60_000);
  if (typeof (ingestTimer as any).unref === "function")
    (ingestTimer as any).unref();

  return store;
}

export { PRESENCE_TTL_DEFAULT };
