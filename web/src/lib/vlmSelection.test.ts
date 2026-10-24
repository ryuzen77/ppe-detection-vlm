import { describe, expect, it } from 'vitest'
import {
  validationBadge,
  handleSelectionError,
  backupChange,
  currentBackupIsLocal,
  withLocalNote,
  modelForProvider,
  formDirty,
  groupModels,
  modelSelectable,
  modelOptionLabel,
  reconcileModel,
  modelListReason,
  validationOf,
  rolesNeedingTest,
  needsTest,
  listMatches,
} from './vlmSelection'
import type { VlmModelListEntry, VlmValidationStatus } from './api/types'

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
    expect(handleSelectionError('test_required', 'msg')).toEqual({
      type: 'test_required',
      code: 'test_required',
      message: 'msg',
    })
    expect(handleSelectionError('model_not_found', 'msg')).toMatchObject({ type: 'error', isWarn: false })
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

describe('ganti penyedia & perubahan belum diterapkan (temuan uji UI #13)', () => {
  const ollama = { default_model: 'qwen2.5vl:7b', models: [{ model: 'qwen2.5vl:7b' }, { model: 'gemma3:12b' }] }
  it('model lama yang bukan milik penyedia baru diganti model bawaannya', () => {
    expect(modelForProvider(ollama, 'gemini-3.5-flash-lite')).toBe('qwen2.5vl:7b')
    expect(modelForProvider(ollama, 'gemma3:12b')).toBe('gemma3:12b')
    expect(modelForProvider({ default_model: '', models: [{ model: 'x' }] }, 'y')).toBe('x')
    expect(modelForProvider(undefined, 'y')).toBe('')
  })
  it('formulir berbeda dari server = dirty; sama = bersih', () => {
    const g = { provider: 'gemini', model: 'm' }
    const current = { primary: g, backup: g, local_fallback: null }
    expect(formDirty(current, { primary: g, backup: g, local_fallback: null })).toBe(false)
    expect(formDirty(current, { primary: { provider: 'ollama', model: 'q' }, backup: g, local_fallback: null })).toBe(
      true,
    )
    expect(formDirty(current, { primary: g, backup: null, local_fallback: null })).toBe(true)
    expect(formDirty({ primary: g, backup: null }, { primary: g, backup: null, local_fallback: null })).toBe(false)
  })
})

describe('daftar model dari penyedia (T97)', () => {
  const entry = (
    model: string,
    validated: VlmValidationStatus,
    available: boolean | null = true,
  ): VlmModelListEntry => ({
    model,
    validated,
    available,
    photos: null,
    missed: null,
    false_rejects: null,
    median_seconds: null,
  })
  const models = [
    entry('zeta', 'unvalidated'),
    entry('Beta', 'partial'),
    entry('alpha', 'validated'),
    entry('gamma', 'outdated'),
    entry('old-model', 'validated', false),
    entry('bad', 'unsafe'),
  ]

  it('mengelompokkan teruji/sebagian dulu, lalu sisanya; masing-masing A–Z tanpa peduli huruf besar', () => {
    const { tested, untested } = groupModels(models)
    expect(tested.map((m) => m.model)).toEqual(['alpha', 'Beta', 'old-model'])
    expect(untested.map((m) => m.model)).toEqual(['bad', 'gamma', 'zeta'])
  })

  it('model katalog yang tidak ada di akun & model tidak aman tidak bisa dipilih', () => {
    expect(modelSelectable(entry('x', 'validated', false))).toBe(false)
    expect(modelSelectable(entry('x', 'unsafe'))).toBe(false)
    expect(modelSelectable(entry('x', 'unvalidated', null))).toBe(true)
    expect(modelOptionLabel(entry('x', 'validated', false), 'tidak ada')).toBe('x (tidak ada)')
    expect(modelOptionLabel(entry('x', 'validated'), 'tidak ada')).toBe('x')
  })

  it('ganti penyedia: model lama bila bisa dipilih, lalu bawaan, lalu model teruji pertama', () => {
    expect(reconcileModel(models, 'zeta', 'alpha')).toBe('zeta')
    expect(reconcileModel(models, 'tidak-ada', 'gamma')).toBe('gamma')
    expect(reconcileModel(models, 'old-model', 'bad')).toBe('alpha')
    expect(reconcileModel([entry('u', 'unvalidated')], '', '')).toBe('u')
    expect(reconcileModel([], 'ketikan', 'x')).toBe('ketikan')
  })

  it('daftar penyedia/peran lain tidak dipakai selama daftar baru dimuat (tinjauan Codex)', () => {
    const list = { provider: 'gemini', role: 'backup' as const }
    expect(listMatches(list, 'gemini', 'backup')).toBe(true)
    expect(listMatches(list, 'ollama', 'backup')).toBe(false)
    expect(listMatches(list, 'gemini', 'primary')).toBe(false)
    expect(listMatches(null, 'gemini', 'backup')).toBe(false)
    expect(listMatches(list, undefined, 'backup')).toBe(false)
  })

  it('alasan daftar gagal → teks; tanpa kode = permintaan ke server gagal', () => {
    const reasons = {
      no_key: 'k',
      unreachable: 'u',
      timeout: 't',
      unsupported: 's',
      auth_failed: 'a',
      request: 'r',
    }
    expect(modelListReason('auth_failed', reasons)).toBe('a')
    expect(modelListReason(null, reasons)).toBe('r')
  })

  it('alur uji-dulu: hanya model belum teruji/kedaluwarsa yang wajib diuji', () => {
    expect(needsTest('unvalidated')).toBe(true)
    expect(needsTest('outdated')).toBe(true)
    expect(needsTest('validated')).toBe(false)
    expect(needsTest('partial')).toBe(false)
    expect(needsTest('unsafe')).toBe(false)
    const gemini = { models: [{ model: 'g', validated: 'partial' as const }] }
    expect(validationOf(gemini, 'g')).toBe('partial')
    expect(validationOf(gemini, 'salah-ketik')).toBe('unvalidated')
    expect(validationOf(undefined, 'g')).toBe('unvalidated')
    expect(
      rolesNeedingTest([
        { role: 'primary', model: 'g', status: 'partial' },
        { role: 'backup', model: 'baru', status: 'unvalidated' },
        { role: 'local', model: '', status: 'unvalidated' },
      ]),
    ).toEqual(['backup'])
  })
})
