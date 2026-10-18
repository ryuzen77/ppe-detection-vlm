<script lang="ts">
  import { onMount } from 'svelte'
  import { api } from '../../lib/api/client'
  import type { Worker, WorkerTemplate } from '../../lib/api/types'
  import { WORKERS } from '../../lib/messages'
  import { extractApiError } from '../../lib/api/error'
  import {
    validateWorkerForm,
    getWorkerBadge,
    formatWorkerSalutation,
    formatDeleteSchedule,
  } from '../../lib/workers'
  import UserPlus from '@lucide/svelte/icons/user-plus'
  import ShieldAlert from '@lucide/svelte/icons/shield-alert'
  import AlertTriangle from '@lucide/svelte/icons/alert-triangle'
  import Trash2 from '@lucide/svelte/icons/trash-2'
  import Edit2 from '@lucide/svelte/icons/edit-2'
  import UserX from '@lucide/svelte/icons/user-x'
  import UserCheck from '@lucide/svelte/icons/user-check'

  let workers = $state<Worker[]>([])
  let faceReady = $state(true)
  let galleryLimit = $state<{ tested: number; count: number; over: boolean } | null>(null)
  let loading = $state(false)
  let errorMsg = $state('')

  // Modal Tambah Pekerja
  let showAddModal = $state(false)
  let newEmployeeNo = $state('')
  let newName = $state('')
  let newNickname = $state('')
  let newGender = $state<'male' | 'female'>('male')
  let newConsent = $state(false)
  let adding = $state(false)
  let addError = $state('')

  // Modal Ubah Profil
  let editingWorker = $state<Worker | null>(null)
  let editNickname = $state('')
  let editGender = $state<'male' | 'female'>('male')
  let updating = $state(false)
  let updateError = $state('')

  // Modal Konfirmasi Hapus Wajah
  let deleteFaceWorker = $state<Worker | null>(null)
  let deletingFace = $state(false)
  let deleteFaceError = $state('')

  // Modal Konfirmasi Hapus Templat
  let deleteTemplateTarget = $state<{ workerId: number; templateId: number } | null>(null)
  let deletingTemplate = $state(false)
  let deleteTemplateError = $state('')

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

  function openAddModal() {
    newEmployeeNo = ''
    newName = ''
    newNickname = ''
    newGender = 'male'
    newConsent = false
    addError = ''
    showAddModal = true
  }

  async function handleAddWorker(e: Event) {
    e.preventDefault()
    addError = ''
    const valErr = validateWorkerForm({
      employee_no: newEmployeeNo,
      name: newName,
      nickname: newNickname,
      gender: newGender,
      consent: newConsent,
    })
    if (valErr) {
      addError = valErr
      return
    }

    adding = true
    try {
      await api.createWorker({
        employee_no: newEmployeeNo.trim(),
        name: newName.trim(),
        nickname: newNickname.trim(),
        gender: newGender,
        consent: newConsent,
      })
      showAddModal = false
      await loadWorkers()
    } catch (e) {
      addError = extractApiError(e, WORKERS.errAdd)
    } finally {
      adding = false
    }
  }

  function openEditModal(worker: Worker) {
    editingWorker = worker
    editNickname = worker.nickname || ''
    editGender = (worker.gender === 'female' ? 'female' : 'male')
    updateError = ''
  }

  async function handleUpdateWorker(e: Event) {
    e.preventDefault()
    if (!editingWorker) return
    updateError = ''
    if (!editNickname.trim()) {
      updateError = `${WORKERS.fieldNickname} wajib diisi.`
      return
    }

    updating = true
    try {
      await api.updateWorker(editingWorker.id, {
        nickname: editNickname.trim(),
        gender: editGender,
      })
      editingWorker = null
      await loadWorkers()
    } catch (e) {
      updateError = extractApiError(e, WORKERS.errUpdate)
    } finally {
      updating = false
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

  function confirmDeleteFace(worker: Worker) {
    deleteFaceWorker = worker
    deleteFaceError = ''
  }

  async function executeDeleteFace(e: Event) {
    e.preventDefault()
    if (!deleteFaceWorker) return
    deletingFace = true
    deleteFaceError = ''
    try {
      await api.deleteWorkerFace(deleteFaceWorker.id)
      deleteFaceWorker = null
      await loadWorkers()
    } catch (e) {
      deleteFaceError = extractApiError(e, WORKERS.errDeleteFace)
    } finally {
      deletingFace = false
    }
  }

  function confirmDeleteTemplate(workerId: number, templateId: number) {
    deleteTemplateTarget = { workerId, templateId }
    deleteTemplateError = ''
  }

  async function executeDeleteTemplate(e: Event) {
    e.preventDefault()
    if (!deleteTemplateTarget) return
    deletingTemplate = true
    deleteTemplateError = ''
    try {
      await api.deleteWorkerTemplate(deleteTemplateTarget.workerId, deleteTemplateTarget.templateId)
      deleteTemplateTarget = null
      await loadWorkers()
    } catch (e) {
      deleteTemplateError = extractApiError(e, WORKERS.errDeleteTemplate)
    } finally {
      deletingTemplate = false
    }
  }
</script>

<section class="card">
  <div class="header-row">
    <div>
      <h2>{WORKERS.sectionTitle}</h2>
      <p class="subtitle">{WORKERS.sectionSubtitle}</p>
    </div>
    <button class="btn btn-primary" onclick={openAddModal}>
      <UserPlus size={16} />
      {WORKERS.addWorkerBtn}
    </button>
  </div>

  {#if !faceReady}
    <div class="banner banner-warn" role="alert">
      <ShieldAlert size={20} class="banner-icon" />
      <div>
        <p class="banner-title">{WORKERS.faceDisabledBanner}</p>
        <code class="banner-code">{WORKERS.generateKeyHint}</code>
      </div>
    </div>
  {/if}

  {#if galleryLimit?.over}
    <div class="banner banner-danger" role="alert">
      <AlertTriangle size={20} class="banner-icon" />
      <p class="banner-title">{WORKERS.limitOverWarning(galleryLimit.count, galleryLimit.tested)}</p>
    </div>
  {/if}

  {#if errorMsg}
    <div class="error-box" role="alert">{errorMsg}</div>
  {/if}

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
                            onclick={() => confirmDeleteTemplate(worker.id, t.id)}
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
                    onclick={() => openEditModal(worker)}
                  >
                    <Edit2 size={13} />
                  </button>

                  <button
                    class="btn btn-xs {worker.active ? 'btn-deactivate' : 'btn-activate'}"
                    onclick={() => toggleWorkerActive(worker)}
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
                      onclick={() => confirmDeleteFace(worker)}
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
</section>

<!-- Modal Tambah Pekerja -->
{#if showAddModal}
  <div class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-add-title">
    <div class="modal-card">
      <h3 id="modal-add-title">{WORKERS.modalAddTitle}</h3>
      {#if addError}
        <div class="error-box" role="alert">{addError}</div>
      {/if}

      <form class="form-layout" onsubmit={handleAddWorker}>
        <div class="form-group">
          <label for="new-emp-no">{WORKERS.fieldEmployeeNo}</label>
          <input
            id="new-emp-no"
            type="text"
            placeholder={WORKERS.fieldEmployeeNoPlaceholder}
            bind:value={newEmployeeNo}
            disabled={adding}
            required
          />
        </div>

        <div class="form-group">
          <label for="new-name">{WORKERS.fieldName}</label>
          <input
            id="new-name"
            type="text"
            placeholder={WORKERS.fieldNamePlaceholder}
            bind:value={newName}
            disabled={adding}
            required
          />
        </div>

        <div class="form-row">
          <div class="form-group flex-1">
            <label for="new-nickname">{WORKERS.fieldNickname}</label>
            <input
              id="new-nickname"
              type="text"
              placeholder={WORKERS.fieldNicknamePlaceholder}
              bind:value={newNickname}
              disabled={adding}
              required
            />
            <span class="form-hint">{WORKERS.fieldNicknameHint}</span>
          </div>

          <div class="form-group flex-1">
            <label for="new-gender">{WORKERS.fieldGender}</label>
            <select id="new-gender" bind:value={newGender} disabled={adding}>
              <option value="male">{WORKERS.genderMale}</option>
              <option value="female">{WORKERS.genderFemale}</option>
            </select>
          </div>
        </div>

        <div class="consent-box">
          <label class="consent-label">
            <input
              type="checkbox"
              bind:checked={newConsent}
              disabled={adding}
            />
            <span>{WORKERS.fieldConsentLabel}</span>
          </label>
        </div>

        <div class="modal-actions">
          <button
            type="button"
            class="btn"
            onclick={() => showAddModal = false}
            disabled={adding}
          >
            {WORKERS.cancelBtn}
          </button>
          <button
            type="submit"
            class="btn btn-primary"
            disabled={adding || !newConsent}
          >
            {WORKERS.submitBtn}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<!-- Modal Ubah Profil -->
{#if editingWorker}
  <div class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-edit-title">
    <div class="modal-card">
      <h3 id="modal-edit-title">{WORKERS.modalEditTitle} - {editingWorker.employee_no}</h3>
      {#if updateError}
        <div class="error-box" role="alert">{updateError}</div>
      {/if}

      <form class="form-layout" onsubmit={handleUpdateWorker}>
        <div class="form-group">
          <label for="edit-nickname">{WORKERS.fieldNickname}</label>
          <input
            id="edit-nickname"
            type="text"
            placeholder={WORKERS.fieldNicknamePlaceholder}
            bind:value={editNickname}
            disabled={updating}
            required
          />
          <span class="form-hint">{WORKERS.fieldNicknameHint}</span>
        </div>

        <div class="form-group">
          <label for="edit-gender">{WORKERS.fieldGender}</label>
          <select id="edit-gender" bind:value={editGender} disabled={updating}>
            <option value="male">{WORKERS.genderMale}</option>
            <option value="female">{WORKERS.genderFemale}</option>
          </select>
        </div>

        <div class="modal-actions">
          <button
            type="button"
            class="btn"
            onclick={() => editingWorker = null}
            disabled={updating}
          >
            {WORKERS.cancelBtn}
          </button>
          <button
            type="submit"
            class="btn btn-primary"
            disabled={updating || !editNickname.trim()}
          >
            {WORKERS.saveBtn}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

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
            onclick={() => deleteFaceWorker = null}
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
            onclick={() => deleteTemplateTarget = null}
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

  h3 {
    margin: 0 0 var(--space-3);
    font-size: var(--text-md);
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

  .btn-danger {
    background: var(--danger);
    color: var(--surface);
    border: none;
  }

  .btn-danger:hover {
    opacity: 0.9;
  }

  .text-right {
    text-align: right;
  }

  .error-box {
    background: var(--danger-line);
    color: var(--danger);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    margin-bottom: var(--space-3);
  }

  .loading-text, .empty-box {
    padding: var(--space-6);
    text-align: center;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  /* Form & Modal */
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

  .form-layout {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .form-row {
    display: flex;
    gap: var(--space-3);
  }

  .flex-1 {
    flex: 1;
  }

  label {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-muted);
  }

  input[type="text"],
  select {
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface-2);
    color: var(--text);
    font-size: var(--text-sm);
  }

  input[type="text"]:focus,
  select:focus {
    outline: none;
    border-color: var(--primary);
  }

  .form-hint {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .consent-box {
    background: var(--surface-2);
    padding: var(--space-3);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
  }

  .consent-label {
    display: flex;
    align-items: flex-start;
    gap: var(--space-2);
    cursor: pointer;
    font-weight: 400;
    color: var(--text);
    line-height: 1.4;
  }

  .consent-label input[type="checkbox"] {
    margin-top: 3px;
  }

  .del-prompt {
    font-size: var(--text-sm);
    color: var(--text);
    line-height: 1.5;
    margin: 0 0 var(--space-4);
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }
</style>
