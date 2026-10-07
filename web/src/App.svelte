<script lang="ts">
  import { onDestroy, onMount } from 'svelte'
  import Toasts from './components/Toasts.svelte'
  import TopBar from './components/TopBar.svelte'
  import { api } from './lib/api/client'
  import { detectEvents, initialWatch } from './lib/notify'
  import { router } from './lib/router.svelte'
  import { session } from './lib/stores/session.svelte'
  import { getViewState, telemetryAction, shouldLoadData } from './lib/sessionLogic'
  import Login from './pages/Login.svelte'
  import Setup from './pages/Setup.svelte'
  import { catalog } from './lib/stores/catalog.svelte'
  import { telemetry } from './lib/stores/telemetry.svelte'
  import { toasts } from './lib/stores/toasts.svelte'
  import Laporan from './pages/Laporan.svelte'
  import Monitoring from './pages/Monitoring.svelte'
  import Pengaturan from './pages/Pengaturan.svelte'

  let view = $derived(getViewState(session))
  let prevState = $state({ authenticated: false, setupRequired: false, loaded: false })

  onMount(() => {
    router.start()
    session.load()
    api.onUnauthorized = () => { session.clear() }
  })
  onDestroy(() => telemetry.stop())

  $effect(() => {
    if (shouldLoadData(prevState, session)) {
      catalog.load()
    }
    prevState = { 
      authenticated: session.authenticated, 
      setupRequired: session.setupRequired, 
      loaded: session.loaded 
    }
  })

  $effect(() => {
    const action = telemetryAction(session)
    if (action === 'start') {
      telemetry.start()
    } else if (action === 'stop') {
      telemetry.stop()
    }
  })

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
  {#if view === 'loading'}
    <div>Memuat sesi...</div>
  {:else if view === 'setup'}
    <Setup />
  {:else if view === 'login'}
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
