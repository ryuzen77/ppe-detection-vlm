import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  buildShots,
  fitPrompt,
  keepEnrollmentHold,
  mirrorPreview,
  pollEnrollmentPreview,
  shotPrompts,
  type EnrollmentClient,
} from './enrollment'
import type { CameraStatus, EnrollmentPlan, EnrollmentPreview } from './api/types'
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

// Bentuk sama dengan GET /api/workers/enrollment/plan (kontrak T76)
const PLAN: EnrollmentPlan = {
  shots_per_condition: 5,
  poses: ['daftar_lurus', 'daftar_kiri', 'daftar_kanan', 'daftar_menunduk', 'daftar_lurus'],
  condition_sets: { no_glasses: ['bare', 'helmet'], glasses: ['glasses', 'helmet_glasses'] },
  interocular_px: { min: 24, max: 60 },
  prompts: {
    condition_switch: 'daftar_pakai_helm',
    fit: { too_far: 'daftar_mendekat', too_close: 'daftar_menjauh' },
    done: 'daftar_selesai',
  },
}

describe('buildShots', () => {
  it('10 foto: 5 tanpa helm lalu 5 dengan helm, arah kepala berulang', () => {
    const shots = buildShots(PLAN, false)
    expect(shots).toHaveLength(10)
    expect(shots.map((s) => s.condition)).toEqual([...Array(5).fill('bare'), ...Array(5).fill('helmet')])
    expect(shots.map((s) => s.number)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    expect(shots[5]).toMatchObject({ pose: 'daftar_lurus', switchesCondition: true })
    expect(shots.filter((s) => s.switchesCondition)).toHaveLength(1)
  })

  it('pekerja berkacamata memakai kondisi kacamata', () => {
    expect(new Set(buildShots(PLAN, true).map((s) => s.condition))).toEqual(new Set(['glasses', 'helmet_glasses']))
  })
})

describe('petunjuk suara', () => {
  it('pakai helm diucapkan sebelum arah kepala foto pertama kondisi kedua', () => {
    const shots = buildShots(PLAN, false)
    expect(shotPrompts(PLAN, shots[1])).toEqual(['daftar_kiri'])
    expect(shotPrompts(PLAN, shots[5])).toEqual(['daftar_pakai_helm', 'daftar_lurus'])
  })

  it('arahan jarak hanya untuk terlalu jauh / terlalu dekat', () => {
    expect(fitPrompt(PLAN, 'too_close')).toBe('daftar_menjauh')
    expect(fitPrompt(PLAN, 'too_far')).toBe('daftar_mendekat')
    expect(fitPrompt(PLAN, 'ok')).toBeNull()
    expect(fitPrompt(PLAN, null)).toBeNull()
  })
})

describe('pollEnrollmentPreview', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('tidak bertumpuk, galat = null, berhenti saat dihentikan', async () => {
    const ok: EnrollmentPreview = { fit: 'ok', faces: 1, interocular_px: 40 }
    // Janji dibuat saat dipanggil (janji gagal yang dibuat lebih awal = rejection tak tertangani)
    const replies = [() => Promise.resolve(ok), () => Promise.reject(new Error('409'))]
    const fetchPreview = vi.fn(() => (replies.shift() ?? (() => Promise.resolve(ok)))())
    const seen: (EnrollmentPreview | null)[] = []
    const stop = pollEnrollmentPreview(fetchPreview, (p) => seen.push(p), 1000)
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchPreview).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1000)
    expect(seen).toEqual([ok, null])
    stop()
    await vi.advanceTimersByTimeAsync(5000)
    expect(fetchPreview).toHaveBeenCalledTimes(2)
  })
})

describe('mirrorPreview', () => {
  const cam = (over: Partial<CameraStatus>) => ({ status: 'OK', is_synthetic: false, ...over }) as CameraStatus

  it('hanya kamera sungguhan yang dicerminkan (tulisan layar pesan tetap terbaca)', () => {
    expect(mirrorPreview(cam({}))).toBe(true)
    expect(mirrorPreview(cam({ is_synthetic: true }))).toBe(false)
    expect(mirrorPreview(cam({ status: 'IDLE' }))).toBe(false)
    expect(mirrorPreview(null)).toBe(false)
  })
})
