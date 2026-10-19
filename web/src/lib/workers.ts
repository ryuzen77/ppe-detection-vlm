import type { Worker } from './api/types'
import { WORKERS } from './messages'

export interface WorkerFormData {
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
  if (!data.employee_no || data.employee_no.trim() === '') {
    return WORKERS.fieldRequired(WORKERS.fieldEmployeeNo)
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

export function isFaceReenrollmentNeeded(worker: Worker): boolean {
  return worker.active && worker.templates.length === 0
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

  if (isFaceReenrollmentNeeded(worker)) {
    return {
      label: WORKERS.statusReenroll,
      variant: 'warn',
    }
  }

  return {
    label: WORKERS.statusActive,
    variant: 'ok',
    hint: WORKERS.photoCount(worker.templates.length),
  }
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
