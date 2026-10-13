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
  it('formats local date string without Z', () => {
    const raw = '2026-10-08T17:21:20'
    const d = new Date(raw)
    expect(formatServerDate(raw)).toBe(d.toLocaleString('id-ID'))
  })
  it('returns original string if invalid', () => {
    expect(formatServerDate('not-a-date')).toBe('not-a-date')
  })
})
