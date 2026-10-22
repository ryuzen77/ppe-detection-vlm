/** Tafsir data backend untuk tampilan (tanpa teks tampilan; teks di messages.ts). */

export type SourceRole = 'utama' | 'cadangan' | 'darurat' | 'gangguan' | 'lama'

export interface SourceInfo {
  role: SourceRole
  /** Penyedia/model mentah, mis. "gemini/gemini-3.5-flash-lite" — untuk log/admin, bukan UI operator */
  label: string
}

/** Awalan `inference_source` dari backend (VLMEngine.label & _no_decision) */
const SOURCE_PREFIX = {
  primary: 'VLM_LIVE:',
  backup: 'VLM_CADANGAN:',
  localFallback: 'VLM_DARURAT:',
  outage: 'VLM_GANGGUAN',
  legacyGemini: 'GEMINI',
} as const

/**
 * Asal keputusan dari `inference_source`. Label lama tetap terbaca:
 * GEMINI_LIVE (sebelum T23), VLM_GAGAL (T21–T26), LOCAL_* / OFFLINE_FALLBACK
 * dari heuristik OpenCV yang sudah dibuang.
 */
export function describeSource(source: string | null | undefined): SourceInfo {
  const s = source ?? ''
  if (s.startsWith(SOURCE_PREFIX.primary)) return { role: 'utama', label: s.slice(SOURCE_PREFIX.primary.length) }
  if (s.startsWith(SOURCE_PREFIX.backup)) return { role: 'cadangan', label: s.slice(SOURCE_PREFIX.backup.length) }
  // T72: VLM lokal darurat (susunan A)
  if (s.startsWith(SOURCE_PREFIX.localFallback))
    return { role: 'darurat', label: s.slice(SOURCE_PREFIX.localFallback.length) }
  if (s === SOURCE_PREFIX.outage) return { role: 'gangguan', label: '' }
  // label sumber audit sebelum T23 (data lama), bukan UI lama
  if (s.includes(SOURCE_PREFIX.legacyGemini)) return { role: 'utama', label: 'gemini' }
  return { role: 'lama', label: s }
}
