import { describe, expect, it } from 'vitest'
import type { PpeItem } from './api/types'
import { assessItem, ppeItemTone } from './ppe'

describe('ppeItemTone (pemetaan keadaan -> warna)', () => {
  it('saat gerbang siaga (tidak ada pekerja), item pending tampil netral', () => {
    // Siaga: standby, offline, no-camera
    expect(ppeItemTone('pending', 'standby')).toBe('neutral')
    expect(ppeItemTone('pending', 'offline')).toBe('neutral')
    expect(ppeItemTone('pending', 'no-camera')).toBe('neutral')
  })

  it('kuning hanya saat sedang menilai atau menunggu', () => {
    // Sedang menilai frame stabil / VLM: analyzing
    expect(ppeItemTone('pending', 'analyzing')).toBe('warn')
    // VLM gangguan dan mohon tunggu: waiting
    expect(ppeItemTone('pending', 'waiting')).toBe('warn')
    // Pekerja di jalur diarahkan posisinya: position
    expect(ppeItemTone('pending', 'position')).toBe('warn')
  })

  it('hasil tetap hijau untuk item lengkap dan merah untuk item kurang/melanggar', () => {
    expect(ppeItemTone('ok', 'granted')).toBe('ok')
    expect(ppeItemTone('ok', 'standby')).toBe('ok')
    expect(ppeItemTone('missing', 'denied')).toBe('danger')
    expect(ppeItemTone('missing', 'standby')).toBe('danger')
  })
})

describe('assessItem dengan tone', () => {
  const helm: PpeItem = {
    key: 'helm',
    label: 'Helm Keselamatan',
    short_label: 'Helm',
    icon: '',
    icon_name: 'hard-hat',
    ok_label: 'Terpakai',
    fail_label: 'Tidak ada',
    reports_color: false,
    required: true,
    prohibited: false,
    qualifier: null,
  }

  it('belum ada hasil dan gerbang siaga -> status pending dan tone neutral', () => {
    const res = assessItem(helm, null, 'standby')
    expect(res).toEqual({
      status: 'pending',
      text: 'Belum dinilai',
      tone: 'neutral',
    })
  })

  it('belum ada hasil dan gerbang sedang menganalisis -> status pending dan tone warn', () => {
    const res = assessItem(helm, null, 'analyzing')
    expect(res).toEqual({
      status: 'pending',
      text: 'Belum dinilai',
      tone: 'warn',
    })
  })

  it('belum ada hasil dan gerbang menunggu retry -> status pending dan tone warn', () => {
    const res = assessItem(helm, null, 'waiting')
    expect(res).toEqual({
      status: 'pending',
      text: 'Belum dinilai',
      tone: 'warn',
    })
  })

  it('item terdeteksi lengkap -> tone ok', () => {
    const res = assessItem(helm, { detected: true, color: '', description: '' }, 'granted')
    expect(res).toEqual({
      status: 'ok',
      text: 'Terpakai',
      tone: 'ok',
    })
  })

  it('item tidak terdeteksi -> tone danger', () => {
    const res = assessItem(helm, { detected: false, color: '', description: '' }, 'denied')
    expect(res).toEqual({
      status: 'missing',
      text: 'Tidak ada',
      tone: 'danger',
    })
  })
})
