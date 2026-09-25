/**
 * Deteksi kejadian penting dari telemetri untuk notifikasi (logika murni, teruji).
 *
 * Notifikasi hanya untuk hal yang perlu diketahui operator saat ia tidak
 * melihat Monitoring: pekerja DITOLAK dan sistem VLM gangguan/pulih.
 */
import type { HistoryRecord, Telemetry, VlmMode } from './api/types'
import { NOTIFY } from './messages'

export interface GateEvent {
  kind: 'denied' | 'outage' | 'recovered'
  title: string
  detail: string
}

export interface WatchState {
  /** Kunci riwayat terbaru yang sudah dilihat; null = belum ada telemetri */
  lastHistoryKey: string | null
  lastMode: VlmMode | null
}

export const initialWatch = (): WatchState => ({ lastHistoryKey: null, lastMode: null })

const keyOf = (r: HistoryRecord) => `${r.track_id}|${r.timestamp}|${r.snapshot_filename}`

/** Kejadian baru sejak `prev`, beserta state berikutnya. Telemetri pertama hanya dicatat. */
export function detectEvents(prev: WatchState, t: Telemetry): { events: GateEvent[]; next: WatchState } {
  const events: GateEvent[] = []
  const history = t.history ?? []
  const next: WatchState = {
    lastHistoryKey: history.length ? keyOf(history[0]) : prev.lastHistoryKey,
    lastMode: t.api_monitor?.mode ?? prev.lastMode,
  }
  if (prev.lastHistoryKey === null && prev.lastMode === null) {
    return { events, next: { ...next, lastHistoryKey: next.lastHistoryKey ?? '' } }
  }

  // Riwayat terbaru ada di depan; kumpulkan yang belum pernah dilihat
  for (const rec of history) {
    if (keyOf(rec) === prev.lastHistoryKey) break
    if (!rec.is_complete) {
      events.push({ kind: 'denied', title: NOTIFY.denied(rec.track_id), detail: NOTIFY.missing(rec.missing_items) })
    }
  }

  if (next.lastMode !== prev.lastMode && prev.lastMode !== null && next.lastMode !== null) {
    if (next.lastMode === 'GANGGUAN') {
      events.push({ kind: 'outage', title: NOTIFY.outageTitle, detail: NOTIFY.outageDetail })
    } else if (prev.lastMode === 'GANGGUAN') {
      events.push({ kind: 'recovered', title: NOTIFY.recoveredTitle, detail: NOTIFY.recoveredDetail(next.lastMode) })
    }
  }
  return { events, next }
}
