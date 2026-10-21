// T89: checklist APD Wajib menimpa pilihan sebelumnya (katalog basi). Termasuk skenario tinjauan Codex
// 21-10: dua tab admin, GET terlambat, dan POST yang tersimpan tetapi jawabannya hilang.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import type { PpeCatalog, PpeItem } from '../api/types'
import { catalog } from './catalog.svelte'

const item = (key: string, required: boolean) => ({ key, label: key, required }) as unknown as PpeItem
const catalogOf = (state: Record<string, boolean>): PpeCatalog =>
  ({ items: Object.entries(state).map(([k, v]) => item(k, v)) }) as PpeCatalog
const requiredOf = () => Object.fromEntries(catalog.items.map((i) => [i.key, i.required]))

/** Server tiruan seperti `ppe_rules.set_active`: perubahan sebagian digabung ke status server. */
function fakeServer(initial: Record<string, boolean>) {
  const state = { ...initial }
  vi.spyOn(api, 'ppeRules').mockImplementation(async () => catalogOf(state))
  const save = vi.spyOn(api, 'setPpeActive').mockImplementation(async (active) => {
    Object.assign(state, active)
    return catalogOf(state)
  })
  return { state, save }
}

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

beforeEach(() => {
  catalog.replace([])
  catalog.unconfirmed = false
})
afterEach(() => vi.restoreAllMocks())

describe('catalog.load (T89)', () => {
  it('mengambil ulang setelah muat pertama berhasil', async () => {
    const spy = vi.spyOn(api, 'ppeRules')
      .mockResolvedValueOnce(catalogOf({ helm: true }))
      .mockResolvedValueOnce(catalogOf({ helm: false }))
    await catalog.load()
    await catalog.load()
    expect(spy).toHaveBeenCalledTimes(2)
    expect(requiredOf()).toEqual({ helm: false })
  })

  it('panggilan bersamaan memakai satu permintaan', async () => {
    const spy = vi.spyOn(api, 'ppeRules').mockResolvedValue(catalogOf({ helm: true }))
    await Promise.all([catalog.load(), catalog.load()])
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('setelah gagal, panggilan berikutnya mencoba lagi', async () => {
    const spy = vi.spyOn(api, 'ppeRules')
      .mockRejectedValueOnce(new Error('putus'))
      .mockResolvedValueOnce(catalogOf({ helm: true }))
    await catalog.load()
    expect(catalog.error).toBe('putus')
    await catalog.load()
    expect(spy).toHaveBeenCalledTimes(2)
    expect(catalog.error).toBe('')
  })
})

describe('catalog.setRequired (T89)', () => {
  it('hanya mengirim item yang diubah', async () => {
    const server = fakeServer({ helm: true, sarung_tangan: false, kacamata: false })
    await catalog.load()
    await catalog.setRequired('sarung_tangan', true)
    await catalog.setRequired('kacamata', true)
    expect(server.save.mock.calls.map((c) => c[0])).toEqual([{ sarung_tangan: true }, { kacamata: true }])
    expect(server.state).toEqual({ helm: true, sarung_tangan: true, kacamata: true })
    expect(requiredOf()).toEqual(server.state)
  })

  it('dua tab admin: perubahan tab lain tidak dimatikan lagi oleh katalog basi', async () => {
    const server = fakeServer({ helm: true, sarung_tangan: false, kacamata: false })
    await catalog.load()                       // tab ini memuat: sarung_tangan = false
    server.state.sarung_tangan = true          // tab lain mewajibkan sarung tangan
    await catalog.setRequired('kacamata', true)
    expect(server.state.sarung_tangan).toBe(true)
    expect(requiredOf()).toEqual({ helm: true, sarung_tangan: true, kacamata: true })
  })

  it('GET yang dimulai sebelum penyimpanan tidak menimpa hasil penyimpanan', async () => {
    const server = fakeServer({ helm: true, rompi: true })
    await catalog.load()
    const lateGet = deferred<PpeCatalog>()
    vi.spyOn(api, 'ppeRules').mockReturnValueOnce(lateGet.promise)
    const loading = catalog.load()             // mis. login ulang memicu GET
    await catalog.setRequired('rompi', false)  // admin menyimpan sebelum GET selesai
    lateGet.resolve(catalogOf({ helm: true, rompi: true }))  // jawaban basi tiba belakangan
    await loading
    expect(server.state.rompi).toBe(false)
    expect(requiredOf()).toEqual({ helm: true, rompi: false })
  })

  it('server menolak: galat diteruskan, katalog tetap status server', async () => {
    fakeServer({ helm: true })
    await catalog.load()
    vi.spyOn(api, 'setPpeActive').mockRejectedValueOnce(new Error('minimal satu APD'))
    await expect(catalog.setRequired('helm', false)).rejects.toThrow('minimal satu APD')
    expect(requiredOf()).toEqual({ helm: true })
    expect(catalog.unconfirmed).toBe(false)
  })

  it('POST tersimpan tetapi jawabannya hilang: katalog dibaca ulang dari server', async () => {
    const server = fakeServer({ helm: true, rompi: true })
    await catalog.load()
    vi.spyOn(api, 'setPpeActive').mockImplementationOnce(async (active) => {
      Object.assign(server.state, active)      // tersimpan di server…
      throw new Error('koneksi terputus')      // …tetapi jawabannya tidak sampai
    })
    await expect(catalog.setRequired('rompi', false)).rejects.toThrow('koneksi terputus')
    expect(requiredOf()).toEqual({ helm: true, rompi: false })
    expect(catalog.unconfirmed).toBe(false)
  })

  it('POST tersimpan, jawaban hilang, lalu GET lama tiba setelah pemulihan: tidak menimpa', async () => {
    // Skenario tinjauan Codex 22-10 terhadap v2
    const server = fakeServer({ helm: true, rompi: true })
    await catalog.load()
    const oldGet = deferred<PpeCatalog>()
    vi.spyOn(api, 'ppeRules').mockReturnValueOnce(oldGet.promise)
    const loading = catalog.load()                              // GET lama dimulai sebelum perubahan
    vi.spyOn(api, 'setPpeActive').mockImplementationOnce(async (active) => {
      Object.assign(server.state, active)
      throw new Error('koneksi terputus')
    })
    await expect(catalog.setRequired('rompi', false)).rejects.toThrow()   // pemulihan membaca rompi=false
    oldGet.resolve(catalogOf({ helm: true, rompi: true }))      // jawaban basi tiba paling akhir
    await loading
    expect(requiredOf()).toEqual({ helm: true, rompi: false })
    expect(catalog.unconfirmed).toBe(false)
  })

  it('GET yang dimulai saat POST masih berjalan tidak menimpa hasil POST', async () => {
    const server = fakeServer({ helm: true, rompi: true })
    await catalog.load()
    const post = deferred<PpeCatalog>()
    vi.spyOn(api, 'setPpeActive').mockReturnValueOnce(post.promise)
    const saving = catalog.setRequired('rompi', false)
    const midGet = deferred<PpeCatalog>()
    vi.spyOn(api, 'ppeRules').mockReturnValueOnce(midGet.promise)
    const loading = catalog.load()                              // membaca sebelum POST tersimpan
    server.state.rompi = false
    post.resolve(catalogOf(server.state))
    await saving
    midGet.resolve(catalogOf({ helm: true, rompi: true }))
    await loading
    expect(requiredOf()).toEqual({ helm: true, rompi: false })
  })

  it('status server tidak terbaca setelah galat: ditandai belum pasti sampai dibaca ulang', async () => {
    fakeServer({ helm: true, rompi: true })
    await catalog.load()
    vi.spyOn(api, 'setPpeActive').mockRejectedValueOnce(new Error('koneksi terputus'))
    vi.spyOn(api, 'ppeRules').mockRejectedValueOnce(new Error('koneksi terputus'))
    await expect(catalog.setRequired('rompi', false)).rejects.toThrow()
    expect(catalog.unconfirmed).toBe(true)
    expect(await catalog.refresh()).toBe(true)
    expect(catalog.unconfirmed).toBe(false)
  })
})
