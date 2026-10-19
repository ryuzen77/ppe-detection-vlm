<script lang="ts">
  import type { Worker } from '../../../lib/api/types'
  import { WORKERS } from '../../../lib/messages'
  import { api } from '../../../lib/api/client'
  import { extractApiError } from '../../../lib/api/error'

  interface Props {
    deleteFaceWorker: Worker | null
    deleteTemplateTarget: { workerId: number; templateId: number } | null
    onClose: () => void
    onDeleted: () => void
  }

  let { deleteFaceWorker, deleteTemplateTarget, onClose, onDeleted }: Props = $props()

  let deletingFace = $state(false)
  let deleteFaceError = $state('')
  let deletingTemplate = $state(false)
  let deleteTemplateError = $state('')

  $effect(() => {
    if (deleteFaceWorker) {
      deleteFaceError = ''
    }
  })

  $effect(() => {
    if (deleteTemplateTarget) {
      deleteTemplateError = ''
    }
  })

  async function executeDeleteFace(e: Event) {
    e.preventDefault()
    if (!deleteFaceWorker) return
    deletingFace = true
    deleteFaceError = ''
    try {
      await api.deleteWorkerFace(deleteFaceWorker.id)
      onDeleted()
    } catch (e) {
      deleteFaceError = extractApiError(e, WORKERS.errDeleteFace)
    } finally {
      deletingFace = false
    }
  }

  async function executeDeleteTemplate(e: Event) {
    e.preventDefault()
    if (!deleteTemplateTarget) return
    deletingTemplate = true
    deleteTemplateError = ''
    try {
      await api.deleteWorkerTemplate(deleteTemplateTarget.workerId, deleteTemplateTarget.templateId)
      onDeleted()
    } catch (e) {
      deleteTemplateError = extractApiError(e, WORKERS.errDeleteTemplate)
    } finally {
      deletingTemplate = false
    }
  }
</script>

<!-- Modal Konfirmasi Hapus Wajah -->
{#if deleteFaceWorker}
  <div class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-del-face-title">
    <div class="modal-card">
      <h3 id="modal-del-face-title">{WORKERS.confirmDeleteFaceTitle} - {deleteFaceWorker.name}</h3>
      <p class="del-prompt">{WORKERS.confirmDeleteFaceMsg}</p>
      {#if deleteFaceError}
        <div class="error-box" role="alert">{deleteFaceError}</div>
      {/if}

      <form onsubmit={executeDeleteFace}>
        <div class="modal-actions">
          <button
            type="button"
            class="btn"
            onclick={onClose}
            disabled={deletingFace}
          >
            {WORKERS.cancelBtn}
          </button>
          <button
            type="submit"
            class="btn btn-danger"
            disabled={deletingFace}
          >
            {WORKERS.deleteFaceBtn}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<!-- Modal Konfirmasi Hapus Templat -->
{#if deleteTemplateTarget}
  <div class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-del-tpl-title">
    <div class="modal-card modal-card-sm">
      <h3 id="modal-del-tpl-title">{WORKERS.confirmDeleteTemplateTitle}</h3>
      <p class="del-prompt">{WORKERS.confirmDeleteTemplateMsg}</p>
      {#if deleteTemplateError}
        <div class="error-box" role="alert">{deleteTemplateError}</div>
      {/if}

      <form onsubmit={executeDeleteTemplate}>
        <div class="modal-actions">
          <button
            type="button"
            class="btn"
            onclick={onClose}
            disabled={deletingTemplate}
          >
            {WORKERS.cancelBtn}
          </button>
          <button
            type="submit"
            class="btn btn-danger"
            disabled={deletingTemplate}
          >
            {WORKERS.deleteTemplateBtn}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.65);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-4);
    z-index: 100;
  }

  .modal-card {
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    padding: var(--space-6);
    width: 100%;
    max-width: 520px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
  }

  .modal-card-sm {
    max-width: 400px;
  }

  h3 {
    margin: 0 0 var(--space-3);
    font-size: var(--text-md);
    font-weight: 600;
  }

  .del-prompt {
    font-size: var(--text-sm);
    color: var(--text);
    line-height: 1.5;
    margin: 0 0 var(--space-4);
  }

  .error-box {
    background: var(--danger-line);
    color: var(--danger);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    margin-bottom: var(--space-3);
  }

  .btn-danger {
    background: var(--danger);
    color: var(--surface);
    border: none;
  }

  .btn-danger:hover {
    opacity: 0.9;
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }
</style>
