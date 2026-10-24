import { describe, expect, it } from 'vitest'
import { REPORTS as TEXT } from './messages'
import {
  hasNextPeriod,
  reportEmptyText,
  clampPercent,
  complianceTone,
  historyHead,
  pageInfo,
  resultKind,
  sourceText,
  offsetDate,
  formatReportRange,
  calculateYAxis,
  workerCell,
} from './reports'
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
  it('menghasilkan tick bilangan bulat unik, terurut naik, dan y menurun', () => {
    const testCases = [0, 1, 2, 3, 4, 7, 10, 17, 100]

    for (const maxTotal of testCases) {
      const paddingY = 24
      const usableHeight = 192
      const ticks = calculateYAxis(maxTotal, paddingY, usableHeight)

      expect(ticks.length).toBeGreaterThanOrEqual(2)

      const values = ticks.map((t) => t.value)
      // Semua tick harus integer
      expect(values.every((v) => Number.isInteger(v))).toBe(true)
      // Tidak ada tick duplikat
      expect(new Set(values).size).toBe(values.length)
      // Tick harus dimulai dari 0
      expect(values[0]).toBe(0)
      // Nilai puncak tick harus >= maxTotal
      expect(values[values.length - 1]).toBeGreaterThanOrEqual(maxTotal)

      // Verifikasi urutan nilai naik dan koordinat y menurun (karena Y=0 di atas)
      for (let i = 0; i < ticks.length - 1; i++) {
        expect(ticks[i + 1].value).toBeGreaterThan(ticks[i].value)
        expect(ticks[i + 1].y).toBeLessThan(ticks[i].y)
      }

      // Verifikasi posisi linear persis: y = paddingY + usableHeight * (1 - value / puncak)
      const yMax = values[values.length - 1]
      for (const t of ticks) {
        const expectedY = paddingY + usableHeight * (1 - t.value / yMax)
        expect(t.y).toBeCloseTo(expectedY, 5)
      }
    }
  })

  it('menghasilkan step bulat 1 untuk maxTotal kecil (<= 4)', () => {
    const ticks = calculateYAxis(3, 20, 100)
    expect(ticks.map((t) => t.value)).toEqual([0, 1, 2, 3, 4])
  })
})

describe('workerCell (T79)', () => {
  const base = { track_id: 49, fr_status: null, worker_name: null, employee_no: null, department: null, company: null }
  it('dikenali: nama, lalu nomor · divisi · perusahaan (snapshot saat pemeriksaan)', () => {
    expect(
      workerCell({
        ...base,
        fr_status: 'recognized',
        worker_name: 'Zen',
        employee_no: 'p001',
        department: 'Produksi',
        company: 'Internal',
      }),
    ).toEqual({ primary: 'Zen', secondary: 'p001 · Produksi · Internal', known: true })
  })
  it('FR berjalan tanpa kecocokan = "Tidak dikenali" + nomor lintasan', () => {
    expect(workerCell({ ...base, fr_status: 'unknown' })).toEqual({
      primary: TEXT.table.unknownWorker,
      secondary: '#49',
      known: false,
    })
  })
  it('baris lama / FR mati: nomor lintasan seperti sebelumnya', () => {
    expect(workerCell(base)).toEqual({ primary: '#49', secondary: '', known: false })
  })
})

describe('hasNextPeriod (temuan uji UI #5)', () => {
  it('periode yang sudah mencakup hari ini tidak punya periode berikutnya', () => {
    expect(hasNextPeriod('2026-10-23', '2026-10-24')).toBe(true)
    expect(hasNextPeriod('2026-10-24', '2026-10-24')).toBe(false)
    expect(hasNextPeriod('2026-10-31', '2026-10-24')).toBe(false)
    expect(hasNextPeriod(undefined, '2026-10-24')).toBe(false)
  })
})

describe('reportEmptyText (temuan uji UI #7)', () => {
  it('saringan tanpa hasil = "tidak cocok", walau ringkasan tersaring bernilai 0', () => {
    expect(reportEmptyText({ loading: false, periodTotal: 0, hasFilter: true })).toBe(TEXT.emptyFiltered)
    expect(reportEmptyText({ loading: false, periodTotal: 0, hasFilter: false })).toBe(TEXT.emptyPeriod)
    expect(reportEmptyText({ loading: false, periodTotal: undefined, hasFilter: false })).toBe(TEXT.empty)
    expect(reportEmptyText({ loading: true, periodTotal: 0, hasFilter: true })).toBe(TEXT.loading)
  })
})
