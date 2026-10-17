<script lang="ts">
  // Layar utama operator: video kiri setinggi layar; kanan keputusan besar,
  // checklist APD, dan riwayat (keputusan UX T33) — tanpa ruang kosong.
  import CameraPicker from '../components/monitoring/CameraPicker.svelte'
  import DecisionPanel from '../components/monitoring/DecisionPanel.svelte'
  import PpeChecklist from '../components/monitoring/PpeChecklist.svelte'
  import RecentHistory from '../components/monitoring/RecentHistory.svelte'
  import VideoPanel from '../components/monitoring/VideoPanel.svelte'
  import { gateView } from '../lib/gate'
  import { catalog } from '../lib/stores/catalog.svelte'
  import { telemetry } from '../lib/stores/telemetry.svelte'

  const t = $derived(telemetry.data)
  const gate = $derived(gateView(t, telemetry.status))
  const result = $derived(t?.active_track?.vlm_result ?? null)

  // Dialog kamera terbuka otomatis saat belum ada kamera, dan tertutup sendiri
  // begitu kamera tersambung — kecuali operator membukanya sendiri.
  let pickerOpen = $state(false)
  let openedByOperator = false
  let lastStatus = ''
  $effect(() => {
    const status = t?.camera.status ?? ''
    if (status === lastStatus) return
    lastStatus = status
    if (status === 'IDLE') {
      pickerOpen = true
      openedByOperator = false
    } else if (status === 'OK' && pickerOpen && !openedByOperator) {
      pickerOpen = false
    }
  })

  function pickCamera() {
    openedByOperator = true
    pickerOpen = true
  }
</script>

<div class="monitoring">
  <VideoPanel onPickCamera={pickCamera} />
  <aside>
    <DecisionPanel {gate} />
    <PpeChecklist items={catalog.active} {result} decidedBy={result?.decided_by ?? ''} gateKind={gate.kind} />
    <RecentHistory records={t?.history ?? []} />
  </aside>
</div>

<CameraPicker bind:open={pickerOpen} />

<style>
  .monitoring {
    height: calc(100vh - var(--topbar-h));
    display: grid;
    grid-template-columns: minmax(0, 1fr) 400px;
    gap: var(--space-4);
    padding: var(--space-4);
  }
  aside {
    display: grid;
    grid-template-rows: auto auto minmax(0, 1fr);
    gap: var(--space-4);
    min-height: 0;
  }
  @media (max-width: 1100px) {
    .monitoring {
      height: auto;
      grid-template-columns: 1fr;
    }
    .monitoring :global(.video) {
      height: 60vh;
    }
  }
</style>
