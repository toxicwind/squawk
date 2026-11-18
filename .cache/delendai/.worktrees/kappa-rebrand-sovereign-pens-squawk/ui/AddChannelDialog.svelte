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
  <div id="dlg" role="dialog" aria-modal="true" aria-label="add channel">
    <p class="dlg-title">new channel</p>
    <p class="dlg-sub">tune into another feed</p>
    <input
      bind:this={inputEl}
      bind:value={name}
      oninput={() => (err = "")}
      onkeydown={(e) => { if (e.key === "Enter") submit(); }}
      placeholder="channel name"
      aria-label="channel name"
      autocapitalize="none"
      spellcheck="false"
    />
    {#if err}<div class="dlg-err" role="alert">{err}</div>{/if}
    <div class="row">
      <button class="btn ghost" onclick={onClose}>cancel</button>
      <button class="btn primary" onclick={submit}>add channel</button>
    </div>
  </div>
</div>
