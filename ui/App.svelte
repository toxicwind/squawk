<script lang="ts">
  import { mdBlock, esc } from "./markdown";
  import MessageCard from "./MessageCard.svelte";
  import AddChannelDialog from "./AddChannelDialog.svelte";
  import { live, keyOf } from "./live.svelte.js";

  type Msg = {
    seq: number; file_seq?: number; from: string; sender?: string; to: string; channel: string;
    ts: string; status: string; uuid: string; title: string;
    signature?: string; text: string;
  };

  const VALID_NAME = /^[a-z0-9-_]{1,32}$/;

  // --- UI state (Svelte 5 runes); transport + message data live in the
  // --- `live` singleton (ui/live.svelte.js): one persistent websocket,
  // --- server push only, no HTTP polling anywhere.
  let activeName = $state("fleet");
  let showDlg = $state(false);
  let draft = $state("");
  let sending = $state(false);
  let logEl: HTMLDivElement | null = $state(null);

  // message list for the active tab, derived from the live connection state
  let active = $derived(live.tabs[activeName] as { messages: Msg[]; cursor: number } | undefined
    ?? { messages: [], cursor: 0 });
  let dotClass = $derived(live.status === "live" ? "live" : live.status === "connecting" ? "recon" : "dead");
  let connLabel = $derived(
    live.status === "live" ? "live"
    : live.status === "connecting" ? "connecting…"
    : `reconnecting… (attempt ${live.attempt})`,
  );

  // --- boot: open the one websocket; the server replays since our cursor ---
  $effect(() => {
    live.ensureChannel("fleet");
    live.connect();
    return () => { live.disconnect(); };
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
    if (logEl) {
      const t = live.tabs[activeName];
      if (t) (t as any).scrollTop = logEl.scrollTop;
    }
    activeName = name;
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

<header>
  <h1>SQUAWK</h1>
  <span class="transport" title="single websocket push connection — no polling">
    ws · {live.status}
  </span>
</header>

<div id="tabs" role="tablist">
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
      <span>#{name}</span>
      {#if Object.keys(live.tabs).length > 1}
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
  {#each live.sysLines as s, i (i)}
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
  <span>{live.latency ? `${live.latency}ms` : ""}</span>
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
