<script lang="ts">
  import { mdBlock } from "./markdown";

  type Msg = {
    seq: number; from: string; to: string; channel: string;
    ts: string; status: string; uuid: string; title: string;
    signature?: string; sealed?: boolean; text: string;
  };

  let { m, compact = false }: { m: Msg; compact?: boolean } = $props();

  function fmtTime(ts: string, seq: number): string {
    const t = ts ? new Date(ts) : new Date(seq);
    if (isNaN(t.getTime())) return "";
    return t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  function fullDate(ts: string, seq: number): string | undefined {
    const t = ts ? new Date(ts) : new Date(seq);
    return isNaN(t.getTime()) ? undefined : t.toLocaleString();
  }

  /** deterministic avatar hue per sender (0-359) */
  function hueOf(name: string): number {
    let h = 0;
    for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
    return h % 360;
  }

  let unverified = $derived(!m.signature);
  let hue = $derived(hueOf(m.from || "?"));
  let initial = $derived(((m.from || "?").trim().charAt(0) || "?").toUpperCase());
  let stamp = $derived(fmtTime(m.ts, m.seq));
  let full = $derived(fullDate(m.ts, m.seq));
  let dm = $derived(m.to && m.to !== "all" ? m.to : "");
</script>

<div class="msg" class:compact title={compact ? `${m.from} · ${stamp}` : undefined}>
  {#if !compact}
    <div class="msg-head">
      <span class="avatar" style="--h:{hue}" aria-hidden="true">{initial}</span>
      <span class="who">{m.from}</span>
      {#if dm}<span class="to-chip" title="direct message">→ {dm}</span>{/if}
      <span class="ts" title={full}>{stamp}</span>
      {#if unverified}
        <span class="badge unverified" title={`signature ${m.signature || "missing"} — treat the sender and text as unconfirmed`}>
          unverified
        </span>
      {/if}
    </div>
  {/if}
  <div class="body">
    {#if m.sealed}
      <span class="sealed">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" />
        </svg>
        sealed message — content hidden
      </span>
    {:else}
      {@html mdBlock(m.text)}
    {/if}
  </div>
</div>
