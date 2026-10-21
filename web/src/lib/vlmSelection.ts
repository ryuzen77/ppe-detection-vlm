import type { VlmMissingSetting, VlmValidationStatus } from './api/types'
import { VLM_SETTINGS } from './messages'

export type ValidationTone = 'ok' | 'warn' | 'muted'

export function validationBadge(status: VlmValidationStatus): { text: string; tone: ValidationTone } {
  switch (status) {
    case 'validated':
      return { text: 'Teruji', tone: 'ok' }
    case 'partial':
      return { text: 'Sebagian', tone: 'warn' }
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

/** Teks pilihan penyedia: label + keterangan setelan server yang belum diisi. */
export function providerOptionLabel(p: { label: string; missing: VlmMissingSetting }): string {
  if (p.missing === 'base_url') return `${p.label} ${VLM_SETTINGS.missingBaseUrl}`
  if (p.missing === 'key') return `${p.label} ${VLM_SETTINGS.missingKey}`
  return p.label
}

export type LocalFallbackAvailability = 'available' | 'backup_is_local' | 'no_local_provider'

type ProviderKind = { name: string; is_local: boolean }

/**
 * Apakah VLM lokal darurat (T72) bisa dipilih: bila cadangan = API atau tidak ada cadangan
 * (keduanya sah di backend; tanpa cadangan dulu disembunyikan lalu terhapus saat Terapkan —
 * tinjauan Codex 22-10). Cadangan lokal (susunan B) sudah siaga dingin sendiri — backend
 * menolak kombinasi itu (`local_fallback_with_local_backup`).
 */
export function localFallbackAvailability(backupProvider: string, providers: ProviderKind[]): LocalFallbackAvailability {
  if (!providers.some((p) => p.is_local)) return 'no_local_provider'
  return providers.find((p) => p.name === backupProvider)?.is_local ? 'backup_is_local' : 'available'
}

/** Isi `local_fallback` permintaan apply: null bila tidak tersedia atau tidak dipilih. */
export function localFallbackChoice(
  availability: LocalFallbackAvailability,
  provider: string,
  model: string,
): { provider: string; model: string } | null {
  return availability === 'available' && provider ? { provider, model } : null
}

export type BackupChange = 'unchanged' | 'disable' | 'enable_local' | 'other'

/**
 * Jenis perubahan VLM cadangan saat admin menekan Terapkan (T70).
 * `disable` perlu konfirmasi (model dikeluarkan dari GPU, pekerja menunggu bila VLM utama gangguan);
 * `enable_local` butuh waktu menyiapkan model di GPU, jadi teks menunggunya berbeda.
 */
export function backupChange(
  current: { provider: string; model: string } | null,
  nextProvider: string,
  nextModel: string,
  providers: { name: string; is_local: boolean }[],
): BackupChange {
  const same = (current?.provider ?? '') === nextProvider && (current?.model ?? '') === (nextProvider ? nextModel : '')
  if (same) return 'unchanged'
  if (!nextProvider) return 'disable'
  return providers.find((p) => p.name === nextProvider)?.is_local ? 'enable_local' : 'other'
}
