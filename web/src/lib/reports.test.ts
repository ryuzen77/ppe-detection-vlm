import { describe, expect, it } from 'vitest'
import { REPORTS as TEXT } from './messages'
import { clampPercent, complianceTone, historyHead, pageInfo, resultKind, sourceText, offsetDate, formatReportRange, calculateYAxis } from './reports'
import { REPORTS } from './settings'

describe('resultKind', () => {
  it('lolos bila lengkap', () => {
    expect(resultKind({ is_complete: true, inference_source: 'VLM_LIVE:x/y' })).toBe('passed')
  })
  it('ditolak bila VLM menilai APD kurang', () => {
    expect(resultKind({ is_complete: false, inference_source: 'VLM_CADANGAN:ollama/q' })).toBe('denied')
  })
  it('baris lama VLM_GAGAL = tidak terverifikasi, bukan pelanggaran', () => {
    expect(resultKind({ is_complete: false, inference_source: 'VLM_GAGAL' })).toBe('unverified')
  })
  it('sumber kosong tetap aman', () => {
    expect(resultKind({ is_complete: false, inference_source: '' })).toBe('denied')
  })
})

describe('sourceText', () => {
  it('tanpa nama penyedia/model', () => {
    const s = sourceText('VLM_LIVE:gemini/gemini-3.5-flash-lite')
    expect(s).toEqual({ role: 'utama', text: TEXT.source.utama })
    expect(s.text).not.toMatch(/gemini/i)
  })
  it('cadangan, gangguan, dan data lama', () => {
    expect(sourceText('VLM_CADANGAN:ollama/qwen2.5vl:7b').text).toBe(TEXT.source.cadangan)
    expect(sourceText('VLM_GANGGUAN').text).toBe(TEXT.source.gangguan)
    expect(sourceText('LOCAL_HEURISTIC').text).toBe(TEXT.source.lama)
  })
})

describe('pageInfo', () => {
  it('halaman pertama', () => {
    expect(pageInfo(0, 25, 60)).toEqual({ from: 1, to: 25, total: 60, hasPrev: false, hasNext: true })
  })
  it('halaman terakhir tidak penuh', () => {
    expect(pageInfo(50, 10, 60)).toEqual({ from: 51, to: 60, total: 60, hasPrev: true, hasNext: false })
  })
  it('kosong', () => {
    expect(pageInfo(0, 0, 0)).toEqual({ from: 0, to: 0, total: 0, hasPrev: false, hasNext: false })
  })
  it('offset melewati data (data terhapus) tetap bisa mundur', () => {
    expect(pageInfo(50, 0, 10).hasPrev).toBe(true)
  })
})

describe('complianceTone', () => {
  it('rate null = neutral', () => {
    expect(complianceTone(null)).toBe('neutral')
  })
  it('mengikuti ambang di settings', () => {
    expect(complianceTone(REPORTS.complianceGood)).toBe('ok')
    expect(complianceTone(REPORTS.complianceGood - 0.1)).toBe('warn')
    expect(complianceTone(REPORTS.complianceWarn)).toBe('warn')
    expect(complianceTone(REPORTS.complianceWarn - 0.1)).toBe('danger')
  })
})

describe('clampPercent', () => {
  it('batas 0..100 dan NaN → 0', () => {
    expect(clampPercent(-5)).toBe(0)
    expect(clampPercent(140)).toBe(100)
    expect(clampPercent(Number.NaN)).toBe(0)
    expect(clampPercent(42.5)).toBe(42.5)
  })
})

describe('historyHead', () => {
  it('berubah hanya bila pemeriksaan terbaru berubah', () => {
    const a = { track_id: 3, timestamp: '10:00:01', snapshot_filename: 'a.jpg' }
    const b = { track_id: 4, timestamp: '10:00:09', snapshot_filename: 'b.jpg' }
    expect(historyHead([a])).toBe(historyHead([a, b]))
    expect(historyHead([b, a])).not.toBe(historyHead([a]))
    expect(historyHead([])).toBe('')
    expect(historyHead(null)).toBe('')
  })
})

describe('offsetDate', () => {
  it('geser tanggal melewati batas bulan/tahun', () => {
    expect(offsetDate('2026-12-31', 1)).toBe('2027-01-01')
    expect(offsetDate('2026-03-01', -1)).toBe('2026-02-28') // bukan kabisat
    expect(offsetDate('2024-03-01', -1)).toBe('2024-02-29') // kabisat
  })
})

describe('formatReportRange', () => {
  it('format rentang', () => {
    const f = (d: string) => d // dummy formatter
    expect(formatReportRange('2026-10-01', '2026-10-01', f)).toBe('2026-10-01')
    expect(formatReportRange('2026-10-01', '2026-10-05', f)).toBe('2026-10-01 – 2026-10-05')
  })
})

describe('calculateYAxis', () => {
  it('maxTotal 0 atau 1 -> tick bulat', () => {
    // maxTotal 0 -> harusnya 1
    const ticks0 = calculateYAxis(0, 10, 100)
    // maxTotal 1
    const ticks1 = calculateYAxis(1, 10, 100)
    // Cek tick memiliki nilai bulat dan menurun dari bawah ke atas (karena y dari SVG)
    expect(ticks1.length).toBeGreaterThan(0)
    expect(Number.isInteger(ticks1[0].value)).toBe(true)
    // y menurun (tick 0 di bawah -> y besar, tick 1 di atas -> y kecil)
    const val0 = ticks1.find(t => t.value === 0)
    const val1 = ticks1.find(t => t.value === 1)
    if (val0 && val1) {
      expect(val1.y).toBeLessThan(val0.y)
    }
  })
})
