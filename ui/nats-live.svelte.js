// ui/nats-live.svelte.js — NATS + JetStream live source for the Squawk UI.
//
// Same public interface as live.svelte.js's LiveConnection so App.svelte can
// swap sources with ?src=nats. No flag day: the default stays the feed WS,
// this module is the alternate live path.
//
// Wire: one WebSocket to {mount}/nats-ws. squawk-ui.ts shuttles it
// frame-by-frame to the NATS server's :4223 websocket listener and injects
// the feed token into our CONNECT server-side — the browser never sees the
// secret. Protocol: INFO -> CONNECT -> SUB <channel>.messages <sid>; the
// server pushes MSG frames carrying the v1 JSON envelope; PING -> PONG.
//
// Initial history comes from the file feed (/wait?tail=) via ingestSnapshot;
// NATS carries live messages only. The file feed stays the source of truth —
// if NATS dies, the UI falls back to the feed WS (toggle in the header).
//
// NOTE: compiled by ui/build.ts via svelte/compiler compileModule, which
// parses JS only — NO TypeScript syntax in this file (JSDoc types only).
//
// @typedef {"connecting"|"live"|"reconnecting"} ConnStatus
// @typedef {{seq:number,file_seq?:number,from:string,sender?:string,to:string,channel:string,ts:string,status:string,uuid:string,title:string,signature?:string,sealed?:boolean,text:string}} Msg
// @typedef {{messages:Msg[],cursor:number}} TabData

const MAX_BACKOFF_MS = 30000;
const BASE_BACKOFF_MS = 1000;
const FLUSH_MS = 250;
const SYS_CAP = 20;

/** WebSocket URL for the page's mount: /fleet/nats-ws through the funnel, /nats-ws at root. */
function natsWsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  let base = location.pathname;
  if (base === "/fleet" || base.startsWith("/fleet/")) base = "/fleet";
  else base = base.replace(/\/[^/]*$/, "");
  return `${proto}//${location.host}${base}/nats-ws`;
}

/**
 * Normalize one NATS v1 envelope ({v,seq,channel,from,to,ts,title,type,
 * sealed,signature,body}) into the UI Msg shape.
 * @param {any} env
 * @returns {Msg|null}
 */
function normalizeEnvelope(env) {
  if (!env || typeof env.seq !== "number") return null;
  const sealed = !!env.sealed;
  return {
    seq: env.seq,
    file_seq: undefined,
    from: env.from || "?",
    to: env.to || "all",
    channel: typeof env.channel === "string" ? env.channel : "",
    ts: env.ts || "",
    status: "discussion",
    uuid: "",
    title: env.title || "msg",
    signature: env.signature,
    sealed: sealed,
    text: sealed ? "" : (typeof env.body === "string" ? env.body : ""),
  };
}

/**
 * Normalize one file-feed store message (the /wait?tail= snapshot shape) —
 * same rules as live.svelte.js's normalize().
 * @param {any} d
 * @param {string} fallbackChannel
 * @returns {Msg|null}
 */
function normalizeStore(d, fallbackChannel) {
  if (!d || typeof d.seq !== "number") return null;
  return {
    seq: d.seq,
    file_seq: typeof d.file_seq === "number" ? d.file_seq : undefined,
    from: d.sender ?? d.from ?? "?",
    to: d.to ?? "all",
    channel: typeof d.channel === "string" ? d.channel : fallbackChannel,
    ts: d.ts ?? "",
    status: d.status ?? "discussion",
    uuid: d.uuid ?? "",
    title: d.title ?? "msg",
    signature: d.signature,
    sealed: !!d.sealed,
    text: typeof d.text === "string" ? d.text : (typeof d.body === "string" ? d.body : ""),
  };
}

/** @param {Msg} m */
export function keyOf(m) { return m.file_seq || m.seq; }

class NatsLiveConnection {
  // ---- reactive state (Svelte 5 runes) ----
  /** @type {ConnStatus} */
  status = $state("connecting");
  attempt = $state(0);
  /** @type {Record<string, TabData>} */
  tabs = $state({});
  /** @type {string[]} */
  sysLines = $state([]);

  // ---- private ----
  ws = null;
  running = false;
  backoffTimer = undefined;
  flushTimer = undefined;
  /** @type {{channel:string, msg:Msg}[]} inbound buffer (renderer-crash guard) */
  buf = [];
  /** @type {Record<string, Set<number>>} per-channel dedupe keys */
  seen = {};
  /** @type {Record<string, number>} channel -> NATS subscription id */
  sids = {};
  nextSid = 1;
  /** raw inbound accumulator for the NATS frame parser */
  inbuf = "";

  constructor() {
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") this.nudge();
    });
    window.addEventListener("online", () => this.nudge());
  }

  /** @param {{ticket?:string}} [opts] (accepted for interface parity; unused) */
  configure(opts) {}

  sysLine(s) {
    this.sysLines = [...this.sysLines.slice(-(SYS_CAP - 1)), "nats: " + s];
  }

  channelNames() { return Object.keys(this.tabs); }

  /** @param {string} name */
  cursorOf(name) { return this.tabs[name]?.cursor ?? 0; }

  /** @param {string} name */
  ensureChannel(name) {
    if (!this.tabs[name]) {
      // Replace whole object: dynamic-key set on $state bypasses Svelte 5 reactivity
      this.tabs = { ...this.tabs, [name]: { messages: [], cursor: 0 } };
      this.seen[name] = new Set();
    }
  }

  /** @param {string} name */
  addChannel(name) {
    if (this.tabs[name]) return;
    this.ensureChannel(name);
    this.sysLine(`channel #${name} added — tuned in`);
    this.reconnect();
  }

  /** @param {string} name */
  removeChannel(name) {
    if (!this.tabs[name] || this.channelNames().length <= 1) return;
    const { [name]: _, ...rest } = this.tabs;
    this.tabs = rest;
    delete this.seen[name];
    this.reconnect();
  }

  /**
   * Merge inbound messages into a channel tab: dedupe by seq key, keep
   * sorted, advance the resume cursor.
   * @param {string} channel
   * @param {Msg[]} msgs
   */
  ingest(channel, msgs) {
    const t = this.tabs[channel];
    if (!t || !msgs.length) return;
    const seen = this.seen[channel] ?? (this.seen[channel] = new Set());
    const fresh = [];
    for (const m of msgs) {
      const k = keyOf(m);
      if (!seen.has(k)) { seen.add(k); fresh.push(m); }
    }
    if (!fresh.length) return;
    this.tabs = {
      ...this.tabs,
      [channel]: {
        messages: [...t.messages, ...fresh].sort((a, b) => keyOf(a) - keyOf(b)),
        cursor: Math.max(t.cursor, ...fresh.map(keyOf)),
      },
    };
  }

  /**
   * Ingest a /wait?tail= snapshot (file-feed store shape) into a channel.
   * @param {string} channel
   * @param {any[]} storeMsgs
   */
  ingestSnapshot(channel, storeMsgs) {
    const msgs = [];
    for (const raw of storeMsgs || []) {
      const m = normalizeStore(raw, channel);
      if (m) msgs.push(m);
    }
    this.ingest(channel, msgs);
  }

  connect() {
    if (this.running) return;
    this.running = true;
    this.dial();
  }

  disconnect() {
    this.running = false;
    this.clearTimers();
    this.flush();
    if (this.ws) {
      const s = this.ws;
      this.ws = null;
      s.onclose = null; s.onerror = null; s.onmessage = null; s.onopen = null;
      try { s.close(); } catch {}
    }
  }

  /** drop the socket and dial again now (channel set changed, or wakeup nudge) */
  reconnect() {
    if (!this.running) return;
    this.clearTimers();
    this.sids = {};
    if (this.ws) {
      const s = this.ws;
      this.ws = null;
      s.onclose = null; s.onerror = null; s.onmessage = null; s.onopen = null;
      try { s.close(); } catch {}
    }
    this.dial();
  }

  /** if we're down, skip the remaining backoff and dial now */
  nudge() {
    if (!this.running || this.status === "live" || this.ws) return;
    clearTimeout(this.backoffTimer);
    this.backoffTimer = undefined;
    this.dial();
  }

  clearTimers() {
    clearTimeout(this.backoffTimer); this.backoffTimer = undefined;
    clearTimeout(this.flushTimer); this.flushTimer = undefined;
  }

  dial() {
    if (!this.running || this.ws) return;
    const chans = this.channelNames();
    if (!chans.length) return;
    this.status = "connecting";
    this.inbuf = "";
    let sock;
    try {
      sock = new WebSocket(natsWsUrl());
    } catch {
      this.sysLine("websocket unavailable in this browser — retrying");
      this.onDown();
      return;
    }
    this.ws = sock;

    sock.onopen = () => {
      if (this.ws !== sock) return;
      // wait for the server INFO, then CONNECT (the shuttle injects our
      // auth token server-side) and SUB each channel.
      this.sendRaw(`CONNECT {"verbose":false,"pedantic":false,"name":"squawk-ui"}\r\n`);
      for (const ch of this.channelNames()) {
        const sid = this.nextSid++;
        this.sids[ch] = sid;
        this.sendRaw(`SUB ${ch}.messages ${sid}\r\n`);
      }
      this.status = "live";
      this.attempt = 0;
      this.sysLine(`connected over NATS — #${chans.join(" #")}`);
    };

    sock.onmessage = (ev) => {
      if (this.ws !== sock) return;
      this.onData(typeof ev.data === "string" ? ev.data : "");
    };

    sock.onerror = () => {};

    sock.onclose = () => {
      if (this.ws !== sock) return;
      this.ws = null;
      if (!this.running) return;
      this.onDown();
    };
  }

  /** @param {string} s */
  sendRaw(s) {
    try { this.ws?.send(s); } catch {}
  }

  /** NATS frame parser: INFO/CONNECT-ack/MSG/PING/PONG/-ERR, payload-aware. */
  onData(chunk) {
    this.inbuf += chunk;
    for (;;) {
      const eol = this.inbuf.indexOf("\r\n");
      if (eol < 0) return;
      const line = this.inbuf.slice(0, eol);
      if (line.startsWith("MSG ")) {
        // MSG <subject> <sid> <#bytes>
        const parts = line.split(" ");
        const nbytes = parseInt(parts[3] || "0", 10);
        const need = eol + 2 + nbytes + 2;
        if (this.inbuf.length < need) return; // wait for the full payload
        const payload = this.inbuf.slice(eol + 2, eol + 2 + nbytes);
        this.inbuf = this.inbuf.slice(need);
        this.onMsg(parts[1] || "", payload);
        continue;
      }
      this.inbuf = this.inbuf.slice(eol + 2);
      if (line === "PING") {
        this.sendRaw("PONG\r\n");
      } else if (line.startsWith("-ERR")) {
        this.sysLine("server error: " + line.slice(5, 120));
        this.reconnect();
        return;
      }
      // INFO / +OK: nothing to do (verbose=false, auth injected by shuttle)
    }
  }

  /** @param {string} subject @param {string} payload */
  onMsg(subject, payload) {
    // subject: <channel>.messages
    const dot = subject.lastIndexOf(".");
    const ch = dot > 0 ? subject.slice(0, dot) : "";
    if (!ch || !this.tabs[ch]) return;
    let env;
    try { env = JSON.parse(payload); } catch { return; }
    const m = normalizeEnvelope(env);
    if (m) {
      m.channel = ch;
      this.buf.push({ channel: ch, msg: m });
      this.scheduleFlush();
    }
  }

  /** socket lost (or never opened): back off with full jitter, keep retrying */
  onDown() {
    this.flush();
    this.status = "reconnecting";
    const exp = Math.min(MAX_BACKOFF_MS, BASE_BACKOFF_MS * 2 ** this.attempt);
    const delay = Math.random() * exp;
    this.attempt += 1;
    this.sysLine(`connection lost — retrying in ${Math.round(delay)}ms (attempt ${this.attempt})`);
    clearTimeout(this.backoffTimer);
    this.backoffTimer = setTimeout(() => {
      this.backoffTimer = undefined;
      if (this.running && !this.ws) this.dial();
    }, delay);
  }

  scheduleFlush() {
    if (this.flushTimer === undefined) {
      this.flushTimer = setTimeout(() => this.flush(), FLUSH_MS);
    }
  }

  /** group the buffered frames by channel and ingest — at most every 250ms */
  flush() {
    clearTimeout(this.flushTimer);
    this.flushTimer = undefined;
    if (!this.buf.length || !this.running) { this.buf = []; return; }
    /** @type {Map<string, Msg[]>} */
    const byCh = new Map();
    for (const { channel, msg } of this.buf.splice(0)) {
      let a = byCh.get(channel);
      if (!a) { a = []; byCh.set(channel, a); }
      a.push(msg);
    }
    for (const [ch, msgs] of byCh) this.ingest(ch, msgs);
  }
}

export const natsLive = new NatsLiveConnection();
