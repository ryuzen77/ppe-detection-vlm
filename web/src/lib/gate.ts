/**
 * Model tampilan panel keputusan gerbang: telemetri → satu status yang jelas.
 *
 * Urutan prioritas (berbeda dari UI lama, yang menimpa keputusan dengan arahan
 * posisi bila pekerja bergeser): keputusan terkunci per sesi sampai jalur
 * kosong, jadi setelah ada hasil, hasil itulah yang tampil. Semua kalimat
 * berasal dari messages.ts.
 */
import type { ConnectionStatus } from './api/telemetry'
import type { ClipType, Telemetry } from './api/types'
import { CAMERA_FAULT, CAMERA_NOT_READY, GATE, POSITION, POSITION_FALLBACK } from './messages'

export type GateKind =
  | 'offline' // WebSocket ke server terputus
  | 'no-camera' // kamera belum dipilih / terputus
  | 'standby' // menunggu pekerja
  | 'position' // arahan posisi
  | 'analyzing' // mengumpulkan frame / menunggu VLM
  | 'granted' // APD lengkap
  | 'denied' // APD kurang
  | 'waiting' // utama & cadangan VLM gagal: mohon tunggu
  | 'enrollment' // admin memotret wajah pendaftaran: pemeriksaan dijeda (T75)
  | 'face-retry' // T83: APD lengkap, FR diulang sebelum diputuskan ("Mohon tatap kamera")
  | 'held' // T83: APD lengkap tetapi ditahan (wajah belum terdaftar / FR mati) — kuning

export type Tone = 'neutral' | 'ok' | 'danger' | 'warn'

export interface GateView {
  kind: GateKind
  tone: Tone
  title: string
  detail: string
  /** Item yang kurang (hanya 'denied') */
  missing: string[]
  /** Kemajuan 0..1 (mengumpulkan frame stabil) atau null */
  progress: number | null
  trackId: number | null
}

function positionText(clip: ClipType, reason: string): { title: string; detail: string } {
  return POSITION[clip] ?? { title: POSITION_FALLBACK.title, detail: reason || POSITION_FALLBACK.detail }
}

function view(
  kind: GateKind,
  tone: Tone,
  text: { title: string; detail?: string },
  extra: Partial<GateView> = {},
): GateView {
  return {
    kind,
    tone,
    title: text.title,
    detail: text.detail ?? '',
    missing: [],
    progress: null,
    trackId: null,
    ...extra,
  }
}

export function gateView(t: Telemetry | null, connection: ConnectionStatus): GateView {
  if (connection !== 'connected' || !t) return view('offline', 'neutral', GATE.offline)
  // Jeda pendaftaran menimpa semuanya: gerbang memang tidak sedang memeriksa siapa pun
  if (t.enrollment?.active) return view('enrollment', 'warn', GATE.enrollment)

  const a = t.active_track
  if (!a) {
    // Gangguan kamera didahulukan: statusnya bisa sekejap OK saat menyambung ulang
    if (t.camera_fault)
      return view('no-camera', 'warn', { title: GATE.noCamera.title, detail: CAMERA_FAULT[t.camera_fault].detail })
    if (t.camera.status !== 'OK') {
      return view('no-camera', 'warn', { title: GATE.noCamera.title, detail: CAMERA_NOT_READY[t.camera.status] })
    }
    return view('standby', 'neutral', GATE.standby)
  }

  const trackId = a.track_id

  if (a.state === 'WAITING_SYSTEM') {
    const retry = a.retry_in_s != null ? GATE.waiting.retry(a.retry_in_s) : ''
    return view('waiting', 'warn', { title: GATE.waiting.title, detail: GATE.waiting.detail + retry }, { trackId })
  }

  // T83: ditahan lebih dulu — APD lengkap (is_complete) tetapi gerbang TIDAK mengizinkan
  if (a.decision === 'held') {
    const detail = GATE.held.detail[a.hold_reason ?? 'unregistered']
    return view('held', 'warn', { title: GATE.held.title, detail }, { trackId })
  }

  // T83: backend mengulang FR hanya setelah APD dinilai lengkap, SEBELUM hasilnya dipasang ke sesi
  // (vlm_result masih null selama ulang FR)
  if (a.face_retry_s != null) {
    return view(
      'face-retry',
      'neutral',
      { title: GATE.faceRetry.title, detail: GATE.faceRetry.detail(a.face_retry_s) },
      { trackId },
    )
  }

  const r = a.vlm_result
  if (r && !r.is_system_unavailable) {
    return r.is_complete
      ? view('granted', 'ok', GATE.granted, { trackId })
      : view('denied', 'danger', GATE.denied, { trackId, missing: r.missing_items })
  }

  if (a.state === 'ANALYZING') return view('analyzing', 'neutral', GATE.analyzing, { trackId })

  if (!a.is_full_body) return view('position', 'warn', positionText(a.clip_type, a.reason), { trackId })

  const need = Math.max(1, t.stable_frames_required)
  return view('analyzing', 'neutral', GATE.holding, { trackId, progress: Math.min(1, a.stable_frames / need) })
}
