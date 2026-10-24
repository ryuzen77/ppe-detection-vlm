import { describe, expect, it } from 'vitest'
import {
  validationBadge,
  handleSelectionError,
  backupChange,
  currentBackupIsLocal,
  withLocalNote,
} from './vlmSelection'

describe('vlmSelection', () => {
  it('validationBadge memetakan status ke tone yang benar (tanpa danger/merah)', () => {
    expect(validationBadge('validated')).toEqual({ text: 'Teruji', tone: 'ok' })
    expect(validationBadge('partial')).toEqual({ text: 'Sebagian', tone: 'warn' })
    expect(validationBadge('outdated')).toEqual({ text: 'Kedaluwarsa', tone: 'warn' })
    expect(validationBadge('unvalidated')).toEqual({ text: 'Belum teruji', tone: 'warn' })
    expect(validationBadge('unsafe')).toEqual({ text: 'Tidak aman', tone: 'muted' })
  })

  it('handleSelectionError merespons code dengan benar', () => {
    expect(handleSelectionError('needs_confirmation', 'msg')).toEqual({
      type: 'confirm',
      code: 'needs_confirmation',
      message: 'msg',
    })
    expect(handleSelectionError('lane_busy', 'msg')).toEqual({
      type: 'error',
      code: 'lane_busy',
      message: 'msg',
      isWarn: true,
    })
    expect(handleSelectionError('unsafe_model', 'msg')).toEqual({
      type: 'error',
      code: 'unsafe_model',
      message: 'msg',
      isWarn: false,
    })
  })
})

describe('backupChange (T70)', () => {
  const providers = [
    { name: 'ollama', is_local: true },
    { name: 'gemini', is_local: false },
  ]
  const local = { provider: 'ollama', model: 'qwen2.5vl:7b' }

  it('mematikan cadangan perlu konfirmasi', () => {
    expect(backupChange(local, '', '', providers)).toBe('disable')
  })
  it('mengaktifkan cadangan lokal = menunggu model siap di GPU', () => {
    expect(backupChange(null, 'ollama', 'qwen2.5vl:7b', providers)).toBe('enable_local')
    expect(backupChange(local, 'ollama', 'qwen2.5vl:3b', providers)).toBe('enable_local')
  })
  it('tanpa perubahan atau cadangan cloud', () => {
    expect(backupChange(local, 'ollama', 'qwen2.5vl:7b', providers)).toBe('unchanged')
    expect(backupChange(null, '', 'apa saja', providers)).toBe('unchanged')
    expect(backupChange(null, 'gemini', 'x', providers)).toBe('other')
  })
})

describe('teks GPU hanya untuk cadangan lokal (temuan uji UI #12)', () => {
  const providers = [
    { name: 'gemini', is_local: false },
    { name: 'ollama', is_local: true },
  ]
  it('mengenali cadangan aktif lokal vs cloud', () => {
    expect(currentBackupIsLocal({ provider: 'ollama' }, providers)).toBe(true)
    expect(currentBackupIsLocal({ provider: 'gemini' }, providers)).toBe(false)
    expect(currentBackupIsLocal(null, providers)).toBe(false)
  })
  it('catatan GPU ditempel hanya bila lokal', () => {
    expect(withLocalNote('Teks.', 'GPU.', true)).toBe('Teks. GPU.')
    expect(withLocalNote('Teks.', 'GPU.', false)).toBe('Teks.')
  })
})
