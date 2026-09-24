<script lang="ts">
  // Video kamera + overlay jalur inspeksi. Aliran MJPEG hanya hidup selama
  // komponen ini tampil: saat operator pindah halaman, komponen dilepas dan
  // aliran diputus (UI lama tetap mengunduhnya walau tersembunyi).
  import Camera from '@lucide/svelte/icons/camera'
  import VideoOff from '@lucide/svelte/icons/video-off'
  import Eye from '@lucide/svelte/icons/eye'
  import EyeOff from '@lucide/svelte/icons/eye-off'
  import RotateCcw from '@lucide/svelte/icons/rotate-ccw'
  import Volume2 from '@lucide/svelte/icons/volume-2'
  import VolumeX from '@lucide/svelte/icons/volume-x'
  import { onDestroy, onMount } from 'svelte'
  import { api } from '../../lib/api/client'
  import { drawHud } from '../../lib/hud'
  import { telemetry } from '../../lib/stores/telemetry.svelte'

  let { onPickCamera }: { onPickCamera: () => void } = $props()

  const GUIDES_KEY = 'safeguard_guides_visible'
  function loadGuides(): boolean {
    try {
      return localStorage.getItem(GUIDES_KEY) !== 'false'
    } catch {
      return true
    }
  }

  let img: HTMLImageElement | undefined = $state()
  let canvas: HTMLCanvasElement | undefined = $state()
  let frame: HTMLDivElement | undefined = $state()
  let size = $state({ w: 0, h: 0 })
  let guides = $state(loadGuides())
  let streamKey = $state(Date.now())
  let message = $state('')

  const t = $derived(telemetry.data)
  const cameraOk = $derived(t?.camera.status === 'OK')
  const muted = $derived(t?.audio_muted ?? false)

  // Aliran dimuat ulang saat kamera berganti atau baru tersambung kembali
  let lastCamera = ''
  $effect(() => {
    const c = t?.camera
    const key = c ? `${c.index}|${c.status === 'OK'}` : ''
    if (key !== lastCamera) {
      lastCamera = key
      streamKey = Date.now()
    }
  })

  $effect(() => {
    if (!canvas) return
    canvas.width = size.w
    canvas.height = size.h
    const ctx = canvas.getContext('2d')
    if (ctx) drawHud(ctx, size.w, size.h, t, guides)
  })

  let observer: ResizeObserver | null = null
  onMount(() => {
    if (!frame) return
    observer = new ResizeObserver(([entry]) => {
      size = { w: Math.round(entry.contentRect.width), h: Math.round(entry.contentRect.height) }
    })
    observer.observe(frame)
  })
  onDestroy(() => {
    observer?.disconnect()
    // Memutus koneksi MJPEG secara eksplisit; menghapus elemen saja tidak
    // selalu membatalkan unduhan di semua browser.
    if (img) img.src = ''
  })

  function toggleGuides() {
    guides = !guides
    try {
      localStorage.setItem(GUIDES_KEY, String(guides))
    } catch {
      // penyimpanan diblokir: pilihan berlaku selama halaman terbuka
    }
  }

  async function run(action: () => Promise<unknown>, failText: string) {
    message = ''
    try {
      await action()
    } catch (e) {
      message = `${failText}: ${e instanceof Error ? e.message : e}`
    }
  }
</script>

<section class="video" aria-label="Kamera inspeksi">
  <div class="frame" bind:this={frame}>
    {#if cameraOk}
      <!-- Video & overlay hanya saat kamera siap: frame tunggu dari backend
           tidak diunduh dan tidak bertumpuk dengan placeholder di bawah. -->
      <img bind:this={img} src={api.streamUrl() + `?t=${streamKey}`} alt="Video kamera gerbang" />
      <canvas bind:this={canvas} aria-hidden="true"></canvas>
    {:else}
      <div class="placeholder">
        <VideoOff size={40} strokeWidth={1.5} aria-hidden="true" />
        <p>
          {!t ? 'Menunggu server…'
            : t.camera.status === 'IDLE' ? 'Kamera belum dipilih'
            : t.camera.status === 'LOST' ? 'Kamera terputus — menyambung ulang…'
            : t.camera.status === 'SYNTHETIC' ? 'Kamera tidak dapat dibuka'
            : 'Menyiapkan kamera…'}
        </p>
        {#if t}<button class="btn btn-primary" onclick={onPickCamera}><Camera size={16} /> Pilih kamera</button>{/if}
      </div>
    {/if}
  </div>

  <div class="controls">
    <span class="camera-name">
      {#if t?.camera.selected}
        <Camera size={14} aria-hidden="true" /> {t.camera.name} · <span class="mono">{t.camera.width}×{t.camera.height}</span>
      {/if}
    </span>
    {#if message}<span class="error" role="alert">{message}</span>{/if}
    <button class="btn" onclick={toggleGuides} aria-pressed={guides} title="Tampilkan jalur inspeksi & area pijakan">
      {#if guides}<Eye size={16} />{:else}<EyeOff size={16} />{/if} Panduan
    </button>
    <button class="btn" onclick={() => run(() => api.setAudioMuted(!muted), 'Gagal mengubah suara')} aria-pressed={!muted}>
      {#if muted}<VolumeX size={16} /> Senyap{:else}<Volume2 size={16} /> Suara{/if}
    </button>
    <button class="btn" onclick={onPickCamera}><Camera size={16} /> Ganti kamera</button>
    <button class="btn" onclick={() => run(() => api.reset(), 'Gagal memulai ulang')} title="Mulai ulang sesi pemeriksaan">
      <RotateCcw size={16} /> Mulai ulang
    </button>
  </div>
</section>

<style>
  .video {
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }
  .frame {
    position: relative;
    flex: 1;
    min-height: 0;
    background: #000;
  }
  img,
  canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }
  img {
    object-fit: contain;
  }
  .placeholder {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-3);
    background: var(--surface-2);
    color: var(--text-faint);
  }
  .placeholder p {
    color: var(--text-muted);
  }
  .placeholder p {
    margin: 0;
  }
  .controls {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    border-top: 1px solid var(--border);
  }
  .camera-name {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-right: auto;
    color: var(--text-muted);
    font-size: var(--text-sm);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .error {
    color: var(--danger);
    font-size: var(--text-sm);
  }
</style>
