/** Kartu Wajib terdaftar (T83): logika murni, teks di messages.ts. */
import type { RegistrationPolicy, RegistrationPolicyErrorCode } from './api/types'
import { REGISTRATION_POLICY as TEXT, percent } from './messages'

type Recognition = RegistrationPolicy['recognition']

/** Kontrak T83: rate & threshold berupa pecahan 0..1; percent() menerima angka persen */
const pct = (fraction: number): string => percent(fraction * 100)

/** Ringkasan tingkat pengenalan, mis. "60% (12 dari 20 lintasan, 7 hari terakhir)" */
export function recognitionText(rec: Recognition): string {
  if (rec.rate === null) return TEXT.recognitionNone(rec.days)
  return TEXT.recognition(pct(rec.rate), rec.recognized, rec.passes, rec.days)
}

/** Sama dengan aturan backend: di bawah ambang atau belum ada data = perlu konfirmasi admin */
export function needsConfirmation(rec: Recognition): boolean {
  return rec.rate === null || rec.rate < rec.threshold
}

export function thresholdText(rec: Recognition): string {
  return pct(rec.threshold)
}

export function confirmText(rec: Recognition): string {
  const threshold = pct(rec.threshold)
  return rec.rate === null ? TEXT.confirmBodyNoData(threshold) : TEXT.confirmBody(pct(rec.rate), threshold)
}

/** Sakelar boleh dipakai untuk mematikan kapan pun, tetapi menyalakan hanya bila FR siap */
export function toggleDisabled(policy: RegistrationPolicy): boolean {
  return !policy.require_registered && !policy.fr_ready
}

export type SaveErrorAction = 'confirm' | 'fr_not_ready' | 'error'

/** Kode galat 400 dari server → tindakan kartu (kontrak T83) */
export function saveErrorAction(code: string | undefined): SaveErrorAction {
  const known: Record<RegistrationPolicyErrorCode, SaveErrorAction> = {
    low_recognition_needs_confirmation: 'confirm',
    fr_not_ready: 'fr_not_ready',
  }
  return (code && known[code as RegistrationPolicyErrorCode]) || 'error'
}
