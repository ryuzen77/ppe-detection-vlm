<script lang="ts">
  import { onMount } from 'svelte'
  import { api, ApiError } from '../../lib/api/client'
  import type { VlmChoice, VlmProvidersResponse, VlmTestResponse, VlmModelEntry } from '../../lib/api/types'
  import { SETTINGS_TAB } from '../../lib/messages'
  import { validationBadge, handleSelectionError } from '../../lib/vlmSelection'
  import Server from '@lucide/svelte/icons/server'

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

  async function load() {
    try {
      data = await api.getVlmProviders()
      primaryProvider = data.current.primary?.provider || ''
      primaryModel = data.current.primary?.model || ''
      backupProvider = data.current.backup?.provider || ''
      backupModel = data.current.backup?.model || ''
    } catch (e) {
      errorMsg = e instanceof Error ? e.message : 'Gagal memuat'
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
    applyStatus = 'Menyiapkan...'
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
      applyStatus = 'Berhasil diterapkan'
      setTimeout(() => applyStatus = '', 3000)
    } catch (e) {
      applyStatus = ''
      if (e instanceof ApiError && e.body && typeof e.body === 'object' && 'detail' in (e.body as any)) {
        const detail = (e.body as any).detail
        const action = handleSelectionError(detail.code, detail.message)
        if (action.type === 'confirm') {
          confirmation = { code: action.code, message: action.message }
        } else if (action.type === 'error') {
          errorMsg = action.message
        }
      } else {
        errorMsg = e instanceof Error ? e.message : 'Gagal'
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
      let err = e instanceof Error ? e.message : 'Gagal uji'
      if (e instanceof ApiError && e.body && typeof e.body === 'object' && 'detail' in (e.body as any)) {
         err = (e.body as any).detail.message || err
      }
      testResult = { role, res: null, err }
    } finally {
      testing = null
    }
  }

  async function handleReset() {
    if (!confirm('Kembali ke konfigurasi .env?')) return
    applying = true
    errorMsg = ''
    try {
      const res = await api.resetVlmSelection()
      if (data) data.current = res
      primaryProvider = res.primary?.provider || ''
      primaryModel = res.primary?.model || ''
      backupProvider = res.backup?.provider || ''
      backupModel = res.backup?.model || ''
    } catch (e) {
      errorMsg = e instanceof Error ? e.message : 'Gagal'
    } finally {
      applying = false
    }
  }
</script>

{#if loading}
  <p>Memuat...</p>
{:else if data}
  <div class="header-info">
    <p class="source-info">
      Sumber aktif: <strong>{data.current.primary?.source === 'dashboard' ? 'Dashboard' : '.env'}</strong>
      {#if data.current.primary?.source === 'dashboard'}
        <button class="btn btn-secondary btn-sm" onclick={handleReset} disabled={applying}>Kembali ke .env</button>
      {/if}
    </p>
  </div>

  {#if errorMsg}
    <p class="error">{errorMsg}</p>
  {/if}

  <div class="roles">
    <!-- Utama -->
    <div class="role-box">
      <h3>VLM Utama</h3>
      <label>
        <span>Penyedia</span>
        <select bind:value={primaryProvider} disabled={applying}>
          {#each providers as p}
            <option value={p.name} disabled={!p.has_key}>{p.label} {!p.has_key ? '(isi key di .env)' : ''}</option>
          {/each}
        </select>
      </label>
      
      {#if primaryProvider}
        {@const pList = providers.find(p => p.name === primaryProvider)}
        <label>
          <span>Model</span>
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
              <span class="location" title="Lokasi Data"><Server size={14}/> {pList.data_location}</span>
            {/if}
          </div>
          {#if mData.photos}
            <div class="stats">
              {mData.photos} foto, meleset {mData.missed}, salah tolak {mData.false_rejects}, ~{mData.median_seconds}s
            </div>
          {/if}
        {/if}
        
        <button class="btn btn-secondary mt-2" onclick={() => handleTest('primary')} disabled={testing !== null || applying || !primaryModel}>
          {testing === 'primary' ? 'Menguji...' : 'Uji Penyedia'}
        </button>
      {/if}
    </div>

    <!-- Cadangan -->
    <div class="role-box">
      <h3>VLM Cadangan</h3>
      <label>
        <span>Penyedia</span>
        <select bind:value={backupProvider} disabled={applying}>
          <option value="">(Tanpa cadangan)</option>
          {#each providers as p}
            <option value={p.name} disabled={!p.has_key}>{p.label} {!p.has_key ? '(isi key di .env)' : ''}</option>
          {/each}
        </select>
      </label>
      
      {#if backupProvider}
        {@const pList = providers.find(p => p.name === backupProvider)}
        <label>
          <span>Model</span>
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
              <span class="location" title="Lokasi Data"><Server size={14}/> {pList.data_location}</span>
            {/if}
          </div>
        {/if}
        <button class="btn btn-secondary mt-2" onclick={() => handleTest('backup')} disabled={testing !== null || applying || !backupModel}>
          {testing === 'backup' ? 'Menguji...' : 'Uji Penyedia'}
        </button>
      {/if}
    </div>
  </div>
  
  {#if testResult.role}
    <div class="test-result">
      <strong>Hasil Uji {testResult.role === 'primary' ? 'Utama' : 'Cadangan'}:</strong>
      {#if testResult.err}
        <span class="error">{testResult.err}</span>
      {:else if testResult.res}
        {#if testResult.res.error}
          <span class="error">{testResult.res.error}</span>
        {:else}
          <span class="ok">Berhasil ({testResult.res.latency_ms}ms, valid JSON: {testResult.res.json_ok ? 'Ya' : 'Tidak'})</span>
        {/if}
      {/if}
    </div>
  {/if}

  {#if confirmation}
    <div class="confirmation-box">
      <p><strong>Peringatan:</strong> {confirmation.message}</p>
      <div class="actions">
        <button class="btn btn-secondary" onclick={() => confirmation = null} disabled={applying}>Batal</button>
        <button class="btn btn-primary" onclick={() => handleApply(true)} disabled={applying}>Saya Yakin, Lanjutkan</button>
      </div>
    </div>
  {/if}

  <div class="footer-actions">
    <button class="btn btn-primary" onclick={() => handleApply(false)} disabled={applying}>Terapkan</button>
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
  .tone-ok { background: var(--ok); color: #fff; }
  .tone-warn { background: var(--warn); color: #000; }
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
    background: rgba(255, 170, 0, 0.1);
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
