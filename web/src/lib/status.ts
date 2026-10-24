/** Status kamera & VLM → nada warna + teks chip (logika murni, teruji). */
import type { InternetState, LocalStandbyState, Telemetry } from './api/types'
import type { Tone } from './gate'
import {
  CAMERA_CHIP,
  CAMERA_FAULT,
  VLM_CHIP,
  VLM_CHIP_NO_BACKUP,
  IOT_CHIP,
  SETTINGS_TAB,
  INTERNET_CHIP,
  LOCAL_STANDBY_CHIP,
  REGISTRATION_CHIP,
  SYSTEM_STATUS,
  cameraChipOk,
} from './messages'

export interface Chip {
  tone: Tone
  text: string
  hint: string
}

export function cameraChip(t: Telemetry | null): Chip {
  const c = t?.camera
  if (!c) return { tone: 'neutral', text: CAMERA_CHIP.UNKNOWN, hint: '' }
  if (t!.camera_fault) return { tone: 'warn', text: CAMERA_FAULT[t!.camera_fault].chip, hint: c.name }
  const tone: Tone = c.status === 'OK' ? 'ok' : 'warn'
  const text = c.status === 'OK' ? cameraChipOk(t!.fps) : CAMERA_CHIP[c.status]
  return { tone, text, hint: c.name }
}

const VLM_TONE: Record<string, Tone> = { UTAMA: 'ok', CADANGAN: 'warn', LOKAL: 'warn', GANGGUAN: 'danger' }

/** Nama penyedia/model sengaja tidak ditampilkan (keputusan pengguna): hanya status umum */
export function vlmChip(t: Telemetry | null): Chip {
  const mode = t?.api_monitor?.mode
  // T71: tanpa cadangan (bawaan) operator perlu tahu bahwa gangguan VLM utama = pekerja menunggu
  // T72: VLM lokal darurat tanpa cadangan API tetap "punya cadangan" (tinjauan Codex 22-10)
  const noBackup =
    mode === 'UTAMA' && t?.api_monitor?.backup?.configured === false && t?.api_monitor?.local?.role !== 'darurat'
  const label = noBackup ? VLM_CHIP_NO_BACKUP : mode ? VLM_CHIP[mode] : VLM_CHIP.UNKNOWN
  return { tone: (mode && VLM_TONE[mode]) || 'neutral', text: label.text, hint: label.hint }
}

const INTERNET_TONE: Record<InternetState, Tone> = { normal: 'ok', lambat: 'warn', putus: 'warn' }

/**
 * T72: koneksi internet gerbang. null = pemantau mati (tanpa VLM lokal untuk dialihkan,
 * atau server sebelum T72a) — tidak ada chip. Putus tetap kuning, bukan merah: gerbang masih
 * menilai lewat VLM lokal; merah hanya bila tidak ada VLM sama sekali (chip VLM gangguan).
 */
export function internetChip(t: Telemetry | null): Chip | null {
  const state = t?.api_monitor?.internet?.state
  if (!state) return null
  return { tone: INTERNET_TONE[state], ...INTERNET_CHIP[state] }
}

const LOCAL_TONE: Record<LocalStandbyState, Tone> = {
  unloaded: 'neutral',
  loading: 'warn',
  ready: 'ok',
  failed: 'warn',
}

/** T72: VLM lokal siaga dingin. Siaga = keadaan normal (netral), bukan masalah di ringkasan. */
export function localStandbyChip(t: Telemetry | null): Chip | null {
  const local = t?.api_monitor?.local
  if (!local?.role) return null
  return { tone: LOCAL_TONE[local.state], ...LOCAL_STANDBY_CHIP[local.state] }
}

/**
 * T83: hanya muncul sebagai masalah — setelan Wajib terdaftar aktif tetapi FR tidak berfungsi,
 * sehingga semua pekerja ditahan. Kuning (bukan merah): merah hanya untuk APD/larangan.
 */
export function registrationChip(t: Telemetry | null): Chip | null {
  const policy = t?.registration_policy
  if (!policy?.enabled || policy.fr_ready) return null
  return { tone: 'warn', ...REGISTRATION_CHIP }
}

export function iotChip(t: Telemetry | null): Chip {
  const iot = t?.iot
  if (!iot) return { tone: 'neutral', text: IOT_CHIP.disabled, hint: '' }
  if (!iot.enabled) return { tone: 'neutral', text: IOT_CHIP.disabled, hint: '' }
  return {
    tone: iot.connected ? 'ok' : 'warn',
    text: iot.connected ? IOT_CHIP.connected : IOT_CHIP.disconnected,
    hint: iot.error || '',
  }
}

/** Pesan akhir tes lampu Pengaturan menurut status lampu fisik (temuan uji UI #14) */
export function lightTestDoneText(t: Telemetry | null): string {
  const iot = t?.iot
  if (!iot?.enabled) return SETTINGS_TAB.lightTestDone.disabled
  return iot.connected ? SETTINGS_TAB.lightTestDone.connected : SETTINGS_TAB.lightTestDone.disconnected
}

const TONE_RANK: Record<Tone, number> = { neutral: 0, ok: 1, warn: 2, danger: 3 }

/**
 * Satu ringkasan untuk bilah atas (T78): 6 chip berdampingan melebihi layar 1366 px (1464 px
 * terukur). Nada = yang terburuk; teks = masalah satu-satunya, atau jumlah masalahnya.
 */
export function systemSummary(chips: Chip[]): { tone: Tone; text: string; problems: Chip[] } {
  const problems = chips.filter((c) => c.tone === 'warn' || c.tone === 'danger')
  const tone = chips.reduce<Tone>((worst, c) => (TONE_RANK[c.tone] > TONE_RANK[worst] ? c.tone : worst), 'neutral')
  const text =
    problems.length === 0
      ? SYSTEM_STATUS.ready
      : problems.length === 1
        ? problems[0].text
        : SYSTEM_STATUS.issues(problems.length)
  return { tone: problems.length ? tone : 'ok', text, problems }
}
