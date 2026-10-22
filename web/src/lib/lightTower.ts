// Menara lampu gerbang di Monitoring (T88). Operator sering tidak bisa melihat lampu fisik;
// layar harus menunjukkan lampu NYATA: merah & hijau dari baca balik perangkat (`iot.lamps_on`),
// kuning dari perintah server bila perangkat tidak punya lampu kuning (relay USB 2 kanal) —
// keputusan pengguna 20-10. Logika murni; komponen hanya merakit.
import type { GateLamp, LightState, Telemetry } from './api/types'
import { LIGHT_TOWER as TEXT } from './messages'

export type LampSource = 'physical' | 'plan' | 'unknown'
export type TowerTone = 'ok' | 'warn' | 'danger' | 'neutral'

export interface LampView {
  lamp: GateLamp
  on: boolean
  source: LampSource
}

export interface TowerView {
  lamps: LampView[] // urut atas -> bawah: merah, kuning, hijau
  state: string // teks lampu yang menyala (MERAH/KUNING/HIJAU/MATI)
  tone: TowerTone
  message: string // pesan lampu dari server (mis. "APD lengkap, silakan masuk")
  notes: string[] // peringatan untuk operator
}

const ORDER: GateLamp[] = ['red', 'yellow', 'green']
const COMMAND_LAMP: Record<LightState, GateLamp | null> = { RED: 'red', YELLOW: 'yellow', GREEN: 'green', OFF: null }
const TONE: Record<GateLamp, TowerTone> = { red: 'danger', yellow: 'warn', green: 'ok' }

export function towerView(t: Telemetry | null): TowerView {
  const command = t?.light?.light_state ?? 'OFF'
  const commanded = COMMAND_LAMP[command]
  const iot = t?.iot
  // Server sebelum T88a tidak mengirim lamps_on (undefined): sama dengan tanpa lampu fisik
  const physicalKnown = Boolean(iot?.enabled) && iot?.lamps_on !== undefined
  const available = new Set(iot?.lamps_available ?? [])
  const lampsOn = iot?.lamps_on ?? null

  const lamps = ORDER.map((lamp): LampView => {
    const fromDevice = physicalKnown && (lamp !== 'yellow' || available.has('yellow'))
    if (!fromDevice) return { lamp, on: commanded === lamp, source: 'plan' }
    if (lampsOn === null) return { lamp, on: false, source: 'unknown' }
    return { lamp, on: lampsOn.includes(lamp), source: 'physical' }
  })

  const lit = lamps.filter((l) => l.on).map((l) => l.lamp)
  const state = lit.length ? lit.map((l) => TEXT.states[l]).join(' + ') : TEXT.states.off
  return {
    lamps,
    state,
    tone: lit.length ? TONE[lit[0]] : 'neutral',
    message: t?.light?.message ?? '',
    notes: towerNotes(lamps, commanded, physicalKnown, available),
  }
}

function towerNotes(
  lamps: LampView[],
  commanded: GateLamp | null,
  physicalKnown: boolean,
  available: Set<GateLamp>,
): string[] {
  if (!physicalKnown) return [TEXT.noPhysical]
  const notes: string[] = []
  if (lamps.some((l) => l.source === 'unknown')) notes.push(TEXT.disconnected)
  const mismatch = lamps.some((l) => l.source === 'physical' && l.on !== (commanded === l.lamp))
  if (mismatch) notes.push(TEXT.mismatch(TEXT.states[commanded ?? 'off']))
  if (commanded === 'yellow' && !available.has('yellow')) notes.push(TEXT.yellowPlanOnly)
  return notes
}
