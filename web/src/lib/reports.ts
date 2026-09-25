/** Logika tampilan halaman Laporan (murni, teruji). Teks di messages.ts, angka di settings.ts. */
import type { HistoryRecord, ReportRecord } from './api/types'
import { describeSource, type SourceRole } from './format'
import type { Tone } from './gate'
import { REPORTS as TEXT } from './messages'
import { REPORTS } from './settings'

export type ResultKind = 'passed' | 'denied' | 'unverified'

/** Awalan sumber baris lama (T21–T26) yang ditolak karena VLM tidak menjawab */
const LEGACY_UNVERIFIED_PREFIX = 'VLM_GAGAL'

export function resultKind(rec: Pick<ReportRecord, 'is_complete' | 'inference_source'>): ResultKind {
  if (rec.is_complete) return 'passed'
  return (rec.inference_source ?? '').startsWith(LEGACY_UNVERIFIED_PREFIX) ? 'unverified' : 'denied'
}

export const RESULT_TONE: Record<ResultKind, Tone> = { passed: 'ok', denied: 'danger', unverified: 'warn' }

/** Siapa yang menilai, tanpa nama penyedia/model (keputusan pengguna) */
export function sourceText(source: string): { role: SourceRole; text: string } {
  const { role } = describeSource(source)
  return { role, text: TEXT.source[role] }
}

export interface PageInfo {
  /** Nomor baris pertama & terakhir di halaman ini (1-based), 0 bila kosong */
  from: number
  to: number
  total: number
  hasPrev: boolean
  hasNext: boolean
}

export function pageInfo(offset: number, shown: number, total: number): PageInfo {
  if (total <= 0 || shown <= 0) return { from: 0, to: 0, total: Math.max(0, total), hasPrev: offset > 0, hasNext: false }
  return {
    from: offset + 1,
    to: offset + shown,
    total,
    hasPrev: offset > 0,
    hasNext: offset + shown < total,
  }
}

/** Nada meter kepatuhan (fill membawa tingkat keparahan) */
export function complianceTone(rate: number): Tone {
  if (rate >= REPORTS.complianceGood) return 'ok'
  if (rate >= REPORTS.complianceWarn) return 'warn'
  return 'danger'
}

/** Batasi 0..100 untuk lebar meter */
export const clampPercent = (n: number): number => Math.min(100, Math.max(0, Number.isFinite(n) ? n : 0))

/**
 * Penanda pemeriksaan terbaru dari riwayat telemetri. Berubah → ada baris audit
 * baru, jadi halaman Laporan memuat ulang tanpa polling terpisah.
 */
export function historyHead(history: ReadonlyArray<Pick<HistoryRecord, 'track_id' | 'timestamp' | 'snapshot_filename'>> | null | undefined): string {
  const h = history?.[0]
  return h ? `${h.track_id}|${h.timestamp}|${h.snapshot_filename}` : ''
}
