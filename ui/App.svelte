<script lang="ts">
  import { mdBlock, esc } from "./markdown";
  import MessageCard from "./MessageCard.svelte";
  import AddChannelDialog from "./AddChannelDialog.svelte";

  type Msg = {
    seq: number; file_seq?: number; from: string; sender?: string; to: string; channel: string;
    ts: string; status: string; uuid: string; title: string;
    signature?: string; text: string;
  };
  type TabState = { messages: Msg[]; cursor: number; scrollTop: number; wsSeq: number };
  type ConnState = "live" | "degraded" | "reconnecting";

  const VALID_NAME = /^[a-z0-9-_]{1,32}$/;

  // --- state (Svelte 5 runes) ---
  let tabs = $state<Record<string, TabState>>({
    fleet: { messages: [], cursor: 0, scrollTop: 0, wsSeq: 0 },
  });
  let activeName = $state("fleet");
  let conn = $state<ConnState>("reconnecting");
  let latency = $state(0);
  let sysLines = $state<string[]>([]);
  let showDlg = $state(false);
  let draft = $state("");
  let sending = $state(false);

  let active = $derived(tabs[activeName] ?? { messages: [], cursor: 0, scrollTop: 0, wsSeq: 0 });
  let dotClass = $derived(conn === "live" ? "live" : conn === "degraded" ? "recon" : "recon");
  let connLabel = $derived(conn === "live" ? "live" : conn === "degraded" ? "degraded — auto-fallback" : "reconnecting…");

  let logEl: HTMLDivElement | null = $state(null);
  let ws: WebSocket | null = null;
  let pollTimer: number | undefined;
  let wsFailTimer: number | undefined;
  let reconTimer: number | undefined;
  let wsFlushTimer: number | undefined;
  let reconnectDelay = 1000;
  let running = true;
  let polling = false;
  let intentionalClose = false;
  let useWs = $state(false); // transport: ws primary, poll fallback (automatic, no user choice)

  // identity key: unifies the poll seq space (file_seq) and the ws gseq space
  // (ws frames carry both seq=gseq and file_seq). Same logical message -> same key.
  // Note: file_seq is 0 (not undefined) for live-tail messages not yet on disk,
  // so use || not ?? — a 0 must fall through to the gseq.
  function keyOf(m: Msg): number { return m.file_seq || m.seq; }

  function sysLine(s: string) {
    sysLines = [...sysLines.slice(-19), s];
  }

  function ingest(channel: string, msgs: Msg[]) {
    const t = tabs[channel];
    if (!t || !msgs.length) return;
    const seen = new Set(t.messages.map(keyOf));
    const fresh = msgs.filter(m => !seen.has(keyOf(m)));
    if (!fresh.length) return;
    tabs[channel] = {
      ...t,
      messages: [...t.messages, ...fresh].sort((a, b) => keyOf(a) - keyOf(b)),
      cursor: Math.max(t.cursor, ...fresh.map(keyOf)),
    };
  }

  // normalize a squawk-ws broadcast frame into our Msg shape
  // (server sends {seq, file_seq, channel, sender, ts, sealed, text})
  function normalizeWs(d: any, fallbackChannel: string): Msg | null {
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
      text: typeof d.text === "string" ? d.text : "",
    };
  }

  // --- transport: WebSocket primary (squawk-ws protocol), automatic fallback to polling ---
  function wsUrl(): string {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const base = location.pathname.replace(/\/[^/]*$/, "");
    return `${proto}//${location.host}${base}/squawk-ws`;
  }

  function closeWs() {
    intentionalClose = true;
    window.clearTimeout(wsFailTimer);
    flushWsBuf();
    if (ws) {
      try { ws.onclose = null; ws.onerror = null; ws.onmessage = null; ws.close(); } catch {}
      ws = null;
    }
  }

  // incoming ws frames are buffered and flushed at most every 250ms:
  // a subscribe replay can deliver ~1000 frames at once, and ingesting +
  // re-rendering per frame is what crashed the renderer.
  let wsBuf: { channel: string; msg: Msg }[] = [];
  function flushWsBuf() {
    window.clearTimeout(wsFlushTimer);
    wsFlushTimer = undefined;
    if (!wsBuf.length || !running) { wsBuf = []; return; }
    const byCh = new Map<string, Msg[]>();
    for (const { channel, msg } of wsBuf.splice(0)) {
      let a = byCh.get(channel);
      if (!a) { a = []; byCh.set(channel, a); }
      a.push(msg);
    }
    for (const [ch, msgs] of byCh) ingest(ch, msgs);
  }

  function onWsFrames(ev: MessageEvent) {
    try {
      const d = JSON.parse(ev.data);
      const arr: any[] = Array.isArray(d) ? d : d.messages ? d.messages : [d];
      for (const raw of arr) {
        const ch = typeof raw?.channel === "string" && tabs[raw.channel] ? raw.channel : activeName;
        const m = normalizeWs(raw, ch);
        if (!m) continue;
        const t = tabs[ch];
        if (!t) continue;
        // gseq resume cursor (ws seq space; poll cursor stays in file_seq space)
        if (raw.seq > t.wsSeq) t.wsSeq = raw.seq;
        wsBuf.push({ channel: ch, msg: m });
      }
      window.clearTimeout(wsFailTimer);
      if (!useWs) onPushLive();
      if (wsFlushTimer === undefined) wsFlushTimer = window.setTimeout(flushWsBuf, 250);
    } catch {}
  }

  function onPushLive() {
    window.clearTimeout(wsFailTimer);
    window.clearTimeout(reconTimer);
    reconnectDelay = 1000;
    if (!useWs) sysLine("live push connected");
    useWs = true;
    conn = "live";
    polling = false;
    window.clearTimeout(pollTimer);
  }

  function onPushLost() {
    flushWsBuf();
    if (useWs) sysLine("live push lost — reconnecting");
    useWs = false;
    conn = "reconnecting";
    startPoll("push disconnected");
    scheduleReconnect();
  }

  // server protocol: first text frame must be {subscribe: [...channels], since}
  // (since = per-channel gseq, or a single gseq). since=0 replays newest 1000.
  function connectPush(quiet = false) {
    if (!running) return;
    closeWs();
    const chans = Object.keys(tabs);
    if (!chans.length) return;
    intentionalClose = false;
    let sock: WebSocket;
    try { sock = new WebSocket(wsUrl()); }
    catch { useWs = false; startPoll("ws unavailable"); return; }
    ws = sock;
    if (!quiet) conn = "reconnecting";

    wsFailTimer = window.setTimeout(() => {
      if (ws !== sock) return;
      intentionalClose = true;
      try { sock.close(); } catch {}
      ws = null;
      if (!quiet) sysLine("live push unavailable — auto-fallback to polling");
      startPoll(quiet ? "ws retry failed" : "ws protocol timeout");
    }, 8000);

    sock.onopen = () => {
      const since: Record<string, number> = {};
      for (const c of chans) since[c] = tabs[c]?.wsSeq ?? 0;
      try { sock.send(JSON.stringify({ subscribe: chans, since })); } catch {}
    };
    sock.onmessage = onWsFrames;
    sock.onerror = () => { /* onclose follows */ };
    sock.onclose = () => {
      if (ws !== sock) return;
      ws = null;
      if (intentionalClose || !running) return;
      onPushLost();
    };
  }

  function scheduleReconnect() {
    if (!running) return;
    const d = reconnectDelay;
    reconnectDelay = Math.min(reconnectDelay * 2, 30000);
    window.clearTimeout(reconTimer);
    reconTimer = window.setTimeout(() => {
      if (!running || useWs) return;
      connectPush();
    }, d);
  }

  async function pollOnce(channel: string, cursor: number): Promise<boolean> {
    const t0 = performance.now();
    try {
      const r = await fetch(`wait?since=${cursor}&channel=${encodeURIComponent(channel)}&tail=200`);
      if (!r.ok) throw new Error("http " + r.status);
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || "bad response");
      latency = Math.round(performance.now() - t0);
      ingest(channel, d.messages || []);
      return true;
    } catch { return false; }
  }

  function startPoll(reason: string) {
    if (!running || polling) return;
    polling = true;
    if (!useWs) sysLine(reason + " — on polling fallback");
    let lastRetry = 0;
    const loop = async () => {
      if (!running || useWs) { polling = false; return; }
      const ok = await pollOnce(activeName, tabs[activeName]?.cursor ?? 0);
      if (!running || useWs) { polling = false; return; }
      conn = ok ? "degraded" : "reconnecting";
      // quiet background retry of live push every 30s while polling healthy
      const now = Date.now();
      if (ok && now - lastRetry > 30000) { lastRetry = now; connectPush(true); }
      pollTimer = window.setTimeout(loop, ok ? 2500 : 5000);
    };
    loop();
  }

  // --- boot: snapshot then live transport ---
  $effect(() => {
    running = true;
    sysLine("tuned in — pulling the latest traffic…");
    (async () => {
      const t = tabs[activeName];
      if (t) await pollOnce(activeName, t.cursor);
      if (running) connectPush();
    })();
    const onOnline = () => { if (running && !useWs) connectPush(); };
    window.addEventListener("online", onOnline);
    return () => {
      running = false;
      window.removeEventListener("online", onOnline);
      window.clearTimeout(pollTimer);
      window.clearTimeout(wsFailTimer);
      window.clearTimeout(reconTimer);
      window.clearTimeout(wsFlushTimer);
      try { ws?.close(); } catch {}
      ws = null;
    };
  });

  // --- scroll: stick to bottom when new messages arrive ---
  $effect(() => {
    const el = logEl;
    const n = active.messages.length;
    const name = activeName;
    if (!el || !n) return;
    // run after DOM updates
    queueMicrotask(() => {
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
      if (atBottom) el.scrollTop = el.scrollHeight;
    });
  });

  function showTab(name: string) {
    if (logEl && tabs[activeName]) {
      tabs[activeName] = { ...tabs[activeName], scrollTop: logEl.scrollTop };
    }
    activeName = name;
    queueMicrotask(() => {
      const t = tabs[name];
      if (logEl && t) logEl.scrollTop = t.scrollTop || logEl.scrollHeight;
    });
  }

  function addTab(name: string) {
    if (tabs[name]) { showTab(name); showDlg = false; return; }
    tabs[name] = { messages: [], cursor: 0, scrollTop: 0, wsSeq: 0 };
    showDlg = false;
    sysLine(`channel #${name} added — tuned in`);
    showTab(name);
    // re-subscribe push to include the new channel (delta-only replay via since)
    connectPush();
    if (!useWs) pollOnce(name, 0);
  }

  function closeTab(name: string) {
    if (!tabs[name] || Object.keys(tabs).length <= 1) return;
    const { [name]: _, ...rest } = tabs;
    tabs = rest;
    if (name === activeName) showTab(Object.keys(rest)[0]);
  }

  async function sendMsg() {
    const text = draft.trim();
    if (!text || sending || !activeName) return;
    sending = true;
    try {
      const r = await fetch("send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel: activeName, text }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) throw new Error(d.error || "http " + r.status);
      draft = "";
      // the live loop renders it; no optimistic duplicate needed
    } catch (e: any) {
      sysLine("send failed: " + (e.message || e) + " — retrying is safe");
    } finally {
      sending = false;
    }
  }
</script>

<header>
  <h1>SQUAWK</h1>
  <span class="transport" title={useWs ? "live push via websocket" : "polling fallback — push unavailable"}>
    {useWs ? "push" : "poll"}
  </span>
</header>

<div id="tabs" role="tablist">
  {#each Object.keys(tabs) as name (name)}
    <div
      role="tab"
      aria-selected={name === activeName}
      class="tab"
      class:active={name === activeName}
      onclick={() => showTab(name)}
      onkeydown={(e) => e.key === "Enter" && showTab(name)}
      tabindex="0"
    >
      <span>#{name}</span>
      {#if Object.keys(tabs).length > 1}
        <span
          class="x"
          title={`close #${name}`}
          role="button"
          tabindex="0"
          onclick={(e) => { e.stopPropagation(); closeTab(name); }}
          onkeydown={(e) => { if (e.key === "Enter") { e.stopPropagation(); closeTab(name); } }}
        >×</span>
      {/if}
    </div>
  {/each}
  <button id="addTab" onclick={() => (showDlg = true)} title="add channel" aria-label="add channel">+</button>
</div>

<div id="log" bind:this={logEl}>
  {#each sysLines as s, i (i)}
    <div class="sys">{s}</div>
  {/each}
  {#each active.messages as m (keyOf(m))}
    <MessageCard {m} />
  {/each}
</div>

<div id="composer">
  <input
    id="msg"
    bind:value={draft}
    onkeydown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMsg(); } }}
    placeholder={`message #${activeName}…  (enter to send)`}
    autocomplete="off"
    aria-label="message"
    disabled={sending}
  />
  <button id="send" onclick={sendMsg} disabled={sending || !draft.trim()}>send</button>
</div>

<div id="statusbar">
  <span><span class="dot {dotClass}"></span>{connLabel}</span>
  <span>seq {active.cursor || "—"}</span>
  <span>{latency ? `${latency}ms` : ""}</span>
</div>

{#if showDlg}
  <AddChannelDialog onClose={() => (showDlg = false)} onAdd={addTab} />
{/if}

<style>
  .transport {
    margin-left: auto;
    font-size: 11px;
    color: var(--faint);
    border: 1px solid var(--line);
    border-radius: 6px;
    padding: 4px 8px;
  }
</style>
