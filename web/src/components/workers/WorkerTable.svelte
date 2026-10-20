<script lang="ts">
  // Daftar pekerja (T79): satu baris per orang, klik untuk detail. Tindakan (ubah, foto,
  // nonaktifkan, hapus wajah) ada di panel detail supaya tabel tetap terbaca selebar layar.
  import type { Worker } from '../../lib/api/types'
  import { WORKERS, WORKERS_PAGE } from '../../lib/messages'
  import { faceStatus, formatShortDateTime, formatWorkerSalutation, getWorkerBadge, orgSummary } from '../../lib/workers'

  interface Props {
    workers: Worker[]
    loading: boolean
    selectedId: number | null
    onSelect: (worker: Worker) => void
  }

  let { workers, loading, selectedId, onSelect }: Props = $props()
</script>

{#if loading && workers.length === 0}
  <p class="empty">{WORKERS.loading}</p>
{:else if workers.length === 0}
  <p class="empty">{WORKERS_PAGE.noMatch}</p>
{:else}
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>{WORKERS_PAGE.colNo}</th>
          <th>{WORKERS_PAGE.colName}</th>
          <th>{WORKERS_PAGE.colOrg}</th>
          <th>{WORKERS_PAGE.colFace}</th>
          <th>{WORKERS_PAGE.colLastSeen}</th>
          <th>{WORKERS_PAGE.colStatus}</th>
        </tr>
      </thead>
      <tbody>
        {#each workers as worker (worker.id)}
          {@const face = faceStatus(worker)}
          {@const badge = getWorkerBadge(worker)}
          <tr class:selected={worker.id === selectedId} class:inactive={!worker.active}>
            <td class="mono">{worker.employee_no}</td>
            <td>
              <button type="button" class="name" onclick={() => onSelect(worker)} aria-current={worker.id === selectedId ? 'true' : undefined}>
                <span class="primary">{worker.name}</span>
                <span class="secondary">{formatWorkerSalutation(worker)}</span>
              </button>
            </td>
            <td class="muted">{orgSummary(worker)}</td>
            <td><span class="tag tag-{face.tone}">{face.label}</span></td>
            <td class="muted">
              {#if worker.last_seen}
                <span class="mono">{formatShortDateTime(worker.last_seen.at)}</span>
                <span class="seen" class:fail={!worker.last_seen.is_complete}>
                  {worker.last_seen.is_complete ? WORKERS_PAGE.lastSeenPass : WORKERS_PAGE.lastSeenFail}
                </span>
              {:else}
                {WORKERS_PAGE.lastSeenNever}
              {/if}
            </td>
            <td>
              <span class="tag tag-{badge.variant}" title={badge.hint}>{badge.label}</span>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .table-wrap {
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
  }
  th,
  td {
    padding: var(--space-3);
    text-align: left;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }
  th {
    font-weight: 600;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  tbody tr:hover {
    background: var(--surface-2);
  }
  tr.selected {
    background: var(--accent-soft);
  }
  tr.inactive td {
    color: var(--text-faint);
  }
  .name {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    padding: 0;
    border: 0;
    background: none;
    cursor: pointer;
    text-align: left;
  }
  .name .primary {
    font-weight: 600;
    color: var(--text);
  }
  .name:hover .primary {
    color: var(--accent);
  }
  .name .secondary,
  .muted {
    color: var(--text-muted);
  }
  .name .secondary {
    font-size: var(--text-xs);
  }
  .seen {
    margin-left: var(--space-1);
    color: var(--ok);
  }
  .seen.fail {
    color: var(--danger);
  }
  .empty {
    padding: var(--space-8) var(--space-4);
    text-align: center;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
</style>
