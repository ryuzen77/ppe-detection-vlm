<script lang="ts">
  import { onDestroy, onMount } from 'svelte'
    import Toasts from './components/Toasts.svelte'
  import TopBar from './components/TopBar.svelte'
  import { api } from './lib/api/client'
  import { detectEvents, initialWatch } from './lib/notify'
  import { router } from './lib/router.svelte'
  import { session } from './lib/stores/session.svelte'
  import { shouldShowLogin } from './lib/sessionLogic'
import Login from './pages/Login.svelte'
  import { catalog } from './lib/stores/catalog.svelte'
  import { telemetry } from './lib/stores/telemetry.svelte'
  import { toasts } from './lib/stores/toasts.svelte'
  import Laporan from './pages/Laporan.svelte'
  import Monitoring from './pages/Monitoring.svelte'
  import Pengaturan from './pages/Pengaturan.svelte'

  onMount(() => {
    router.start()
    session.load()
    catalog.load()
    // Perintah mana pun yang ditolak karena token → buka isian token
    api.onUnauthorized = () => { session.clear() }
  })
  onDestroy(() => telemetry.stop())

  $effect(() => {
    if (!shouldShowLogin(session)) {
      if (telemetry.status === 'disconnected' && !telemetry.data) {
        telemetry.start()
      }
    } else {
      telemetry.stop()
    }
  })

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
  {#if shouldShowLogin(session)}
    <Login />
  {:else if router.current === 'monitoring'}
    <Monitoring />
  {:else if router.current === 'laporan'}
    <Laporan />
  {:else}
    <Pengaturan />
  {/if}
</main>
<Toasts />

