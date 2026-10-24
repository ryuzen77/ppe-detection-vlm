<script lang="ts">
  import CameraPicker from '../components/monitoring/CameraPicker.svelte'
  import ZoneSettings from '../components/settings/ZoneSettings.svelte'
  import Accounts from '../components/settings/Accounts.svelte'
  import VlmProviders from '../components/settings/VlmProviders.svelte'
  import LocalVlmCard from '../components/settings/LocalVlmCard.svelte'
  import RegistrationPolicyCard from '../components/settings/RegistrationPolicyCard.svelte'
  import { api } from '../lib/api/client'
  import type { LightTestAction } from '../lib/api/types'
  import { CAMERA_CHIP, SETTINGS_TAB, modeLabel } from '../lib/messages'
  import { LIGHT_TEST } from '../lib/settings'
  import { telemetry } from '../lib/stores/telemetry.svelte'
  import { catalog } from '../lib/stores/catalog.svelte'
  import { formatLostSince } from '../lib/diagnostics'
  import { iotChip } from '../lib/status'
  import { pingRows, type PingRow } from '../lib/ping'
  import { withError } from '../lib/messages'
  import ShieldCheck from '@lucide/svelte/icons/shield-check'
  import WifiOff from '@lucide/svelte/icons/wifi-off'
  import Camera from '@lucide/svelte/icons/camera'

  let pickerOpen = $state(false)

  let ppeError = $state('')
  let lightStatus = $state('')
  let pingStatus = $state('')
  let pingList = $state<PingRow[]>([])

  const gateIot = $derived(iotChip(telemetry.data))
  const camera = $derived(telemetry.data?.camera ?? null)
  // T78: kesehatan VLM cadangan hanya berarti bila cadangan memang dipakai
  // Kartu kesehatan VLM lokal (porsi GPU, latensi) hanya bermakna untuk cadangan lokal (temuan uji UI #12)
  const backupActive = $derived(
    telemetry.data?.api_monitor?.backup?.configured === true && telemetry.data.api_monitor.backup.is_local,
  )
  const LIGHTS = [
    { color: 'green', label: SETTINGS_TAB.testLightBtn },
    { color: 'red', label: SETTINGS_TAB.testRedBtn },
    { color: 'yellow', label: SETTINGS_TAB.testYellowBtn },
  ] as const

  const lostSince = $derived.by(() =>
    formatLostSince(telemetry.lastMessageAt, SETTINGS_TAB.serverDisconnected, SETTINGS_TAB.serverDisconnectedSince),
  )

  async function testLight(color: Exclude<LightTestAction, 'off'>) {
    lightStatus = SETTINGS_TAB.running
    try {
      await api.testLight(color)
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
    pingList = []
    try {
      const res = await api.pingVlm()
      pingList = pingRows(res)
      // Sibuk / tidak dikonfigurasi: tidak ada baris per VLM, pesan server yang tampil
      pingStatus = pingList.length ? SETTINGS_TAB.ping.note : res.message
    } catch (e) {
      pingStatus = withError(SETTINGS_TAB.pingFailed, e)
    }
  }

  // T89: satu perubahan pada satu waktu, supaya pesan galat & status centang jelas milik perubahan mana
  let ppeSaving = $state(false)

  async function togglePpe(input: HTMLInputElement, key: string) {
    ppeError = ''
    ppeSaving = true
    try {
      await catalog.setRequired(key, input.checked)
    } catch (e) {
      ppeError = withError(SETTINGS_TAB.ppeUpdateFailed, e)
    } finally {
      // Centang mengikuti status server terakhir yang diketahui (ditolak, atau ternyata tersimpan)
      input.checked = catalog.items.find((i) => i.key === key)?.required ?? input.checked
      ppeSaving = false
    }
  }

  async function refreshPpe() {
    ppeSaving = true
    if (await catalog.refresh()) ppeError = ''
    ppeSaving = false
  }
</script>

<div class="wrap">
  <div class="content">
    <section class="group" id="grup-gerbang" aria-labelledby="h-gerbang">
      <header>
        <h2 id="h-gerbang">{SETTINGS_TAB.groups.gerbang}</h2>
        <p>{SETTINGS_TAB.groupHints.gerbang}</p>
      </header>

      <section class="card">
        <div class="card-head">
          <h3>{SETTINGS_TAB.camera}</h3>
          <button class="btn btn-primary" onclick={() => (pickerOpen = true)}
            ><Camera size={16} /> {SETTINGS_TAB.pickCamera}</button
          >
        </div>
        {#if camera?.selected}
          <p class="line">
            <strong>{camera.name}</strong>
            {#if camera.status === 'OK'}<span class="mono muted">{modeLabel(camera)}</span>{:else}<span class="warn"
                >{CAMERA_CHIP[camera.status]}</span
              >{/if}
          </p>
        {:else}
          <p class="line muted">{SETTINGS_TAB.cameraNone}</p>
        {/if}
        <CameraPicker bind:open={pickerOpen} />
      </section>

      <ZoneSettings />

      <section class="card">
        <h3>{SETTINGS_TAB.ppeRequired}</h3>
        {#if ppeError}<p class="error" role="alert">{ppeError}</p>{/if}
        {#if catalog.unconfirmed}
          <p class="warn" role="alert">
            {SETTINGS_TAB.ppeUnconfirmed}
            <button class="btn" onclick={refreshPpe} disabled={ppeSaving}>{SETTINGS_TAB.ppeRefresh}</button>
          </p>
        {/if}
        <div class="ppe-list">
          {#if catalog.items}
            {#each catalog.items as item (item.key)}
              <label class="ppe-item">
                <input
                  type="checkbox"
                  checked={item.required}
                  disabled={ppeSaving || catalog.unconfirmed}
                  onchange={(e) => togglePpe(e.currentTarget, item.key)}
                />
                {item.label}
              </label>
            {/each}
          {/if}
        </div>
      </section>

      <RegistrationPolicyCard />

      <section class="card">
        <h3>{SETTINGS_TAB.lightTest}</h3>
        <p class="line muted">
          {gateIot.text}{#if gateIot.hint}
            ({gateIot.hint}){/if}
        </p>
        <div class="row">
          {#each LIGHTS as light (light.color)}
            <button class="btn" onclick={() => testLight(light.color)}
              ><span class="lamp lamp-{light.color}" aria-hidden="true"></span>{light.label}</button
            >
          {/each}
        </div>
        <p class="hint">{lightStatus || SETTINGS_TAB.lightTestHint}</p>
      </section>
    </section>

    <section class="group" id="grup-vlm" aria-labelledby="h-vlm">
      <header>
        <h2 id="h-vlm">{SETTINGS_TAB.groups.vlm}</h2>
        <p>{SETTINGS_TAB.groupHints.vlm}</p>
      </header>
      <VlmProviders />
      {#if backupActive}<LocalVlmCard />{/if}
    </section>

    <section class="group" id="grup-akun" aria-labelledby="h-akun">
      <header>
        <h2 id="h-akun">{SETTINGS_TAB.groups.akun}</h2>
        <p>{SETTINGS_TAB.groupHints.akun}</p>
      </header>
      <Accounts />
    </section>

    <section class="group" id="grup-diagnostik" aria-labelledby="h-diagnostik">
      <header>
        <h2 id="h-diagnostik">{SETTINGS_TAB.groups.diagnostik}</h2>
        <p>{SETTINGS_TAB.groupHints.diagnostik}</p>
      </header>
      <section class="card">
        <div class="card-head">
          {#if telemetry.status !== 'connected'}
            <p class="status warn"><WifiOff size={20} /> {lostSince}</p>
          {:else}
            <p class="status ok"><ShieldCheck size={20} /> {SETTINGS_TAB.serverConnected}</p>
          {/if}
          <button class="btn" onclick={pingVlm}>{SETTINGS_TAB.latencyTestBtn}</button>
        </div>
        {#if pingList.length}
          <ul class="ping-list">
            {#each pingList as row (row.label)}
              <li class="ping-{row.tone}">
                <span class="lamp lamp-{row.tone}" aria-hidden="true"></span>
                <span
                  ><strong>{row.label}</strong>: {row.text}{#if row.hint}<br /><span class="muted">{row.hint}</span
                    >{/if}</span
                >
              </li>
            {/each}
          </ul>
        {/if}
        {#if pingStatus}<p class="hint">{pingStatus}</p>{/if}
      </section>
    </section>
  </div>
</div>

<style>
  .wrap {
    max-width: 960px;
    margin: 0 auto;
    padding: var(--space-6) var(--space-5) var(--space-8);
  }
  .content {
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
    min-width: 0;
  }
  .group {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .group > header h2 {
    margin: 0;
    font-size: var(--text-xl);
  }
  .group > header p {
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
  .card {
    padding: var(--space-5) var(--space-6);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    color: var(--text);
  }
  h3 {
    margin: 0 0 var(--space-3);
    font-size: var(--text-lg);
  }
  .card-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    flex-wrap: wrap;
  }
  .card-head h3 {
    margin: 0;
  }
  .line {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    margin: var(--space-3) 0 0;
    font-size: var(--text-sm);
  }
  .muted {
    color: var(--text-muted);
  }
  .warn {
    color: var(--warn);
  }
  .ppe-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: var(--space-2) var(--space-4);
  }
  .ppe-item {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-sm);
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin-top: var(--space-3);
  }
  .lamp {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }
  .lamp-green {
    background: var(--ok);
  }
  .lamp-red {
    background: var(--danger);
  }
  .lamp-yellow,
  .lamp-warn {
    background: var(--warn);
  }
  .lamp-ok {
    background: var(--ok);
  }
  .lamp-danger {
    background: var(--danger);
  }
  .lamp-muted {
    background: var(--text-faint);
  }
  .ping-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: var(--space-3) 0 0;
    padding: 0;
    list-style: none;
    font-size: var(--text-sm);
  }
  .ping-list li {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
  }
  .ping-list .lamp {
    flex: none;
    transform: translateY(1px);
  }
  .status {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
    font-size: var(--text-sm);
  }
  .status.ok {
    color: var(--ok);
  }
  .hint {
    margin: var(--space-2) 0 0;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }
  .error {
    color: var(--danger);
    font-size: var(--text-sm);
    margin: 0 0 var(--space-2);
  }
</style>
