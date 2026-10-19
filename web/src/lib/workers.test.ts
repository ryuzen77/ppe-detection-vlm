import { describe, it, expect } from 'vitest'
import {
  validateWorkerForm,
  getWorkerBadge,
  formatWorkerSalutation,
  formatDeleteSchedule,
  isFaceReenrollmentNeeded,
  getConditionLabel,
  hasTemplateCondition,
  formatRecognizedWorker,
} from './workers'
import type { Worker } from './api/types'

describe('validateWorkerForm', () => {
  it('menolak bila persetujuan belum dicentang', () => {
    const err = validateWorkerForm({
      employee_no: 'P-001',
      name: 'Muhammad Zen Fikri',
      nickname: 'Zen',
      gender: 'male',
      consent: false,
    })
    expect(err?.toLowerCase()).toContain('persetujuan')
  })

  it('menolak bila nomor pegawai kosong', () => {
    const err = validateWorkerForm({
      employee_no: '   ',
      name: 'Muhammad Zen Fikri',
      nickname: 'Zen',
      gender: 'male',
      consent: true,
    })
    expect(err?.toLowerCase()).toContain('nomor pegawai')
  })

  it('menolak bila nama lengkap kosong', () => {
    const err = validateWorkerForm({
      employee_no: 'P-001',
      name: '   ',
      nickname: 'Zen',
      gender: 'male',
      consent: true,
    })
    expect(err?.toLowerCase()).toContain('nama lengkap')
  })

  it('menolak bila nama panggilan kosong', () => {
    const err = validateWorkerForm({
      employee_no: 'P-001',
      name: 'Muhammad Zen Fikri',
      nickname: '   ',
      gender: 'male',
      consent: true,
    })
    expect(err?.toLowerCase()).toContain('nama panggilan')
  })

  it('menolak bila jenis kelamin belum dipilih', () => {
    const err = validateWorkerForm({
      employee_no: 'P-001',
      name: 'Muhammad Zen Fikri',
      nickname: 'Zen',
      gender: '',
      consent: true,
    })
    expect(err?.toLowerCase()).toContain('jenis kelamin')
  })

  it('lolos bila semua bidang valid', () => {
    const err = validateWorkerForm({
      employee_no: 'P-001',
      name: 'Muhammad Zen Fikri',
      nickname: 'Zen',
      gender: 'male',
      consent: true,
    })
    expect(err).toBeNull()
  })
})

describe('getWorkerBadge', () => {
  const baseWorker: Worker = {
    id: 1,
    employee_no: 'P-001',
    name: 'Muhammad Zen Fikri',
    nickname: 'Zen',
    gender: 'male',
    salutation: 'Pak',
    active: true,
    consent: { at: '2026-10-18T10:00:00', by: 'admin', version: '1' },
    created_at: '2026-10-18T10:00:00',
    deactivated_at: null,
    delete_after: null,
    face_deleted_at: null,
    templates: [
      { id: 10, condition: 'bare', model_version: 'intel_0095', created_at: '2026-10-18T10:05:00' }
    ],
  }

  it('memberikan status aktif dan jumlah foto bila aktif dan punya templat', () => {
    const badge = getWorkerBadge(baseWorker)
    expect(badge.label).toBe('Aktif')
    expect(badge.variant).toBe('ok')
    expect(badge.hint).toBe('1 foto')
  })

  it('memberikan status perlu foto ulang bila aktif tapi templat kosong', () => {
    const badge = getWorkerBadge({ ...baseWorker, templates: [] })
    expect(badge.label).toBe('Perlu Foto Ulang')
    expect(badge.variant).toBe('warn')
  })

  it('memberikan status nonaktif dan jadwal hapus bila dinonaktifkan', () => {
    const badge = getWorkerBadge({
      ...baseWorker,
      active: false,
      deactivated_at: '2026-10-18T12:00:00',
      delete_after: '2026-11-17T12:00:00',
    })
    expect(badge.label).toBe('Nonaktif')
    expect(badge.variant).toBe('muted')
    expect(badge.hint).toContain('2026')
    expect(badge.hint).toContain('17')
  })

  it('memberikan status wajah terhapus bila data wajah sudah dihapus', () => {
    const badge = getWorkerBadge({
      ...baseWorker,
      active: false,
      deactivated_at: '2026-09-01T12:00:00',
      face_deleted_at: '2026-10-01T12:00:00',
      templates: [],
    })
    expect(badge.label).toBe('Nonaktif')
    expect(badge.hint).toBe('Data wajah terhapus')
  })
})

describe('formatWorkerSalutation', () => {
  it('menyertakan sapaan dan nama panggilan bila tersedia', () => {
    const text = formatWorkerSalutation({
      name: 'Muhammad Zen Fikri',
      nickname: 'Zen',
      salutation: 'Pak',
    })
    expect(text).toBe('Pak Zen')
  })

  it('menggunakan sapaan dari backend (mis. Bu)', () => {
    const text = formatWorkerSalutation({
      name: 'Siti Aminah',
      nickname: 'Siti',
      salutation: 'Bu',
    })
    expect(text).toBe('Bu Siti')
  })

  it('menggunakan nama lengkap bila tanpa nickname', () => {
    const text = formatWorkerSalutation({
      name: 'Budi Santoso',
      salutation: 'Pak',
    })
    expect(text).toBe('Pak Budi Santoso')
  })

  it('menggunakan nama saja bila tanpa salutation', () => {
    const text = formatWorkerSalutation({
      name: 'Budi Santoso',
    })
    expect(text).toBe('Budi Santoso')
  })
})

describe('isFaceReenrollmentNeeded', () => {
  it('true bila aktif dan templat kosong', () => {
    expect(isFaceReenrollmentNeeded({ active: true, templates: [] } as unknown as Worker)).toBe(true)
  })

  it('false bila aktif dan ada templat', () => {
    expect(isFaceReenrollmentNeeded({ active: true, templates: [{ id: 1 }] } as unknown as Worker)).toBe(false)
  })

  it('false bila nonaktif', () => {
    expect(isFaceReenrollmentNeeded({ active: false, templates: [] } as unknown as Worker)).toBe(false)
  })
})

describe('formatDeleteSchedule', () => {
  it('memformat tanggal ISO menjadi bentuk lokal ringkas', () => {
    const text = formatDeleteSchedule('2026-11-17T12:00:00')
    expect(text).toContain('17')
    expect(text).toContain('2026')
  })

  it('mengembalikan string kosong jika null', () => {
    expect(formatDeleteSchedule(null)).toBe('')
  })
})

describe('getConditionLabel', () => {
  it('mengembalikan label bahasa Indonesia yang ramah untuk tiap kondisi', () => {
    expect(getConditionLabel('bare').toLowerCase()).toContain('polos')
    expect(getConditionLabel('glasses').toLowerCase()).toContain('kacamata')
    expect(getConditionLabel('helmet').toLowerCase()).toContain('helm')
    expect(getConditionLabel('helmet_glasses').toLowerCase()).toContain('kacamata')
  })

  it('mengembalikan string apa adanya untuk kondisi tidak dikenal', () => {
    expect(getConditionLabel('custom_condition')).toBe('custom_condition')
  })
})

describe('hasTemplateCondition', () => {
  const workerWithBare = {
    templates: [{ condition: 'bare' }],
  } as unknown as Worker

  it('true bila kondisi sudah ada di templat pekerja', () => {
    expect(hasTemplateCondition(workerWithBare, 'bare')).toBe(true)
  })

  it('false bila kondisi belum ada di templat pekerja', () => {
    expect(hasTemplateCondition(workerWithBare, 'helmet')).toBe(false)
  })
})

describe('formatRecognizedWorker', () => {
  it('mengembalikan string "Dikenali: <nama>" bila status recognized dan nama ada', () => {
    const text = formatRecognizedWorker({ status: 'recognized', name: 'Muhammad Zen Fikri' })
    expect(text).toBe('Dikenali: Muhammad Zen Fikri')
  })

  it('mengembalikan null bila status bukan recognized', () => {
    expect(formatRecognizedWorker({ status: 'unknown', name: 'Unknown' })).toBeNull()
    expect(formatRecognizedWorker({ status: 'disabled', name: null })).toBeNull()
  })

  it('mengembalikan null bila identity null atau undefined atau nama kosong', () => {
    expect(formatRecognizedWorker(null)).toBeNull()
    expect(formatRecognizedWorker(undefined)).toBeNull()
    expect(formatRecognizedWorker({ status: 'recognized', name: '' })).toBeNull()
  })
})

