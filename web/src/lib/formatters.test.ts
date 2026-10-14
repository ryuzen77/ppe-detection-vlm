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
