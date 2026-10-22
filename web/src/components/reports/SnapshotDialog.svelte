<script lang="ts">
  // Foto bukti ukuran penuh. Terbuka saat `record` diisi; ditutup (Esc, tombol,
  // klik latar) → `record` kembali null.
  import X from '@lucide/svelte/icons/x'
  import { api } from '../../lib/api/client'
  import type { ReportRecord } from '../../lib/api/types'
  import { REPORTS as TEXT, shortDate } from '../../lib/messages'
  import { resultKind } from '../../lib/reports'

  let { record = $bindable(null) }: { record?: ReportRecord | null } = $props()

  let dialog: HTMLDialogElement | undefined = $state()

  $effect(() => {
    if (!dialog) return
    if (record && !dialog.open) dialog.showModal()
    else if (!record && dialog.open) dialog.close()
  })

  // Klik di latar (di luar isi dialog) menutup
  function onBackdrop(e: MouseEvent) {
    if (e.target === dialog) record = null
  }
</script>

<dialog bind:this={dialog} onclose={() => (record = null)} onclick={onBackdrop} aria-labelledby="snapshot-title">
  {#if record}
    <header>
      <h2 id="snapshot-title">{TEXT.photo.title(record.track_id)}</h2>
      <button class="btn icon" onclick={() => (record = null)} aria-label={TEXT.photo.close}><X size={16} /></button>
    </header>
    <img src={api.snapshotUrl(record.snapshot_filename)} alt={TEXT.photo.title(record.track_id)} />
    <p class="caption">
      {TEXT.photo.caption(shortDate(record.date_str), record.time_str, TEXT.result[resultKind(record)])}
    </p>
  {/if}
</dialog>

<style>
  dialog {
    width: min(720px, calc(100vw - 32px));
    padding: var(--space-5);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    background: var(--surface);
    color: var(--text);
  }
  dialog::backdrop {
    background: var(--backdrop);
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--space-3);
  }
  h2 {
    margin: 0;
    font-size: var(--text-lg);
  }
  .icon {
    padding: 6px;
  }
  img {
    display: block;
    width: 100%;
    max-height: 70vh;
    object-fit: contain;
    background: var(--bg);
    border-radius: var(--radius);
  }
  .caption {
    margin: var(--space-3) 0 0;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }
</style>
