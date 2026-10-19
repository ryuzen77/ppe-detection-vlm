<script lang="ts">
  import type { Worker } from '../../../lib/api/types'
  import { WORKERS } from '../../../lib/messages'
  import { getWorkerBadge, formatWorkerSalutation } from '../../../lib/workers'
  import Trash2 from '@lucide/svelte/icons/trash-2'
  import Edit2 from '@lucide/svelte/icons/edit-2'
  import UserX from '@lucide/svelte/icons/user-x'
  import UserCheck from '@lucide/svelte/icons/user-check'

  interface Props {
    workers: Worker[]
    loading: boolean
    onEdit: (worker: Worker) => void
    onToggleActive: (worker: Worker) => void
    onDeleteFace: (worker: Worker) => void
    onDeleteTemplate: (workerId: number, templateId: number) => void
  }

  let {
    workers,
    loading,
    onEdit,
    onToggleActive,
    onDeleteFace,
    onDeleteTemplate,
  }: Props = $props()
</script>

{#if loading}
  <p class="loading-text">Memuat data pekerja…</p>
{:else if workers.length === 0}
  <div class="empty-box">
    <p>{WORKERS.emptyList}</p>
  </div>
{:else}
  <div class="table-wrap">
    <table class="workers-table">
      <thead>
        <tr>
          <th>{WORKERS.tableHeaderNo}</th>
          <th>{WORKERS.tableHeaderName}</th>
          <th>{WORKERS.tableHeaderStatus}</th>
          <th>{WORKERS.tableHeaderTemplates}</th>
          <th class="text-right">{WORKERS.tableHeaderAction}</th>
        </tr>
      </thead>
      <tbody>
        {#each workers as worker (worker.id)}
          {@const badge = getWorkerBadge(worker)}
          <tr class:row-inactive={!worker.active}>
            <td class="cell-mono">{worker.employee_no}</td>
            <td>
              <div class="worker-name-box">
                <span class="salutation-name">{formatWorkerSalutation(worker)}</span>
                {#if worker.name !== worker.nickname}
                  <span class="full-name">{worker.name}</span>
                {/if}
              </div>
            </td>
            <td>
              <div class="status-cell">
                <span class="badge badge-{badge.variant}">{badge.label}</span>
                {#if badge.hint}
                  <span class="badge-hint">{badge.hint}</span>
                {/if}
              </div>
            </td>
            <td>
              <div class="templates-cell">
                <span class="template-summary">{WORKERS.photoCount(worker.templates.length)}</span>
                {#if worker.templates.length > 0}
                  <div class="template-chips">
                    {#each worker.templates as t (t.id)}
                      <span class="template-chip">
                        <span class="condition-tag">{t.condition}</span>
                        <button
                          type="button"
                          class="chip-delete-btn"
                          title="{WORKERS.deleteTemplateBtn}"
                          aria-label="{WORKERS.deleteTemplateBtn} {t.condition}"
                          onclick={() => onDeleteTemplate(worker.id, t.id)}
                        >
                          <Trash2 size={12} />
                        </button>
                      </span>
                    {/each}
                  </div>
                {/if}
              </div>
            </td>
            <td class="text-right">
              <div class="action-buttons">
                <button
                  class="btn btn-xs"
                  title="{WORKERS.editBtn}"
                  aria-label="{WORKERS.editBtn}"
                  onclick={() => onEdit(worker)}
                >
                  <Edit2 size={13} />
                </button>

                <button
                  class="btn btn-xs {worker.active ? 'btn-deactivate' : 'btn-activate'}"
                  onclick={() => onToggleActive(worker)}
                >
                  {#if worker.active}
                    <UserX size={13} /> {WORKERS.deactivateBtn}
                  {:else}
                    <UserCheck size={13} /> {WORKERS.activateBtn}
                  {/if}
                </button>

                {#if worker.templates.length > 0}
                  <button
                    class="btn btn-xs tone-danger"
                    title="{WORKERS.deleteFaceBtn}"
                    onclick={() => onDeleteFace(worker)}
                  >
                    <Trash2 size={13} />
                  </button>
                {/if}
              </div>
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

  .workers-table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
  }

  .workers-table th,
  .workers-table td {
    padding: var(--space-3) var(--space-2);
    text-align: left;
    border-bottom: 1px solid var(--border);
  }

  .workers-table th {
    font-weight: 600;
    color: var(--text-muted);
  }

  .row-inactive {
    opacity: 0.65;
  }

  .cell-mono {
    font-family: monospace;
    font-weight: 600;
  }

  .worker-name-box {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .salutation-name {
    font-weight: 500;
    color: var(--text);
  }

  .full-name {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .status-cell {
    display: flex;
    flex-direction: column;
    gap: 4px;
    align-items: flex-start;
  }

  .badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: var(--radius-full, 9999px);
    font-size: var(--text-xs);
    font-weight: 600;
  }

  .badge-ok {
    background: var(--ok-line);
    color: var(--ok);
  }

  .badge-warn {
    background: var(--warn-line);
    color: var(--warn);
  }

  .badge-muted {
    background: var(--surface-2);
    color: var(--text-muted);
  }

  .badge-hint {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .templates-cell {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .template-summary {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .template-chips {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }

  .template-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    padding: 2px 6px;
    border-radius: var(--radius-sm);
    font-size: var(--text-xs);
  }

  .chip-delete-btn {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    color: var(--text-muted);
    display: flex;
    align-items: center;
  }

  .chip-delete-btn:hover {
    color: var(--danger);
  }

  .action-buttons {
    display: flex;
    gap: var(--space-1);
    justify-content: flex-end;
    align-items: center;
  }

  .btn-xs {
    padding: 4px 8px;
    font-size: var(--text-xs);
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }

  .btn-deactivate {
    color: var(--text-muted);
  }

  .btn-activate {
    color: var(--ok);
  }

  .tone-danger {
    color: var(--danger);
    border-color: var(--danger-line);
  }

  .tone-danger:hover {
    background: var(--danger-line);
  }

  .text-right {
    text-align: right;
  }

  .loading-text, .empty-box {
    padding: var(--space-6);
    text-align: center;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
</style>
