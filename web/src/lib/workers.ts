import type { Worker } from './api/types'
import { WORKERS } from './messages'

export interface WorkerFormData {
  /** Kosong = nomor otomatis dari backend (T79) */
  employee_no: string
  name: string
  nickname?: string
  gender?: string
  consent: boolean
}

export function validateWorkerForm(data: WorkerFormData): string | null {
  if (!data.consent) {
    return WORKERS.fieldConsentRequired
  }
  if (!data.name || data.name.trim() === '') {
    return WORKERS.fieldRequired(WORKERS.fieldName)
  }
  if (!data.nickname || data.nickname.trim() === '') {
    return WORKERS.fieldRequired(WORKERS.fieldNickname)
  }
  if (!data.gender || (data.gender !== 'male' && data.gender !== 'female')) {
    return WORKERS.fieldSelectRequired(WORKERS.fieldGender)
  }
  return null
}

export function getWorkerBadge(worker: Worker): {
  label: string
  variant: 'ok' | 'warn' | 'muted' | 'danger'
  hint?: string
} {
  if (!worker.active) {
    if (worker.face_deleted_at) {
      return {
        label: WORKERS.statusInactive,
        variant: 'muted',
        hint: WORKERS.statusFaceDeleted,
      }
    }
    if (worker.delete_after) {
      return {
        label: WORKERS.statusInactive,
        variant: 'muted',
        hint: WORKERS.deleteSchedule(formatDeleteSchedule(worker.delete_after)),
      }
    }
    return {
      label: WORKERS.statusInactive,
      variant: 'muted',
    }
  }

  return { label: WORKERS.statusActive, variant: 'ok' }
}

// --- Halaman Pekerja (T79) --------------------------------------------------------------

export type WorkerStatusFilter = 'active' | 'inactive' | 'all'

export interface WorkerFilter {
  q: string
  status: WorkerStatusFilter
  departmentId: number | null
  companyId: number | null
}

/** Saring di peramban: daftar pekerja kecil (batas galeri teruji ratusan), hasil langsung terasa. */
export function filterWorkers(workers: Worker[], f: WorkerFilter): Worker[] {
  const q = f.q.trim().toLowerCase()
  return workers.filter((w) => {
    if (f.status === 'active' && !w.active) return false
    if (f.status === 'inactive' && w.active) return false
    if (f.departmentId !== null && w.department?.id !== f.departmentId) return false
    if (f.companyId !== null && w.company?.id !== f.companyId) return false
    if (!q) return true
    return [w.employee_no, w.name, w.nickname ?? ''].some((v) => v.toLowerCase().includes(q))
  })
}

/**
 * Status data wajah. Pekerja baru belum pernah difoto ("Belum ada foto"); "Perlu foto ulang"
 * hanya bila data wajahnya pernah dihapus (analisa UI 19-10: pekerja baru tampil "Perlu Foto Ulang").
 */
export function faceStatus(worker: Worker): { label: string; tone: 'ok' | 'warn' | 'muted' } {
  const n = worker.templates.length
  if (n > 0) return { label: WORKERS.photoCount(n), tone: 'ok' }
  if (!worker.active) return { label: WORKERS.photoCount(0), tone: 'muted' }
  return { label: worker.face_deleted_at ? WORKERS.statusReenroll : WORKERS.faceNone, tone: 'warn' }
}

const HELMET_CONDITIONS = new Set(['helmet', 'helmet_glasses'])

/** Ringkasan foto per kondisi: tanpa helm vs dengan helm (pendaftaran terpandu T76). */
export function templateGroups(templates: { condition: string }[]): { label: string; count: number }[] {
  const helmet = templates.filter((t) => HELMET_CONDITIONS.has(t.condition)).length
  return [
    { label: WORKERS.groupNoHelmet, count: templates.length - helmet },
    { label: WORKERS.groupHelmet, count: helmet },
  ]
}

/** Perusahaan yang terpilih di form tambah: bawaan ("Internal"), atau yang pertama. */
export function defaultCompanyId(companies: { id: number; builtin?: boolean }[]): number | null {
  return (companies.find((c) => c.builtin) ?? companies[0])?.id ?? null
}

/** "Produksi · PT Maju" — perusahaan bawaan tetap ditulis supaya kontraktor & internal sejajar. */
export function orgSummary(worker: Pick<Worker, 'department' | 'company'>): string {
  const parts = [worker.department?.name, worker.company?.name].filter(Boolean)
  return parts.length ? parts.join(' · ') : WORKERS.orgNone
}

/** Tanggal & jam singkat lokal ("20 Okt 07.39"); teks asli bila tidak terbaca. */
export function formatShortDateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('id-ID', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function formatWorkerSalutation(worker: {
  name: string
  nickname?: string
  gender?: string
  salutation?: string | null
}): string {
  const displayName = (worker.nickname && worker.nickname.trim()) || worker.name.trim()
  return worker.salutation ? `${worker.salutation} ${displayName}` : displayName
}

export function formatDeleteSchedule(deleteAfterIso: string | null): string {
  if (!deleteAfterIso) return ''
  try {
    const d = new Date(deleteAfterIso)
    if (Number.isNaN(d.getTime())) {
      return deleteAfterIso.split('T')[0] || deleteAfterIso
    }
    return d.toLocaleDateString('id-ID', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return deleteAfterIso.split('T')[0] || deleteAfterIso
  }
}

export function getConditionLabel(condition: string): string {
  switch (condition) {
    case 'bare':
      return WORKERS.conditionBare
    case 'glasses':
      return WORKERS.conditionGlasses
    case 'helmet':
      return WORKERS.conditionHelmet
    case 'helmet_glasses':
      return WORKERS.conditionHelmetGlasses
    default:
      return condition
  }
}

export function formatRecognizedWorker(identity?: { status: string; name?: string | null } | null): string | null {
  if (identity && identity.status === 'recognized' && identity.name && identity.name.trim()) {
    return WORKERS.recognizedName(identity.name.trim())
  }
  return null
}

export function formatTemplateQuality(quality: { interocular_px: number }): string {
  return WORKERS.qualityBadge(Math.round(quality.interocular_px))
}
