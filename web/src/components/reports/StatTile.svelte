<script lang="ts">
  // Satu angka ringkas. Nilai memakai warna teks (bukan warna status); warna
  // status hanya di isi meter, selalu didampingi angka persennya.
  import type { Tone } from '../../lib/gate'
  import { clampPercent } from '../../lib/reports'

  let {
    label,
    value,
    note = '',
    hint = '',
    meter = null,
    tone = 'neutral',
  }: {
    label: string
    value: string
    /** Keterangan kecil yang tampil di bawah angka */
    note?: string
    /** Penjelasan saat kursor diarahkan */
    hint?: string
    /** Persen 0..100 untuk meter; null = tanpa meter */
    meter?: number | null
    tone?: Tone
  } = $props()
</script>

<div class="tile" title={hint || undefined}>
  <span class="label">{label}</span>
  <span class="value">{value}</span>
  {#if meter !== null}
    <span class="meter" aria-hidden="true"
      ><span class="fill tone-{tone}" style:width="{clampPercent(meter)}%"></span></span
    >
  {/if}
  {#if note}<span class="note">{note}</span>{/if}
</div>

<style>
  .tile {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-4);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    min-width: 0;
  }
  .label {
    font-size: var(--text-sm);
    color: var(--text-muted);
  }
  .value {
    font-size: var(--text-xl);
    font-weight: 600;
    color: var(--text);
  }
  .meter {
    height: 6px;
    border-radius: 3px;
    background: var(--surface-3);
    overflow: hidden;
  }
  .fill {
    display: block;
    height: 100%;
    border-radius: 3px;
    background: var(--text-muted);
  }
  .tone-ok {
    background: var(--ok);
  }
  .tone-warn {
    background: var(--warn);
  }
  .tone-danger {
    background: var(--danger);
  }
  .note {
    font-size: var(--text-xs);
    color: var(--text-faint);
  }
</style>
