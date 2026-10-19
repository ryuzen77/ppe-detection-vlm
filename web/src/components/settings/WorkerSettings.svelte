<script lang="ts">
  import { onMount } from 'svelte'
  import { api } from '../../lib/api/client'
  import type { Worker } from '../../lib/api/types'
  import { WORKERS } from '../../lib/messages'
  import { extractApiError } from '../../lib/api/error'
  import UserPlus from '@lucide/svelte/icons/user-plus'
  import ShieldAlert from '@lucide/svelte/icons/shield-alert'
  import AlertTriangle from '@lucide/svelte/icons/alert-triangle'
  import WorkerTable from './workers/WorkerTable.svelte'
  import WorkerAddModal from './workers/WorkerAddModal.svelte'
  import WorkerEditModal from './workers/WorkerEditModal.svelte'
  import WorkerDeleteDialog from './workers/WorkerDeleteDialog.svelte'
  import WorkerPhotoModal from './workers/WorkerPhotoModal.svelte'

  let workers = $state<Worker[]>([])
  let faceReady = $state(true)
  let galleryLimit = $state<{ tested: number; count: number; over: boolean } | null>(null)
  let loading = $state(false)
  let errorMsg = $state('')

  let showAddModal = $state(false)
  let editingWorker = $state<Worker | null>(null)
  let photoWorker = $state<Worker | null>(null)
  let deleteFaceWorker = $state<Worker | null>(null)
  let deleteTemplateTarget = $state<{ workerId: number; templateId: number } | null>(null)

  onMount(() => {
    loadWorkers()
  })

  async function loadWorkers() {
    loading = true
    errorMsg = ''
    try {
      const res = await api.workers()
      workers = res.workers
      faceReady = res.face_ready
      galleryLimit = res.limit
    } catch (e) {
      errorMsg = extractApiError(e, WORKERS.errLoad)
    } finally {
      loading = false
    }
  }

  async function toggleWorkerActive(worker: Worker) {
    try {
      if (worker.active) {
        await api.deactivateWorker(worker.id)
      } else {
        await api.activateWorker(worker.id)
      }
      await loadWorkers()
    } catch (e) {
      errorMsg = extractApiError(e, WORKERS.errStatus)
    }
  }
</script>

<section class="card">
  <div class="header-row">
    <div>
      <h2>{WORKERS.sectionTitle}</h2>
      <p class="subtitle">{WORKERS.sectionSubtitle}</p>
    </div>
    <button class="btn btn-primary" onclick={() => showAddModal = true}>
      <UserPlus size={16} />
      {WORKERS.addWorkerBtn}
    </button>
  </div>

  {#if !faceReady}
    <div class="banner banner-warn" role="alert">
      <span class="banner-icon"><ShieldAlert size={20} /></span>
      <div>
        <p class="banner-title">{WORKERS.faceDisabledBanner}</p>
        <code class="banner-code">{WORKERS.generateKeyHint}</code>
      </div>
    </div>
  {/if}

  {#if galleryLimit?.over}
    <div class="banner banner-danger" role="alert">
      <span class="banner-icon"><AlertTriangle size={20} /></span>
      <p class="banner-title">{WORKERS.limitOverWarning(galleryLimit.count, galleryLimit.tested)}</p>
    </div>
  {/if}

  {#if errorMsg}
    <div class="error-box" role="alert">{errorMsg}</div>
  {/if}

  <WorkerTable
    {workers}
    {loading}
    onEdit={(w) => editingWorker = w}
    onAddPhoto={(w) => photoWorker = w}
    onToggleActive={toggleWorkerActive}
    onDeleteFace={(w) => deleteFaceWorker = w}
    onDeleteTemplate={(wId, tId) => deleteTemplateTarget = { workerId: wId, templateId: tId }}
  />
</section>

<WorkerAddModal
  show={showAddModal}
  onClose={() => showAddModal = false}
  onSaved={async () => {
    showAddModal = false
    await loadWorkers()
  }}
/>

<WorkerEditModal
  worker={editingWorker}
  onClose={() => editingWorker = null}
  onSaved={async () => {
    editingWorker = null
    await loadWorkers()
  }}
/>

<WorkerPhotoModal
  worker={photoWorker}
  onClose={() => photoWorker = null}
  onSaved={async () => {
    photoWorker = null
    await loadWorkers()
  }}
/>

<WorkerDeleteDialog
  {deleteFaceWorker}
  {deleteTemplateTarget}
  onClose={() => {
    deleteFaceWorker = null
    deleteTemplateTarget = null
  }}
  onDeleted={async () => {
    deleteFaceWorker = null
    deleteTemplateTarget = null
    await loadWorkers()
  }}
/>

<style>
  .card {
    padding: var(--space-6);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    color: var(--text);
  }

  .header-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-4);
    margin-bottom: var(--space-4);
    flex-wrap: wrap;
  }

  h2 {
    margin: 0 0 var(--space-1);
    font-size: var(--text-lg);
    font-weight: 600;
  }

  .subtitle {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  .banner {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    border-radius: var(--radius-md);
    margin-bottom: var(--space-4);
    font-size: var(--text-sm);
  }

  .banner-warn {
    background: var(--warn-line);
    color: var(--warn);
    border: 1px solid var(--warn);
  }

  .banner-danger {
    background: var(--danger-line);
    color: var(--danger);
    border: 1px solid var(--danger);
  }

  .banner-icon {
    flex-shrink: 0;
    margin-top: 2px;
  }

  .banner-title {
    margin: 0 0 var(--space-1);
    font-weight: 500;
  }

  .banner-code {
    display: inline-block;
    background: var(--surface);
    padding: 2px 6px;
    border-radius: var(--radius-sm);
    font-family: monospace;
    font-size: var(--text-xs);
    color: var(--text);
  }

  .error-box {
    background: var(--danger-line);
    color: var(--danger);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    margin-bottom: var(--space-3);
  }
</style>
