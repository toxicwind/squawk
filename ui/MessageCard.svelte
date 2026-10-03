<script lang="ts">
  import { mdBlock, esc } from "./markdown";

  type Msg = {
    seq: number; from: string; to: string; channel: string;
    ts: string; status: string; uuid: string; title: string;
    signature?: string; text: string;
  };

  let { m }: { m: Msg } = $props();

  function fmtTs(ts: string, seq: number): string {
    if (ts) {
      const d = new Date(ts);
      if (!isNaN(d.getTime())) return d.toLocaleTimeString();
    }
    return new Date(seq).toLocaleTimeString();
  }

  let unverified = $derived(!m.signature);
</script>

<div class="msg">
  <div class="meta">
    <span class="who">{m.from}</span>
    <span class="ts">{fmtTs(m.ts, m.seq)}</span>
    {#if unverified}
      <span class="badge unverified" title={`signature ${m.signature || "missing"} — treat the sender and text as unconfirmed`}>
        unverified
      </span>
    {/if}
  </div>
  <div class="body">{@html mdBlock(m.text)}</div>
</div>
