import { describe, expect, it } from 'vitest'
import type { ActiveTrack, HistoryRecord, InspectionResult, PpeItem, Telemetry } from './api/types'
import type { CameraState } from './api/types'
import { describeSource } from './format'
import { gateView } from './gate'
import { computeFit, detectionStyle, drawHud, withAlpha, type HudPalette } from './hud'
import { STAND_ZONE } from './settings'
import { zoneLineY } from './zone'
import { CAMERA_CHIP, CAMERA_NOT_READY, VIDEO, chipTitle, seconds } from './messages'
import { detectEvents, initialWatch } from './notify'
import { assessItem } from './ppe'
import { parseRoute } from './router.svelte'
import { cameraChip, vlmChip, iotChip } from './status'
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
    zone: { enabled: false, y_min: 0.7, y_max: 0.85 },
    light: { light_state: 'OFF', message: '', timestamp: 0 }, iot: { enabled: true, connected: true, last_ack_age_s: null, error: null }, camera_fault: null, history: [], stable_frames_required: 3,
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
    reports_color: true, required: true, prohibited: false, qualifier: { key: 'is_valid_color', fail_label: 'Bukan hi-vis' },
  }
  it('belum dinilai = pending (netral saat default/siaga, kuning saat menilai)', () => {
    expect(assessItem(rompi, undefined)).toEqual({ status: 'pending', text: 'Belum dinilai', tone: 'neutral' })
    expect(assessItem(rompi, undefined, 'analyzing')).toEqual({ status: 'pending', text: 'Belum dinilai', tone: 'warn' })
  })
  it('lengkap menampilkan warna bila item melaporkan warna', () => {
    expect(assessItem(rompi, { detected: true, color: 'orange', description: '', is_valid_color: true })).toEqual({ status: 'ok', text: 'orange', tone: 'ok' })
  })
  it('terdeteksi tetapi syarat tambahan gagal', () => {
    expect(assessItem(rompi, { detected: true, color: 'biru', description: '', is_valid_color: false })).toEqual({ status: 'missing', text: 'Bukan hi-vis', tone: 'danger' })
  })
  it('tidak terdeteksi', () => {
    expect(assessItem(rompi, { detected: false, color: '', description: '' }).status).toBe('missing')
  })

  const larangan: PpeItem = {
    key: 'rokok', label: 'Larangan Rokok', short_label: 'Rokok', icon: '🚭', icon_name: 'cigarette',
    ok_label: 'Tidak Ada', fail_label: 'Terlihat', reports_color: false, required: true,
    prohibited: true, qualifier: null,
  }

  it('larangan: belum dinilai = pending', () => {
    expect(assessItem(larangan, null)).toEqual({ status: 'pending', text: 'Belum dinilai', tone: 'neutral' })
    expect(assessItem(larangan, undefined)).toEqual({ status: 'pending', text: 'Belum dinilai', tone: 'neutral' })
  })

  it('larangan: terdeteksi (melanggar) = missing ("Terlihat")', () => {
    expect(assessItem(larangan, { detected: true, color: '', description: '' })).toEqual({
      status: 'missing',
      text: 'Terlihat',
      tone: 'danger',
    })
  })

  it('larangan: tidak terdeteksi atau null/ragu = ok ("Tidak Ada")', () => {
    expect(assessItem(larangan, { detected: false, color: '', description: '' })).toEqual({
      status: 'ok',
      text: 'Tidak Ada',
      tone: 'ok',
    })
    expect(assessItem(larangan, { detected: null as any, color: '', description: '' })).toEqual({
      status: 'ok',
      text: 'Tidak Ada',
      tone: 'ok',
    })
    expect(assessItem(larangan, {} as any)).toEqual({
      status: 'ok',
      text: 'Tidak Ada',
      tone: 'ok',
    })
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
  it('draws zone correctly', () => {
    const calls: { fn: string; args: any[]; style?: string }[] = []
    const ctx = new Proxy({} as Record<string, unknown>, {
      get(target, prop: string) {
        if (prop in target) return target[prop]
        if (prop === 'measureText') return () => ({ width: 50 })
        return (...args: any[]) => calls.push({ fn: prop, args, style: String(target.strokeStyle ?? '') })
      },
      set(target, prop: string, value) {
        target[prop] = value
        return true
      },
    }) as unknown as CanvasRenderingContext2D
    const p = { ok: 'ok', warn: 'warn', outside: 'out', text: 'txt', background: 'bg', font: 'sans' }
    const fit = computeFit(100, 100, 1280, 720)

    // a. zone.enabled = true, guides = true
    let t = tele({ zone: { enabled: true, y_min: 0.7, y_max: 0.85 } })
    drawHud(ctx, 100, 100, t, true, p)
    const lineY1 = zoneLineY(0.7, fit.offsetY, fit.drawH)
    const lineY2 = zoneLineY(0.85, fit.offsetY, fit.drawH)
    
    const moveTos = calls.filter(c => c.fn === 'moveTo' && (c.args[1] === lineY1 || c.args[1] === lineY2))
    expect(moveTos).toHaveLength(2)

    // zone.enabled = false -> tidak ada garis
    calls.length = 0
    t = tele({ zone: { enabled: false, y_min: 0.7, y_max: 0.85 } })
    drawHud(ctx, 100, 100, t, true, p)
    const moveTosFalse = calls.filter(c => c.fn === 'moveTo' && (c.args[1] === lineY1 || c.args[1] === lineY2))
    expect(moveTosFalse).toHaveLength(0)

    // b. zone.enabled = true dan detection in_zone = false -> strokeStyle kotak deteksi
    calls.length = 0
    t = tele({ 
      zone: { enabled: true, y_min: 0.7, y_max: 0.85 },
      detections: [{
        track_id: 1,
        bbox: [0, 0, 10, 10] as [number, number, number, number],
        clip_type: 'OPTIMAL',
        is_full_body: true,
        is_inside_corridor: true,
        keypoints: [],
        foot_y: 0,
        in_zone: false,
        reason: '',
        conf: 0.9
      }]
    })
    drawHud(ctx, 100, 100, t, true, p)
    
    const bracketsStroke = calls.find(c => c.fn === 'stroke' && c.style !== 'txt' && c.style !== '')
    const expectedColor = withAlpha(p.ok, STAND_ZONE.outsideAlpha)
    expect(bracketsStroke?.style).toBe(expectedColor)
  })

  const palette: HudPalette = { ok: '#00ff00', warn: '#ffaa00', outside: '#777777', text: '#ffffff', background: '#000000', font: 'sans-serif' }

  it('video 16:9 di kanvas 4:3 diberi bilah atas-bawah, bukan diregangkan', () => {
    const f = computeFit(800, 600, 1280, 720)
    expect(f.drawW).toBe(800)
    expect(f.drawH).toBe(450)
    expect(f.offsetY).toBe(75)
  })
  it('warna kotak dari palet token: pas hijau, arahan kuning, di luar jalur abu', () => {
    const base = { track_id: 1, bbox: [0, 0, 1, 1] as [number, number, number, number], reason: '', conf: 1, keypoints: null, foot_y: null, in_zone: true }
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
      keypoints: [[150, 150, 0.9], [160, 160, 0.2]], foot_y: null, in_zone: true,
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

  it('iotChip: nada dan teks sesuai status', () => {
    expect(iotChip(null).tone).toBe('neutral')
    expect(iotChip(tele({ iot: { enabled: false, connected: true, last_ack_age_s: null, error: null } })).tone).toBe('neutral')
    expect(iotChip(tele({ iot: { enabled: true, connected: true, last_ack_age_s: null, error: null } })).tone).toBe('ok')
    expect(iotChip(tele({ iot: { enabled: true, connected: false, last_ack_age_s: null, error: 'lost' } })).tone).toBe('warn')
    expect(iotChip(tele({ iot: { enabled: true, connected: false, last_ack_age_s: null, error: 'lost' } })).hint).toBe('lost')
  })

  it('kamera: nada per status', () => {
    expect(cameraChip(tele()).tone).toBe('ok')
    expect(cameraChip(tele({ camera: { ...tele().camera, status: 'LOST' } })).tone).toBe('warn')
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

describe('chipTitle', () => {
  it('menggabungkan teks & keterangan; tanpa keterangan cukup teks', () => {
    expect(chipTitle('Kamera siap', 'USB Cam')).toBe('Kamera siap · USB Cam')
    expect(chipTitle('Kamera siap', '')).toBe('Kamera siap')
  })
})
