// T89: checklist APD Wajib menimpa pilihan sebelumnya karena katalog tidak pernah dimuat ulang.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import type { PpeCatalog, PpeItem } from '../api/types'
import { requiredMap } from '../ppe'
import { catalog } from './catalog.svelte'

const item = (key: string, required: boolean) => ({ key, label: key, required }) as unknown as PpeItem
const catalogOf = (...items: PpeItem[]): PpeCatalog => ({ items }) as PpeCatalog

/** Server tiruan yang menyimpan status apa adanya (seperti `ppe_rules.set_active`). */
function fakeServer(initial: Record<string, boolean>) {
  const state = { ...initial }
  const snapshot = () => catalogOf(...Object.entries(state).map(([k, v]) => item(k, v)))
  vi.spyOn(api, 'ppeRules').mockImplementation(async () => snapshot())
  const save = vi.spyOn(api, 'setPpeActive').mockImplementation(async (active) => {
    Object.assign(state, active)
    return snapshot()
  })
  return { state, save }
}

beforeEach(() => catalog.replace([]))
afterEach(() => vi.restoreAllMocks())

describe('catalog.load (T89)', () => {
  it('mengambil ulang setelah muat pertama berhasil', async () => {
    const spy = vi.spyOn(api, 'ppeRules')
      .mockResolvedValueOnce(catalogOf(item('helm', true)))
      .mockResolvedValueOnce(catalogOf(item('helm', false)))
    await catalog.load()
    await catalog.load()
    expect(spy).toHaveBeenCalledTimes(2)
    expect(catalog.items[0].required).toBe(false)
  })

  it('panggilan bersamaan memakai satu permintaan', async () => {
    const spy = vi.spyOn(api, 'ppeRules').mockResolvedValue(catalogOf(item('helm', true)))
    await Promise.all([catalog.load(), catalog.load()])
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('setelah gagal, panggilan berikutnya mencoba lagi', async () => {
    const spy = vi.spyOn(api, 'ppeRules')
      .mockRejectedValueOnce(new Error('putus'))
      .mockResolvedValueOnce(catalogOf(item('helm', true)))
    await catalog.load()
    expect(catalog.error).toBe('putus')
    await catalog.load()
    expect(spy).toHaveBeenCalledTimes(2)
    expect(catalog.error).toBe('')
  })
})

describe('catalog.setRequired (T89)', () => {
  it('dua centang berturut-turut: perubahan pertama tidak ditimpa', async () => {
    const server = fakeServer({ helm: true, sarung_tangan: false, kacamata: false })
    await catalog.load()
    await catalog.setRequired('sarung_tangan', true)
    await catalog.setRequired('kacamata', true)
    expect(server.save.mock.calls[1][0]).toEqual({ helm: true, sarung_tangan: true, kacamata: true })
    expect(server.state).toEqual({ helm: true, sarung_tangan: true, kacamata: true })
    expect(catalog.items.map((i) => [i.key, i.required])).toEqual([
      ['helm', true], ['sarung_tangan', true], ['kacamata', true],
    ])
  })

  it('server menolak: galat diteruskan dan katalog tetap status server', async () => {
    fakeServer({ helm: true })
    await catalog.load()
    vi.spyOn(api, 'setPpeActive').mockRejectedValueOnce(new Error('minimal satu APD'))
    await expect(catalog.setRequired('helm', false)).rejects.toThrow('minimal satu APD')
    expect(catalog.items[0].required).toBe(true)
  })
})

describe('requiredMap (T89)', () => {
  it('hanya item yang diubah; item lain dari katalog', () => {
    const items = [item('helm', true), item('rompi', false), item('rokok', true)]
    expect(requiredMap(items, 'rompi', true)).toEqual({ helm: true, rompi: true, rokok: true })
    expect(requiredMap(items, 'helm', false)).toEqual({ helm: false, rompi: false, rokok: true })
  })
})
