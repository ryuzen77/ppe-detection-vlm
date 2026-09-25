import { describe, expect, it } from 'vitest'
import type { ActiveTrack, HistoryRecord, InspectionResult, PpeItem, Telemetry } from './api/types'
import type { CameraState } from './api/types'
import { describeSource } from './format'
import { gateView } from './gate'
import { computeFit, detectionStyle, drawHud, withAlpha, type HudPalette } from './hud'
import { CAMERA_CHIP, CAMERA_NOT_READY, VIDEO, seconds } from './messages'
import { detectEvents, initialWatch } from './notify'
import { assessItem } from './ppe'
import { parseRoute } from './router.svelte'
import { cameraChip, vlmChip } from './status'
import { readItem, writeItem } from './storage'

// --- data tiruan ---------------------------------------------------------------

function result(over: Partial<InspectionResult> = {}): InspectionResult {
  return {
    items: {}, is_complete: true, missing_items: [], notes: '', inference_source: 'VLM_LIVE:gemini/m',
    inference_time_ms: 1500, decided_by: 'utama', is_system_unavailable: false, ...over,
  }
}

function track(over: Partial<ActiveTrack> = {}): ActiveTrack {
  return {
    track_id: 42, session_id: 1, state: 'INITIAL', is_full_body: true, reason: '', clip_type: 'OPTIMAL',
    stable_frames: 0, retry_in_s: null, vlm_result: null, ...over,
  }
}

function tele(over: Partial<Telemetry> = {}): Telemetry {
  return {
    timestamp: 0, frame_width: 1280, frame_height: 720, has_person: false, active_track: null, detections: [],
    corridor: { enabled: true, left_ratio: 0.3, right_ratio: 0.7 },
    light: { light_state: 'OFF', message: '', timestamp: 0 }, history: [], stable_frames_required: 3,
    keypoint_conf_threshold: 0.35,
    is_live_vlm: true,
    vlm: { role: 'utama', provider: 'gemini', model: 'm', is_local: false, needs_key: true, has_key: true, is_live: true, timeout_s: 4, error: '', backup: null, primary_down: false },
    api_monitor: { mode: 'UTAMA' } as Telemetry['api_monitor'],
    fps: 30, audio_muted: false,
    camera: { index: 0, name: 'Cam', selected: true, status: 'OK', error: '', mode: null, optimizing: false, width: 1280, height: 720, fps: 30, is_synthetic: false },
    ...over,
  }
}

// --- panel keputusan -------------------------------------------------------------

describe('gateView', () => {
  it('server terputus', () => {
    expect(gateView(tele(), 'disconnected').kind).toBe('offline')
    expect(gateView(null, 'connected').kind).toBe('offline')
  })

  it('kamera belum dipilih / terputus', () => {
    const v = gateView(tele({ camera: { ...tele().camera, status: 'IDLE', selected: false } }), 'connected')
    expect([v.kind, v.tone]).toEqual(['no-camera', 'warn'])
    expect(gateView(tele({ camera: { ...tele().camera, status: 'LOST' } }), 'connected').detail).toMatch(/terputus/)
  })

  it('menunggu pekerja', () => {
    expect(gateView(tele(), 'connected')).toMatchObject({ kind: 'standby', tone: 'neutral' })
  })

  it('arahan posisi memakai kuning, bukan merah (merah khusus APD kurang)', () => {
    const v = gateView(tele({ active_track: track({ is_full_body: false, clip_type: 'FEET_CLIPPED' }) }), 'connected')
    expect(v).toMatchObject({ kind: 'position', tone: 'warn', title: 'Mundur satu langkah', trackId: 42 })
  })

  it('mengumpulkan frame stabil menampilkan kemajuan', () => {
    const v = gateView(tele({ active_track: track({ state: 'STABILIZING', stable_frames: 2 }) }), 'connected')
    expect(v.kind).toBe('analyzing')
    expect(v.progress).toBeCloseTo(2 / 3)
  })

  it('lolos dan ditolak', () => {
    const ok = gateView(tele({ active_track: track({ state: 'ANALYZED', vlm_result: result() }) }), 'connected')
    expect(ok).toMatchObject({ kind: 'granted', tone: 'ok' })
    const bad = gateView(tele({ active_track: track({ state: 'ANALYZED', vlm_result: result({ is_complete: false, missing_items: ['Rompi'] }) }) }), 'connected')
    expect(bad).toMatchObject({ kind: 'denied', tone: 'danger', missing: ['Rompi'] })
  })

  it('keputusan tetap tampil walau pekerja bergeser (terkunci per sesi)', () => {
    const v = gateView(tele({ active_track: track({ state: 'ANALYZED', is_full_body: false, clip_type: 'FEET_CLIPPED', vlm_result: result({ is_complete: false, missing_items: ['Helm'] }) }) }), 'connected')
    expect(v.kind).toBe('denied')
  })

  it('gangguan sistem: mohon tunggu dengan hitung mundur, bukan ditolak', () => {
    const v = gateView(tele({ active_track: track({ state: 'WAITING_SYSTEM', retry_in_s: 12.3 }) }), 'connected')
    expect(v).toMatchObject({ kind: 'waiting', tone: 'warn' })
    expect(v.detail).toMatch(/13 dtk/)
  })
})

// --- penilaian APD ----------------------------------------------------------------

describe('assessItem', () => {
  const rompi: PpeItem = {
    key: 'rompi', label: 'Rompi', short_label: 'Rompi', icon: '', icon_name: 'safety-vest', ok_label: 'Terpasang', fail_label: 'Tidak ada',
    reports_color: true, required: true, qualifier: { key: 'is_valid_color', fail_label: 'Bukan hi-vis' },
  }
  it('belum dinilai = pending (kuning)', () => {
    expect(assessItem(rompi, undefined)).toEqual({ status: 'pending', text: 'Belum dinilai' })
  })
  it('lengkap menampilkan warna bila item melaporkan warna', () => {
    expect(assessItem(rompi, { detected: true, color: 'orange', description: '', is_valid_color: true })).toEqual({ status: 'ok', text: 'orange' })
  })
  it('terdeteksi tetapi syarat tambahan gagal', () => {
    expect(assessItem(rompi, { detected: true, color: 'biru', description: '', is_valid_color: false })).toEqual({ status: 'missing', text: 'Bukan hi-vis' })
  })
  it('tidak terdeteksi', () => {
    expect(assessItem(rompi, { detected: false, color: '', description: '' }).status).toBe('missing')
  })
})

// --- notifikasi ---------------------------------------------------------------------

describe('detectEvents', () => {
  const rec = (id: number, ok: boolean, snap = `s${id}`): HistoryRecord => ({
    track_id: id, timestamp: `10:00:0${id}`, is_complete: ok, items: {}, missing_items: ok ? [] : ['Helm'], notes: '',
    inference_source: 'VLM_LIVE:x/y', inference_time_ms: 1, decided_by: 'utama', snapshot_filename: snap,
  })

  it('telemetri pertama tidak memicu notifikasi riwayat lama', () => {
    const { events } = detectEvents(initialWatch(), tele({ history: [rec(1, false)] }))
    expect(events).toEqual([])
  })

  it('pekerja ditolak yang baru memicu notifikasi; yang lolos tidak', () => {
    let { next } = detectEvents(initialWatch(), tele({ history: [rec(1, true)] }))
    const r = detectEvents(next, tele({ history: [rec(3, false), rec(2, true), rec(1, true)] }))
    expect(r.events.map((e) => e.title)).toEqual(['Pekerja #3 ditolak'])
    next = r.next
    expect(detectEvents(next, tele({ history: [rec(3, false), rec(2, true), rec(1, true)] })).events).toEqual([])
  })

  it('gangguan dan pulih', () => {
    let { next } = detectEvents(initialWatch(), tele())
    const down = detectEvents(next, tele({ api_monitor: { mode: 'GANGGUAN' } as Telemetry['api_monitor'] }))
    expect(down.events.map((e) => e.kind)).toEqual(['outage'])
    next = down.next
    const up = detectEvents(next, tele({ api_monitor: { mode: 'CADANGAN' } as Telemetry['api_monitor'] }))
    expect(up.events.map((e) => e.kind)).toEqual(['recovered'])
  })
})

// --- router, format, overlay -----------------------------------------------------------

describe('parseRoute', () => {
  it.each([
    ['#/laporan', 'laporan'], ['#/pengaturan', 'pengaturan'], ['#/monitoring', 'monitoring'],
    ['', 'monitoring'], ['#/tidak-ada', 'monitoring'], ['#/laporan?status=all', 'laporan'],
  ])('%s → %s', (hash, route) => {
    expect(parseRoute(hash)).toBe(route)
  })
})

describe('describeSource', () => {
  it.each([
    ['VLM_LIVE:gemini/g', 'utama', 'gemini/g'],
    ['VLM_CADANGAN:ollama/qwen2.5vl:7b', 'cadangan', 'ollama/qwen2.5vl:7b'],
    ['VLM_GANGGUAN', 'gangguan', ''],
    ['GEMINI_LIVE', 'utama', 'gemini'],
    ['LOCAL_FAST_PASS', 'lama', 'LOCAL_FAST_PASS'],
  ])('%s', (src, role, label) => {
    expect(describeSource(src)).toEqual({ role, label })
  })
  it('detik berformat Indonesia', () => {
    expect(seconds(1543)).toBe('1,5 dtk')
    expect(seconds(null)).toBe('-')
  })
})

describe('overlay', () => {
  const palette: HudPalette = { ok: '#00ff00', warn: '#ffaa00', outside: '#777777', text: '#ffffff', background: '#000000', font: 'sans-serif' }

  it('video 16:9 di kanvas 4:3 diberi bilah atas-bawah, bukan diregangkan', () => {
    const f = computeFit(800, 600, 1280, 720)
    expect(f.drawW).toBe(800)
    expect(f.drawH).toBe(450)
    expect(f.offsetY).toBe(75)
  })
  it('warna kotak dari palet token: pas hijau, arahan kuning, di luar jalur abu', () => {
    const base = { track_id: 1, bbox: [0, 0, 1, 1] as [number, number, number, number], reason: '', conf: 1, keypoints: null }
    expect(detectionStyle({ ...base, is_full_body: true, is_inside_corridor: true, clip_type: 'OPTIMAL' }, palette).color).toBe(palette.ok)
    expect(detectionStyle({ ...base, is_full_body: false, is_inside_corridor: true, clip_type: 'FEET_CLIPPED' }, palette).color).toBe(palette.warn)
    expect(detectionStyle({ ...base, is_full_body: true, is_inside_corridor: false, clip_type: 'OPTIMAL' }, palette).color).toBe(palette.outside)
  })
  it('drawHud memakai palet & ambang keypoint dari backend', () => {
    const calls: { fn: string; style?: string }[] = []
    const ctx = new Proxy({} as Record<string, unknown>, {
      get(target, prop: string) {
        if (prop in target) return target[prop]
        if (prop === 'measureText') return () => ({ width: 50 })
        return (..._args: unknown[]) => calls.push({ fn: prop, style: String(target.fillStyle ?? '') })
      },
      set(target, prop: string, value) {
        target[prop] = value
        return true
      },
    }) as unknown as CanvasRenderingContext2D
    const det = {
      track_id: 7, bbox: [100, 100, 300, 600] as [number, number, number, number], reason: '', conf: 0.9,
      is_full_body: true, is_inside_corridor: true, clip_type: 'OPTIMAL',
      // satu titik di atas ambang 0.35, satu di bawahnya
      keypoints: [[150, 150, 0.9], [160, 160, 0.2]],
    }
    drawHud(ctx, 800, 450, tele({ detections: [det] }), true, palette)
    expect(calls.filter((c) => c.fn === 'arc')).toHaveLength(1)
    expect(calls.some((c) => c.fn === 'fillText')).toBe(true)
    expect((ctx as unknown as { font: string }).font).toContain(palette.font)
  })
  it('warna token + alfa', () => {
    expect(withAlpha('#ff8000', 0.5)).toBe('rgba(255, 128, 0, 0.5)')
    expect(withAlpha('rgb(1,2,3)', 0.5)).toBe('rgb(1,2,3)')
  })
})

// --- chip status, teks, penyimpanan ------------------------------------------------------

describe('chip status', () => {
  it('VLM tanpa nama penyedia (keputusan pengguna)', () => {
    for (const mode of ['UTAMA', 'CADANGAN', 'GANGGUAN'] as const) {
      const chip = vlmChip(tele({ api_monitor: { mode } as Telemetry['api_monitor'] }))
      expect(chip.text).not.toMatch(/gemini|ollama|qwen/i)
    }
    expect(vlmChip(tele({ api_monitor: { mode: 'CADANGAN' } as Telemetry['api_monitor'] })).tone).toBe('warn')
  })
  it('kamera: nada per status', () => {
    expect(cameraChip(tele()).tone).toBe('ok')
    expect(cameraChip(tele({ camera: { ...tele().camera, status: 'LOST' } })).tone).toBe('danger')
    expect(cameraChip(null).tone).toBe('neutral')
  })
})

describe('messages', () => {
  it('setiap status kamera punya teks untuk chip, panel keputusan, dan video', () => {
    const states: CameraState[] = ['IDLE', 'OPENING', 'OK', 'OPTIMIZING', 'LOST', 'SYNTHETIC']
    for (const s of states) {
      expect(CAMERA_CHIP[s]).toBeTruthy()
      expect(s === 'OK' || Boolean(CAMERA_NOT_READY[s])).toBe(true)
      expect(s === 'OK' || Boolean(VIDEO.placeholder[s])).toBe(true)
    }
  })
})

describe('storage', () => {
  it('penyimpanan diblokir tidak menjatuhkan UI', () => {
    const blocked = {
      getItem: () => { throw new Error('SecurityError') },
      setItem: () => { throw new Error('SecurityError') },
      removeItem: () => { throw new Error('SecurityError') },
    }
    expect(readItem('k', blocked)).toBeNull()
    expect(() => writeItem('k', 'v', blocked)).not.toThrow()
  })
})
