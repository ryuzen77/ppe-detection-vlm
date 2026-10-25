/** Logika tampilan halaman Laporan (murni, teruji). Teks di messages.ts, angka di settings.ts. */
import type { HistoryRecord, ReportBucket, ReportRecord, ReportStatusFilter, ReportsPage } from './api/types'
import { describeSource, type SourceRole } from './format'
import type { Tone } from './gate'
import { REPORTS as TEXT } from './messages'
import { REPORTS } from './settings'

export type ResultKind = 'passed' | 'denied' | 'unverified' | 'held'

/** Awalan sumber baris lama (T21–T26) yang ditolak karena VLM tidak menjawab */
const LEGACY_UNVERIFIED_PREFIX = 'VLM_GAGAL'

export function resultKind(rec: Pick<ReportRecord, 'is_complete' | 'inference_source' | 'gate_hold'>): ResultKind {
  // T83: ditahan = APD lengkap (is_complete tetap true) tetapi gerbang tidak mengizinkan
  if (rec.gate_hold) return 'held'
  if (rec.is_complete) return 'passed'
  return (rec.inference_source ?? '').startsWith(LEGACY_UNVERIFIED_PREFIX) ? 'unverified' : 'denied'
}

/** Saringan status yang didukung server: "Ditahan" (T83) hanya bila server mengirim held_count */
export function reportStatuses(page: Pick<ReportsPage, 'held_count'> | null): ReportStatusFilter[] {
  const base: ReportStatusFilter[] = ['all', 'complete', 'incomplete']
  return page?.held_count !== undefined ? [...base, 'held'] : base
}

export const RESULT_TONE: Record<ResultKind, Tone> = {
  passed: 'ok',
  denied: 'danger',
  unverified: 'warn',
  held: 'warn',
}

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

/** Periode berikutnya ada isinya hanya bila periode tampil belum mencapai hari ini (temuan uji UI #5).
 *  Tanggal ISO (YYYY-MM-DD) dibandingkan sebagai teks. */
export function hasNextPeriod(rangeTo: string | undefined, today: string): boolean {
  return !!rangeTo && rangeTo < today
}

/**
 * Pesan tabel kosong. Saringan (status/pekerja/divisi/perusahaan) didahulukan: ringkasan periode ikut
 * tersaring, jadi totalnya 0 walau periodenya berisi (temuan uji UI #7). Tanggal bukan saringan.
 */
export function reportEmptyText(o: { loading: boolean; periodTotal: number | undefined; hasFilter: boolean }): string {
  if (o.loading) return TEXT.loading
  if (o.hasFilter) return TEXT.emptyFiltered
  return o.periodTotal === 0 ? TEXT.emptyPeriod : TEXT.empty
}

/** Tanggal ketikan manual melewati hari ini → hari ini (atribut `max` tidak menahan ketikan; tinjauan Codex T95) */
export function clampToToday(value: string, today: string): string {
  return value && value > today ? today : value
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

// --- T101: tumpukan batang grafik volume (merah atas → kuning → hijau bawah)

export type BucketSeries = 'rejected' | 'held' | 'passed'

/** Urutan tumpukan dari atas ke bawah; warna mengikuti aturan tone (merah/kuning/hijau) */
export const BUCKET_SERIES: { key: BucketSeries; tone: Tone }[] = [
  { key: 'rejected', tone: 'danger' },
  { key: 'held', tone: 'warn' },
  { key: 'passed', tone: 'ok' },
]

const countOf = (b: ReportBucket, key: BucketSeries) => b[key] ?? 0

export const bucketTotal = (b: ReportBucket) => BUCKET_SERIES.reduce((sum, s) => sum + countOf(b, s.key), 0)

/** Ruas batang yang tampil (nilai 0 dilewati), dengan posisi y relatif terhadap puncak batang */
export function bucketSegments(
  b: ReportBucket,
  heightOf: (value: number) => number,
): { key: BucketSeries; tone: Tone; offset: number; height: number }[] {
  let offset = 0
  return BUCKET_SERIES.filter((s) => countOf(b, s.key) > 0).map((s) => {
    const height = heightOf(countOf(b, s.key))
    const segment = { ...s, offset, height }
    offset += height
    return segment
  })
}

/** Tooltip batang: "08: 2 Lolos, 1 Ditahan, 1 Ditolak" (seri bernilai 0 tidak disebut) */
export function bucketTitle(b: ReportBucket, labels: Record<BucketSeries, string>): string {
  const parts = (['passed', 'held', 'rejected'] as const)
    .filter((key) => countOf(b, key) > 0)
    .map((key) => `${countOf(b, key)} ${labels[key]}`)
  return `${b.label}: ${parts.join(', ') || 0}`
}
