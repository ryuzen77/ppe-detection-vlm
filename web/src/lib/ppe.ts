/**
 * Penilaian item APD di sisi tampilan.
 *
 * Cermin `PPEItem.is_satisfied` di backend: item harus terdeteksi, dan bila
 * punya syarat tambahan (qualifier) field syarat itu harus true. Keputusan
 * lengkap/tidak tetap dihitung backend; ini hanya untuk teks & warna per baris.
 */
import type { ItemResult, PpeItem } from './api/types'
import type { GateKind, Tone } from './gate'
import { CHECKLIST } from './messages'

/** ok: lengkap | missing: kurang | pending: belum dinilai */
export type ItemStatus = 'ok' | 'missing' | 'pending'

export interface ItemAssessment {
  status: ItemStatus
  text: string
  tone: Tone
}

/**
 * Pemetaan keadaan gerbang & status item ke warna tampilan (tone):
 * - saat gerbang siaga (tidak ada pekerja: 'standby', 'offline', 'no-camera'): item tampil netral
 * - saat sedang menilai atau menunggu ('analyzing', 'waiting', 'position'): kuning ('warn')
 * - setelah ada hasil: tetap hijau ('ok') atau merah ('danger')
 */
export function ppeItemTone(status: ItemStatus, gateKind: GateKind = 'standby'): Tone {
  if (status === 'ok') return 'ok'
  if (status === 'missing') return 'danger'
  if (gateKind === 'analyzing' || gateKind === 'waiting' || gateKind === 'position') {
    return 'warn'
  }
  return 'neutral'
}

export function assessItem(
  item: PpeItem,
  result: ItemResult | undefined | null,
  gateKind: GateKind = 'standby'
): ItemAssessment {
  if (!result) {
    return {
      status: 'pending',
      text: CHECKLIST.pending,
      tone: ppeItemTone('pending', gateKind),
    }
  }
  if (item.prohibited) {
    if (result.detected) {
      return { status: 'missing', text: item.fail_label, tone: 'danger' }
    }
    return { status: 'ok', text: item.ok_label, tone: 'ok' }
  }
  const qualifier = item.qualifier
  const qualifierOk = qualifier ? Boolean(result[qualifier.key]) : true
  if (result.detected && qualifierOk) {
    const color = item.reports_color && typeof result.color === 'string' ? result.color : ''
    return { status: 'ok', text: color || item.ok_label, tone: 'ok' }
  }
  if (result.detected && qualifier) return { status: 'missing', text: qualifier.fail_label, tone: 'danger' }
  return { status: 'missing', text: item.fail_label, tone: 'danger' }
}

/** Item yang sedang diwajibkan (diperiksa gerbang). */
/**
 * Isi `POST /api/ppe-rules/active` saat satu centang APD Wajib diubah: backend menerima status
 * SEMUA item, jadi item lain wajib diambil dari katalog terkini — katalog basi menimpa
 * pilihan sebelumnya (bug T89).
 */
export function requiredMap(items: PpeItem[], key: string, required: boolean): Record<string, boolean> {
  return Object.fromEntries(items.map((item) => [item.key, item.key === key ? required : item.required]))
}

export function activeItems(items: PpeItem[]): PpeItem[] {
  return items.filter((i) => i.required)
}
