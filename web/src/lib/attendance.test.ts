import { describe, expect, it } from 'vitest'
import { attendanceError, attendanceTiles, localDateIso, orgText, rateTone } from './attendance'
import { ApiError } from './api/client'
import type { AttendanceReport } from './api/types'
import { ATTENDANCE as TEXT, percent } from './messages'
import { ATTENDANCE_RATE } from './settings'

function report(over: Partial<AttendanceReport['totals']> = {}, notSeen = 1): AttendanceReport {
  return {
    date: '2026-10-21',
    seen: [],
    not_seen: Array.from({ length: notSeen }, (_, i) => ({
      worker_id: i,
      employee_no: `P${i}`,
      name: 'X',
      department: null,
      company: null,
    })),
    unknown: { passes: 5, passed: 3, rejected: 2 },
    totals: { passes: 8, recognized: 3, recognition_rate: 0.375, active_workers: 4, seen_workers: 1, ...over },
  }
}

describe('attendance (T80)', () => {
  it('tanggal lokal, bukan UTC', () => {
    expect(localDateIso(new Date(2026, 9, 21, 23, 30))).toBe('2026-10-21')
    expect(localDateIso(new Date(2026, 0, 5, 0, 5))).toBe('2026-01-05')
  })

  it('warna tingkat pengenalan mengikuti ambang settings', () => {
    expect(rateTone(null)).toBe('neutral')
    expect(rateTone(ATTENDANCE_RATE.good)).toBe('ok')
    expect(rateTone(ATTENDANCE_RATE.fair)).toBe('warn')
    expect(rateTone(ATTENDANCE_RATE.fair - 0.01)).toBe('danger')
  })

  it('kartu ringkasan: terlihat x dari y, belum terlihat + keterangan, tidak dikenali, tingkat pengenalan', () => {
    const [seen, notSeen, unknown, rate] = attendanceTiles(report())
    expect(seen).toMatchObject({ value: '1', hint: TEXT.ofActive(1, 4) })
    expect(notSeen).toMatchObject({ value: '1', hint: TEXT.notSeenNotice })
    expect(unknown).toMatchObject({ value: '5', hint: TEXT.unknownHint(3, 2) })
    expect(rate).toMatchObject({ value: percent(37.5), hint: TEXT.rateHint(3, 8), tone: 'danger' })
  })

  it('hari tanpa lintasan: tingkat pengenalan kosong, bukan 0%', () => {
    const rate = attendanceTiles(report({ passes: 0, recognized: 0, recognition_rate: null }))[3]
    expect(rate).toMatchObject({ value: '—', hint: TEXT.noPasses, tone: 'neutral' })
  })

  it('divisi & perusahaan', () => {
    expect(orgText('Produksi', 'PT Alfa')).toBe('Produksi · PT Alfa')
    expect(orgText(null, 'Internal')).toBe('Internal')
    expect(orgText(null, null)).toBe('—')
  })

  it('403 = khusus admin, 404 = server belum mendukung', () => {
    expect(attendanceError(new ApiError(403, 'x', null))).toBe(TEXT.adminOnly)
    expect(attendanceError(new ApiError(404, 'x', null))).toBe(TEXT.unavailable)
    expect(attendanceError(new Error('putus'))).toContain(TEXT.loadFailed)
  })
})
