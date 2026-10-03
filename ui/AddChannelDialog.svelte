<script lang="ts">
  const VALID_NAME = /^[a-z0-9-_]{1,32}$/;

  let { onClose, onAdd }: { onClose: () => void; onAdd: (name: string) => void } = $props();

  let name = $state("");
  let err = $state("");
  let inputEl: HTMLInputElement | null = $state(null);

  $effect(() => { inputEl?.focus(); });

  function submit() {
    const n = name.trim().toLowerCase();
    if (!VALID_NAME.test(n)) {
      err = "channel names are 1-32 chars: a-z 0-9 - _";
      return;
    }
    onAdd(n);
  }
</script>

<div
  id="dlg-back"
  onclick={(e) => { if (e.target === e.currentTarget) onClose(); }}
  onkeydown={(e) => { if (e.key === "Escape") onClose(); }}
  role="presentation"
>
  <div id="dlg" role="dialog" aria-label="add channel">
    <div><strong>new channel</strong></div>
    <input
      bind:this={inputEl}
      bind:value={name}
      oninput={() => (err = "")}
      onkeydown={(e) => { if (e.key === "Enter") submit(); }}
      placeholder="channel name (a-z, 0-9, -, _)"
      aria-label="channel name"
    />
    {#if err}<div class="sys">{err}</div>{/if}
    <div class="row">
      <button onclick={onClose}>cancel</button>
      <button class="primary" onclick={submit}>add</button>
    </div>
  </div>
</div>
