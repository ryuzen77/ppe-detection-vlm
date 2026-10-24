import { describe, expect, it } from 'vitest'
import { extractApiErrorCode } from './api/error'
import type { RegistrationPolicy, Telemetry } from './api/types'
import {
  confirmText,
  needsConfirmation,
  recognitionText,
  saveErrorAction,
  thresholdText,
  toggleDisabled,
} from './registrationPolicy'
import { reportStatuses, resultKind } from './reports'
import { registrationChip } from './status'

function policy(over: Partial<RegistrationPolicy> = {}, rec: Partial<RegistrationPolicy['recognition']> = {}) {
  return {
    require_registered: false,
    fr_ready: true,
    recognition: { rate: 0.6, recognized: 12, passes: 20, days: 7, threshold: 0.95, ...rec },
    ...over,
  } satisfies RegistrationPolicy
}

describe('kartu Wajib terdaftar (T83)', () => {
  it('angka pengenalan dari pecahan ke persen', () => {
    expect(recognitionText(policy().recognition)).toBe('60% (12 dari 20 lintasan, 7 hari terakhir)')
    expect(thresholdText(policy().recognition)).toBe('95%')
    expect(recognitionText(policy({}, { rate: null, recognized: 0, passes: 0 }).recognition)).toMatch(/Belum ada/)
  })

  it('konfirmasi bila di bawah ambang atau belum ada data, tidak bila di atas', () => {
    expect(needsConfirmation(policy().recognition)).toBe(true)
    expect(needsConfirmation(policy({}, { rate: null }).recognition)).toBe(true)
    expect(needsConfirmation(policy({}, { rate: 0.95 }).recognition)).toBe(false)
    expect(confirmText(policy().recognition)).toMatch(/60%.*95%/)
    expect(confirmText(policy({}, { rate: null }).recognition)).toMatch(/Belum ada data/)
  })

  it('FR tidak siap: tidak bisa menyalakan, tetapi tetap bisa mematikan', () => {
    expect(toggleDisabled(policy({ fr_ready: false }))).toBe(true)
    expect(toggleDisabled(policy({ fr_ready: false, require_registered: true }))).toBe(false)
    expect(toggleDisabled(policy())).toBe(false)
  })

  it('kode galat server → tindakan', () => {
    expect(saveErrorAction('low_recognition_needs_confirmation')).toBe('confirm')
    expect(saveErrorAction('fr_not_ready')).toBe('fr_not_ready')
    expect(saveErrorAction('lain')).toBe('error')
    expect(saveErrorAction(undefined)).toBe('error')
    const err = { body: { detail: { code: 'fr_not_ready', message: 'x' } } }
    expect(extractApiErrorCode(err)).toBe('fr_not_ready')
    expect(extractApiErrorCode({ body: { detail: 'teks biasa' } })).toBeUndefined()
  })
})

describe('peringatan operator & laporan (T83)', () => {
  const t = (registration_policy?: Telemetry['registration_policy']) => ({ registration_policy }) as Telemetry

  it('chip hanya saat setelan aktif dan FR mati — kuning, bukan merah', () => {
    expect(registrationChip(t({ enabled: true, fr_ready: false }))).toMatchObject({ tone: 'warn' })
    expect(registrationChip(t({ enabled: true, fr_ready: true }))).toBeNull()
    expect(registrationChip(t({ enabled: false, fr_ready: false }))).toBeNull()
    expect(registrationChip(t())).toBeNull()
  })

  it('ditahan didahulukan walau is_complete true; tanpa gate_hold = perilaku lama', () => {
    const rec = { is_complete: true, inference_source: 'VLM_LIVE:x/y' }
    expect(resultKind({ ...rec, gate_hold: 'unregistered' })).toBe('held')
    expect(resultKind({ ...rec, gate_hold: null })).toBe('passed')
    expect(resultKind(rec)).toBe('passed')
  })

  it('saringan "Ditahan" hanya bila server mengirim held_count', () => {
    expect(reportStatuses({ held_count: 0 })).toContain('held')
    expect(reportStatuses({})).not.toContain('held')
    expect(reportStatuses(null)).not.toContain('held')
  })
})
