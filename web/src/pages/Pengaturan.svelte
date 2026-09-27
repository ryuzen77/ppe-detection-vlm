<script lang="ts">
  import AdminToken from '../components/settings/AdminToken.svelte'
  import CameraPicker from '../components/monitoring/CameraPicker.svelte'
  import ZoneSettings from '../components/settings/ZoneSettings.svelte'
  import { api } from '../lib/api/client'
  import type { VlmInfo } from '../lib/api/types'
  import { SETTINGS_TAB } from '../lib/messages'
  import { LIGHT_TEST } from '../lib/settings'
  import { telemetry } from '../lib/stores/telemetry.svelte'
  import { catalog } from '../lib/stores/catalog.svelte'
  import { formatLostSince } from '../lib/diagnostics'
  import { withError } from '../lib/messages'
  import ShieldCheck from '@lucide/svelte/icons/shield-check'
  import WifiOff from '@lucide/svelte/icons/wifi-off'
  import Camera from '@lucide/svelte/icons/camera'

  let pickerOpen = $state(false)
  let vlmInfo = $state<VlmInfo | null>(null)
  
  let ppeError = $state('')
  let lightStatus = $state('')
  let pingStatus = $state('')

  $effect(() => {
    api.vlmInfo().then(info => vlmInfo = info).catch(() => {})
  })

  const lostSince = $derived.by(() => formatLostSince(
    telemetry.lastMessageAt,
    SETTINGS_TAB.serverDisconnected,
    SETTINGS_TAB.serverDisconnectedSince
  ))

  async function testLight() {
    lightStatus = SETTINGS_TAB.running
    try {
      await api.testLight('green')
      setTimeout(async () => {
        try {
          await api.testLight('off')
          lightStatus = SETTINGS_TAB.success
        } catch (e) {
          lightStatus = withError(SETTINGS_TAB.lightOffFailed, e)
        }
      }, LIGHT_TEST.offDelayMs)
    } catch (e) {
      lightStatus = withError(SETTINGS_TAB.lightOnFailed, e)
    }
  }

  async function pingVlm() {
    pingStatus = SETTINGS_TAB.running
    try {
      const res = await api.pingVlm()
      pingStatus = SETTINGS_TAB.pingResult(res.status, res.latency_ms, res.message)
    } catch (e) {
      pingStatus = withError(SETTINGS_TAB.pingFailed, e)
    }
  }

  async function togglePpe(key: string, checked: boolean) {
    if (!catalog.items) return
    ppeError = ''
    const active: Record<string, boolean> = {}
    for (const item of catalog.items) {
      active[item.key] = item.key === key ? checked : item.required
    }
    try {
      await api.setPpeActive(active)
      catalog.load()
    } catch (e) {
      ppeError = withError(SETTINGS_TAB.ppeUpdateFailed, e)
    }
  }
</script>

<div class="wrap">
  <div class="content">
    <AdminToken />

    <ZoneSettings />

    <section class="card">
      <h2>{SETTINGS_TAB.camera}</h2>
      <button class="btn btn-primary" onclick={() => pickerOpen = true}><Camera size={16} /> {SETTINGS_TAB.pickCamera}</button>
      <CameraPicker bind:open={pickerOpen} />
    </section>

    <section class="card">
      <h2>{SETTINGS_TAB.ppeRequired}</h2>
      {#if ppeError}<p class="error" role="alert">{ppeError}</p>{/if}
      <div class="ppe-list">
        {#if catalog.items}
          {#each catalog.items as item (item.key)}
            <label class="ppe-item">
              <input type="checkbox" checked={item.required} onchange={(e) => togglePpe(item.key, e.currentTarget.checked)} />
              {item.label}
            </label>
          {/each}
        {/if}
      </div>
    </section>

    <section class="card">
      <h2>{SETTINGS_TAB.vlm}</h2>
      {#if vlmInfo}
        <div class="vlm-info">
          <p><strong>{SETTINGS_TAB.mainModel}:</strong> {vlmInfo.provider}/{vlmInfo.model}</p>
          {#if vlmInfo.backup}
            <p><strong>{SETTINGS_TAB.backupModel}:</strong> {vlmInfo.backup.provider}/{vlmInfo.backup.model}</p>
          {/if}
        </div>
      {/if}
    </section>

    <section class="card">
      <h2>{SETTINGS_TAB.lightTest}</h2>
      <button class="btn btn-primary" onclick={testLight}>{SETTINGS_TAB.testLightBtn}</button>
      {#if lightStatus}<p class="status-msg">{lightStatus}</p>{/if}
    </section>

    <section class="card">
      <h2>{SETTINGS_TAB.diagnostics}</h2>
      <div class="diagnostic-status">
        {#if telemetry.status !== 'connected'}
          <div class="disconnected">
            <WifiOff size={24} />
            <p>{lostSince}</p>
          </div>
        {:else}
          <div class="connected">
            <ShieldCheck size={24} />
            <p>{SETTINGS_TAB.serverConnected}</p>
          </div>
        {/if}
      </div>
      <button class="btn btn-primary mt-4" onclick={pingVlm}>{SETTINGS_TAB.latencyTestBtn}</button>
      {#if pingStatus}<p class="status-msg">{pingStatus}</p>{/if}
    </section>
  </div>
</div>

<style>
  .wrap {
    padding: var(--space-8) var(--space-4);
    display: flex;
    justify-content: center;
  }
  .content {
    width: min(600px, 100%);
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }
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
  .ppe-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .ppe-item {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .vlm-info p {
    margin: var(--space-1) 0;
  }
  .diagnostic-status {
    margin-top: var(--space-2);
  }
  .disconnected, .connected {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .disconnected {
    color: var(--warn);
  }
  .connected {
    color: var(--ok);
  }
  .error {
    color: var(--danger);
    font-size: var(--text-sm);
    margin-bottom: var(--space-2);
  }
  .status-msg {
    margin-top: var(--space-2);
    font-size: var(--text-sm);
    color: var(--text-muted);
  }
  .mt-4 {
    margin-top: var(--space-4);
  }
</style>
