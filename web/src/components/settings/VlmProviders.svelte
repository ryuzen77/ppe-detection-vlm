<script lang="ts">
  import { onMount } from 'svelte'
  import { api } from '../../lib/api/client'
  import type { VlmChoice, VlmProvidersResponse, VlmTestResponse, VlmModelEntry } from '../../lib/api/types'
  import { SETTINGS_TAB, VLM_SETTINGS } from '../../lib/messages'
  import { validationBadge, handleSelectionError } from '../../lib/vlmSelection'
  import Server from '@lucide/svelte/icons/server'
  import { extractApiError } from '../../lib/api/error'

  let data = $state<VlmProvidersResponse | null>(null)
  let loading = $state(true)
  let errorMsg = $state('')

  let primaryProvider = $state('')
  let primaryModel = $state('')
  let backupProvider = $state('')
  let backupModel = $state('')

  let applying = $state(false)
  let applyStatus = $state('')
  
  let testing = $state<'primary'|'backup'|null>(null)
  let testResult = $state<{role: string, res: VlmTestResponse | null, err: string}>({ role: '', res: null, err: '' })

  let confirmation = $state<{code: string, message: string} | null>(null)
  let resetConfirmation = $state(false)

  async function load() {
    try {
      data = await api.getVlmProviders()
      primaryProvider = data.current.primary?.provider || ''
      primaryModel = data.current.primary?.model || ''
      backupProvider = data.current.backup?.provider || ''
      backupModel = data.current.backup?.model || ''
    } catch (e) {
      errorMsg = extractApiError(e, VLM_SETTINGS.errLoad)
    } finally {
      loading = false
    }
  }

  onMount(load)

  const providers = $derived(data?.providers || [])

  function findModel(pName: string, mName: string): VlmModelEntry | undefined {
    return providers.find(p => p.name === pName)?.models.find(m => m.model === mName)
  }

  async function handleApply(confirmUnvalidated = false) {
    applyStatus = VLM_SETTINGS.applying
    applying = true
    confirmation = null
    errorMsg = ''
    try {
      const primary: VlmChoice = { provider: primaryProvider, model: primaryModel }
      const backup: VlmChoice | null = backupProvider ? { provider: backupProvider, model: backupModel } : null
      
      const res = await api.applyVlmSelection({
        primary,
        backup,
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

  async function handleTest(role: 'primary'|'backup') {
    testing = role
    testResult = { role, res: null, err: '' }
    try {
      const provider = role === 'primary' ? primaryProvider : backupProvider
      const model = role === 'primary' ? primaryModel : backupModel
      const res = await api.testVlmProvider({ role, provider, model })
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
      primaryProvider = res.primary?.provider || ''
      primaryModel = res.primary?.model || ''
      backupProvider = res.backup?.provider || ''
      backupModel = res.backup?.model || ''
    } catch (e) {
      errorMsg = extractApiError(e, VLM_SETTINGS.errReset)
    } finally {
      applying = false
    }
  }
</script>

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
          {#each providers as p}
            <option value={p.name} disabled={p.missing !== null}>{p.label}{p.missing === 'base_url' ? ` ${VLM_SETTINGS.missingBaseUrl}` : p.missing === 'key' ? ` ${VLM_SETTINGS.missingKey}` : ''}</option>
          {/each}
        </select>
      </label>
      
      {#if primaryProvider}
        {@const pList = providers.find(p => p.name === primaryProvider)}
        <label>
          <span>{VLM_SETTINGS.modelLabel}</span>
          <input type="text" bind:value={primaryModel} list="models-primary" disabled={applying} />
          <datalist id="models-primary">
            {#each pList?.models || [] as m}
              <option value={m.model}></option>
            {/each}
          </datalist>
        </label>
        
        {@const mData = findModel(primaryProvider, primaryModel)}
        {#if mData}
          {@const badge = validationBadge(mData.validated)}
          <div class="meta">
            <span class="badge tone-{badge.tone}">{badge.text}</span>
            {#if pList?.data_location}
              <span class="location" title={VLM_SETTINGS.dataLocation}><Server size={14}/> {pList.data_location}</span>
            {/if}
          </div>
          {#if mData.photos}
            <div class="stats">
              {VLM_SETTINGS.stats(mData.photos, mData.missed, mData.false_rejects, mData.median_seconds)}
            </div>
          {/if}
        {/if}
        
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
          {#each providers as p}
            <option value={p.name} disabled={p.missing !== null}>{p.label}{p.missing === 'base_url' ? ` ${VLM_SETTINGS.missingBaseUrl}` : p.missing === 'key' ? ` ${VLM_SETTINGS.missingKey}` : ''}</option>
          {/each}
        </select>
      </label>
      
      {#if backupProvider}
        {@const pList = providers.find(p => p.name === backupProvider)}
        <label>
          <span>{VLM_SETTINGS.modelLabel}</span>
          <input type="text" bind:value={backupModel} list="models-backup" disabled={applying} />
          <datalist id="models-backup">
            {#each pList?.models || [] as m}
              <option value={m.model}></option>
            {/each}
          </datalist>
        </label>
        
        {@const mData = findModel(backupProvider, backupModel)}
        {#if mData}
          {@const badge = validationBadge(mData.validated)}
          <div class="meta">
            <span class="badge tone-{badge.tone}">{badge.text}</span>
            {#if pList?.data_location}
              <span class="location" title={VLM_SETTINGS.dataLocation}><Server size={14}/> {pList.data_location}</span>
            {/if}
          </div>
        {/if}
        <button class="btn btn-secondary mt-2" onclick={() => handleTest('backup')} disabled={testing !== null || applying || !backupModel}>
          {testing === 'backup' ? VLM_SETTINGS.testingBtn : VLM_SETTINGS.testBtn}
        </button>
      {/if}
    </div>
  </div>
  
  {#if testResult.role}
    <div class="test-result">
      <strong>{testResult.role === 'primary' ? VLM_SETTINGS.testResultPrimary : VLM_SETTINGS.testResultBackup}:</strong>
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

  <div class="footer-actions">
    <button class="btn btn-primary" onclick={() => handleApply(false)} disabled={applying}>{VLM_SETTINGS.applyBtn}</button>
    {#if applyStatus}
      <span class="status-msg">{applyStatus}</span>
    {/if}
  </div>

{/if}

<style>
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
  select, input {
    padding: 6px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-strong);
    background: var(--surface);
    color: var(--text);
  }
  .meta {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin-bottom: var(--space-1);
  }
  .badge {
    padding: 2px 8px;
    border-radius: 999px;
    font-size: var(--text-xs);
    font-weight: 500;
  }
  .tone-ok { background: var(--ok); color: var(--text); }
  .tone-warn { background: var(--warn); color: var(--surface); }
  .tone-muted { background: var(--border-strong); color: var(--text); }
  
  .location {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: var(--text-xs);
    color: var(--text-muted);
  }
  .stats {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }
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
