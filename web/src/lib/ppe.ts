/**
 * Penilaian item APD di sisi tampilan.
 *
 * Cermin `PPEItem.is_satisfied` di backend: item harus terdeteksi, dan bila
 * punya syarat tambahan (qualifier) field syarat itu harus true. Keputusan
 * lengkap/tidak tetap dihitung backend; ini hanya untuk teks & warna per baris.
 */
import type { ItemResult, PpeItem } from './api/types'
import { CHECKLIST } from './messages'

/** ok: lengkap | missing: kurang | pending: belum dinilai (kuning, keputusan pengguna) */
export type ItemStatus = 'ok' | 'missing' | 'pending'

export interface ItemAssessment {
  status: ItemStatus
  text: string
}

export function assessItem(item: PpeItem, result: ItemResult | undefined | null): ItemAssessment {
  if (!result) return { status: 'pending', text: CHECKLIST.pending }
  if (item.prohibited) {
    if (result.detected) {
      return { status: 'missing', text: item.fail_label }
    }
    return { status: 'ok', text: item.ok_label }
  }
  const qualifier = item.qualifier
  const qualifierOk = qualifier ? Boolean(result[qualifier.key]) : true
  if (result.detected && qualifierOk) {
    const color = item.reports_color && typeof result.color === 'string' ? result.color : ''
    return { status: 'ok', text: color || item.ok_label }
  }
  if (result.detected && qualifier) return { status: 'missing', text: qualifier.fail_label }
  return { status: 'missing', text: item.fail_label }
}

/** Item yang sedang diwajibkan (diperiksa gerbang). */
export function activeItems(items: PpeItem[]): PpeItem[] {
  return items.filter((i) => i.required)
}
