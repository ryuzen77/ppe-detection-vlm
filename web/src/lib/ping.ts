// Uji latensi VLM (T86): satu baris per VLM aktif, dibandingkan dengan batas waktu pemeriksaannya.
// Logika murni; Pengaturan hanya merakit. Uji 20-10: ping teks "aman" padahal pemeriksaan foto habis
// waktu — kini server mengukur dengan gambar contoh, dan baris ditandai bila melebihi batas.
import type { LocalStandby, PingResult } from './api/types'
import { SETTINGS_TAB } from './messages'

export type PingTone = 'ok' | 'warn' | 'danger' | 'muted'

export interface PingRow {
  label: string
  tone: PingTone
  text: string
  hint?: string
}

const TEXT = SETTINGS_TAB.ping

/**
 * `local` = status VLM lokal siaga dari telemetri (T72). Lokal yang `unloaded` memang tidak
 * diuji server (supaya tidak memuat ±6 GB), jadi bukan kegagalan: baris netral, bukan merah.
 */
export function pingRows(res: PingResult, local?: LocalStandby | null): PingRow[] {
  const engines = res.engines ?? []
  const rows: PingRow[] = engines.map((e) => {
    const kind = e.is_local === undefined ? '' : ` (${e.is_local ? TEXT.local : TEXT.online})`
    const label = (TEXT.roles[e.role] ?? e.role) + kind
    if (!e.ok && e.is_local && local?.role === e.role && local.state === 'unloaded') {
      return { label, tone: 'muted', text: TEXT.standby, hint: TEXT.standbyHint }
    }
    if (!e.ok) {
      return { label, tone: 'danger', text: TEXT.failed(e.error ?? ''), hint: e.is_local ? TEXT.localLoading : undefined }
    }
    if (e.timeout_ms && e.latency_ms > e.timeout_ms) {
      return { label, tone: 'warn', text: TEXT.answered(e.latency_ms), hint: TEXT.overLimit(e.timeout_ms) }
    }
    return { label, tone: 'ok', text: TEXT.answered(e.latency_ms) }
  })
  if (engines.length && !engines.some((e) => e.role === 'cadangan')) {
    rows.push({ label: TEXT.roles.cadangan, tone: 'muted', text: TEXT.noBackup })
  }
  return rows
}
