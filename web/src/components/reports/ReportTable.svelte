<script lang="ts">
  // Tabel riwayat pemeriksaan. Warna status selalu berpasangan dengan ikon &
  // teks; APD per item memakai penilaian yang sama dengan checklist Monitoring.
  import Check from '@lucide/svelte/icons/check'
  import CircleCheck from '@lucide/svelte/icons/circle-check'
  import CircleQuestionMark from '@lucide/svelte/icons/circle-question-mark'
  import CircleX from '@lucide/svelte/icons/circle-x'
  import ImageOff from '@lucide/svelte/icons/image-off'
  import X from '@lucide/svelte/icons/x'
  import { api } from '../../lib/api/client'
  import type { PpeItem, ReportRecord } from '../../lib/api/types'
  import { REPORTS as TEXT, seconds, shortDate } from '../../lib/messages'
  import { assessItem } from '../../lib/ppe'
  import { RESULT_TONE, resultKind, sourceText, type ResultKind } from '../../lib/reports'
  import { REPORTS } from '../../lib/settings'
  import PpeIcon from '../PpeIcon.svelte'

  let { records, items, onOpen }: {
    records: ReportRecord[]
    /** Katalog APD; tiap baris hanya menampilkan item yang dinilai pada pemeriksaan itu */
    items: PpeItem[]
    onOpen: (record: ReportRecord) => void
  } = $props()

  const RESULT_ICON: Record<ResultKind, typeof CircleCheck> = {
    passed: CircleCheck,
    denied: CircleX,
    unverified: CircleQuestionMark,
  }

  const judged = (rec: ReportRecord) => items.filter((i) => rec.items && i.key in rec.items)
</script>

<div class="scroll">
  <table aria-label={TEXT.table.ariaLabel}>
    <thead>
      <tr>
        <th>{TEXT.table.photo}</th>
        <th>{TEXT.table.time}</th>
        <th>{TEXT.table.worker}</th>
        <th>{TEXT.table.result}</th>
        <th>{TEXT.table.ppe}</th>
        <th>{TEXT.table.source}</th>
        <th class="num">{TEXT.table.duration}</th>
      </tr>
    </thead>
    <tbody>
      {#each records as rec (rec.id)}
        {@const kind = resultKind(rec)}
        {@const Icon = RESULT_ICON[kind]}
        {@const src = sourceText(rec.inference_source)}
        <tr>
          <td>
            {#if rec.snapshot_filename}
              <button class="thumb" onclick={() => onOpen(rec)} aria-label={TEXT.table.openPhoto(rec.track_id)}
                      style:--thumb="{REPORTS.thumbPx}px">
                <img src={api.snapshotUrl(rec.snapshot_filename)} alt="" loading="lazy" />
              </button>
            {:else}
              <span class="thumb none" title={TEXT.table.noPhoto} style:--thumb="{REPORTS.thumbPx}px">
                <ImageOff size={16} aria-label={TEXT.table.noPhoto} />
              </span>
            {/if}
          </td>
          <td class="time">
            <span>{shortDate(rec.date_str)}</span>
            <span class="mono sub">{rec.time_str}</span>
          </td>
          <td class="mono">{TEXT.table.worker_id(rec.track_id)}</td>
          <td>
            <span class="result tone-{RESULT_TONE[kind]}">
              <Icon size={16} strokeWidth={2.25} aria-hidden="true" />{TEXT.result[kind]}
            </span>
            {#if kind === 'denied' && rec.missing_items.length}
              <span class="sub">{TEXT.table.missing(rec.missing_items)}</span>
            {/if}
          </td>
          <td>
            <ul class="ppe">
              {#each judged(rec) as item (item.key)}
                {@const a = assessItem(item, rec.items[item.key])}
                <li class="st-{a.status}" title="{item.label}: {a.text}">
                  <PpeIcon name={item.icon_name} size={16} />
                  {#if a.status === 'ok'}<Check size={12} strokeWidth={3} aria-hidden="true" />
                  {:else}<X size={12} strokeWidth={3} aria-hidden="true" />{/if}
                  <span class="sr">{item.label}: {a.text}</span>
                </li>
              {/each}
            </ul>
          </td>
          <td class="source role-{src.role}">{src.text}</td>
          <td class="num mono">{seconds(rec.inference_time_ms)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .scroll {
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
  }
  th {
    text-align: left;
    font-weight: 500;
    color: var(--text-muted);
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--border-strong);
    white-space: nowrap;
  }
  td {
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--border);
    vertical-align: middle;
  }
  tbody tr:hover {
    background: var(--surface-2);
  }
  .num {
    text-align: right;
    white-space: nowrap;
  }
  .thumb {
    display: grid;
    place-items: center;
    width: var(--thumb);
    height: var(--thumb);
    padding: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--surface-2);
    overflow: hidden;
    color: var(--text-faint);
  }
  button.thumb {
    cursor: zoom-in;
  }
  button.thumb:hover {
    border-color: var(--accent);
  }
  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .time {
    white-space: nowrap;
  }
  .time span {
    display: block;
  }
  .sub {
    display: block;
    font-size: var(--text-xs);
    color: var(--text-muted);
  }
  .result {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    font-weight: 600;
    white-space: nowrap;
  }
  .tone-ok {
    color: var(--ok);
  }
  .tone-danger {
    color: var(--danger);
  }
  .tone-warn {
    color: var(--warn);
  }
  .ppe {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .ppe li {
    display: inline-flex;
    align-items: center;
    gap: 1px;
    padding: 2px 4px;
    border-radius: var(--radius-sm);
  }
  .st-ok {
    color: var(--ok);
    background: var(--ok-soft);
  }
  .st-missing {
    color: var(--danger);
    background: var(--danger-soft);
  }
  .st-pending {
    color: var(--warn);
    background: var(--warn-soft);
  }
  .source {
    white-space: nowrap;
    color: var(--text-muted);
  }
  .role-cadangan,
  .role-gangguan {
    color: var(--warn);
  }
  .sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
</style>
