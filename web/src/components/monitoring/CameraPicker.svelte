<script lang="ts">
  // Pemilihan sumber kamera. Terbuka otomatis saat belum ada kamera (IDLE),
  // atau lewat tombol "Ganti kamera". Pembukaan kamera dikerjakan thread di
  // server, jadi hasilnya ditunggu lewat polling sebelum dialog ditutup.
  import { onDestroy } from 'svelte'
  import { api } from '../../lib/api/client'
  import type { CameraCatalog, CameraDevice } from '../../lib/api/types'
  import { CAMERA_PICKER as TEXT, modeLabel, withError } from '../../lib/messages'
  import { formatDeviceMeta } from '../../lib/formatters'
  import { CAMERA_POLL } from '../../lib/settings'

  let { open = $bindable(false) }: { open?: boolean } = $props()

  /** Penanda backend untuk "belum pernah dipindai" */
  const NEVER_SCANNED = '-'

  let dialog: HTMLDialogElement | undefined = $state()
  let catalog = $state<CameraCatalog | null>(null)
  let choice = $state<number | null>(null)
  let status = $state('')
  let busy = $state<'connect' | 'scan' | 'release' | null>(null)
  let poll: ReturnType<typeof setInterval> | null = null

  const stopPoll = () => {
    if (poll) clearInterval(poll)
    poll = null
  }
  onDestroy(stopPoll)

  const activeIndex = $derived(catalog?.active.selected ? catalog.active.index : null)

  function scanStatus(data: CameraCatalog): string {
    if (data.scanning) return TEXT.scanning
    if (data.last_scan_time && data.last_scan_time !== NEVER_SCANNED) return TEXT.lastScan(data.last_scan_time)
    return TEXT.scanOptional
  }

  async function refresh(): Promise<CameraCatalog | null> {
    try {
      const data = await api.cameras()
      catalog = data
      if (choice === null && data.devices.length) {
        // Kamera terakhir hanya disorot sebagai bawaan; tetap harus dikonfirmasi
        const saved = data.devices.find((d) => data.saved?.name && d.name === data.saved.name)
        choice = saved ? saved.index : data.devices[0].index
      }
      if (!busy) status = scanStatus(data)
      return data
    } catch (e) {
      status = withError(TEXT.loadFailed, e)
      return null
    }
  }

  $effect(() => {
    if (!dialog) return
    if (open && !dialog.open) {
      choice = null
      dialog.showModal()
      refresh()
    } else if (!open && dialog.open) {
      dialog.close()
    }
  })

  async function connect() {
    if (choice === null) return
    busy = 'connect'
    status = TEXT.opening
    try {
      await api.selectCamera(choice)
    } catch (e) {
      busy = null
      status = withError(TEXT.connectFailed, e)
      return
    }
    let tries = 0
    stopPoll()
    poll = setInterval(async () => {
      tries += 1
      const data = await refresh()
      const st = data?.active.status
      if (st === 'OK' || st === 'SYNTHETIC' || tries > CAMERA_POLL.connectMaxTries) {
        stopPoll()
        busy = null
        if (st === 'OK') open = false
        else status = TEXT.cannotOpen
      }
    }, CAMERA_POLL.connectPollMs)
  }

  async function scan() {
    busy = 'scan'
    status = TEXT.scanning
    try {
      await api.scanCameras()
    } catch (e) {
      busy = null
      status = withError(TEXT.scanFailed, e)
      return
    }
    stopPoll()
    poll = setInterval(async () => {
      const data = await refresh()
      if (data && !data.scanning) {
        stopPoll()
        busy = null
        await refresh()
      }
    }, CAMERA_POLL.scanPollMs)
  }

  async function release() {
    busy = 'release'
    try {
      await api.selectCamera(null)
      status = TEXT.released
    } catch (e) {
      status = withError(TEXT.releaseFailed, e)
    } finally {
      busy = null
      await refresh()
    }
  }
</script>

<dialog bind:this={dialog} onclose={() => (open = false)} aria-labelledby="camera-picker-title">
  <h2 id="camera-picker-title">{TEXT.title}</h2>
  <p class="hint">{TEXT.hintBefore} <strong>{TEXT.confirm}</strong>.</p>

  <div class="list" role="radiogroup" aria-label={TEXT.listLabel}>
    {#if catalog && catalog.devices.length === 0}
      <p class="hint">{TEXT.none}</p>
    {/if}
    {#each catalog?.devices ?? [] as dev (dev.index)}
      <button
        type="button"
        role="radio"
        aria-checked={dev.index === choice}
        class="device"
        class:selected={dev.index === choice}
        onclick={() => (choice = dev.index)}
      >
        <span class="name">{dev.name || TEXT.deviceFallback(dev.index)}</span>
        <span class="meta">
          {formatDeviceMeta(dev)}
          {#if dev.index === activeIndex}
            · <span class="active">{TEXT.inUse}</span>{/if}
          {#if catalog?.saved?.name && dev.name === catalog.saved.name && dev.index !== activeIndex}
            · {TEXT.lastUsed}{/if}
        </span>
      </button>
    {/each}
  </div>

  {#if catalog?.quality_warning}
    <p class="warn">{TEXT.lowQuality}</p>
  {/if}
  <p class="status" aria-live="polite">{status}</p>

  <div class="actions">
    <button class="btn" onclick={scan} disabled={busy !== null}>{busy === 'scan' ? TEXT.scanBusy : TEXT.scan}</button>
    {#if activeIndex !== null}
      <button class="btn" onclick={release} disabled={busy !== null}>{TEXT.release}</button>
    {/if}
    <span class="spacer"></span>
    <button class="btn" onclick={() => (open = false)} disabled={busy === 'connect'}>{TEXT.close}</button>
    <button class="btn btn-primary" onclick={connect} disabled={choice === null || busy !== null}>
      {busy === 'connect' ? TEXT.connecting : TEXT.confirm}
    </button>
  </div>
</dialog>

<style>
  dialog {
    width: min(520px, calc(100vw - 32px));
    padding: var(--space-6);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    background: var(--surface);
    color: var(--text);
  }
  dialog::backdrop {
    background: rgba(0, 0, 0, 0.6);
  }
  h2 {
    margin: 0 0 var(--space-2);
    font-size: var(--text-lg);
  }
  .hint {
    margin: 0 0 var(--space-4);
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
  .list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    max-height: 280px;
    overflow-y: auto;
  }
  .device {
    display: flex;
    flex-direction: column;
    gap: 2px;
    text-align: left;
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface-2);
    cursor: pointer;
  }
  .device:hover {
    border-color: var(--border-strong);
  }
  .device.selected {
    border-color: var(--accent);
    background: var(--accent-soft);
  }
  .name {
    font-weight: 600;
  }
  .meta {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }
  .active {
    color: var(--ok);
  }
  .warn {
    color: var(--warn);
    font-size: var(--text-sm);
  }
  .status {
    min-height: 1.4em;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
  .actions {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }
  .spacer {
    flex: 1;
  }
</style>
