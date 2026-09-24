<script lang="ts">
  // Pemilihan sumber kamera. Terbuka otomatis saat belum ada kamera (IDLE),
  // atau lewat tombol "Ganti kamera". Pembukaan kamera dikerjakan thread di
  // server, jadi hasilnya ditunggu lewat polling sebelum dialog ditutup.
  import { onDestroy } from 'svelte'
  import { api } from '../../lib/api/client'
  import type { CameraCatalog, CameraMode } from '../../lib/api/types'

  let { open = $bindable(false) }: { open?: boolean } = $props()

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

  function modeLabel(m: CameraMode | null): string {
    if (!m) return ''
    return `${m.width}×${m.height}${m.fps ? ` @${Math.round(m.fps)} fps` : ''}`
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
      if (!busy) {
        status = data.scanning ? 'Mengukur kemampuan kamera…'
          : data.last_scan_time && data.last_scan_time !== '-' ? `Pemindaian terakhir pukul ${data.last_scan_time}.`
          : 'Pemindaian bersifat opsional; kamera tetap bisa langsung dipakai.'
      }
      return data
    } catch (e) {
      status = `Gagal memuat daftar kamera: ${e instanceof Error ? e.message : e}`
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
    status = 'Membuka kamera…'
    try {
      await api.selectCamera(choice)
    } catch (e) {
      busy = null
      status = `Gagal menyambungkan: ${e instanceof Error ? e.message : e}`
      return
    }
    let tries = 0
    stopPoll()
    poll = setInterval(async () => {
      tries += 1
      const data = await refresh()
      const st = data?.active.status
      if (st === 'OK' || st === 'SYNTHETIC' || tries > 25) {
        stopPoll()
        busy = null
        if (st === 'OK') open = false
        else status = 'Kamera itu tidak dapat dibuka. Pilih sumber lain.'
      }
    }, 1000)
  }

  async function scan() {
    busy = 'scan'
    status = 'Mengukur kemampuan kamera…'
    try {
      await api.scanCameras()
    } catch (e) {
      busy = null
      status = `Gagal memulai pemindaian: ${e instanceof Error ? e.message : e}`
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
    }, 1500)
  }

  async function release() {
    busy = 'release'
    try {
      await api.selectCamera(null)
      status = 'Kamera dilepas. Pilih sumber baru.'
    } catch (e) {
      status = `Gagal melepas kamera: ${e instanceof Error ? e.message : e}`
    } finally {
      busy = null
      await refresh()
    }
  }

  const activeIndex = $derived(catalog?.active.selected ? catalog.active.index : null)
</script>

<dialog bind:this={dialog} onclose={() => (open = false)} aria-labelledby="camera-picker-title">
  <h2 id="camera-picker-title">Pilih sumber kamera</h2>
  <p class="hint">Pilih kamera yang dipakai untuk inspeksi, lalu tekan <strong>Gunakan kamera ini</strong>.</p>

  <div class="list" role="radiogroup" aria-label="Kamera">
    {#if catalog && catalog.devices.length === 0}
      <p class="hint">Tidak ada kamera terdeteksi. Colokkan kamera lalu tekan Pindai.</p>
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
        <span class="name">{dev.name || `Kamera ${dev.index}`}</span>
        <span class="meta">
          index {dev.index}
          · {dev.selected_mode ? modeLabel(dev.selected_mode) : dev.scanned === false ? 'belum dipindai' : 'tidak tersedia'}
          {#if dev.index === activeIndex} · <span class="active">sedang dipakai</span>{/if}
          {#if catalog?.saved?.name && dev.name === catalog.saved.name && dev.index !== activeIndex} · terakhir dipakai{/if}
        </span>
      </button>
    {/each}
  </div>

  {#if catalog?.quality_warning}
    <p class="warn">Resolusi kamera rendah: video lebih lancar, tetapi potongan gambar untuk AI lebih kecil sehingga penilaian helm dan sepatu bisa kurang teliti.</p>
  {/if}
  <p class="status" aria-live="polite">{status}</p>

  <div class="actions">
    <button class="btn" onclick={scan} disabled={busy !== null}>{busy === 'scan' ? 'Memindai…' : 'Pindai kemampuan'}</button>
    {#if activeIndex !== null}
      <button class="btn" onclick={release} disabled={busy !== null}>Lepas kamera</button>
    {/if}
    <span class="spacer"></span>
    <button class="btn" onclick={() => (open = false)} disabled={busy === 'connect'}>Tutup</button>
    <button class="btn btn-primary" onclick={connect} disabled={choice === null || busy !== null}>
      {busy === 'connect' ? 'Menyambungkan…' : 'Gunakan kamera ini'}
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
