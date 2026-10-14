/**
 * Logika murni pemeriksaan kesehatan VLM lokal (T56-UI).
 * Sesuai Kontrak T56 di docs/RENCANA.md.
 */
import type { LocalVlmHealth, LocalVlmState } from './api/types'
import { LOCAL_VLM } from './messages'

export interface LocalVlmChip {
  tone: 'warn'
  text: string
  hint: string
}

/**
 * Chip operator di bilah atas hanya tampil bila VLM cadangan mengalami masalah:
 * lambat ('slow') atau sebagian model jatuh ke CPU ('partial_gpu').
 * Kondisi 'ok' dan 'unknown' tidak memunculkan chip (unknown = kondisi normal
 * saat server baru menyala atau tanpa VLM lokal).
 */
export function shouldShowLocalVlmChip(health: LocalVlmHealth | null | undefined): boolean {
  if (!health) return false
  return health.state === 'slow' || health.state === 'partial_gpu'
}

/**
 * Tampilan chip untuk operator. Tanpa nama model/penyedia (AGENTS.md §5).
 */
export function localVlmChipView(health: LocalVlmHealth | null | undefined): LocalVlmChip | null {
  if (!shouldShowLocalVlmChip(health)) return null
  const config = health!.state === 'slow' ? LOCAL_VLM.chips.slow : LOCAL_VLM.chips.partial_gpu
  return {
    tone: 'warn',
    text: config.text,
    hint: config.hint,
  }
}

/**
 * Teks label status untuk halaman Pengaturan admin.
 */
export function localVlmStatusText(state: LocalVlmState | null | undefined): string {
  if (state && state in LOCAL_VLM.states) {
    return LOCAL_VLM.states[state]
  }
  return LOCAL_VLM.states.unknown
}

/**
 * Format porsi model di GPU dalam persen, misal 1.0 -> '100%'.
 * Nilai null/undefined ditampilkan '—'.
 */
export function formatGpuRatio(ratio: number | null | undefined): string {
  if (ratio == null || typeof ratio !== 'number' || Number.isNaN(ratio)) {
    return LOCAL_VLM.emptyValue
  }
  return `${Math.round(ratio * 100)}%`
}

/**
 * Format latensi inspeksi terakhir dalam detik, misal 3.6 -> '3.6 dtk'.
 * Nilai null/undefined ditampilkan '—'.
 */
export function formatLatency(latency: number | null | undefined): string {
  if (latency == null || typeof latency !== 'number' || Number.isNaN(latency)) {
    return LOCAL_VLM.emptyValue
  }
  return `${latency.toFixed(1)} dtk`
}

/**
 * Format daftar proses/aplikasi lain di GPU NVIDIA.
 * Daftar kosong ditampilkan 'Tidak ada'.
 */
export function formatOtherGpuApps(apps: string[] | null | undefined): string {
  if (!apps || apps.length === 0) {
    return LOCAL_VLM.noApps
  }
  return apps.join(', ')
}

/**
 * Cek apakah ada aplikasi lain di GPU untuk menentukan apakah banner peringatan tampil.
 */
export function hasOtherGpuApps(apps: string[] | null | undefined): boolean {
  return Boolean(apps && apps.length > 0)
}
