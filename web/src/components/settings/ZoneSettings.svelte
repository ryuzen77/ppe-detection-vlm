<script lang="ts">
  import { api, ApiError } from '../../lib/api/client'
  import type { Zone } from '../../lib/api/types'
  import { SETTINGS_TAB, withError } from '../../lib/messages'
  import { STAND_ZONE } from '../../lib/settings'
  import { isValidZoneBand } from '../../lib/zone'

  let zone = $state<Zone | null>(null)
  let errorMsg = $state('')
  let successMsg = $state('')

  $effect(() => {
    api.zone().then(z => zone = z).catch(() => {})
  })

  async function reload() {
    try { zone = await api.zone() } catch { /* biarkan zone lama */ }
  }

  async function toggleZone(e: Event) {
    if (!zone) return
    const checked = (e.target as HTMLInputElement).checked
    try {
      zone = await api.setZone({ enabled: checked })
      errorMsg = ''
    } catch (e) {
      errorMsg = withError(SETTINGS_TAB.zoneSaveFailed, e)
      await reload()
    }
  }

  async function saveRange() {
    if (!zone) return
    if (!isValidZoneBand(zone.y_min, zone.y_max, STAND_ZONE.minHeight)) {
      errorMsg = SETTINGS_TAB.zoneInvalidBand
      await reload()
      return
    }
    try {
      zone = await api.setZone({ y_min: zone.y_min, y_max: zone.y_max })
      errorMsg = ''
    } catch (e) {
      errorMsg = withError(SETTINGS_TAB.zoneRangeFailed, e)
      await reload()
    }
  }

  async function calibrate() {
    try {
      zone = await api.calibrateZone()
      errorMsg = ''
      successMsg = SETTINGS_TAB.zoneCalibrated
      setTimeout(() => successMsg = '', STAND_ZONE.successMessageMs)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        errorMsg = e.message || SETTINGS_TAB.zoneNoPerson
      } else {
        errorMsg = withError(SETTINGS_TAB.zoneCalibrateFailed, e)
      }
      await reload()
    }
  }
</script>

<section class="card">
  <h2>{SETTINGS_TAB.zone}</h2>
  {#if errorMsg}<p class="error" role="alert">{errorMsg}</p>{/if}
  {#if successMsg}<p class="success" role="alert">{successMsg}</p>{/if}

  {#if zone}
    <label class="zone-toggle">
      <input type="checkbox" checked={zone.enabled} onchange={toggleZone} />
      {SETTINGS_TAB.zoneEnabled}
    </label>
    
    <div class="zone-controls" class:disabled={!zone.enabled}>
      <div class="slider-group">
        <label>
          {SETTINGS_TAB.sliderTop(zone.y_min.toFixed(2))}
          <input type="range" min="0" max="1" step={STAND_ZONE.sliderStep} bind:value={zone.y_min} onchange={saveRange} disabled={!zone.enabled} />
        </label>
        <label>
          {SETTINGS_TAB.sliderBottom(zone.y_max.toFixed(2))}
          <input type="range" min="0" max="1" step={STAND_ZONE.sliderStep} bind:value={zone.y_max} onchange={saveRange} disabled={!zone.enabled} />
        </label>
      </div>

      <div class="calibrate-section">
        <button class="btn btn-primary" onclick={calibrate} disabled={!zone.enabled}>{SETTINGS_TAB.zoneCalibrate}</button>
        <span class="source-label">{SETTINGS_TAB.zoneSource(zone.source)}</span>
      </div>
    </div>
  {:else}
    <p>Memuat pengaturan zona...</p>
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
  .error {
    color: var(--danger);
    font-size: var(--text-sm);
    margin-bottom: var(--space-2);
  }
  .success {
    color: var(--ok);
    font-size: var(--text-sm);
    margin-bottom: var(--space-2);
  }
  .zone-toggle {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-weight: 500;
  }
  .zone-controls {
    margin-top: var(--space-4);
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .zone-controls.disabled {
    opacity: 0.5;
  }
  .slider-group {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .slider-group label {
    display: flex;
    flex-direction: column;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }
  .slider-group input {
    margin-top: var(--space-1);
    width: 100%;
  }
  .calibrate-section {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    flex-wrap: wrap;
  }
  .source-label {
    font-size: var(--text-sm);
    color: var(--text-faint);
  }
</style>
