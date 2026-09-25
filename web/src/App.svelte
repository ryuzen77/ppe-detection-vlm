<script lang="ts">
  import { onDestroy, onMount } from 'svelte'
  import Toasts from './components/Toasts.svelte'
  import TopBar from './components/TopBar.svelte'
  import { PAGES } from './lib/messages'
  import { detectEvents, initialWatch } from './lib/notify'
  import { router } from './lib/router.svelte'
  import { catalog } from './lib/stores/catalog.svelte'
  import { telemetry } from './lib/stores/telemetry.svelte'
  import { toasts } from './lib/stores/toasts.svelte'
  import Monitoring from './pages/Monitoring.svelte'
  import NotYetMigrated from './pages/NotYetMigrated.svelte'

  onMount(() => {
    router.start()
    telemetry.start()
    catalog.load()
  })
  onDestroy(() => telemetry.stop())

  // Notifikasi kejadian penting hanya saat operator TIDAK melihat Monitoring;
  // di Monitoring panel keputusan sudah menampilkannya.
  let watch = initialWatch()
  $effect(() => {
    const data = telemetry.data
    if (!data) return
    const { events, next } = detectEvents(watch, data)
    watch = next
    if (router.current !== 'monitoring') events.forEach((e) => toasts.push(e))
  })
  $effect(() => {
    if (router.current === 'monitoring') toasts.clear()
  })
</script>

<TopBar />
<main>
  {#if router.current === 'monitoring'}
    <Monitoring />
  {:else if router.current === 'laporan'}
    <NotYetMigrated {...PAGES.laporan} />
  {:else}
    <NotYetMigrated {...PAGES.pengaturan} />
  {/if}
</main>
<Toasts />
