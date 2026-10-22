import { describe, it, expect } from 'vitest'
import {
  shouldShowLocalVlmChip,
  localVlmChipView,
  localVlmStatusText,
  formatGpuRatio,
  formatLatency,
  formatOtherGpuApps,
  hasOtherGpuApps,
  shouldShowGpuAppsWarning,
} from './localVlm'
import type { LocalVlmHealth } from './api/types'

describe('localVlm - shouldShowLocalVlmChip', () => {
  it('tidak menampilkan chip saat data kosong, ok, atau unknown', () => {
    expect(shouldShowLocalVlmChip(null)).toBe(false)
    expect(shouldShowLocalVlmChip(undefined)).toBe(false)
    expect(
      shouldShowLocalVlmChip({
        state: 'ok',
        gpu_ratio: 1.0,
        slow_streak: 0,
        last_latency_s: 3.5,
        other_gpu_apps: [],
      }),
    ).toBe(false)
    expect(
      shouldShowLocalVlmChip({
        state: 'unknown',
        gpu_ratio: null,
        slow_streak: 0,
        last_latency_s: null,
        other_gpu_apps: [],
      }),
    ).toBe(false)
  })

  it('menampilkan chip saat state slow atau partial_gpu', () => {
    const slowHealth: LocalVlmHealth = {
      state: 'slow',
      gpu_ratio: 1.0,
      slow_streak: 2,
      last_latency_s: 8.5,
      other_gpu_apps: ['Code.exe'],
    }
    expect(shouldShowLocalVlmChip(slowHealth)).toBe(true)

    const partialHealth: LocalVlmHealth = {
      state: 'partial_gpu',
      gpu_ratio: 0.26,
      slow_streak: 0,
      last_latency_s: 27.0,
      other_gpu_apps: [],
    }
    expect(shouldShowLocalVlmChip(partialHealth)).toBe(true)
  })
})

describe('localVlm - localVlmChipView', () => {
  it('mengembalikan null saat chip tidak perlu tampil', () => {
    expect(localVlmChipView(null)).toBeNull()
    expect(
      localVlmChipView({
        state: 'ok',
        gpu_ratio: 1.0,
        slow_streak: 0,
        last_latency_s: 3.5,
        other_gpu_apps: [],
      }),
    ).toBeNull()
    expect(
      localVlmChipView({
        state: 'unknown',
        gpu_ratio: null,
        slow_streak: 0,
        last_latency_s: null,
        other_gpu_apps: [],
      }),
    ).toBeNull()
  })

  it('mengembalikan konfigurasi chip tone-warn untuk slow dan partial_gpu', () => {
    const slowChip = localVlmChipView({
      state: 'slow',
      gpu_ratio: 1.0,
      slow_streak: 2,
      last_latency_s: 9.0,
      other_gpu_apps: [],
    })
    expect(slowChip).toEqual({
      tone: 'warn',
      text: 'VLM cadangan lambat',
      hint: 'Panggilan VLM cadangan lambat atau habis waktu berturut-turut',
    })

    const partialChip = localVlmChipView({
      state: 'partial_gpu',
      gpu_ratio: 0.5,
      slow_streak: 0,
      last_latency_s: 18.0,
      other_gpu_apps: [],
    })
    expect(partialChip).toEqual({
      tone: 'warn',
      text: 'VLM cadangan di CPU',
      hint: 'Sebagian model VLM cadangan dimuat di CPU',
    })
  })
})

describe('localVlm - localVlmStatusText', () => {
  it('memberikan teks deskripsi untuk setiap status', () => {
    expect(localVlmStatusText('ok')).toBe('Normal')
    expect(localVlmStatusText('slow')).toBe('Lambat')
    expect(localVlmStatusText('partial_gpu')).toBe('Sebagian di CPU')
    expect(localVlmStatusText('unknown')).toBe('Belum diketahui')
    expect(localVlmStatusText(null)).toBe('Belum diketahui')
    expect(localVlmStatusText(undefined)).toBe('Belum diketahui')
  })
})

describe('localVlm - formatGpuRatio', () => {
  it('memformat rasio menjadi persentase dengan format Indonesia', () => {
    expect(formatGpuRatio(1.0)).toBe('100%')
    expect(formatGpuRatio(0.5)).toBe('50%')
    expect(formatGpuRatio(0.264)).toBe('26,4%')
    expect(formatGpuRatio(0)).toBe('0%')
  })

  it('menampilkan tanda pisah bila rasio null, undefined, atau bukan angka', () => {
    expect(formatGpuRatio(null)).toBe('—')
    expect(formatGpuRatio(undefined)).toBe('—')
    expect(formatGpuRatio(Number.NaN)).toBe('—')
  })
})

describe('localVlm - formatLatency', () => {
  it('memformat latensi satu desimal dengan koma dan satuan dtk', () => {
    expect(formatLatency(3.6)).toBe('3,6 dtk')
    expect(formatLatency(12)).toBe('12,0 dtk')
    expect(formatLatency(0)).toBe('0,0 dtk')
  })

  it('menampilkan tanda pisah bila latensi null, undefined, atau bukan angka', () => {
    expect(formatLatency(null)).toBe('—')
    expect(formatLatency(undefined)).toBe('—')
    expect(formatLatency(Number.NaN)).toBe('—')
  })
})

describe('localVlm - formatOtherGpuApps & hasOtherGpuApps', () => {
  it('menampilkan "Tidak ada" dan false untuk daftar kosong atau null', () => {
    expect(formatOtherGpuApps([])).toBe('Tidak ada')
    expect(formatOtherGpuApps(null)).toBe('Tidak ada')
    expect(formatOtherGpuApps(undefined)).toBe('Tidak ada')
    expect(hasOtherGpuApps([])).toBe(false)
    expect(hasOtherGpuApps(null)).toBe(false)
  })

  it('menggabungkan nama aplikasi dan mengembalikan true bila ada aplikasi', () => {
    expect(formatOtherGpuApps(['Code.exe'])).toBe('Code.exe')
    expect(formatOtherGpuApps(['Code.exe', 'explorer.exe'])).toBe('Code.exe, explorer.exe')
    expect(hasOtherGpuApps(['Code.exe'])).toBe(true)
  })
})

describe('localVlm - shouldShowGpuAppsWarning', () => {
  it('tidak menampilkan peringatan bila data kosong atau tidak ada aplikasi lain', () => {
    expect(shouldShowGpuAppsWarning(null)).toBe(false)
    expect(shouldShowGpuAppsWarning(undefined)).toBe(false)
    expect(
      shouldShowGpuAppsWarning({
        state: 'slow',
        gpu_ratio: 1.0,
        slow_streak: 2,
        last_latency_s: 9.0,
        other_gpu_apps: [],
      }),
    ).toBe(false)
  })

  it('tidak menampilkan peringatan saat state normal (ok atau unknown) meski ada aplikasi lain', () => {
    expect(
      shouldShowGpuAppsWarning({
        state: 'ok',
        gpu_ratio: 1.0,
        slow_streak: 0,
        last_latency_s: 3.5,
        other_gpu_apps: ['Code.exe'],
      }),
    ).toBe(false)

    expect(
      shouldShowGpuAppsWarning({
        state: 'unknown',
        gpu_ratio: null,
        slow_streak: 0,
        last_latency_s: null,
        other_gpu_apps: ['Code.exe'],
      }),
    ).toBe(false)
  })

  it('menampilkan peringatan hanya bila state slow atau partial_gpu dan ada aplikasi lain', () => {
    expect(
      shouldShowGpuAppsWarning({
        state: 'slow',
        gpu_ratio: 1.0,
        slow_streak: 2,
        last_latency_s: 9.0,
        other_gpu_apps: ['Code.exe'],
      }),
    ).toBe(true)

    expect(
      shouldShowGpuAppsWarning({
        state: 'partial_gpu',
        gpu_ratio: 0.5,
        slow_streak: 0,
        last_latency_s: 18.0,
        other_gpu_apps: ['Discord.exe'],
      }),
    ).toBe(true)
  })
})
