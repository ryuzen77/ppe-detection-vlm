<script lang="ts">
  import type { Worker, TemplateCondition } from '../../../lib/api/types'
  import { WORKERS } from '../../../lib/messages'
  import { api } from '../../../lib/api/client'
  import { extractApiError } from '../../../lib/api/error'
  import { keepEnrollmentHold } from '../../../lib/enrollment'
  import {
    TEMPLATE_CONDITIONS,
    getConditionLabel,
    hasTemplateCondition,
    formatTemplateQuality,
  } from '../../../lib/workers'
  import Camera from '@lucide/svelte/icons/camera'
  import LoaderCircle from '@lucide/svelte/icons/loader-circle'

  interface Props {
    worker: Worker | null
    onClose: () => void
    onSaved: () => void
  }

  let { worker, onClose, onSaved }: Props = $props()

  let selectedCondition = $state<TemplateCondition>('bare')
  let taking = $state(false)
  let photoError = $state('')
  let photoSuccess = $state('')
  let streamKey = $state(Date.now())

  $effect(() => {
    if (worker) {
      photoError = ''
      photoSuccess = ''
      taking = false
      streamKey = Date.now()
      // Pilih kondisi pertama yang belum ada
      const available = TEMPLATE_CONDITIONS.find((c) => !hasTemplateCondition(worker, c))
      selectedCondition = available || 'bare'
    }
  })

  // T75: gerbang jeda selama modal terbuka, supaya orang yang difoto tidak langsung diperiksa
  $effect(() => {
    if (!worker) return
    return keepEnrollmentHold(api, () => (photoError = WORKERS.errEnrollmentHold))
  })

  async function handleTakePhoto() {
    if (!worker) return
    photoError = ''
    photoSuccess = ''
    taking = true
    try {
      const res = await api.addWorkerTemplate(worker.id, selectedCondition)
      photoSuccess = `${WORKERS.takePhotoSuccess} (${formatTemplateQuality(res.quality)})`
      setTimeout(() => {
        onSaved()
      }, 1000)
    } catch (e) {
      photoError = extractApiError(e, WORKERS.errTakePhoto)
    } finally {
      taking = false
    }
  }
</script>

{#if worker}
  <div class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-photo-title">
    <div class="modal-card">
      <div class="modal-header">
        <h3 id="modal-photo-title">
          {WORKERS.modalPhotoTitle} — {worker.name}
        </h3>
        <span class="emp-badge">{worker.employee_no}</span>
      </div>
      <p class="subtitle">{WORKERS.modalPhotoSubtitle}</p>

      <div class="camera-preview-box">
        <div class="preview-header">
          <Camera size={14} />
          <span>{WORKERS.cameraPreviewTitle}</span>
        </div>
        <div class="video-container">
          <img src="{api.streamUrl()}?t={streamKey}" alt="{WORKERS.cameraPreviewTitle}" class="stream-img" />
          <div class="target-guide" aria-hidden="true"></div>
        </div>
        <span class="preview-hint">{WORKERS.cameraPreviewHint}</span>
        <span class="preview-hint">{WORKERS.enrollmentHoldHint}</span>
      </div>

      <div class="form-group">
        <label for="condition-options">{WORKERS.conditionLabel}</label>
        <div id="condition-options" class="conditions-grid">
          {#each TEMPLATE_CONDITIONS as cond}
            {@const alreadyHas = hasTemplateCondition(worker, cond)}
            <label class="condition-card" class:selected={selectedCondition === cond}>
              <input
                type="radio"
                name="condition"
                value={cond}
                bind:group={selectedCondition}
                disabled={taking}
              />
              <span class="condition-title">{getConditionLabel(cond)}</span>
              {#if alreadyHas}
                <span class="already-badge">{WORKERS.conditionAlreadyAdded}</span>
              {/if}
            </label>
          {/each}
        </div>
      </div>

      {#if photoError}
        <div class="error-box" role="alert">{photoError}</div>
      {/if}

      {#if photoSuccess}
        <div class="success-box" role="status">{photoSuccess}</div>
      {/if}

      <div class="modal-actions">
        <button
          type="button"
          class="btn"
          onclick={onClose}
          disabled={taking}
        >
          {WORKERS.cancelBtn}
        </button>
        <button
          type="button"
          class="btn btn-primary"
          onclick={handleTakePhoto}
          disabled={taking}
        >
          {#if taking}
            <span class="spin"><LoaderCircle size={14} /></span>
            {WORKERS.takingPhoto}
          {:else}
            <Camera size={14} />
            {WORKERS.takePhotoBtn}
          {/if}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: var(--backdrop);
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
    max-width: 540px;
    box-shadow: 0 10px 25px var(--backdrop);
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    margin-bottom: var(--space-1);
  }

  h3 {
    margin: 0;
    font-size: var(--text-md);
    font-weight: 600;
    color: var(--text);
  }

  .emp-badge {
    font-family: monospace;
    font-size: var(--text-xs);
    font-weight: 600;
    padding: 2px 6px;
    border-radius: var(--radius-sm);
    background: var(--surface-2);
    border: 1px solid var(--border);
    color: var(--text-muted);
  }

  .subtitle {
    margin: 0 0 var(--space-4);
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .camera-preview-box {
    margin-bottom: var(--space-4);
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .preview-header {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-muted);
  }

  .video-container {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    background: var(--bg);
    border-radius: var(--radius-md);
    overflow: hidden;
    border: 1px solid var(--border);
  }

  .stream-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .target-guide {
    position: absolute;
    inset: 15% 30%;
    border: 2px dashed var(--border-strong);
    border-radius: var(--radius-full, 9999px);
    pointer-events: none;
  }

  .preview-hint {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin-bottom: var(--space-4);
  }

  label {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-muted);
  }

  .conditions-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: var(--space-2);
  }

  .condition-card {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: var(--surface-2);
    cursor: pointer;
    font-size: var(--text-xs);
    transition: border-color 0.15s, background 0.15s;
  }

  .condition-card input[type="radio"] {
    display: none;
  }

  .condition-card.selected {
    border-color: var(--primary);
    background: var(--surface);
  }

  .condition-title {
    font-weight: 500;
    color: var(--text);
  }

  .already-badge {
    font-size: 10px;
    color: var(--text-muted);
  }

  .error-box {
    background: var(--danger-line);
    color: var(--danger);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    margin-bottom: var(--space-3);
  }

  .success-box {
    background: var(--ok-line);
    color: var(--ok);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    margin-bottom: var(--space-3);
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
  }

  .spin {
    display: inline-flex;
    animation: spin 1.2s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
