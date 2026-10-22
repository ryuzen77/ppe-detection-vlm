import { describe, expect, it } from 'vitest'
import { pingRows } from './ping'
import { SETTINGS_TAB } from './messages'
import type { PingResult } from './api/types'

const TEXT = SETTINGS_TAB.ping

function result(engines: PingResult['engines']): PingResult {
  return { status: 'ONLINE', latency_ms: 0, message: '', engines }
}

describe('pingRows — VLM lokal siaga (T72)', () => {
  const darurat = (standby?: boolean, error = 'Siaga (belum dimuat).') => [
    { role: 'darurat' as const, ok: false, latency_ms: 0, error, is_local: true, timeout_ms: 12000, standby },
  ]

  it('standby dari jawaban ping = baris netral, bukan "tidak menjawab"', () => {
    const [row] = pingRows(result(darurat(true)))
    expect(row).toMatchObject({ label: 'VLM lokal darurat (lokal)', tone: 'muted', text: TEXT.standby })
  })

  it('tanpa penanda standby (gagal sungguhan / server lama) tetap merah', () => {
    expect(pingRows(result(darurat(false, 'timeout > 12 dtk')))[0].tone).toBe('danger')
    expect(pingRows(result(darurat(undefined)))[0].tone).toBe('danger')
  })
})

describe('pingRows (T86)', () => {
  it('satu baris per VLM aktif, dengan jenis online/lokal', () => {
    const rows = pingRows(
      result([
        { role: 'utama', ok: true, latency_ms: 2100, is_local: false, timeout_ms: 5000 },
        { role: 'cadangan', ok: true, latency_ms: 8400, is_local: true, timeout_ms: 12000 },
      ]),
    )
    expect(rows.map((r) => r.label)).toEqual([
      `${TEXT.roles.utama} (${TEXT.online})`,
      `${TEXT.roles.cadangan} (${TEXT.local})`,
    ])
    expect(rows.every((r) => r.tone === 'ok')).toBe(true)
    expect(rows[0].text).toBe(TEXT.answered(2100))
  })

  it('melebihi batas pemeriksaan ditandai peringatan', () => {
    const [row] = pingRows(result([{ role: 'utama', ok: true, latency_ms: 5600, is_local: false, timeout_ms: 5000 }]))
    expect(row.tone).toBe('warn')
    expect(row.hint).toBe(TEXT.overLimit(5000))
  })

  it('gagal: alasan tampil; VLM lokal diberi petunjuk sedang dimuat', () => {
    const rows = pingRows(
      result([
        { role: 'utama', ok: false, latency_ms: 5000, error: 'timeout > 5 dtk', is_local: false, timeout_ms: 5000 },
        {
          role: 'cadangan',
          ok: false,
          latency_ms: 12000,
          error: 'timeout > 12 dtk',
          is_local: true,
          timeout_ms: 12000,
        },
      ]),
    )
    expect(rows[0]).toMatchObject({ tone: 'danger', text: TEXT.failed('timeout > 5 dtk') })
    expect(rows[0].hint).toBeUndefined()
    expect(rows[1].hint).toBe(TEXT.localLoading)
  })

  it('tanpa cadangan: baris keterangan, bukan galat', () => {
    const rows = pingRows(result([{ role: 'utama', ok: true, latency_ms: 1400, is_local: false, timeout_ms: 5000 }]))
    expect(rows[1]).toEqual({ label: TEXT.roles.cadangan, tone: 'muted', text: TEXT.noBackup })
  })

  it('server lama tanpa is_local/timeout_ms tetap terbaca', () => {
    const [row] = pingRows(result([{ role: 'utama', ok: true, latency_ms: 900 }]))
    expect(row).toEqual({ label: TEXT.roles.utama, tone: 'ok', text: TEXT.answered(900) })
  })

  it('sibuk / tidak dikonfigurasi: tanpa baris (pesan server yang tampil)', () => {
    expect(pingRows({ status: 'BUSY', latency_ms: 0, message: 'sibuk', engines: [] })).toEqual([])
  })
})
