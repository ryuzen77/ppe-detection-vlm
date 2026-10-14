import type { VlmValidationStatus } from './api/types'

export type ValidationTone = 'ok' | 'accent' | 'warn' | 'muted'

export function validationBadge(status: VlmValidationStatus): { text: string; tone: ValidationTone } {
  switch (status) {
    case 'validated':
      return { text: 'Teruji', tone: 'ok' }
    case 'partial':
      return { text: 'Sebagian', tone: 'accent' }
    case 'outdated':
      return { text: 'Kedaluwarsa', tone: 'warn' }
    case 'unvalidated':
      return { text: 'Belum teruji', tone: 'warn' }
    case 'unsafe':
      return { text: 'Tidak aman', tone: 'muted' }
    default:
      return { text: 'Tidak diketahui', tone: 'muted' }
  }
}

export type ActionRequired = 
  | { type: 'none' }
  | { type: 'confirm'; code: string; message: string }
  | { type: 'error'; code: string; message: string; isWarn: boolean }

export function handleSelectionError(code: string, message: string): ActionRequired {
  if (code === 'needs_confirmation') {
    return { type: 'confirm', code, message }
  }
  if (code === 'lane_busy') {
    return { type: 'error', code, message, isWarn: true }
  }
  // unsafe_model, missing_key, engine_failed, etc.
  return { type: 'error', code, message, isWarn: false }
}
