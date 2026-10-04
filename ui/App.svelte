<script lang="ts">
  import MessageCard from "./MessageCard.svelte";
  import AddChannelDialog from "./AddChannelDialog.svelte";
  import { live, keyOf } from "./live.svelte.js";

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
  $effect(() => {
    live.ensureChannel("fleet");
    live.connect();
    return () => { live.disconnect(); };
  });

  // --- count arrivals while stuck (drives the jump pill) ---
  $effect(() => {
    const n = active.messages.length;
    if (stuck && n > prevCount) newWhileStuck += n - prevCount;
    prevCount = n;
  });

  // --- scroll: stick to bottom when new messages arrive (unless stuck) ---
  $effect(() => {
    const el = logEl;
    const n = active.messages.length;
    void activeName;
    if (!el || !n) return;
    // run after DOM updates
    queueMicrotask(() => {
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
      if (atBottom) el.scrollTop = el.scrollHeight;
    });
  });

  function onLogScroll() {
    if (!logEl) return;
    stuck = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight > 120;
    if (!stuck) newWhileStuck = 0;
  }

  function jumpToLatest() {
    if (logEl) logEl.scrollTop = logEl.scrollHeight;
    stuck = false;
    newWhileStuck = 0;
  }

  function showTab(name: string) {
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
