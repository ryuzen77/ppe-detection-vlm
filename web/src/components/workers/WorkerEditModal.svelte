<script lang="ts">
  import type { OrgEntry, UpdateWorkerRequest, Worker } from '../../lib/api/types'
  import { WORKERS } from '../../lib/messages'
  import { api } from '../../lib/api/client'
  import { extractApiError } from '../../lib/api/error'
  import OrgFields from './OrgFields.svelte'

  interface Props {
    worker: Worker | null
    departments: OrgEntry[]
    companies: OrgEntry[]
    onClose: () => void
    onSaved: () => void
  }

  let { worker, departments, companies, onClose, onSaved }: Props = $props()

  let employeeNo = $state('')
  let departmentId = $state<number | null>(null)
  let companyId = $state<number | null>(null)
  let nickname = $state('')
  let gender = $state<'male' | 'female'>('male')
  let updating = $state(false)
  let updateError = $state('')

  $effect(() => {
    if (worker) {
      employeeNo = worker.employee_no
      departmentId = worker.department?.id ?? null
      companyId = worker.company?.id ?? null
      nickname = worker.nickname || ''
      gender = worker.gender === 'female' ? 'female' : 'male'
      updateError = ''
    }
  })

  /** Hanya kolom yang ada di server ini (T79) & nomor yang benar-benar diganti yang dikirim. */
  function changes(w: Worker): UpdateWorkerRequest {
    const body: UpdateWorkerRequest = { nickname: nickname.trim(), gender }
    const number = employeeNo.trim()
    if (number && number !== w.employee_no) body.employee_no = number
    if (departments.length) body.department_id = departmentId
    if (companyId !== null) body.company_id = companyId
    return body
  }

  async function handleUpdateWorker(e: Event) {
    e.preventDefault()
    if (!worker) return
    updateError = ''
    if (!nickname.trim()) {
      updateError = WORKERS.fieldRequired(WORKERS.fieldNickname)
      return
    }

    updating = true
    try {
      await api.updateWorker(worker.id, changes(worker))
      onSaved()
    } catch (e) {
      updateError = extractApiError(e, WORKERS.errUpdate)
    } finally {
      updating = false
    }
  }
</script>

{#if worker}
  <div class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-edit-title">
    <div class="modal-card">
      <h3 id="modal-edit-title">{WORKERS.modalEditTitle} — {worker.name}</h3>
      {#if updateError}
        <div class="error-box" role="alert">{updateError}</div>
      {/if}

      <form class="form-layout" onsubmit={handleUpdateWorker}>
        <div class="form-group">
          <label for="edit-emp-no">{WORKERS.fieldEmployeeNo}</label>
          <input id="edit-emp-no" type="text" bind:value={employeeNo} disabled={updating} required />
        </div>

        <OrgFields {departments} {companies} bind:departmentId bind:companyId disabled={updating} idPrefix="edit" />

        <div class="form-group">
          <label for="edit-nickname">{WORKERS.fieldNickname}</label>
          <input
            id="edit-nickname"
            type="text"
            placeholder={WORKERS.fieldNicknamePlaceholder}
            bind:value={nickname}
            disabled={updating}
            required
          />
          <span class="form-hint">{WORKERS.fieldNicknameHint}</span>
        </div>

        <div class="form-group">
          <label for="edit-gender">{WORKERS.fieldGender}</label>
          <select id="edit-gender" bind:value={gender} disabled={updating}>
            <option value="male">{WORKERS.genderMale}</option>
            <option value="female">{WORKERS.genderFemale}</option>
          </select>
        </div>

        <div class="modal-actions">
          <button
            type="button"
            class="btn"
            onclick={onClose}
            disabled={updating}
          >
            {WORKERS.cancelBtn}
          </button>
          <button
            type="submit"
            class="btn btn-primary"
            disabled={updating || !nickname.trim()}
          >
            {WORKERS.saveBtn}
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
    max-width: 520px;
    box-shadow: 0 10px 25px var(--backdrop);
  }

  h3 {
    margin: 0 0 var(--space-3);
    font-size: var(--text-md);
    font-weight: 600;
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

  .error-box {
    background: var(--danger-line);
    color: var(--danger);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    margin-bottom: var(--space-3);
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }
</style>
