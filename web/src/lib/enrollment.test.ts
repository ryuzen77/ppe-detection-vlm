import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { keepEnrollmentHold, type EnrollmentClient } from './enrollment'
import { ENROLLMENT_HOLD } from './settings'

const HOLD_S = 45

function fakeClient(fail = false) {
  const calls: string[] = []
  const client: EnrollmentClient = {
    holdEnrollment: () => {
      calls.push('hold')
      return fail ? Promise.reject(new Error('jaringan')) : Promise.resolve({ active: true, hold_s: HOLD_S })
    },
    releaseEnrollment: () => {
      calls.push('release')
      return Promise.resolve()
    },
  }
  return { client, calls }
}

describe('keepEnrollmentHold', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('denyut lebih sering dari batas waktu backend, berhenti & melepas saat ditutup', async () => {
    const { client, calls } = fakeClient()
    const close = keepEnrollmentHold(client, () => {})
    await vi.advanceTimersByTimeAsync(HOLD_S * 1000)
    expect(calls.filter((c) => c === 'hold')).toHaveLength(1 + ENROLLMENT_HOLD.beatsPerHold)
    close()
    await vi.advanceTimersByTimeAsync(HOLD_S * 1000)
    expect(calls.at(-1)).toBe('release')
    expect(calls.filter((c) => c === 'release')).toHaveLength(1)
  })

  it('ditutup sebelum jeda pertama terjawab: dilepas lagi, tanpa denyut', async () => {
    const { client, calls } = fakeClient()
    const close = keepEnrollmentHold(client, () => {})
    close()
    await vi.advanceTimersByTimeAsync(HOLD_S * 1000)
    expect(calls).toEqual(['hold', 'release', 'release'])
  })

  it('jeda gagal dilaporkan ke modal', async () => {
    const { client } = fakeClient(true)
    const onError = vi.fn()
    keepEnrollmentHold(client, onError)()
    await vi.advanceTimersByTimeAsync(0)
    expect(onError).toHaveBeenCalledOnce()
  })
})
