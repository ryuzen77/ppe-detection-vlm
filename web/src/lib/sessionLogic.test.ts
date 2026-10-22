import { describe, expect, it } from 'vitest'
import { getViewState, shouldLoadData, tickCountdown, telemetryAction } from './sessionLogic'

describe('sessionLogic', () => {
  it('getViewState memetakan state ke view yang benar', () => {
    expect(getViewState({ loaded: false, setupRequired: false, authenticated: false })).toBe('loading')
    expect(getViewState({ loaded: true, setupRequired: true, authenticated: false })).toBe('setup')
    expect(getViewState({ loaded: true, setupRequired: false, authenticated: false })).toBe('login')
    expect(getViewState({ loaded: true, setupRequired: false, authenticated: true })).toBe('dashboard')
  })

  it('shouldLoadData memicu load jika login sukses atau dimuat dalam keadaan login', () => {
    expect(
      shouldLoadData(
        { loaded: true, setupRequired: false, authenticated: false },
        { loaded: true, setupRequired: false, authenticated: true },
      ),
    ).toBe(true)
    expect(
      shouldLoadData(
        { loaded: false, setupRequired: false, authenticated: false },
        { loaded: true, setupRequired: false, authenticated: true },
      ),
    ).toBe(true)
    expect(
      shouldLoadData(
        { loaded: true, setupRequired: false, authenticated: true },
        { loaded: true, setupRequired: false, authenticated: true },
      ),
    ).toBe(false)
  })

  it('tickCountdown: hitung mundur yang benar', () => {
    expect(tickCountdown(null)).toBe(null)
    expect(tickCountdown(0)).toBe(null)
    expect(tickCountdown(5)).toBe(4)
    expect(tickCountdown(1)).toBe(null)
  })

  it('telemetryAction: belum dimuat -> wait', () => {
    expect(telemetryAction({ loaded: false, setupRequired: true, authenticated: false })).toBe('wait')
  })
  it('telemetryAction: login berhasil -> start', () => {
    expect(telemetryAction({ loaded: true, setupRequired: false, authenticated: true })).toBe('start')
  })
  it('telemetryAction: butuh login/setup -> stop', () => {
    expect(telemetryAction({ loaded: true, setupRequired: true, authenticated: false })).toBe('stop')
    expect(telemetryAction({ loaded: true, setupRequired: false, authenticated: false })).toBe('stop')
  })
})
