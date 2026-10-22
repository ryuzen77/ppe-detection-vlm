import { describe, it, expect } from 'vitest'
import { formatServerDate } from './formatters'

describe('formatServerDate', () => {
  it('returns - for null', () => {
    expect(formatServerDate(null)).toBe('-')
  })
  it('formats valid date string', () => {
    const d = new Date('2026-10-08T17:21:20+07:00')
    expect(formatServerDate('2026-10-08T17:21:20+07:00')).toBe(d.toLocaleString('id-ID'))
  })
  it('keeps local wall-clock time for strings without Z', () => {
    // Waktu server sudah lokal: bila 'Z' ditambahkan, jam bergeser sebesar offset zona.
    expect(formatServerDate('2026-10-08T17:21:20')).toContain('17.21')
  })
  it('returns original string if invalid', () => {
    expect(formatServerDate('not-a-date')).toBe('not-a-date')
  })
})

import { formatDeviceMeta } from './formatters'
import type { CameraDevice } from './api/types'

describe('formatDeviceMeta', () => {
  it('menghasilkan Kamera 0 · kemampuan belum dipindai untuk index 0 belum dipindai', () => {
    const dev: CameraDevice = {
      index: 0,
      name: 'Integrated Webcam',
      available: true,
      scanned: false,
      in_use: false,
      selected_mode: null,
      modes: [],
    }
    expect(formatDeviceMeta(dev)).toBe('Kamera 0 · kemampuan belum dipindai')
  })

  it('menghasilkan informasi mode bila mode terpilih ada', () => {
    const dev: CameraDevice = {
      index: 1,
      name: 'USB Camera',
      available: true,
      scanned: true,
      in_use: false,
      selected_mode: { width: 1280, height: 720, fps: 30, fourcc: 'MJPG' },
      modes: [],
    }
    expect(formatDeviceMeta(dev)).toBe('Kamera 1 · 1280×720 @30 fps')
  })

  it('menghasilkan tidak tersedia bila sudah dipindai tapi tidak ada mode yang cocok', () => {
    const dev: CameraDevice = {
      index: 2,
      name: 'Faulty Camera',
      available: false,
      scanned: true,
      in_use: false,
      selected_mode: null,
      modes: [],
    }
    expect(formatDeviceMeta(dev)).toBe('Kamera 2 · tidak tersedia')
  })
})
