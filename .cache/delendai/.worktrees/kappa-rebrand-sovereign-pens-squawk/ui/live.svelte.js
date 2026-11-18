// ui/live.svelte.js — Squawk live connection: Svelte 5 rune-class singleton.
//
// ONE persistent WebSocket to {mount}/squawk-ws. The server pushes; this
// client NEVER polls. Reconnects with full-jitter exponential backoff
// (1s -> 30s max) and resumes from the per-channel cursor, so a drop costs
// a delta replay, never a flood.
//
// Wire protocol: /tmp/squawk-cell-primary/ws-protocol.md
//   client -> server: { subscribe: string[], since: Record<string, number> }
//   server -> client: { type: "messages", channel, messages: [...] }
//                     { type: "status", kind, ... }
//
// NOTE: compiled by ui/build.ts via svelte/compiler compileModule, which
// parses JS only — NO TypeScript syntax in this file (JSDoc types only).
//
// @typedef {"connecting"|"live"|"reconnecting"} ConnStatus
// @typedef {{seq:number,file_seq?:number,from:string,sender?:string,to:string,channel:string,ts:string,status:string,uuid:string,title:string,signature?:string,sealed?:boolean,text:string}} Msg
// @typedef {{messages:Msg[],cursor:number}} TabData

const MAX_BACKOFF_MS = 30000;
const BASE_BACKOFF_MS = 1000;
const FLUSH_MS = 250;      // inbound batching: never re-render per frame
const SYS_CAP = 20;

/** WebSocket URL for the page's mount: /fleet/squawk-ws through the funnel, /squawk-ws at root. */
function wsUrl(ticket) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  let base = location.pathname;
  if (base === "/fleet" || base.startsWith("/fleet/")) base = "/fleet";
  else base = base.replace(/\/[^/]*$/, "");
  const q = ticket ? "?ticket=" + encodeURIComponent(ticket) : "";
  return `${proto}//${location.host}${base}/squawk-ws${q}`;
}

// identity key unifying the poll seq space (file_seq) and the ws seq space.
// file_seq is 0 (not undefined) for live-tail messages not yet on disk,
// so use || not ?? — a 0 must fall through to the gseq.
/** @param {Msg} m */
export function keyOf(m) { return m.file_seq || m.seq; }

/**
 * Normalize one inbound frame into our Msg shape. Accepts the typed
 * {type:"messages"} envelopes AND the legacy bare squawk-ws frames
 * ({seq, channel, sender, ts, sealed, text}) so the client works against
 * both the cell server and the current :25147 server.
 * @param {any} d
 * @param {string} fallbackChannel
 * @returns {Msg|null}
 */
function normalize(d, fallbackChannel) {
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
    text: typeof d.text === "string" ? d.text : "",
  };
}

class LiveConnection {
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
  ticket = "";
  running = false;
  backoffTimer = undefined;
  flushTimer = undefined;
  /** @type {{channel:string, msg:Msg}[]} inbound frame buffer (renderer-crash guard) */
  buf = [];
  /** @type {Record<string, Set<number>>} per-channel dedupe keys */
  seen = {};

  constructor() {
    // wakeups: reconnect NOW, don't wait out the backoff
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") this.nudge();
    });
    window.addEventListener("online", () => this.nudge());
  }

  /** @param {{ticket?:string}} [opts] */
  configure(opts) {
    if (opts && typeof opts.ticket === "string") this.ticket = opts.ticket;
  }

  sysLine(s) {
    this.sysLines = [...this.sysLines.slice(-(SYS_CAP - 1)), s];
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

  /** @param {string} name add a channel and re-subscribe (reconnect is cheap; cursors prevent replay floods) */
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
    // Replace whole object: dynamic-key set on $state bypasses Svelte 5 reactivity
    this.tabs = {
      ...this.tabs,
      [channel]: {
        messages: [...t.messages, ...fresh].sort((a, b) => keyOf(a) - keyOf(b)),
        cursor: Math.max(t.cursor, ...fresh.map(keyOf)),
      },
    };
  }

  /** subscribe frame for the current channel set */
  subscribeFrame() {
    const since = {};
    for (const c of this.channelNames()) since[c] = this.cursorOf(c);
    return { subscribe: this.channelNames(), since };
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
    let sock;
    try {
      sock = new WebSocket(wsUrl(this.ticket));
    } catch {
      this.sysLine("websocket unavailable in this browser — retrying");
      this.onDown();
      return;
    }
    this.ws = sock;

    sock.onopen = () => {
      if (this.ws !== sock) return;
      try { sock.send(JSON.stringify(this.subscribeFrame())); } catch {}
      this.status = "live";
      this.attempt = 0;
      this.sysLine(`live push connected — #${chans.join(" #")}`);
      // keepalive is server-side: the WS server pings every 30s and the
      // runtime answers automatically. No client JSON ping needed —
      // the server ignores all post-subscribe frames.
    };

    sock.onmessage = (ev) => {
      if (this.ws !== sock) return;
      this.onFrame(ev.data);
    };

    // onerror: onclose follows; nothing to do here but avoid an unhandled throw
    sock.onerror = () => {};

    sock.onclose = () => {
      if (this.ws !== sock) return;
      this.ws = null;
      if (!this.running) return;
      this.onDown();
    };
  }

  /** socket lost (or never opened): back off with full jitter, keep retrying WS — never poll */
  onDown() {
    this.flush();
    this.status = "reconnecting";
    // full-jitter exponential backoff: 1s -> 30s max
    const exp = Math.min(MAX_BACKOFF_MS, BASE_BACKOFF_MS * 2 ** this.attempt);
    const delay = Math.random() * exp;
    this.attempt += 1;
    this.sysLine(`live push lost — retrying websocket in ${Math.round(delay)}ms (attempt ${this.attempt})`);
    clearTimeout(this.backoffTimer);
    this.backoffTimer = setTimeout(() => {
      this.backoffTimer = undefined;
      if (this.running && !this.ws) this.dial();
    }, delay);
  }

  /** typed dispatch over the one socket */
  onFrame(data) {
    let d;
    try { d = JSON.parse(data); } catch { return; }

    // {type:"messages", channel, messages:[...]} — replay + live, same shape
    if (d && d.type === "messages") {
      const ch = typeof d.channel === "string" ? d.channel : "";
      const arr = Array.isArray(d.messages) ? d.messages : [];
      if (!this.tabs[ch]) { this.sysLine(`ignoring messages for unsubscribed channel #${ch}`); return; }
      for (const raw of arr) {
        const m = normalize(raw, ch);
        if (m) this.buf.push({ channel: ch, msg: m });
      }
      this.scheduleFlush();
      return;
    }

    // {type:"status", kind, ...}
    if (d && d.type === "status") {
      if (d.kind === "subscribed" && Array.isArray(d.channels)) {
        this.sysLine(`server confirmed subscription: #${d.channels.join(" #")}`);
      } else if (d.kind === "error") {
        this.sysLine("server: " + String(d.message || "error"));
      }
      return;
    }

    // legacy bare frame from squawk-ws (:25147): {seq, channel, sender, ...}
    const m = normalize(d, "");
    if (m && m.channel && this.tabs[m.channel]) {
      this.buf.push({ channel: m.channel, msg: m });
      this.scheduleFlush();
    }
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

export const live = new LiveConnection();
