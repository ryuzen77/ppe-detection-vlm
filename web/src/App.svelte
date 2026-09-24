<script lang="ts">
  // Kerangka sementara: membuktikan alur data stack baru (tipe, REST, WebSocket,
  // store reaktif) dari ujung ke ujung. Tampilan sebenarnya dibuat pada tahap
  // redesign UI/UX; sampai itu selesai UI lama tetap di "/" sebagai cadangan.
  import { onDestroy, onMount } from 'svelte'
  import { api } from './lib/api/client'
  import type { VlmInfo } from './lib/api/types'
  import { telemetry } from './lib/stores/telemetry.svelte'

  let vlm = $state<VlmInfo | null>(null)
  let error = $state('')

  onMount(async () => {
    telemetry.start()
    try {
      vlm = await api.vlmInfo()
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  })
  onDestroy(() => telemetry.stop())

  const t = $derived(telemetry.data)
</script>

<main>
  <h1>SAFEGUARD AI — UI baru (fondasi)</h1>
  <p>Halaman sementara. UI lama tetap tersedia di <a href="/">/</a>.</p>

  <dl>
    <dt>WebSocket</dt>
    <dd data-testid="ws-status">{telemetry.status}</dd>
    <dt>Kamera</dt>
    <dd>{t ? `${t.camera.status} ${t.camera.name}` : '-'}</dd>
    <dt>VLM</dt>
    <dd data-testid="vlm-mode">{t ? t.api_monitor.mode : '-'}</dd>
    <dt>VLM utama / cadangan</dt>
    <dd>
      {#if vlm}
        {vlm.provider}/{vlm.model} · {vlm.backup ? `${vlm.backup.provider}/${vlm.backup.model}` : 'tanpa cadangan'}
      {:else if error}
        galat: {error}
      {:else}
        memuat...
      {/if}
    </dd>
    <dt>Status gerbang</dt>
    <dd>{t?.active_track ? t.active_track.state : 'standby'} · lampu {t?.light.light_state ?? '-'}</dd>
    <dt>FPS</dt>
    <dd>{t ? t.fps.toFixed(1) : '-'}</dd>
  </dl>
</main>

<style>
  main {
    max-width: 720px;
    margin: 2rem auto;
    padding: 0 1rem;
  }
  dl {
    display: grid;
    grid-template-columns: 12rem 1fr;
    gap: 0.4rem 1rem;
  }
  dt {
    color: #9aa1a9;
  }
  dd {
    margin: 0;
  }
</style>
