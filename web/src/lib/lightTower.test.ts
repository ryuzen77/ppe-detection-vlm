import { describe, expect, it } from 'vitest'
import { towerView } from './lightTower'
import { LIGHT_TOWER as TEXT } from './messages'
import type { GateLamp, LightState, Telemetry } from './api/types'

const RELAY: GateLamp[] = ['green', 'red']
const ESP32: GateLamp[] = ['green', 'red', 'yellow']

function tele(command: LightState, iot: Partial<Telemetry['iot']> | null, message = 'pesan'): Telemetry {
  const base = { enabled: true, connected: true, last_ack_age_s: 0.5, error: null }
  return {
    light: { light_state: command, message, timestamp: 0 },
    iot: iot === null ? undefined : { ...base, ...iot },
  } as unknown as Telemetry
}

const on = (view: ReturnType<typeof towerView>) => view.lamps.filter((l) => l.on).map((l) => l.lamp)
const source = (view: ReturnType<typeof towerView>, lamp: GateLamp) => view.lamps.find((l) => l.lamp === lamp)?.source

describe('towerView (T88)', () => {
  it('hijau mengikuti lampu fisik yang benar-benar menyala (relay)', () => {
    const view = towerView(tele('GREEN', { lamps_on: ['green'], lamps_available: RELAY }))
    expect(on(view)).toEqual(['green'])
    expect(source(view, 'green')).toBe('physical')
    expect(view.state).toBe(TEXT.states.green)
    expect(view.tone).toBe('ok')
    expect(view.notes).toEqual([])
  })

  it('lampu fisik tidak sesuai perintah: yang tampil tetap lampu nyata + peringatan', () => {
    const view = towerView(tele('GREEN', { lamps_on: [], lamps_available: RELAY }))
    expect(on(view)).toEqual([])
    expect(view.state).toBe(TEXT.states.off)
    expect(view.notes).toContain(TEXT.mismatch(TEXT.states.green))
  })

  it('kuning pada relay tanpa lampu kuning: kuning dari perintah, merah/hijau nyata (mati)', () => {
    const view = towerView(tele('YELLOW', { lamps_on: [], lamps_available: RELAY }))
    expect(on(view)).toEqual(['yellow'])
    expect(source(view, 'yellow')).toBe('plan')
    expect(source(view, 'red')).toBe('physical')
    expect(view.tone).toBe('warn')
    expect(view.notes).toEqual([TEXT.yellowPlanOnly])
  })

  it('ESP32 punya lampu kuning: kuning juga dari lampu fisik', () => {
    const view = towerView(tele('YELLOW', { lamps_on: ['yellow'], lamps_available: ESP32 }))
    expect(on(view)).toEqual(['yellow'])
    expect(source(view, 'yellow')).toBe('physical')
    expect(view.notes).toEqual([])
  })

  it('lampu fisik tidak terbaca: merah/hijau "tidak diketahui", bukan dianggap menyala', () => {
    const view = towerView(tele('RED', { connected: false, lamps_on: null, lamps_available: RELAY }))
    expect(source(view, 'red')).toBe('unknown')
    expect(on(view)).toEqual([])
    expect(view.notes).toContain(TEXT.disconnected)
  })

  it('tanpa IoT / server sebelum T88a: mengikuti perintah server dengan label', () => {
    for (const t of [tele('RED', { enabled: false }), tele('RED', null), tele('RED', {})]) {
      const view = towerView(t)
      expect(on(view)).toEqual(['red'])
      expect(view.lamps.every((l) => l.source === 'plan')).toBe(true)
      expect(view.notes).toEqual([TEXT.noPhysical])
    }
  })

  it('uji lampu dari Pengaturan ikut tampil (lewat perintah & baca balik yang sama)', () => {
    const view = towerView(tele('RED', { lamps_on: ['red'], lamps_available: RELAY }, 'Uji Coba Manual - Lampu Merah'))
    expect(on(view)).toEqual(['red'])
    expect(view.message).toBe('Uji Coba Manual - Lampu Merah')
  })

  it('belum ada telemetri: semua mati', () => {
    const view = towerView(null)
    expect(on(view)).toEqual([])
    expect(view.state).toBe(TEXT.states.off)
  })
})
