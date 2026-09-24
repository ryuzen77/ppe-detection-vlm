/**
 * Model tampilan panel keputusan gerbang: telemetri → satu status yang jelas.
 *
 * Urutan prioritas (berbeda dari UI lama, yang menimpa keputusan dengan arahan
 * posisi bila pekerja bergeser): keputusan terkunci per sesi sampai jalur
 * kosong, jadi setelah ada hasil, hasil itulah yang tampil.
 */
import type { ConnectionStatus } from './api/telemetry'
import type { ClipType, Telemetry } from './api/types'

export type GateKind =
  | 'offline' // WebSocket ke server terputus
  | 'no-camera' // kamera belum dipilih / terputus
  | 'standby' // menunggu pekerja
  | 'position' // arahan posisi
  | 'analyzing' // mengumpulkan frame / menunggu VLM
  | 'granted' // APD lengkap
  | 'denied' // APD kurang
  | 'waiting' // utama & cadangan VLM gagal: mohon tunggu

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

const POSITION_TEXT: Record<string, [string, string]> = {
  HEAD_CLIPPED: ['Mundur sedikit', 'Kepala terlalu dekat dengan kamera.'],
  FEET_CLIPPED: ['Mundur satu langkah', 'Kepala hingga kaki harus terlihat di kamera.'],
  TOO_FAR: ['Silakan mendekat', 'Posisi pekerja terlalu jauh dari kamera.'],
  TOO_CLOSE: ['Silakan mundur', 'Terlalu dekat ke kamera.'],
}

function positionText(clip: ClipType, reason: string): [string, string] {
  return POSITION_TEXT[clip] ?? ['Silakan mundur', reason || 'Seluruh tubuh harus terlihat di kamera.']
}

function view(kind: GateKind, tone: Tone, title: string, detail: string, extra: Partial<GateView> = {}): GateView {
  return { kind, tone, title, detail, missing: [], progress: null, trackId: null, ...extra }
}

export function gateView(t: Telemetry | null, connection: ConnectionStatus): GateView {
  if (connection !== 'connected' || !t) {
    return view('offline', 'neutral', 'Server tidak terhubung',
      'Menyambung ulang ke server secara otomatis…')
  }

  const a = t.active_track
  if (!a) {
    if (t.camera.status !== 'OK') {
      const detail = t.camera.status === 'IDLE' ? 'Pilih sumber kamera untuk memulai pemeriksaan.'
        : t.camera.status === 'OPENING' ? 'Membuka kamera…'
        : t.camera.status === 'OPTIMIZING' ? 'Mengukur mode terbaik kamera…'
        : t.camera.status === 'LOST' ? 'Kamera terputus, menyambung ulang…'
        : 'Kamera tidak dapat dibuka.'
      return view('no-camera', 'warn', 'Kamera belum siap', detail)
    }
    return view('standby', 'neutral', 'Menunggu pekerja', 'Pekerja silakan berdiri di dalam jalur inspeksi.')
  }

  const trackId = a.track_id

  if (a.state === 'WAITING_SYSTEM') {
    const retry = a.retry_in_s != null ? ` Diperiksa ulang otomatis dalam ${Math.ceil(a.retry_in_s)} dtk.` : ''
    return view('waiting', 'warn', 'Mohon tunggu',
      `Sistem pemeriksaan sedang gangguan.${retry}`, { trackId })
  }

  const r = a.vlm_result
  if (r && !r.is_system_unavailable) {
    if (r.is_complete) {
      return view('granted', 'ok', 'Lolos', 'APD lengkap — akses diizinkan.', { trackId })
    }
    return view('denied', 'danger', 'Ditolak', 'APD belum lengkap — akses ditolak.',
      { trackId, missing: r.missing_items })
  }

  if (a.state === 'ANALYZING') {
    return view('analyzing', 'neutral', 'Menganalisis APD…', 'Posisi sudah pas. Pekerja mohon diam sejenak.',
      { trackId })
  }

  if (!a.is_full_body) {
    const [title, detail] = positionText(a.clip_type, a.reason)
    return view('position', 'warn', title, detail, { trackId })
  }

  const need = Math.max(1, t.stable_frames_required)
  return view('analyzing', 'neutral', 'Posisi pas', 'Menahan posisi sebelum dianalisis…',
    { trackId, progress: Math.min(1, a.stable_frames / need) })
}
