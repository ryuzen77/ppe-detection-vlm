<script lang="ts">
  // T83: setelan "Wajib terdaftar". Menyalakan dengan pengenalan wajah di bawah ambang butuh
  // konfirmasi admin (keputusan pengguna 22-10); tidak ada tombol "izinkan" per pekerja (AGENTS §5).
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert'
  import { onMount } from 'svelte'
  import { api, ApiError } from '../../lib/api/client'
  import { extractApiErrorCode } from '../../lib/api/error'
  import type { RegistrationPolicy } from '../../lib/api/types'
  import { REGISTRATION_POLICY as TEXT, withError } from '../../lib/messages'
  import {
    confirmText,
    needsConfirmation,
    recognitionText,
    saveErrorAction,
    thresholdText,
    toggleDisabled,
  } from '../../lib/registrationPolicy'

  const HTTP_NOT_FOUND = 404

  let policy = $state<RegistrationPolicy | null>(null)
  /** Server sebelum T83a belum punya rute ini: kartu tidak ditampilkan */
  let supported = $state(true)
  let saving = $state(false)
  let confirming = $state(false)
  let errorMsg = $state('')
  let successMsg = $state('')

  async function load() {
    try {
      policy = await api.registrationPolicy()
    } catch (e) {
      if (e instanceof ApiError && e.status === HTTP_NOT_FOUND) supported = false
      else errorMsg = withError(TEXT.loadFailed, e)
    }
  }

  onMount(load)

  async function save(on: boolean, confirmLow: boolean) {
    saving = true
    errorMsg = ''
    successMsg = ''
    try {
      policy = await api.setRegistrationPolicy({ require_registered: on, confirm_low_recognition: confirmLow })
      confirming = false
      successMsg = TEXT.saved(on)
    } catch (e) {
      const action = saveErrorAction(extractApiErrorCode(e))
      if (action === 'confirm') confirming = true
      else errorMsg = action === 'fr_not_ready' ? TEXT.frNotReady : withError(TEXT.saveFailed, e)
      await load()
    } finally {
      saving = false
    }
  }

  function onToggle(e: Event) {
    if (!policy) return
    const input = e.currentTarget as HTMLInputElement
    const on = input.checked
    // Kotak centang mengikuti server, bukan klik: baru berubah setelah tersimpan
    input.checked = policy.require_registered
    if (on && needsConfirmation(policy.recognition)) {
      confirming = true
      return
    }
    void save(on, false)
  }
</script>

{#if supported}
  <section class="card" aria-labelledby="h-registration">
    <h3 id="h-registration">{TEXT.title}</h3>
    <p class="explain">{TEXT.explain}</p>

    {#if policy}
      <label class="toggle">
        <input
          type="checkbox"
          checked={policy.require_registered}
          disabled={saving || confirming || toggleDisabled(policy)}
          onchange={onToggle}
        />
        {TEXT.toggle}
      </label>

      <dl>
        <dt>{TEXT.recognitionLabel}</dt>
        <dd>{recognitionText(policy.recognition)}</dd>
        <dt>{TEXT.thresholdLabel}</dt>
        <dd class="mono">{thresholdText(policy.recognition)}</dd>
      </dl>
      <p class="hint">{TEXT.recognitionNote}</p>

      {#if !policy.fr_ready}
        <p class="warn" role="alert">
          <TriangleAlert size={16} aria-hidden="true" />
          {policy.require_registered ? TEXT.frDownWhileOn : TEXT.frNotReady}
        </p>
      {/if}

      {#if confirming}
        <div class="confirm" role="alertdialog" aria-labelledby="h-registration-confirm">
          <strong id="h-registration-confirm">{TEXT.confirmTitle}</strong>
          <p>{confirmText(policy.recognition)}</p>
          <div class="row">
            <button class="btn btn-primary" disabled={saving} onclick={() => save(true, true)}>{TEXT.confirmYes}</button
            >
            <button class="btn" disabled={saving} onclick={() => (confirming = false)}>{TEXT.confirmNo}</button>
          </div>
        </div>
      {/if}
    {/if}

    {#if errorMsg}<p class="error" role="alert">{errorMsg}</p>{/if}
    {#if successMsg}<p class="success" role="status">{successMsg}</p>{/if}
  </section>
{/if}

<style>
  .card {
    padding: var(--space-6);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    color: var(--text);
  }
  h3 {
    margin: 0 0 var(--space-2);
  }
  .explain,
  .hint {
    margin: 0 0 var(--space-4);
    color: var(--text-muted);
    font-size: var(--text-sm);
    max-width: 72ch;
  }
  .hint {
    margin: var(--space-2) 0 0;
    color: var(--text-faint);
  }
  .toggle {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-weight: 500;
  }
  dl {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: var(--space-1) var(--space-4);
    margin: var(--space-4) 0 0;
    font-size: var(--text-sm);
  }
  dt {
    color: var(--text-muted);
  }
  dd {
    margin: 0;
  }
  .warn {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: var(--space-4) 0 0;
    color: var(--warn);
    font-size: var(--text-sm);
  }
  .confirm {
    margin-top: var(--space-4);
    padding: var(--space-4);
    border: 1px solid var(--warn-line);
    background: var(--warn-soft);
    border-radius: var(--radius);
    font-size: var(--text-sm);
  }
  .confirm p {
    margin: var(--space-2) 0 var(--space-3);
  }
  .row {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .error {
    margin: var(--space-3) 0 0;
    color: var(--danger);
    font-size: var(--text-sm);
  }
  .success {
    margin: var(--space-3) 0 0;
    color: var(--ok);
    font-size: var(--text-sm);
  }
</style>
