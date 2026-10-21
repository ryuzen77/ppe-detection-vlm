// Laporan kehadiran (T80): logika murni untuk Laporan → tab Kehadiran. Informasi lewat gerbang,
// BUKAN absensi resmi (keputusan pengguna 21-10); komponen hanya merakit.
import { ApiError } from './api/client'
import type { AttendanceReport } from './api/types'
import { ATTENDANCE as TEXT, percent, withError } from './messages'
import { ATTENDANCE_RATE } from './settings'

export type AttendanceTone = 'ok' | 'warn' | 'danger' | 'neutral'

export interface AttendanceTile {
  label: string
  value: string
  hint: string
  tone: AttendanceTone
}

/** Tanggal lokal gerbang (YYYY-MM-DD), bukan UTC — sama dengan `date_str` audit. */
export function localDateIso(d: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function rateTone(rate: number | null): AttendanceTone {
  if (rate === null) return 'neutral'
  if (rate >= ATTENDANCE_RATE.good) return 'ok'
  return rate >= ATTENDANCE_RATE.fair ? 'warn' : 'danger'
}

export function attendanceTiles(r: AttendanceReport): AttendanceTile[] {
  const t = r.totals
  return [
    { label: TEXT.tiles.seen, value: String(t.seen_workers), hint: TEXT.ofActive(t.seen_workers, t.active_workers), tone: 'neutral' },
    { label: TEXT.tiles.notSeen, value: String(r.not_seen.length), hint: TEXT.notSeenNotice, tone: 'neutral' },
    { label: TEXT.tiles.unknown, value: String(r.unknown.passes),
      hint: TEXT.unknownHint(r.unknown.passed, r.unknown.rejected), tone: 'neutral' },
    { label: TEXT.tiles.rate, value: t.recognition_rate === null ? '—' : percent(t.recognition_rate * 100),
      hint: t.passes ? TEXT.rateHint(t.recognized, t.passes) : TEXT.noPasses, tone: rateTone(t.recognition_rate) },
  ]
}

/** "Produksi · PT Alfa" / "Produksi" / "—": snapshot audit atau data pekerja sekarang. */
export function orgText(department: string | null, company: string | null): string {
  return [department, company].filter(Boolean).join(' · ') || '—'
}

/** 403 = bukan admin, 404 = server belum punya T80a; selain itu pesan galat biasa. */
export function attendanceError(e: unknown): string {
  if (e instanceof ApiError && e.status === 403) return TEXT.adminOnly
  if (e instanceof ApiError && e.status === 404) return TEXT.unavailable
  return withError(TEXT.loadFailed, e)
}
