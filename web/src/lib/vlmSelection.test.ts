import { describe, expect, it } from 'vitest'
import { validationBadge, handleSelectionError } from './vlmSelection'

describe('vlmSelection', () => {
  it('validationBadge memetakan status ke tone yang benar (tanpa danger/merah)', () => {
    expect(validationBadge('validated')).toEqual({ text: 'Teruji', tone: 'ok' })
    expect(validationBadge('partial')).toEqual({ text: 'Sebagian', tone: 'accent' })
    expect(validationBadge('outdated')).toEqual({ text: 'Kedaluwarsa', tone: 'warn' })
    expect(validationBadge('unvalidated')).toEqual({ text: 'Belum teruji', tone: 'warn' })
    expect(validationBadge('unsafe')).toEqual({ text: 'Tidak aman', tone: 'muted' })
  })

  it('handleSelectionError merespons code dengan benar', () => {
    expect(handleSelectionError('needs_confirmation', 'msg')).toEqual({ type: 'confirm', code: 'needs_confirmation', message: 'msg' })
    expect(handleSelectionError('lane_busy', 'msg')).toEqual({ type: 'error', code: 'lane_busy', message: 'msg', isWarn: true })
    expect(handleSelectionError('unsafe_model', 'msg')).toEqual({ type: 'error', code: 'unsafe_model', message: 'msg', isWarn: false })
  })
})
