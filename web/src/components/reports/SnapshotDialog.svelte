<script lang="ts">
  // Foto bukti ukuran penuh. Terbuka saat `record` diisi; ditutup (Esc, tombol,
  // klik latar) → `record` kembali null.
  import X from '@lucide/svelte/icons/x'
  import { api } from '../../lib/api/client'
  import type { ReportRecord } from '../../lib/api/types'
  import { REPORTS as TEXT, shortDate } from '../../lib/messages'
  import { resultKind } from '../../lib/reports'
  import ModalDialog from '../ModalDialog.svelte'

  let { record = $bindable(null) }: { record?: ReportRecord | null } = $props()
</script>

<ModalDialog
  open={record !== null}
  onclose={() => (record = null)}
  labelledby="snapshot-title"
  size="lg"
  closeOnBackdrop
>
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
</ModalDialog>

<style>
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
