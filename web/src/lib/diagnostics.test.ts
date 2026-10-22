import { describe, expect, it } from 'vitest'
import { formatLostSince } from './diagnostics'
import { CLOCK } from './settings'

describe('diagnostics', () => {
  it('formats lost since time', () => {
    const time = new Date('2026-09-27T10:15:30Z').getTime()
    const formatted = formatLostSince(time, 'fallback', (t) => `Sejak ${t}`)
    const expectedTime = new Date(time).toLocaleTimeString(CLOCK.locale, { hour12: false })
    expect(formatted).toBe(`Sejak ${expectedTime}`)
  })
  it('returns fallback if no time', () => {
    expect(formatLostSince(null, 'fallback', (t) => t)).toBe('fallback')
  })
})
