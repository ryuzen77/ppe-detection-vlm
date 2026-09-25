/** Status kamera & VLM → nada warna + teks chip (logika murni, teruji). */
import type { Telemetry } from './api/types'
import type { Tone } from './gate'
import { CAMERA_CHIP, VLM_CHIP, cameraChipOk } from './messages'

export interface Chip {
  tone: Tone
  text: string
  hint: string
}

export function cameraChip(t: Telemetry | null): Chip {
  const c = t?.camera
  if (!c) return { tone: 'neutral', text: CAMERA_CHIP.UNKNOWN, hint: '' }
  const tone: Tone = c.status === 'OK' ? 'ok' : c.status === 'LOST' ? 'danger' : 'warn'
  const text = c.status === 'OK' ? cameraChipOk(t!.fps) : CAMERA_CHIP[c.status]
  return { tone, text, hint: c.name }
}

const VLM_TONE: Record<string, Tone> = { UTAMA: 'ok', CADANGAN: 'warn', GANGGUAN: 'danger' }

/** Nama penyedia/model sengaja tidak ditampilkan (keputusan pengguna): hanya status umum */
export function vlmChip(t: Telemetry | null): Chip {
  const mode = t?.api_monitor?.mode
  const label = mode ? VLM_CHIP[mode] : VLM_CHIP.UNKNOWN
  return { tone: (mode && VLM_TONE[mode]) || 'neutral', text: label.text, hint: label.hint }
}
