<script lang="ts">
  import { mdBlock, esc } from "./markdown";

  type Msg = {
    seq: number; from: string; to: string; channel: string;
    ts: string; status: string; uuid: string; title: string;
    signature?: string; text: string;
  };

  let { m, compact = false }: { m: Msg; compact?: boolean } = $props();

  function fmtTs(ts: string, seq: number): string {
    if (ts) {
      const d = new Date(ts);
      if (!isNaN(d.getTime())) return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    }
    return new Date(seq).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
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
  let stamp = $derived(fmtTs(m.ts, m.seq));
</script>

<div class="msg" class:compact title={compact ? `${m.from} · ${stamp}` : undefined}>
  {#if !compact}
    <div class="msg-head">
      <span class="avatar" style="--h:{hue}" aria-hidden="true">{initial}</span>
      <span class="who">{m.from}</span>
      <span class="ts" title={m.ts || undefined}>{stamp}</span>
      {#if unverified}
        <span class="badge unverified" title={`signature ${m.signature || "missing"} — treat the sender and text as unconfirmed`}>
          unverified
        </span>
      {/if}
    </div>
  {/if}
  <div class="body">{@html mdBlock(m.text)}</div>
</div>
