<script lang="ts">
  import { WORKERS } from '../../../lib/messages'
  import { validateWorkerForm } from '../../../lib/workers'
  import { api } from '../../../lib/api/client'
  import { extractApiError } from '../../../lib/api/error'

  interface Props {
    show: boolean
    onClose: () => void
    onSaved: () => void
  }

  let { show, onClose, onSaved }: Props = $props()

  let employeeNo = $state('')
  let name = $state('')
  let nickname = $state('')
  let gender = $state<'male' | 'female'>('male')
  let consent = $state(false)
  let adding = $state(false)
  let addError = $state('')

  $effect(() => {
    if (show) {
      employeeNo = ''
      name = ''
      nickname = ''
      gender = 'male'
      consent = false
      addError = ''
    }
  })

  async function handleAddWorker(e: Event) {
    e.preventDefault()
    addError = ''
    const valErr = validateWorkerForm({
      employee_no: employeeNo,
      name,
      nickname,
      gender,
      consent,
    })
    if (valErr) {
      addError = valErr
      return
    }

    adding = true
    try {
      await api.createWorker({
        employee_no: employeeNo.trim(),
        name: name.trim(),
        nickname: nickname.trim(),
        gender,
        consent,
      })
      onSaved()
    } catch (e) {
      addError = extractApiError(e, WORKERS.errAdd)
    } finally {
      adding = false
    }
  }
</script>

{#if show}
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
            bind:value={employeeNo}
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
            bind:value={name}
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
              bind:value={nickname}
              disabled={adding}
              required
            />
            <span class="form-hint">{WORKERS.fieldNicknameHint}</span>
          </div>

          <div class="form-group flex-1">
            <label for="new-gender">{WORKERS.fieldGender}</label>
            <select id="new-gender" bind:value={gender} disabled={adding}>
              <option value="male">{WORKERS.genderMale}</option>
              <option value="female">{WORKERS.genderFemale}</option>
            </select>
          </div>
        </div>

        <div class="consent-box">
          <label class="consent-label">
            <input
              type="checkbox"
              bind:checked={consent}
              disabled={adding}
            />
            <span>{WORKERS.fieldConsentLabel}</span>
          </label>
        </div>

        <div class="modal-actions">
          <button
            type="button"
            class="btn"
            onclick={onClose}
            disabled={adding}
          >
            {WORKERS.cancelBtn}
          </button>
          <button
            type="submit"
            class="btn btn-primary"
            disabled={adding || !consent}
          >
            {WORKERS.submitBtn}
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
