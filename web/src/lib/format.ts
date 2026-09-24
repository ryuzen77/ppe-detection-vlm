/** Format teks tampilan yang dipakai lintas komponen. */

export type SourceRole = 'utama' | 'cadangan' | 'gangguan' | 'lama'

export interface SourceInfo {
  role: SourceRole
  /** Mis. "gemini/gemini-3.5-flash-lite" atau label lama apa adanya */
  label: string
}

/**
 * Asal keputusan dari `inference_source`.
 * VLM_LIVE:<p>/<m> = utama, VLM_CADANGAN:<p>/<m> = cadangan (T27). Label lama
 * tetap terbaca: GEMINI_LIVE (sebelum T23), VLM_GAGAL (T21–T26),
 * LOCAL_* / OFFLINE_FALLBACK dari heuristik OpenCV yang sudah dibuang.
 */
export function describeSource(source: string | null | undefined): SourceInfo {
  const s = source ?? ''
  if (s.startsWith('VLM_LIVE:')) return { role: 'utama', label: s.slice('VLM_LIVE:'.length) }
  if (s.startsWith('VLM_CADANGAN:')) return { role: 'cadangan', label: s.slice('VLM_CADANGAN:'.length) }
  if (s === 'VLM_GANGGUAN') return { role: 'gangguan', label: 'tanpa keputusan' }
  if (s.includes('GEMINI')) return { role: 'utama', label: 'gemini' }
  return { role: 'lama', label: s || '-' }
}

/** Detik → "3,2 dtk" (format Indonesia). */
export function seconds(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return '-'
  return `${(ms / 1000).toFixed(1).replace('.', ',')} dtk`
}
