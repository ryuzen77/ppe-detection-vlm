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
  import { releaseStream } from '../../lib/mjpeg'
  import { drawHud, readHudPalette, type HudPalette } from '../../lib/hud'
  import { VIDEO, withError } from '../../lib/messages'
  import { STORAGE } from '../../lib/settings'
  import { readFlag, writeFlag } from '../../lib/storage'
  import { telemetry } from '../../lib/stores/telemetry.svelte'

  let { onPickCamera }: { onPickCamera: () => void } = $props()

  let canvas: HTMLCanvasElement | undefined = $state()
  let frame: HTMLDivElement | undefined = $state()
  let size = $state({ w: 0, h: 0 })
  let guides = $state(readFlag(STORAGE.guidesVisible, true))
  let streamKey = $state(Date.now())
  let message = $state('')
  let palette: HudPalette | null = null

  const t = $derived(telemetry.data)
  const cameraOk = $derived(t?.camera.status === 'OK')
  const muted = $derived(t?.audio_muted ?? false)
  const placeholder = $derived(t ? VIDEO.placeholder[t.camera.status] : VIDEO.waitingServer)

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
    // Warna overlay dari token CSS (dibaca sekali, setelah stylesheet termuat)
    palette ??= readHudPalette()
    if (ctx) drawHud(ctx, size.w, size.h, t, guides, palette)
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
  })

  function toggleGuides() {
    guides = !guides
    writeFlag(STORAGE.guidesVisible, guides)
  }

  async function run(action: () => Promise<unknown>, failText: string) {
    message = ''
    try {
      await action()
    } catch (e) {
      message = withError(failText, e)
    }
  }
</script>

<section class="video" aria-label={VIDEO.ariaLabel}>
  <div class="frame" bind:this={frame}>
    {#if cameraOk}
      <!-- Video & overlay hanya saat kamera siap: frame tunggu dari backend
           tidak diunduh dan tidak bertumpuk dengan placeholder di bawah. -->
      <!-- releaseStream: koneksi MJPEG diputus tiap kali <img> dilepas (kamera putus, pindah halaman) -->
      <img use:releaseStream src={`${api.streamUrl()}?t=${streamKey}`} alt={VIDEO.alt} />
      <canvas bind:this={canvas} aria-hidden="true"></canvas>
    {:else}
      <div class="placeholder">
        <VideoOff size={40} strokeWidth={1.5} aria-hidden="true" />
        <p>{placeholder}</p>
        {#if t}<button class="btn btn-primary" onclick={onPickCamera}><Camera size={16} /> {VIDEO.pickCamera}</button
          >{/if}
      </div>
    {/if}
  </div>

  <div class="controls">
    <span class="camera-name">
      {#if t?.camera.selected}
        <Camera size={14} aria-hidden="true" />
        {t.camera.name} · <span class="mono">{t.camera.width}×{t.camera.height}</span>
      {/if}
    </span>
    {#if message}<span class="error" role="alert">{message}</span>{/if}
    <button class="btn" onclick={toggleGuides} aria-pressed={guides} title={VIDEO.guidesHint}>
      {#if guides}<Eye size={16} />{:else}<EyeOff size={16} />{/if}
      {VIDEO.guides}
    </button>
    <button class="btn" onclick={() => run(() => api.setAudioMuted(!muted), VIDEO.soundFailed)} aria-pressed={!muted}>
      {#if muted}<VolumeX size={16} /> {VIDEO.muted}{:else}<Volume2 size={16} /> {VIDEO.sound}{/if}
    </button>
    <button class="btn" onclick={onPickCamera}><Camera size={16} /> {VIDEO.changeCamera}</button>
    <button class="btn" onclick={() => run(() => api.reset(), VIDEO.resetFailed)} title={VIDEO.resetHint}>
      <RotateCcw size={16} />
      {VIDEO.reset}
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
    flex-wrap: wrap;
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
  @media (max-width: 400px) {
    .controls .btn {
      flex: 1 1 40%;
      padding: var(--space-2) var(--space-1);
      font-size: var(--text-xs);
    }
    .camera-name {
      width: 100%;
      margin-bottom: var(--space-2);
    }
  }
</style>
