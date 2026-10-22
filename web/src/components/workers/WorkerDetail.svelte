<script lang="ts">
  // Detail satu pekerja (T79): data diri, foto wajah, riwayat pemeriksaan, dan semua tindakannya.
  import type { Worker } from '../../lib/api/types'
  import { WORKERS, WORKERS_PAGE as TEXT } from '../../lib/messages'
  import {
    faceStatus,
    formatDeleteSchedule,
    formatWorkerSalutation,
    getConditionLabel,
    getWorkerBadge,
    orgSummary,
    templateGroups,
  } from '../../lib/workers'
  import WorkerHistory from './WorkerHistory.svelte'
  import Camera from '@lucide/svelte/icons/camera'
  import Edit2 from '@lucide/svelte/icons/edit-2'
  import Trash2 from '@lucide/svelte/icons/trash-2'
  import UserCheck from '@lucide/svelte/icons/user-check'
  import UserX from '@lucide/svelte/icons/user-x'
  import X from '@lucide/svelte/icons/x'

  interface Props {
    worker: Worker
    onClose: () => void
    onEdit: (w: Worker) => void
    onEnroll: (w: Worker) => void
    onToggleActive: (w: Worker) => void
    onDeleteFace: (w: Worker) => void
    onDeleteTemplate: (workerId: number, templateId: number) => void
  }

  let { worker, onClose, onEdit, onEnroll, onToggleActive, onDeleteFace, onDeleteTemplate }: Props = $props()

  const badge = $derived(getWorkerBadge(worker))
  const face = $derived(faceStatus(worker))
</script>

<aside class="detail" aria-labelledby="worker-detail-title">
  <header>
    <div>
      <p class="number mono">{worker.employee_no}</p>
      <h2 id="worker-detail-title">{worker.name}</h2>
      {#if worker.department || worker.company}<p class="org">{orgSummary(worker)}</p>{/if}
    </div>
    <button type="button" class="icon" onclick={onClose} aria-label={TEXT.closeDetail} title={TEXT.closeDetail}
      ><X size={18} /></button
    >
  </header>

  <section>
    <div class="section-head">
      <h3>{TEXT.sectionProfile}</h3>
      <button type="button" class="btn" onclick={() => onEdit(worker)}><Edit2 size={14} /> {WORKERS.editBtn}</button>
    </div>
    <dl>
      <dt>{TEXT.profileNickname}</dt>
      <dd>{formatWorkerSalutation(worker)}</dd>
      <dt>{TEXT.colStatus}</dt>
      <dd>
        <span class="tag tag-{badge.variant}">{badge.label}</span>{#if badge.hint}<span class="hint">{badge.hint}</span
          >{/if}
      </dd>
      <dt>{TEXT.profileConsent}</dt>
      <dd>{TEXT.consentText(formatDeleteSchedule(worker.consent.at), worker.consent.by)}</dd>
    </dl>
  </section>

  <section>
    <div class="section-head">
      <h3>{TEXT.sectionFace}</h3>
      {#if worker.active}
        <button type="button" class="btn btn-primary" onclick={() => onEnroll(worker)}
          ><Camera size={14} /> {TEXT.enrollBtn}</button
        >
      {/if}
    </div>
    <p class="face">
      <span class="tag tag-{face.tone}">{face.label}</span>
      {#if worker.templates.length}
        {#each templateGroups(worker.templates) as g (g.label)}<span class="hint">{g.label} {g.count}</span>{/each}
      {/if}
    </p>
    {#if worker.templates.length}
      <ul class="templates">
        {#each worker.templates as t (t.id)}
          <li>
            {getConditionLabel(t.condition)}
            <button
              type="button"
              class="icon small"
              onclick={() => onDeleteTemplate(worker.id, t.id)}
              aria-label="{WORKERS.deleteTemplateBtn} {getConditionLabel(t.condition)}"
              title={WORKERS.deleteTemplateBtn}><Trash2 size={12} /></button
            >
          </li>
        {/each}
      </ul>
      <button type="button" class="btn danger" onclick={() => onDeleteFace(worker)}
        ><Trash2 size={14} /> {WORKERS.deleteFaceBtn}</button
      >
    {/if}
  </section>

  <section>
    <h3>{TEXT.sectionHistory}</h3>
    <WorkerHistory workerId={worker.id} />
  </section>

  <footer>
    <button type="button" class="btn" onclick={() => onToggleActive(worker)}>
      {#if worker.active}<UserX size={14} /> {WORKERS.deactivateBtn}{:else}<UserCheck size={14} />
        {WORKERS.activateBtn}{/if}
    </button>
  </footer>
</aside>

<style>
  .detail {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-5);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-3);
  }
  .number {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
  h2 {
    margin: 2px 0;
    font-size: var(--text-lg);
  }
  .org {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
  h3 {
    margin: 0;
    font-size: var(--text-md);
  }
  section {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding-top: var(--space-4);
    border-top: 1px solid var(--border);
  }
  .section-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-3);
  }
  dl {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: var(--space-2) var(--space-4);
    margin: 0;
    font-size: var(--text-sm);
  }
  dt {
    color: var(--text-muted);
  }
  dd {
    margin: 0;
  }
  .face {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
  }
  .hint {
    margin-left: var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .templates {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .templates li {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    padding: 2px 4px 2px 8px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--surface-2);
    font-size: var(--text-xs);
  }
  .icon {
    display: inline-grid;
    place-items: center;
    width: 30px;
    height: 30px;
    padding: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
  }
  .icon.small {
    width: 20px;
    height: 20px;
    border: 0;
  }
  .icon:hover {
    color: var(--text);
  }
  .icon.small:hover {
    color: var(--danger);
  }
  .danger {
    align-self: flex-start;
    color: var(--danger);
    border-color: var(--danger-line);
  }
  footer {
    padding-top: var(--space-4);
    border-top: 1px solid var(--border);
  }
</style>
