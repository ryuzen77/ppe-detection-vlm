// T72: VLM lokal siaga dingin + pemantau internet — chip operator, pilihan admin, notifikasi.
import { describe, expect, it } from 'vitest'
import type { InternetStatus, LocalStandby, MonitorStatus, Telemetry } from './api/types'
import { describeSource } from './format'
import { detectEvents } from './notify'
import { sourceText } from './reports'
import { internetChip, localStandbyChip, systemSummary, vlmChip } from './status'
import { localFallbackAvailability, localFallbackChoice, providerOptionLabel } from './vlmSelection'

function tele(monitor: Partial<MonitorStatus>): Telemetry {
  return { api_monitor: { mode: 'UTAMA', ...monitor } as MonitorStatus, history: [] } as unknown as Telemetry
}
const internet = (state: InternetStatus['state']): InternetStatus => ({ state, median_ms: 40, checked_at: '08:00:00' })
const local = (state: LocalStandby['state'], role: LocalStandby['role'] = 'darurat'): LocalStandby => ({ role, state, since: null })

const PROVIDERS = [
  { name: 'gemini', is_local: false },
  { name: 'openrouter', is_local: false },
  { name: 'ollama', is_local: true },
]

describe('chip internet (T72)', () => {
  it('tidak tampil tanpa pemantau (server lama / tanpa VLM lokal)', () => {
    expect(internetChip(null)).toBeNull()
    expect(internetChip(tele({}))).toBeNull()
    expect(internetChip(tele({ internet: internet(null) }))).toBeNull()
  })

  it('normal hijau; lambat & putus kuning — bukan merah (gerbang masih menilai lewat VLM lokal)', () => {
    expect(internetChip(tele({ internet: internet('normal') }))).toMatchObject({ tone: 'ok', text: 'Internet: normal' })
    expect(internetChip(tele({ internet: internet('lambat') }))).toMatchObject({ tone: 'warn', text: 'Internet: lambat' })
    const putus = internetChip(tele({ internet: internet('putus') }))
    expect(putus).toMatchObject({ tone: 'warn', text: 'Internet: putus' })
    expect(putus?.hint).toMatch(/VLM lokal/)
  })
})

describe('chip VLM lokal (T72)', () => {
  it('tidak tampil bila tidak ada VLM lokal siaga', () => {
    expect(localStandbyChip(tele({}))).toBeNull()
    expect(localStandbyChip(tele({ local: local('unloaded', null) }))).toBeNull()
  })

  it('nada per state; siaga netral sehingga tidak dihitung masalah', () => {
    const tone = (s: LocalStandby['state']) => localStandbyChip(tele({ local: local(s) }))?.tone
    expect(tone('unloaded')).toBe('neutral')
    expect(tone('loading')).toBe('warn')
    expect(tone('ready')).toBe('ok')
    expect(tone('failed')).toBe('warn')
    const siaga = localStandbyChip(tele({ local: local('unloaded', 'cadangan') }))!
    expect(systemSummary([{ tone: 'ok', text: 'VLM utama', hint: '' }, siaga]).problems).toHaveLength(0)
  })

  it('tanpa nama penyedia/model di chip operator (AGENTS §5)', () => {
    for (const s of ['unloaded', 'loading', 'ready', 'failed'] as const) {
      const chip = localStandbyChip(tele({ local: local(s) }))!
      expect(`${chip.text} ${chip.hint}`).not.toMatch(/ollama|qwen|gemini/i)
    }
  })

  it('tanpa cadangan API tetapi ada darurat lokal: bukan "tanpa cadangan"', () => {
    const monitor = (role: LocalStandby['role']) =>
      tele({ backup: { configured: false } as MonitorStatus['backup'], local: local('unloaded', role) })
    expect(vlmChip(monitor('darurat')).text).toBe('VLM utama')
    expect(vlmChip(monitor(null)).text).toBe('VLM utama · tanpa cadangan')
  })

  it('mode LOKAL: chip VLM kuning dengan teks umum', () => {
    expect(vlmChip(tele({ mode: 'LOKAL' }))).toMatchObject({ tone: 'warn', text: 'VLM lokal' })
  })
})

describe('sumber keputusan VLM lokal darurat (T72)', () => {
  it('VLM_DARURAT: terbaca sebagai darurat, teks laporan tanpa nama model', () => {
    expect(describeSource('VLM_DARURAT:ollama/qwen2.5vl:7b')).toEqual({ role: 'darurat', label: 'ollama/qwen2.5vl:7b' })
    expect(sourceText('VLM_DARURAT:ollama/qwen2.5vl:7b')).toEqual({ role: 'darurat', text: 'VLM lokal darurat' })
    // awalan lama tidak berubah
    expect(describeSource('VLM_CADANGAN:gemini/x').role).toBe('cadangan')
  })
})

describe('notifikasi pulih (T72)', () => {
  it('gangguan → LOKAL menyebut VLM lokal, bukan cadangan', () => {
    const prev = { lastHistoryKey: '', lastMode: 'GANGGUAN' as const }
    const { events } = detectEvents(prev, tele({ mode: 'LOKAL' }))
    expect(events).toHaveLength(1)
    expect(events[0].detail).toBe('VLM lokal kembali menilai.')
  })
})

describe('pilihan VLM lokal darurat (T72)', () => {
  it('hanya tersedia bila cadangan = API (susunan A)', () => {
    expect(localFallbackAvailability('gemini', PROVIDERS)).toBe('available')
    expect(localFallbackAvailability('ollama', PROVIDERS)).toBe('backup_is_local')
    // tanpa cadangan + darurat lokal sah (tinjauan Codex 22-10): pilihan tampil & tidak terhapus
    expect(localFallbackAvailability('', PROVIDERS)).toBe('available')
    expect(localFallbackAvailability('gemini', PROVIDERS.filter((p) => !p.is_local))).toBe('no_local_provider')
  })

  it('isi permintaan apply: null bila tidak tersedia atau tidak dipilih', () => {
    expect(localFallbackChoice('available', 'ollama', 'qwen2.5vl:7b')).toEqual({ provider: 'ollama', model: 'qwen2.5vl:7b' })
    expect(localFallbackChoice('available', '', '')).toBeNull()
    // Cadangan diganti ke lokal setelah darurat dipilih: pilihan lama tidak ikut terkirim
    expect(localFallbackChoice('backup_is_local', 'ollama', 'qwen2.5vl:7b')).toBeNull()
    expect(localFallbackChoice('no_local_provider', 'ollama', 'qwen2.5vl:7b')).toBeNull()
  })

  it('label penyedia menyebut setelan server yang belum diisi', () => {
    expect(providerOptionLabel({ label: 'Ollama', missing: null })).toBe('Ollama')
    expect(providerOptionLabel({ label: 'Gemini', missing: 'key' })).toMatch(/^Gemini \(API key/)
    expect(providerOptionLabel({ label: 'vLLM', missing: 'base_url' })).toMatch(/VLM_BASE_URL/)
  })
})
