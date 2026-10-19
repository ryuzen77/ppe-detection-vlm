/**
 * Mode pendaftaran wajah (T75): selama modal foto terbuka gerbang jeda, supaya orang yang
 * difoto tidak langsung diperiksa (uji nyata 19-10: foto selalu ditolak `camera_busy`).
 */
import type {
  CameraStatus,
  EnrollmentFit,
  EnrollmentHoldResponse,
  EnrollmentPlan,
  EnrollmentPreview,
  TemplateCondition,
} from './api/types'
import { ENROLLMENT_HOLD } from './settings'

export interface EnrollmentClient {
  holdEnrollment: () => Promise<EnrollmentHoldResponse>
  releaseEnrollment: () => Promise<void>
}

/**
 * Mulai jeda lalu kirim denyut beberapa kali dalam satu batas waktu backend (`hold_s` dari
 * server, bukan angka salinan). Mengembalikan fungsi penutup (dipakai sebagai cleanup $effect).
 */
export function keepEnrollmentHold(client: EnrollmentClient, onError: () => void): () => void {
  let timer: ReturnType<typeof setInterval> | undefined
  let closed = false
  // Gagal melepas tidak berbahaya: tanpa denyut, backend mengakhiri jeda sendiri
  const release = () => client.releaseEnrollment().catch(() => {})
  client.holdEnrollment().then(
    (res) => {
      // Modal ditutup sebelum jeda pertama terjawab: lepas lagi supaya gerbang tidak tertahan
      if (closed) return void release()
      timer = setInterval(
        () => client.holdEnrollment().catch(onError),
        (res.hold_s * 1000) / ENROLLMENT_HOLD.beatsPerHold,
      )
    },
    onError,
  )
  return () => {
    closed = true
    clearInterval(timer)
    release()
  }
}

// --- Pendaftaran terpandu (T76) ---

export interface EnrollmentShot {
  /** Nomor foto 1..total */
  number: number
  condition: TemplateCondition
  /** Arah kepala = kunci suara petunjuk */
  pose: string
  /** Foto pertama kondisi kedua: pekerja perlu memakai helm dulu */
  switchesCondition: boolean
}

/** Urutan foto dari rencana backend: semua foto kondisi pertama, lalu kondisi kedua. */
export function buildShots(plan: EnrollmentPlan, wearsGlasses: boolean): EnrollmentShot[] {
  const conditions = plan.condition_sets[wearsGlasses ? 'glasses' : 'no_glasses']
  const per = plan.shots_per_condition
  return conditions.flatMap((condition, c) =>
    Array.from({ length: per }, (_, i) => ({
      number: c * per + i + 1,
      condition,
      pose: plan.poses[i % plan.poses.length],
      switchesCondition: c > 0 && i === 0,
    })),
  )
}

/** Suara sebelum memotret: ganti kondisi (pakai helm) lebih dulu, lalu arah kepala. */
export function shotPrompts(plan: EnrollmentPlan, shot: EnrollmentShot): string[] {
  return shot.switchesCondition ? [plan.prompts.condition_switch, shot.pose] : [shot.pose]
}

/** Suara arahan jarak (maju/mundur) atau null bila tidak ada yang perlu diucapkan. */
export function fitPrompt(plan: EnrollmentPlan, fit: EnrollmentFit | null): string | null {
  return (fit && plan.prompts.fit[fit]) || null
}

/**
 * Indikator jarak: periksa kamera berulang tanpa permintaan bertumpuk (berikutnya dijadwalkan
 * setelah jawaban tiba). Gagal = null (mis. jeda belum aktif). Mengembalikan fungsi penghenti.
 */
export function pollEnrollmentPreview(
  fetchPreview: () => Promise<EnrollmentPreview>,
  onResult: (preview: EnrollmentPreview | null) => void,
  intervalMs: number = ENROLLMENT_HOLD.previewIntervalMs,
): () => void {
  let stopped = false
  let timer: ReturnType<typeof setTimeout> | undefined
  const tick = () => {
    fetchPreview()
      .then(
        (preview) => !stopped && onResult(preview),
        () => !stopped && onResult(null),
      )
      .finally(() => {
        if (!stopped) timer = setTimeout(tick, intervalMs)
      })
  }
  tick()
  return () => {
    stopped = true
    clearTimeout(timer)
  }
}

/**
 * Pratinjau dibalik seperti cermin hanya untuk gambar kamera sungguhan: layar pesan server
 * (kamera belum dipilih / terputus) berisi tulisan yang akan terbaca terbalik.
 */
export function mirrorPreview(camera: CameraStatus | null | undefined): boolean {
  return camera?.status === 'OK' && !camera.is_synthetic
}
