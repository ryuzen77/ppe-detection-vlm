import { describe, expect, it } from 'vitest'
import { shouldShowLogin, tickCountdown } from './sessionLogic'

describe('sessionLogic', () => {
  it('shouldShowLogin: true jika authRequired dan !authenticated', () => {
    expect(shouldShowLogin({ authRequired: true, authenticated: false })).toBe(true)
  })

  it('shouldShowLogin: false jika tidak butuh auth', () => {
    expect(shouldShowLogin({ authRequired: false, authenticated: false })).toBe(false)
    expect(shouldShowLogin({ authRequired: false, authenticated: true })).toBe(false)
  })

  it('shouldShowLogin: false jika sudah login', () => {
    expect(shouldShowLogin({ authRequired: true, authenticated: true })).toBe(false)
  })

  it('tickCountdown: hitung mundur yang benar', () => {
    expect(tickCountdown(null)).toBe(null)
    expect(tickCountdown(0)).toBe(null)
    expect(tickCountdown(5)).toBe(4)
    expect(tickCountdown(1)).toBe(null)
  })
})
