<script lang="ts">
  import MessageCard from "./MessageCard.svelte";
  import AddChannelDialog from "./AddChannelDialog.svelte";
  import { untrack, tick } from "svelte";
  import { live as feedLive, keyOf as feedKeyOf } from "./live.svelte.js";
  import { natsLive, keyOf as natsKeyOf } from "./nats-live.svelte.js";
  // ?src=nats swaps the live source to NATS+JetStream (file-feed snapshot
  // for history, NATS for live). Default stays the feed websocket.
  const SRC_NATS = new URLSearchParams(location.search).get("src") === "nats";
  const live = SRC_NATS ? (natsLive as typeof feedLive) : feedLive;
  const keyOf = SRC_NATS ? natsKeyOf : feedKeyOf;

  type Msg = {
    seq: number; file_seq?: number; from: string; sender?: string; to: string; channel: string;
    ts: string; status: string; uuid: string; title: string;
    signature?: string; sealed?: boolean; text: string;
  };

  // --- UI state (Svelte 5 runes); transport + message data live in the
  // --- `live` singleton (ui/live.svelte.js): one persistent websocket,
  // --- server push only, no HTTP polling anywhere.
  let activeName = $state("fleet");
  let showDlg = $state(false);
  let draft = $state("");
  let sending = $state(false);
  let logEl: HTMLDivElement | null = $state(null);
  // stuck = the user scrolled up; new arrivals surface a jump pill
  // instead of yanking the scroll position.
  let stuck = $state(false);
  let newWhileStuck = $state(0);
  let prevCount = 0;
  // --- history paging: the boot snapshot is tail-capped (200); older
  // --- messages load on demand via /wait?before=<oldest loaded seq>.
  // --- Per-channel state; hasMore starts optimistic-true and the server's
  // --- has_more field corrects it on the first page fetch.
  let paging = $state({} as Record<string, { hasMore: boolean; loading: boolean }>);
  let page = $derived(paging[activeName] ?? { hasMore: true, loading: false });
  // while a history page is being prepended, the pin-to-bottom and
  // new-arrival effects must not fire — scroll anchoring owns the position.
  let prepending = $state(false);
  // --- history pack: C1+C3 digest of a channel's deep history from the
  // --- squawk-history service, proxied by the UI server at /pack (the
  // --- server holds the feed token; /pack takes seconds on big channels).
  type PackDigest = { episode: number; count: number; seq_first: number; seq_last: number; senders: Record<string, number>; terms: string[] };
  let pack = $state(null as null | {
    loading?: boolean; error?: string; used?: number; budget?: number;
    nMsgs?: number; digestsTotal?: number; digests?: PackDigest[];
  });
  let packQuery = $state("");
  let msgEl: HTMLTextAreaElement | null = $state(null);

  // auto-growing composer: the textarea expands with content up to a cap,
  // then scrolls internally. Enter sends, Shift+Enter inserts a newline.
  function autogrow() {
    const el = msgEl;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 168) + "px";
  }
  // shrink back to one row whenever the draft clears (e.g. after send)
  $effect(() => {
    if (draft === "") autogrow();
  });

  // message list for the active tab, derived from the live connection state
  let active = $derived(live.tabs[activeName] as { messages: Msg[]; cursor: number } | undefined
    ?? { messages: [], cursor: 0 });
  let dotClass = $derived(live.status === "live" ? "live" : live.status === "connecting" ? "recon" : "dead");
  let connLabel = $derived(
    live.status === "live" ? "live"
    : live.status === "connecting" ? "connecting…"
    : `reconnecting… (attempt ${live.attempt})`,
  );
  let tabCount = $derived(Object.keys(live.tabs).length);
  let loading = $derived(active.messages.length === 0 && live.status !== "live");

  // --- boot: open the one websocket; the server replays since our cursor ---
  // untrack: ensureChannel reads live.tabs ($state). Without untrack, every
  // ingest re-runs this effect → disconnect/connect → duplicate syslines.
  $effect(() => {
    untrack(() => {
      live.ensureChannel("fleet");
      if (SRC_NATS) {
        // NATS carries live messages only - hydrate history from the file
        // feed first (it stays the source of truth), then go live.
        fetch("wait?channel=fleet&tail=200")
          .then((r) => r.json())
          .then((d) => { if (d && Array.isArray(d.messages)) (live as typeof natsLive).ingestSnapshot("fleet", d.messages); })
          .catch((e) => live.sysLine("snapshot failed: " + (e?.message || e)))
          .finally(() => live.connect());
      } else {
        live.connect();
      }
    });
    return () => { live.disconnect(); };
  });

  // --- count arrivals while stuck (drives the jump pill) ---
  $effect(() => {
    const n = active.messages.length;
    if (prepending) { prevCount = n; return; }
    if (stuck && n > prevCount) newWhileStuck += n - prevCount;
    prevCount = n;
  });

  // --- scroll: stick to bottom when new messages arrive (unless stuck) ---
  // On first paint scrollTop is 0 (not "at bottom"), so an atBottom-only
  // check left the feed glued to the top of a huge backlog. When !stuck,
  // always pin to bottom; when stuck, leave the user alone (jump pill).
  $effect(() => {
    const el = logEl;
    const n = active.messages.length;
    void activeName;
    if (!el || !n || stuck || prepending) return;
    // run after DOM updates
    queueMicrotask(() => {
      el.scrollTop = el.scrollHeight;
    });
  });

  function onLogScroll() {
    if (!logEl) return;
    stuck = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight > 120;
    if (!stuck) newWhileStuck = 0;
    // near the top of loaded history: page in the next older chunk
    if (logEl.scrollTop < 90) void loadOlder();
  }

  // Fetch one history page older than the oldest loaded message and
  // prepend it, preserving the exact scroll position (scroll anchoring:
  // record height/top, ingest, then shift top by the height delta).
  async function loadOlder() {
    const name = activeName;
    const t = live.tabs[name] as { messages: Msg[]; cursor: number } | undefined;
    if (!t || !t.messages.length || prepending) return;
    const p = paging[name] ?? { hasMore: true, loading: false };
    if (p.loading || !p.hasMore) return;
    paging = { ...paging, [name]: { hasMore: p.hasMore, loading: true } };
    const el = logEl;
    const prevH = el ? el.scrollHeight : 0;
    const prevTop = el ? el.scrollTop : 0;
    prepending = true;
    try {
      const oldestKey = keyOf(t.messages[0]);
      const r = await fetch(`wait?channel=${encodeURIComponent(name)}&before=${oldestKey}&tail=100`);
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.error || "http " + r.status);
      const fresh: Msg[] = Array.isArray(d.messages) ? d.messages : [];
      if (fresh.length) {
        if (SRC_NATS) (live as typeof natsLive).ingestSnapshot(name, fresh);
        else live.ingest(name, fresh as any);
      }
      paging = { ...paging, [name]: { hasMore: !!d.has_more && fresh.length > 0, loading: false } };
      await tick();
      if (el) el.scrollTop = prevTop + (el.scrollHeight - prevH);
    } catch (e: any) {
      paging = { ...paging, [name]: { hasMore: p.hasMore, loading: false } };
      live.sysLine("load older failed: " + (e.message || e));
    } finally {
      prepending = false;
    }
  }

  function jumpToLatest() {
    if (logEl) logEl.scrollTop = logEl.scrollHeight;
    stuck = false;
    newWhileStuck = 0;
  }

  async function fetchPack() {
    const name = activeName;
    if (pack?.loading) return;
    pack = { loading: true };
    try {
      const r = await fetch(`pack?channel=${encodeURIComponent(name)}&q=${encodeURIComponent(packQuery)}&budget=4000`);
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.error || "http " + r.status);
      pack = {
        used: d.used_tokens_est, budget: d.budget_tokens,
        nMsgs: Array.isArray(d.messages) ? d.messages.length : 0,
        digestsTotal: d.digests_total, digests: Array.isArray(d.digests) ? d.digests : [],
      };
    } catch (e: any) {
      pack = { error: e.message || String(e) };
    }
  }

  function showTab(name: string) {
    pack = null;
    if (logEl) {
      const t = live.tabs[activeName];
      if (t) (t as any).scrollTop = logEl.scrollTop;
    }
    activeName = name;
    stuck = false;
    newWhileStuck = 0;
    queueMicrotask(() => {
      if (logEl) logEl.scrollTop = (live.tabs[name] as any)?.scrollTop || logEl.scrollHeight;
    });
  }

  function addTab(name: string) {
    showDlg = false;
    if (live.tabs[name]) { showTab(name); return; }
    // live re-subscribes over the socket (delta-only replay via since cursors)
    live.addChannel(name);
    showTab(name);
  }

  function closeTab(name: string) {
    if (!live.tabs[name] || Object.keys(live.tabs).length <= 1) return;
    live.removeChannel(name);
    if (name === activeName) showTab(Object.keys(live.tabs)[0]);
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
      // the server push renders the echo; no optimistic duplicate needed
    } catch (e: any) {
      live.sysLine("send failed: " + (e.message || e) + " — retrying is safe");
    } finally {
      sending = false;
    }
  }
</script>

<div class="app">
  <header class="topbar">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true">◈</span>
      <h1>SQUAWK</h1>
    </div>
    <div
      class="conn"
      data-state={live.status}
      title="single websocket push connection — no polling"
      role="status"
      aria-label={`connection: ${connLabel}`}
    >
      <span class="dot {dotClass}"></span>
      <span class="conn-label">{connLabel}</span>
      <button
        class="src-toggle"
        title={SRC_NATS ? "live via NATS+JetStream - click for file-feed websocket" : "live via file-feed websocket - click for NATS+JetStream"}
        aria-label="toggle live source"
        onclick={() => {
          const u = new URL(location.href);
          if (SRC_NATS) u.searchParams.delete("src");
          else u.searchParams.set("src", "nats");
          location.href = u.toString();
        }}
      >src: {SRC_NATS ? "nats" : "feed"}</button>
    </div>
  </header>

  <nav id="tabs" aria-label="channels">
    <div class="tabs-scroll" role="tablist">
      {#each Object.keys(live.tabs) as name (name)}
        <div
          role="tab"
          aria-selected={name === activeName}
          class="tab"
          class:active={name === activeName}
          onclick={() => showTab(name)}
          onkeydown={(e) => e.key === "Enter" && showTab(name)}
          tabindex="0"
        >
          <span class="tab-name">#{name}</span>
          {#if tabCount > 1}
            <button
              class="x"
              title={`close #${name}`}
              aria-label={`close #${name}`}
              onclick={(e) => { e.stopPropagation(); closeTab(name); }}
            >×</button>
          {/if}
        </div>
      {/each}
      <button id="addTab" onclick={() => (showDlg = true)} title="add channel" aria-label="add channel">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
          <path d="M8 3v10M3 8h10" />
        </svg>
      </button>
    </div>
  </nav>

  <div id="log" bind:this={logEl} onscroll={onLogScroll}>
    {#each live.sysLines as s, i (i)}
      <div class="sys">{s}</div>
    {/each}
    {#if active.messages.length === 0}
      {#if loading}
        <div class="skels" aria-hidden="true">
          {#each [0, 1, 2, 3] as i (i)}
            <div class="skel">
              <div class="skel-row"><span class="skel-avatar"></span><span class="skel-name"></span><span class="skel-ts"></span></div>
              <div class="skel-line"></div>
              <div class="skel-line short"></div>
            </div>
          {/each}
        </div>
      {:else}
        <div class="empty">
          <div class="empty-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z" />
            </svg>
          </div>
          <p class="empty-title">nothing on #{activeName} yet</p>
          <p class="empty-sub">messages land here live — say something below</p>
        </div>
      {/if}
    {/if}
    {#if active.messages.length > 0}
      <div style="display:flex;justify-content:center;align-items:center;height:32px;">
        {#if page.loading}
          <span style="opacity:.55;font-size:12px;">loading older…</span>
        {:else if page.hasMore}
          <button onclick={loadOlder} style="background:none;border:1px solid rgba(255,255,255,.14);border-radius:999px;color:inherit;padding:3px 12px;font-size:12px;cursor:pointer;" aria-label="load older messages">↑ load older messages</button>
        {:else}
          <span style="opacity:.45;font-size:12px;">— beginning of #{activeName} —</span>
        {/if}
      </div>
    {/if}
    {#if active.messages.length > 0}
      <div style="margin:2px 8px 6px;border:1px solid rgba(255,255,255,.10);border-radius:10px;padding:6px 10px;font-size:12px;">
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <button onclick={fetchPack} disabled={pack?.loading} style="background:none;border:1px solid rgba(255,255,255,.14);border-radius:999px;color:inherit;padding:3px 12px;font-size:12px;cursor:pointer;" aria-label="summarize channel history as a pack">
            {pack?.loading ? "packing…" : "📦 history pack"}
          </button>
          <input bind:value={packQuery} placeholder="focus terms (optional)" aria-label="pack focus terms"
            style="background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.10);border-radius:999px;color:inherit;padding:3px 10px;font-size:12px;min-width:150px;"
            onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); void fetchPack(); } }} />
          {#if pack && !pack.loading && !pack.error}
            <span style="opacity:.65;">~{pack.used} of {pack.budget} tokens · {pack.nMsgs} messages kept · {pack.digestsTotal} pruned episodes</span>
            <button onclick={() => (pack = null)} style="background:none;border:none;color:inherit;opacity:.6;cursor:pointer;font-size:12px;" aria-label="close pack">✕</button>
          {/if}
          {#if pack?.error}
            <span style="opacity:.8;">pack failed: {pack.error}</span>
          {/if}
        </div>
        {#if pack?.digests?.length}
          <div style="margin-top:6px;display:flex;flex-direction:column;gap:2px;">
            {#each pack.digests.slice(0, 12) as d (d.episode)}
              <div style="opacity:.75;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title={`episode ${d.episode} · seq ${d.seq_first}–${d.seq_last}`}>
                <span style="opacity:.7;">#{d.episode}</span> · {d.count} msgs · {Object.entries(d.senders).map(([s, n]) => n > 1 ? `${s}×${n}` : s).join(", ")} · {d.terms.slice(0, 5).join(" · ")}
              </div>
            {/each}
            {#if pack.digests.length > 12}
              <div style="opacity:.5;">…and {pack.digests.length - 12} more digest spans (of {pack.digestsTotal} pruned episodes)</div>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
    {#each active.messages as m, i (keyOf(m))}
      <MessageCard {m} compact={i > 0 && active.messages[i - 1].from === m.from} />
    {/each}
  </div>

  {#if stuck && newWhileStuck > 0}
    <button id="jump" onclick={jumpToLatest} aria-label={`jump to latest, ${newWhileStuck} new messages`}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M12 5v14M5 12l7 7 7-7" />
      </svg>
      {newWhileStuck} new
    </button>
  {/if}

  <div id="composer">
    <div class="composer-bar">
      <textarea
        id="msg"
        rows={1}
        bind:this={msgEl}
        bind:value={draft}
        oninput={autogrow}
        onkeydown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMsg(); } }}
        placeholder={`message #${activeName}`}
        autocomplete="off"
        autocapitalize="sentences"
        aria-label="message"
        enterkeyhint="send"
        disabled={sending}
      ></textarea>
      <button
        id="send"
        onclick={sendMsg}
        disabled={sending || !draft.trim()}
        aria-label="send message"
        title="send (enter)"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 19V5M5 12l7-7 7 7" />
        </svg>
      </button>
    </div>
    <div class="composer-meta" aria-hidden="true">
      <span><kbd>enter</kbd> to send · <kbd>shift</kbd>+<kbd>enter</kbd> for a new line</span>
    </div>
  </div>

  <footer id="statusbar">
    <span class="sb-item">seq {active.cursor || "—"}</span>
    <span class="sb-item sb-right">{tabCount} channel{tabCount === 1 ? "" : "s"}</span>
  </footer>
</div>

{#if showDlg}
  <AddChannelDialog onClose={() => (showDlg = false)} onAdd={addTab} />
{/if}
