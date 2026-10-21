<script lang="ts">
  import { onMount } from 'svelte'
  import { api } from '../../lib/api/client'
  import type { VlmChoice, VlmProvidersResponse, VlmTestResponse } from '../../lib/api/types'
  import { SETTINGS_TAB, VLM_SETTINGS } from '../../lib/messages'
  import {
    handleSelectionError, backupChange, providerOptionLabel, localFallbackAvailability, localFallbackChoice,
  } from '../../lib/vlmSelection'
  import { extractApiError } from '../../lib/api/error'
  import VlmModelField from './VlmModelField.svelte'

  type TestRole = 'primary' | 'backup' | 'local'

  let data = $state<VlmProvidersResponse | null>(null)
  let loading = $state(true)
  let errorMsg = $state('')

  let primaryProvider = $state('')
  let primaryModel = $state('')
  let backupProvider = $state('')
  let backupModel = $state('')
  // T72: VLM lokal darurat (susunan A)
  let localProvider = $state('')
  let localModel = $state('')

  let applying = $state(false)
  let applyStatus = $state('')

  let testing = $state<TestRole | null>(null)
  let testResult = $state<{role: TestRole | '', res: VlmTestResponse | null, err: string}>({ role: '', res: null, err: '' })

  let confirmation = $state<{code: string, message: string} | null>(null)
  let resetConfirmation = $state(false)
  let disableConfirmation = $state(false)

  function fillForm(current: VlmProvidersResponse['current']) {
    primaryProvider = current.primary?.provider || ''
    primaryModel = current.primary?.model || ''
    backupProvider = current.backup?.provider || ''
    backupModel = current.backup?.model || ''
    localProvider = current.local_fallback?.provider || ''
    localModel = current.local_fallback?.model || ''
  }

  async function load() {
    try {
      data = await api.getVlmProviders()
      fillForm(data.current)
    } catch (e) {
      errorMsg = extractApiError(e, VLM_SETTINGS.errLoad)
    } finally {
      loading = false
    }
  }

  onMount(load)

  const providers = $derived(data?.providers || [])
  const localProviders = $derived(providers.filter((p) => p.is_local))
  // T70: mematikan cadangan perlu konfirmasi; mengaktifkan cadangan lokal = menunggu model siap
  const change = $derived(backupChange(data?.current.backup ?? null, backupProvider, backupModel, providers))
  const localAvailability = $derived(localFallbackAvailability(backupProvider, providers))
  const LOCAL_UNAVAILABLE_HINT = {
    backup_is_local: VLM_SETTINGS.localFallbackBackupIsLocal,
    needs_backup: VLM_SETTINGS.localFallbackNeedsBackup,
    no_local_provider: VLM_SETTINGS.noLocalProvider,
  } as const

  function requestApply() {
    if (change === 'disable') disableConfirmation = true
    else handleApply(false)
  }

  async function handleApply(confirmUnvalidated = false) {
    applyStatus = change === 'enable_local' ? VLM_SETTINGS.applyingLocalBackup : VLM_SETTINGS.applying
    applying = true
    confirmation = null
    disableConfirmation = false
    errorMsg = ''
    try {
      const primary: VlmChoice = { provider: primaryProvider, model: primaryModel }
      const backup: VlmChoice | null = backupProvider ? { provider: backupProvider, model: backupModel } : null

      const res = await api.applyVlmSelection({
        primary,
        backup,
        local_fallback: localFallbackChoice(localAvailability, localProvider, localModel),
        confirm_unvalidated: confirmUnvalidated
      })

      if (data) data.current = res
      applyStatus = VLM_SETTINGS.applySuccess
      setTimeout(() => applyStatus = '', 3000)
    } catch (e) {
      applyStatus = ''
      if (typeof e === 'object' && e !== null && 'body' in e && typeof (e as {body: unknown}).body === 'object' && (e as {body: any}).body !== null && 'detail' in (e as {body: any}).body) {
        const detail = (e as {body: {detail: {code: string, message: string}}}).body.detail
        const action = handleSelectionError(detail.code, detail.message)
        if (action.type === 'confirm') {
          confirmation = { code: action.code, message: action.message }
        } else if (action.type === 'error') {
          errorMsg = action.message
        } else {
           errorMsg = extractApiError(e, VLM_SETTINGS.errApply)
        }
      } else {
        errorMsg = extractApiError(e, VLM_SETTINGS.errApply)
      }
    } finally {
      applying = false
    }
  }

  const TEST_CHOICE = {
    primary: () => ({ provider: primaryProvider, model: primaryModel }),
    backup: () => ({ provider: backupProvider, model: backupModel }),
    local: () => ({ provider: localProvider, model: localModel }),
  }
  const TEST_TITLE = {
    primary: VLM_SETTINGS.testResultPrimary,
    backup: VLM_SETTINGS.testResultBackup,
    local: VLM_SETTINGS.testResultLocal,
  }

  async function handleTest(role: TestRole) {
    testing = role
    testResult = { role, res: null, err: '' }
    try {
      // Kontrak uji (T28) hanya mengenal utama/cadangan; VLM lokal darurat diuji di jalur cadangan
      const res = await api.testVlmProvider({ role: role === 'primary' ? 'primary' : 'backup', ...TEST_CHOICE[role]() })
      testResult = { role, res, err: '' }
    } catch (e) {
      testResult = { role, res: null, err: extractApiError(e, VLM_SETTINGS.errTest) }
    } finally {
      testing = null
    }
  }

  async function handleReset() {
    applying = true
    errorMsg = ''
    resetConfirmation = false
    try {
      const res = await api.resetVlmSelection()
      if (data) data.current = res
      fillForm(res)
    } catch (e) {
      errorMsg = extractApiError(e, VLM_SETTINGS.errReset)
    } finally {
      applying = false
    }
  }
</script>

<section class="card">
  <h2>{SETTINGS_TAB.vlm}</h2>
  {#if loading}
    <p>{VLM_SETTINGS.loading}</p>
  {:else if data}
  <div class="header-info">
    <p class="source-info">
      {VLM_SETTINGS.activeSource}: <strong>{data.current.primary?.source === 'dashboard' ? VLM_SETTINGS.sourceDashboard : VLM_SETTINGS.sourceEnv}</strong>
      {#if data.current.primary?.source === 'dashboard'}
        <button class="btn btn-secondary btn-sm" onclick={() => resetConfirmation = true} disabled={applying}>{VLM_SETTINGS.resetToEnvBtn}</button>
      {/if}
    </p>
  </div>

  {#if errorMsg}
    <p class="error">{errorMsg}</p>
  {/if}

  <div class="roles">
    <!-- Utama -->
    <div class="role-box">
      <h3>{VLM_SETTINGS.primaryTitle}</h3>
      <label>
        <span>{VLM_SETTINGS.providerLabel}</span>
        <select bind:value={primaryProvider} disabled={applying}>
          {#each providers as p (p.name)}
            <option value={p.name} disabled={p.missing !== null}>{providerOptionLabel(p)}</option>
          {/each}
        </select>
      </label>

      {#if primaryProvider}
        <VlmModelField id="primary" provider={providers.find(p => p.name === primaryProvider)}
                       bind:model={primaryModel} disabled={applying} showStats />
        <button class="btn btn-secondary mt-2" onclick={() => handleTest('primary')} disabled={testing !== null || applying || !primaryModel}>
          {testing === 'primary' ? VLM_SETTINGS.testingBtn : VLM_SETTINGS.testBtn}
        </button>
      {/if}
    </div>

    <!-- Cadangan -->
    <div class="role-box">
      <h3>{VLM_SETTINGS.backupTitle}</h3>
      <label>
        <span>{VLM_SETTINGS.providerLabel}</span>
        <select bind:value={backupProvider} disabled={applying}>
          <option value="">{VLM_SETTINGS.noBackup}</option>
          {#each providers as p (p.name)}
            <option value={p.name} disabled={p.missing !== null}>{providerOptionLabel(p)}</option>
          {/each}
        </select>
      </label>
      {#if !backupProvider}
        <p class="hint">{VLM_SETTINGS.noBackupHint}</p>
      {/if}

      {#if backupProvider}
        <VlmModelField id="backup" provider={providers.find(p => p.name === backupProvider)}
                       bind:model={backupModel} disabled={applying} />
        <button class="btn btn-secondary mt-2" onclick={() => handleTest('backup')} disabled={testing !== null || applying || !backupModel}>
          {testing === 'backup' ? VLM_SETTINGS.testingBtn : VLM_SETTINGS.testBtn}
        </button>
      {/if}
    </div>

    <!-- Lokal darurat (T72, susunan A): hanya bila cadangan = API -->
    <div class="role-box">
      <h3>{VLM_SETTINGS.localFallbackTitle}</h3>
      {#if localAvailability === 'available'}
        <label>
          <span>{VLM_SETTINGS.providerLabel}</span>
          <select bind:value={localProvider} disabled={applying}>
            <option value="">{VLM_SETTINGS.noLocalFallback}</option>
            {#each localProviders as p (p.name)}
              <option value={p.name} disabled={p.missing !== null}>{providerOptionLabel(p)}</option>
            {/each}
          </select>
        </label>
        {#if localProvider}
          <VlmModelField id="local" provider={providers.find(p => p.name === localProvider)}
                         bind:model={localModel} disabled={applying} />
          <p class="hint">{VLM_SETTINGS.localFallbackHint}</p>
          <button class="btn btn-secondary mt-2" onclick={() => handleTest('local')} disabled={testing !== null || applying || !localModel}>
            {testing === 'local' ? VLM_SETTINGS.testingBtn : VLM_SETTINGS.testBtn}
          </button>
        {:else}
          <p class="hint">{VLM_SETTINGS.noLocalFallbackHint}</p>
        {/if}
      {:else}
        <p class="hint">{LOCAL_UNAVAILABLE_HINT[localAvailability]}</p>
      {/if}
    </div>
  </div>

  {#if testResult.role}
    <div class="test-result">
      <strong>{TEST_TITLE[testResult.role]}:</strong>
      {#if testResult.err}
        <span class="error">{testResult.err}</span>
      {:else if testResult.res}
        {#if testResult.res.error}
          <span class="error">{testResult.res.error}</span>
        {:else}
          <span class="ok">{VLM_SETTINGS.testSuccess(testResult.res.latency_ms, testResult.res.json_ok)}</span>
        {/if}
      {/if}
    </div>
  {/if}

  {#if confirmation}
    <div class="confirmation-box">
      <p><strong>{VLM_SETTINGS.warningTitle}:</strong> {confirmation.message}</p>
      <div class="actions">
        <button class="btn btn-secondary" onclick={() => confirmation = null} disabled={applying}>{VLM_SETTINGS.cancelBtn}</button>
        <button class="btn btn-primary" onclick={() => handleApply(true)} disabled={applying}>{VLM_SETTINGS.confirmBtn}</button>
      </div>
    </div>
  {/if}

  {#if resetConfirmation}
    <div class="confirmation-box">
      <p><strong>{VLM_SETTINGS.resetConfirmTitle}</strong></p>
      <div class="actions">
        <button class="btn btn-secondary" onclick={() => resetConfirmation = false} disabled={applying}>{VLM_SETTINGS.cancelBtn}</button>
        <button class="btn btn-primary" onclick={handleReset} disabled={applying}>{VLM_SETTINGS.confirmBtn}</button>
      </div>
    </div>
  {/if}

  {#if disableConfirmation}
    <div class="confirmation-box">
      <p><strong>{VLM_SETTINGS.warningTitle}:</strong> {VLM_SETTINGS.disableBackupConfirm}</p>
      <div class="actions">
        <button class="btn btn-secondary" onclick={() => disableConfirmation = false} disabled={applying}>{VLM_SETTINGS.cancelBtn}</button>
        <button class="btn btn-primary" onclick={() => handleApply(false)} disabled={applying}>{VLM_SETTINGS.confirmBtn}</button>
      </div>
    </div>
  {/if}

  <div class="footer-actions">
    <button class="btn btn-primary" onclick={requestApply} disabled={applying}>{VLM_SETTINGS.applyBtn}</button>
    {#if applyStatus}
      <span class="status-msg">{applyStatus}</span>
    {/if}
  </div>

  {/if}
</section>

<style>
  .card {
    padding: var(--space-6);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    color: var(--text);
  }
  h2 {
    margin: 0 0 var(--space-4);
    font-size: var(--text-lg);
  }
  .header-info {
    margin-bottom: var(--space-4);
  }
  .source-info {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin: 0;
  }
  .roles {
    display: flex;
    gap: var(--space-4);
    flex-wrap: wrap;
  }
  .role-box {
    flex: 1;
    min-width: 250px;
    background: var(--bg);
    border: 1px solid var(--border);
    padding: var(--space-4);
    border-radius: var(--radius-md);
  }
  .role-box h3 {
    margin: 0 0 var(--space-3);
    font-size: var(--text-md);
  }
  label {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    margin-bottom: var(--space-3);
  }
  select {
    padding: 6px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-strong);
    background: var(--surface);
    color: var(--text);
  }
  /* T70: konsekuensi cadangan mati; T72: penjelasan VLM lokal darurat */
  .hint { font-size: var(--text-sm); color: var(--text-muted); margin: 0.25rem 0 0; }
  .test-result {
    margin-top: var(--space-4);
    padding: var(--space-3);
    background: var(--bg);
    border-radius: var(--radius-sm);
  }
  .confirmation-box {
    margin-top: var(--space-4);
    padding: var(--space-4);
    border: 1px solid var(--warn-line);
    background: var(--surface-2);
    border-radius: var(--radius-md);
  }
  .confirmation-box p {
    margin-top: 0;
    color: var(--warn);
    font-weight: 500;
  }
  .actions, .footer-actions {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin-top: var(--space-4);
  }
  .error { color: var(--danger); font-size: var(--text-sm); font-weight: 500; }
  .ok { color: var(--ok); font-weight: 500; }
  .status-msg { color: var(--text-muted); }
  .mt-2 { margin-top: var(--space-2); }
  .btn-sm { padding: 4px 10px; font-size: var(--text-sm); }
</style>
