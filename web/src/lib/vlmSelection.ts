import type { VlmMissingSetting, VlmModelListEntry, VlmModelListError, VlmRole, VlmValidationStatus } from './api/types'
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
  | { type: 'test_required'; code: string; message: string }
  | { type: 'error'; code: string; message: string; isWarn: boolean }

export function handleSelectionError(code: string, message: string): ActionRequired {
  if (code === 'needs_confirmation') {
    return { type: 'confirm', code, message }
  }
  // T97: model belum teruji wajib lolos Uji Penyedia (peran itu) sebelum Terapkan
  if (code === 'test_required') {
    return { type: 'test_required', code, message }
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
export function localFallbackAvailability(
  backupProvider: string,
  providers: ProviderKind[],
): LocalFallbackAvailability {
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

/**
 * Model setelah admin mengganti penyedia (temuan uji UI #13): model lama dipakai bila termasuk daftar
 * model penyedia baru; selain itu model bawaan penyedia, supaya tidak terkirim pasangan seperti
 * ollama/gemini-3.5-flash-lite (model yang tidak ada di penyedia itu).
 */
export function modelForProvider(
  provider: { default_model: string; models: { model: string }[] } | undefined,
  currentModel: string,
): string {
  if (!provider) return ''
  if (provider.models.some((m) => m.model === currentModel)) return currentModel
  return provider.default_model || provider.models[0]?.model || ''
}

type Choice = { provider: string; model: string } | null

const sameChoice = (a: Choice, b: Choice) =>
  (a?.provider ?? '') === (b?.provider ?? '') && (a?.provider ? a.model === b?.model : true)

/** Formulir berbeda dari setelan yang berlaku di server (perlu Terapkan) */
export function formDirty(
  current: { primary: Choice; backup: Choice; local_fallback?: Choice },
  form: { primary: Choice; backup: Choice; local_fallback: Choice },
): boolean {
  return (
    !sameChoice(current.primary, form.primary) ||
    !sameChoice(current.backup, form.backup) ||
    !sameChoice(current.local_fallback ?? null, form.local_fallback)
  )
}

export type BackupChange = 'unchanged' | 'disable' | 'enable_local' | 'other'

/**
 * Jenis perubahan VLM cadangan saat admin menekan Terapkan (T70).
 * `disable` perlu konfirmasi (model dikeluarkan dari GPU, pekerja menunggu bila VLM utama gangguan);
 * `enable_local` butuh waktu menyiapkan model di GPU, jadi teks menunggunya berbeda.
 */
/** Cadangan yang SEDANG aktif adalah VLM lokal (memakai GPU) — teks GPU & kartu kesehatan hanya untuknya */
export function currentBackupIsLocal(
  current: { provider: string } | null,
  providers: { name: string; is_local: boolean }[],
): boolean {
  return !!current && !!providers.find((p) => p.name === current.provider)?.is_local
}

/** Kalimat + catatan GPU bila cadangan aktif lokal (temuan uji UI #12) */
export function withLocalNote(text: string, note: string, isLocal: boolean): string {
  return isLocal ? `${text} ${note}` : text
}

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

// --- T97: daftar model dari penyedia

const TESTED_STATUSES: VlmValidationStatus[] = ['validated', 'partial']
// Sama dengan NEEDS_CONFIRMATION backend: Terapkan butuh uji penyedia yang masih segar
const TEST_FIRST_STATUSES: VlmValidationStatus[] = ['unvalidated', 'outdated']

export const isTested = (status: VlmValidationStatus) => TESTED_STATUSES.includes(status)
export const needsTest = (status: VlmValidationStatus) => TEST_FIRST_STATUSES.includes(status)

/** Model yang boleh dipilih: ada di akun penyedia & tidak pernah meloloskan APD kurang (selalu ditolak server). */
export const modelSelectable = (m: VlmModelListEntry) => m.available !== false && m.validated !== 'unsafe'

const byName = (a: VlmModelListEntry, b: VlmModelListEntry) =>
  a.model.localeCompare(b.model, undefined, { sensitivity: 'base' })

/** Grup dropdown: "Sudah diuji" lalu "Tersedia, belum diuji", masing-masing A–Z. */
export function groupModels(models: VlmModelListEntry[]): {
  tested: VlmModelListEntry[]
  untested: VlmModelListEntry[]
} {
  const tested = models.filter((m) => isTested(m.validated)).sort(byName)
  const untested = models.filter((m) => !isTested(m.validated)).sort(byName)
  return { tested, untested }
}

/** Teks pilihan dropdown: model katalog yang tidak ada di akun ditandai (dan dinonaktifkan oleh komponen). */
export function modelOptionLabel(m: VlmModelListEntry, unavailableText: string): string {
  return m.available === false ? `${m.model} (${unavailableText})` : m.model
}

/**
 * Model setelah daftar penyedia dimuat ulang karena admin mengganti penyedia: model sekarang bila bisa
 * dipilih, lalu model bawaan penyedia, lalu model pertama yang bisa dipilih (teruji lebih dulu).
 */
export function reconcileModel(models: VlmModelListEntry[], current: string, defaultModel: string): string {
  const selectable = models.filter(modelSelectable)
  const pick = (name: string) => selectable.find((m) => m.model === name)?.model
  const { tested, untested } = groupModels(selectable)
  return pick(current) ?? pick(defaultModel) ?? tested[0]?.model ?? untested[0]?.model ?? current
}

/**
 * Daftar milik pilihan sekarang? Selama daftar penyedia baru dimuat, daftar penyedia lama tidak boleh
 * tampil/dipilih — pasangan penyedia baru + model penyedia lama bisa terkirim (tinjauan Codex T97b).
 */
export function listMatches(
  list: { provider: string; role: VlmRole } | null,
  provider: string | undefined,
  role: VlmRole,
): boolean {
  return !!list && !!provider && list.provider === provider && list.role === role
}

/** Alasan daftar gagal (`source: 'catalog'`); `request` = permintaan ke server sendiri yang gagal. */
export function modelListReason(
  error: VlmModelListError | 'request' | null,
  reasons: Record<VlmModelListError | 'request', string>,
): string {
  return reasons[error ?? 'request']
}

/** Status validasi pilihan menurut katalog penyedia; model di luar katalog = belum teruji (sama dengan backend). */
export function validationOf(
  provider: { models: { model: string; validated: VlmValidationStatus }[] } | undefined,
  model: string,
): VlmValidationStatus {
  return provider?.models.find((m) => m.model === model)?.validated ?? 'unvalidated'
}

/** Peran yang modelnya perlu Uji Penyedia dulu (galat `test_required`), urut utama → cadangan → lokal. */
export function rolesNeedingTest(choices: { role: VlmRole; model: string; status: VlmValidationStatus }[]): VlmRole[] {
  return choices.filter((c) => c.model && needsTest(c.status)).map((c) => c.role)
}
