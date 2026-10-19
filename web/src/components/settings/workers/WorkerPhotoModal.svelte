<script lang="ts">
  // Pendaftaran wajah terpandu (T76): pendamping memegang layar, pekerja berdiri di posisi
  // pemeriksaan. Urutan foto, arah kepala, dan kunci suara datang dari rencana backend.
  import type { EnrollmentPlan, EnrollmentPreview, Worker } from '../../../lib/api/types'
  import { ENROLLMENT_GUIDE, WORKERS } from '../../../lib/messages'
  import { api } from '../../../lib/api/client'
  import { extractApiError } from '../../../lib/api/error'
  import {
    autoShotCooldown,
    autoShotDue,
    buildShots,
    fitPrompt,
    keepEnrollmentHold,
    mirrorPreview,
    pauseAutoShot,
    pollEnrollmentPreview,
    shotPrompts,
    trackAutoShot,
    type AutoShot,
    type EnrollmentShot,
  } from '../../../lib/enrollment'
  import { getConditionLabel, formatTemplateQuality } from '../../../lib/workers'
  import { telemetry } from '../../../lib/stores/telemetry.svelte'
  import { ENROLLMENT_AUTO } from '../../../lib/settings'
  import Camera from '@lucide/svelte/icons/camera'
  import LoaderCircle from '@lucide/svelte/icons/loader-circle'
  import Volume2 from '@lucide/svelte/icons/volume-2'

  interface Props {
    worker: Worker | null
    onClose: () => void
    onSaved: () => void
  }

  let { worker, onClose, onSaved }: Props = $props()

  let plan = $state<EnrollmentPlan | null>(null)
  let shots = $state<EnrollmentShot[]>([])
  let index = $state(0)
  let preview = $state<EnrollmentPreview | null>(null)
  // Belum ada jawaban pratinjau sama sekali = "memeriksa", bukan "gagal"
  let previewChecked = $state(false)
  let taking = $state(false)
  let photoError = $state('')
  let photoSuccess = $state('')
  let streamKey = $state(Date.now())
  let auto = $state<AutoShot>(pauseAutoShot(0, 0))
  // Foto ditolak (mis. wajah mirip pekerja lain): foto otomatis berhenti supaya tidak mengulang
  // penolakan yang sama terus-menerus; tombol Ambil Foto melanjutkannya
  let autoStopped = $state(false)

  const shot = $derived(shots[index] ?? null)
  const shooting = $derived(shot !== null)
  const done = $derived(shots.length > 0 && index >= shots.length)
  const asking = $derived(plan !== null && shots.length === 0)
  const distancePrompt = $derived(plan ? fitPrompt(plan, preview?.fit ?? null) : null)

  // Modal dibuka: mulai dari pertanyaan kacamata
  $effect(() => {
    if (!worker) return
    plan = null
    shots = []
    index = 0
    preview = null
    previewChecked = false
    photoError = ''
    photoSuccess = ''
    taking = false
    streamKey = Date.now()
    autoStopped = false
    api.enrollmentPlan().then(
      (p) => (plan = p),
      (e) => (photoError = extractApiError(e, ENROLLMENT_GUIDE.errPlan)),
    )
  })

  // T75: gerbang jeda selama modal terbuka, supaya orang yang difoto tidak langsung diperiksa
  $effect(() => {
    if (!worker) return
    return keepEnrollmentHold(api, () => (photoError = WORKERS.errEnrollmentHold))
  })

  // Indikator jarak hanya selama memotret
  $effect(() => {
    if (!shooting) return
    return pollEnrollmentPreview(api.enrollmentPreview, onPreview)
  })

  function onPreview(p: EnrollmentPreview | null) {
    preview = p
    previewChecked = true
    auto = trackAutoShot(auto, p, Date.now())
    if (autoShotDue(auto) && !autoStopped && !taking) takePhoto()
  }

  /** Suara berurutan di speaker gerbang (pakai helm, lalu arah kepala). */
  function speak(prompts: string[]) {
    prompts
      .reduce((chain, key) => chain.then(() => api.enrollmentPrompt(key)), Promise.resolve())
      .catch(() => (photoError = ENROLLMENT_GUIDE.errPrompt))
  }

  function start(wearsGlasses: boolean) {
    if (!plan) return
    shots = buildShots(plan, wearsGlasses)
    index = 0
    auto = pauseAutoShot(Date.now())
    speak(shotPrompts(plan, shots[0]))
  }

  async function takePhoto() {
    if (!worker || !shot || !plan) return
    photoError = ''
    photoSuccess = ''
    taking = true
    try {
      const res = await api.addWorkerTemplate(worker.id, shot.condition)
      photoSuccess = `${ENROLLMENT_GUIDE.saved(shot.number, shots.length)} (${formatTemplateQuality(res.quality)})`
      index += 1
      const next = shots[index]
      // Pekerja bisa mendaftar sendiri: ganti ke helm memakai jeda lebih panjang, bukan tombol
      auto = pauseAutoShot(Date.now(), autoShotCooldown(next))
      autoStopped = false
      speak(next ? shotPrompts(plan, next) : [plan.prompts.done])
    } catch (e) {
      photoError = extractApiError(e, WORKERS.errTakePhoto)
      autoStopped = true
    } finally {
      taking = false
    }
  }

  /** Foto yang sudah tersimpan tetap tersimpan: tabel dimuat ulang walau pendaftaran dibatalkan. */
  function close() {
    if (index > 0) onSaved()
    else onClose()
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key !== 'Escape' || !worker || taking) return
    if (done) onSaved()
    else close()
  }
</script>

<svelte:window onkeydown={onKeydown} />

{#if worker}
  <div class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-photo-title">
    <div class="modal-card">
      <div class="modal-header">
        <h3 id="modal-photo-title">
          {WORKERS.modalPhotoTitle} — {worker.name}
        </h3>
        <span class="emp-badge">{worker.employee_no}</span>
      </div>
      <p class="subtitle">{WORKERS.modalPhotoSubtitle}</p>

      {#if !done}
        <div class="camera-preview-box">
          <div class="preview-header">
            <Camera size={14} />
            <span>{WORKERS.cameraPreviewTitle}</span>
          </div>
          <div class="video-container">
            <img src="{api.streamUrl()}?t={streamKey}" alt={WORKERS.cameraPreviewTitle} class="stream-img" class:mirror={mirrorPreview(telemetry.data?.camera)} />
          </div>
          {#if mirrorPreview(telemetry.data?.camera)}<span class="preview-hint">{ENROLLMENT_GUIDE.mirrorHint}</span>{/if}
          <span class="preview-hint">{WORKERS.enrollmentHoldHint}</span>
        </div>
      {/if}

      {#if asking}
        <div class="question">
          <p>{ENROLLMENT_GUIDE.askGlasses}</p>
          <span class="preview-hint">{ENROLLMENT_GUIDE.askGlassesHint}</span>
          <div class="row">
            <button type="button" class="btn btn-primary" onclick={() => start(true)}>{ENROLLMENT_GUIDE.glassesYes}</button>
            <button type="button" class="btn btn-primary" onclick={() => start(false)}>{ENROLLMENT_GUIDE.glassesNo}</button>
          </div>
        </div>
      {:else if shot && plan}
        <div class="shot" aria-live="polite">
          <span class="step">{ENROLLMENT_GUIDE.step(shot.number, shots.length)} · {getConditionLabel(shot.condition)}</span>
          {#if shot.switchesCondition}<p class="switch">{ENROLLMENT_GUIDE.conditionSwitch}</p>{/if}
          <span class="pose">{ENROLLMENT_GUIDE.poses[shot.pose] ?? shot.pose}</span>
          {#if autoStopped}
            <span class="preview-hint">{ENROLLMENT_GUIDE.autoStopped}</span>
          {:else if shot.switchesCondition}
            <span class="preview-hint">{ENROLLMENT_GUIDE.helmetWaiting(ENROLLMENT_AUTO.switchCooldownMs / 1000)}</span>
          {:else}
            <span class="preview-hint">{ENROLLMENT_GUIDE.autoHint}</span>
          {/if}
          {#if !previewChecked}
            <span class="fit">{ENROLLMENT_GUIDE.checkingFit}</span>
          {:else if !preview}
            <span class="fit">{ENROLLMENT_GUIDE.fitUnavailable}</span>
          {:else}
            <span class="fit" class:ok={preview.fit === 'ok'}>
              {ENROLLMENT_GUIDE.fit[preview.fit]}{#if preview.interocular_px != null}
                · {ENROLLMENT_GUIDE.fitMeasured(preview.interocular_px)}{/if}{#if auto.streak > 0 && !autoStopped}
                · {ENROLLMENT_GUIDE.holdStill}{/if}
            </span>
          {/if}
          <div class="row">
            <button type="button" class="btn" onclick={() => speak(shotPrompts(plan!, shot!))}>
              <Volume2 size={14} />
              {ENROLLMENT_GUIDE.speakPose}
            </button>
            {#if distancePrompt}
              <button type="button" class="btn" onclick={() => speak([distancePrompt!])}>
                <Volume2 size={14} />
                {ENROLLMENT_GUIDE.speakFit}
              </button>
            {/if}
          </div>
        </div>
      {:else if done}
        <div class="shot" role="status">
          <span class="pose">{ENROLLMENT_GUIDE.doneTitle}</span>
          <p>{ENROLLMENT_GUIDE.doneDetail(shots.length)}</p>
        </div>
      {/if}

      {#if photoError}
        <div class="error-box" role="alert">{photoError}</div>
      {/if}

      {#if photoSuccess && !done}
        <div class="success-box" role="status">{photoSuccess}</div>
      {/if}

      <div class="modal-actions">
        {#if done}
          <button type="button" class="btn btn-primary" onclick={onSaved}>{ENROLLMENT_GUIDE.finish}</button>
        {:else}
          <button type="button" class="btn" onclick={close} disabled={taking}>{WORKERS.cancelBtn}</button>
          {#if shot}
            <button
              type="button"
              class="btn btn-primary"
              onclick={takePhoto}
              disabled={taking || preview?.fit !== 'ok'}
            >
              {#if taking}
                <span class="spin"><LoaderCircle size={14} /></span>
                {WORKERS.takingPhoto}
              {:else}
                <Camera size={14} />
                {WORKERS.takePhotoBtn}
              {/if}
            </button>
          {/if}
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: var(--backdrop);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-4);
    z-index: 100;
  }

  .modal-card {
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    padding: var(--space-6);
    width: 100%;
    max-width: 540px;
    /* Layar laptop 768 px: tombol Ambil Foto tidak boleh terdorong keluar layar */
    max-height: calc(100dvh - 2 * var(--space-4));
    overflow-y: auto;
    box-shadow: 0 10px 25px var(--backdrop);
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    margin-bottom: var(--space-1);
  }

  h3 {
    margin: 0;
    font-size: var(--text-md);
    font-weight: 600;
    color: var(--text);
  }

  .emp-badge {
    font-family: monospace;
    font-size: var(--text-xs);
    font-weight: 600;
    padding: 2px 6px;
    border-radius: var(--radius-sm);
    background: var(--surface-2);
    border: 1px solid var(--border);
    color: var(--text-muted);
  }

  .subtitle {
    margin: 0 0 var(--space-4);
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .camera-preview-box {
    margin-bottom: var(--space-4);
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .preview-header {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-muted);
  }

  .video-container {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    background: var(--bg);
    border-radius: var(--radius-md);
    overflow: hidden;
    border: 1px solid var(--border);
  }

  .stream-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  /* Pratinjau seperti cermin (keputusan pengguna 19-10): hanya tampilan, foto tetap asli */
  .mirror {
    transform: scaleX(-1);
  }

  .question,
  .shot {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin-bottom: var(--space-4);
  }

  .question p,
  .shot p {
    margin: 0;
    font-size: var(--text-sm);
    color: var(--text);
  }

  .step {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-muted);
  }

  .pose {
    font-size: var(--text-lg);
    font-weight: 600;
    color: var(--text);
  }

  .switch {
    color: var(--warn);
    font-weight: 600;
  }

  .fit {
    align-self: flex-start;
    font-size: var(--text-xs);
    font-weight: 600;
    padding: 2px 8px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--warn-line);
    background: var(--warn-soft);
    color: var(--warn);
  }

  .fit.ok {
    border-color: var(--ok-line);
    background: var(--ok-soft);
    color: var(--ok);
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .preview-hint {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .error-box {
    background: var(--danger-line);
    color: var(--danger);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    margin-bottom: var(--space-3);
  }

  .success-box {
    background: var(--ok-line);
    color: var(--ok);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    margin-bottom: var(--space-3);
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
  }

  .spin {
    display: inline-flex;
    animation: spin 1.2s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
