import { describe, it, expect } from 'vitest'
import {
  validateWorkerForm,
  getWorkerBadge,
  formatWorkerSalutation,
  formatDeleteSchedule,
  getConditionLabel,
  filterWorkers,
  faceStatus,
  templateGroups,
  orgSummary,
  defaultCompanyId,
  formatRecognizedWorker,
  formatTemplateQuality,
} from './workers'
import type { Worker, WorkerTemplateQuality } from './api/types'

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

  it('nomor pegawai boleh kosong: backend mengisi nomor otomatis (T79)', () => {
    const err = validateWorkerForm({
      employee_no: '   ',
      name: 'Muhammad Zen Fikri',
      nickname: 'Zen',
      gender: 'male',
      consent: true,
    })
    expect(err).toBeNull()
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
    templates: [{ id: 10, condition: 'bare', model_version: 'intel_0095', created_at: '2026-10-18T10:05:00' }],
  }

  it('aktif = Aktif; status foto ada di kolom sendiri (faceStatus)', () => {
    expect(getWorkerBadge(baseWorker)).toEqual({ label: 'Aktif', variant: 'ok' })
    expect(getWorkerBadge({ ...baseWorker, templates: [] })).toEqual({ label: 'Aktif', variant: 'ok' })
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

describe('formatTemplateQuality', () => {
  it('memformat kualitas wajah dengan jarak mata dalam px sesuai data dari backend', () => {
    const quality: WorkerTemplateQuality = {
      face_width_px: 120,
      interocular_px: 48.2,
      det_score: 0.985,
    }
    expect(formatTemplateQuality(quality)).toBe('Jarak mata 48 px')
  })
})

// --- Halaman Pekerja (T79) ---

const worker = (over: Partial<Worker>): Worker => ({
  id: 1,
  employee_no: 'P-0001',
  name: 'Muhammad Zen Fikri',
  nickname: 'Zen',
  active: true,
  consent: { at: '2026-10-18T10:00:00', by: 'admin', version: '1' },
  created_at: '2026-10-18T10:00:00',
  deactivated_at: null,
  delete_after: null,
  face_deleted_at: null,
  templates: [],
  ...over,
})

describe('faceStatus', () => {
  it('pekerja baru tanpa foto = "Belum ada foto", bukan "Perlu foto ulang" (analisa UI 19-10)', () => {
    expect(faceStatus(worker({}))).toEqual({ label: 'Belum ada foto', tone: 'warn' })
  })
  it('data wajah pernah dihapus = perlu foto ulang', () => {
    expect(faceStatus(worker({ face_deleted_at: '2026-10-19T19:19:07' })).label).toBe('Perlu foto ulang')
  })
  it('punya foto = jumlah foto; nonaktif tanpa foto tidak diberi peringatan', () => {
    const t = { id: 1, condition: 'bare', model_version: 'x', created_at: '' }
    expect(faceStatus(worker({ templates: [t, t] }))).toEqual({ label: '2 foto', tone: 'ok' })
    expect(faceStatus(worker({ active: false })).tone).toBe('muted')
  })
})

describe('filterWorkers', () => {
  const list = [
    worker({
      id: 1,
      employee_no: 'P-0001',
      name: 'Budi',
      department: { id: 1, name: 'Produksi' },
      company: { id: 1, name: 'Internal' },
    }),
    worker({
      id: 2,
      employee_no: 'K-77',
      name: 'Siti',
      nickname: 'Ti',
      active: false,
      company: { id: 2, name: 'PT Maju' },
    }),
  ]
  const all = { q: '', status: 'all' as const, departmentId: null, companyId: null }

  it('cari nomor, nama, atau panggilan tanpa beda huruf besar', () => {
    expect(filterWorkers(list, { ...all, q: 'p-00' }).map((w) => w.id)).toEqual([1])
    expect(filterWorkers(list, { ...all, q: 'ti' }).map((w) => w.id)).toEqual([2])
  })
  it('status, divisi, perusahaan', () => {
    expect(filterWorkers(list, { ...all, status: 'active' }).map((w) => w.id)).toEqual([1])
    expect(filterWorkers(list, { ...all, status: 'inactive' }).map((w) => w.id)).toEqual([2])
    expect(filterWorkers(list, { ...all, departmentId: 1 }).map((w) => w.id)).toEqual([1])
    expect(filterWorkers(list, { ...all, companyId: 2 }).map((w) => w.id)).toEqual([2])
  })
})

describe('defaultCompanyId', () => {
  it('perusahaan bawaan terpilih; tanpa daftar = null (backend lama)', () => {
    const c = (id: number, builtin = false) => ({ id, name: `c${id}`, workers: 0, builtin })
    expect(defaultCompanyId([c(3), c(1, true)])).toBe(1)
    expect(defaultCompanyId([c(3), c(4)])).toBe(3)
    expect(defaultCompanyId([])).toBeNull()
  })
})

describe('templateGroups & orgSummary', () => {
  it('foto dikelompokkan tanpa helm / dengan helm', () => {
    const c = (condition: string) => ({ condition })
    expect(templateGroups([c('bare'), c('glasses'), c('helmet'), c('helmet_glasses')])).toEqual([
      { label: 'Tanpa helm', count: 2 },
      { label: 'Dengan helm', count: 2 },
    ])
  })
  it('divisi · perusahaan; kosong = tanda pisah (backend lama tanpa kolom T79)', () => {
    expect(orgSummary({ department: { id: 1, name: 'Produksi' }, company: { id: 2, name: 'PT Maju' } })).toBe(
      'Produksi · PT Maju',
    )
    expect(orgSummary({ department: null, company: { id: 1, name: 'Internal' } })).toBe('Internal')
    expect(orgSummary({})).toBe('—')
  })
})
