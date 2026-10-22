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
  if (total <= 0 || shown <= 0)
    return { from: 0, to: 0, total: Math.max(0, total), hasPrev: offset > 0, hasNext: false }
  return {
    from: offset + 1,
    to: offset + shown,
    total,
    hasPrev: offset > 0,
    hasNext: offset + shown < total,
  }
}

/** Nada meter kepatuhan (fill membawa tingkat keparahan) */
export function complianceTone(rate: number | null): Tone {
  if (rate === null) return 'neutral'
  if (rate >= REPORTS.complianceGood) return 'ok'
  if (rate >= REPORTS.complianceWarn) return 'warn'
  return 'danger'
}

export function offsetDate(base: string, days: number): string {
  if (!base) return ''
  const d = new Date(base + 'T00:00:00')
  d.setDate(d.getDate() + days)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function formatReportRange(from: string, to: string, formatDate: (d: string) => string): string {
  if (from === to) return formatDate(from)
  return `${formatDate(from)} – ${formatDate(to)}`
}

export interface YAxisTick {
  y: number
  value: number
}

export function calculateYAxis(maxTotal: number, paddingY: number, usableHeight: number): YAxisTick[] {
  const safeMax = Math.max(0, Math.ceil(maxTotal))
  let step: number
  let yMax: number

  if (safeMax <= 4) {
    step = 1
    yMax = 4
  } else {
    const rawStep = safeMax / 4
    const magnitude = 10 ** Math.floor(Math.log10(rawStep))
    const normalized = rawStep / magnitude

    let niceFactor = 1
    if (magnitude >= 10 && normalized > 2 && normalized <= 2.5) {
      niceFactor = 2.5
    } else if (normalized > 5) {
      niceFactor = 10
    } else if (normalized > 2) {
      niceFactor = 5
    } else if (normalized > 1) {
      niceFactor = 2
    }

    step = Math.max(1, Math.round(niceFactor * magnitude))
    yMax = Math.ceil(safeMax / step) * step
  }

  const ticks: YAxisTick[] = []
  for (let val = 0; val <= yMax; val += step) {
    const ratio = val / yMax
    ticks.push({
      y: paddingY + usableHeight * (1 - ratio),
      value: val,
    })
  }
  return ticks
}

/** Batasi 0..100 untuk lebar meter */
export const clampPercent = (n: number): number => Math.min(100, Math.max(0, Number.isFinite(n) ? n : 0))

/**
 * Penanda pemeriksaan terbaru dari riwayat telemetri. Berubah → ada baris audit
 * baru, jadi halaman Laporan memuat ulang tanpa polling terpisah.
 */
export function historyHead(
  history: ReadonlyArray<Pick<HistoryRecord, 'track_id' | 'timestamp' | 'snapshot_filename'>> | null | undefined,
): string {
  const h = history?.[0]
  return h ? `${h.track_id}|${h.timestamp}|${h.snapshot_filename}` : ''
}

/**
 * Isi kolom Pekerja (T79): nama & nomor bila dikenali FR, "Tidak dikenali" bila FR berjalan tanpa
 * kecocokan; baris lama / FR mati tetap memakai nomor lintasan. Divisi & perusahaan = snapshot audit.
 */
export function workerCell(
  rec: Pick<ReportRecord, 'track_id' | 'fr_status' | 'worker_name' | 'employee_no' | 'department' | 'company'>,
): {
  primary: string
  secondary: string
  known: boolean
} {
  const org = [rec.department, rec.company].filter(Boolean).join(' · ')
  if (rec.fr_status === 'recognized' && rec.worker_name) {
    return { primary: rec.worker_name, secondary: [rec.employee_no, org].filter(Boolean).join(' · '), known: true }
  }
  const track = TEXT.table.worker_id(rec.track_id)
  if (rec.fr_status === 'unknown') return { primary: TEXT.table.unknownWorker, secondary: track, known: false }
  return { primary: track, secondary: '', known: false }
}
