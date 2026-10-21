/** Katalog item APD dari backend, dimuat sekali untuk seluruh aplikasi. */
import { api } from '../api/client'
import type { PpeItem } from '../api/types'
import { activeItems, requiredMap } from '../ppe'

class CatalogStore {
  items = $state<PpeItem[]>([])
  error = $state('')
  private loading: Promise<void> | null = null

  get active(): PpeItem[] {
    return activeItems(this.items)
  }

  /**
   * Ambil katalog dari server. Panggilan yang bersamaan memakai satu permintaan; setelah selesai
   * (berhasil maupun gagal) panggilan berikutnya mengambil ulang — dulu janji yang sudah
   * berhasil disimpan selamanya sehingga katalog tidak pernah diperbarui (bug T89).
   */
  load(): Promise<void> {
    this.loading ??= api.ppeRules()
      .then((c) => {
        this.items = c.items
        this.error = ''
      })
      .catch((e: unknown) => {
        this.error = e instanceof Error ? e.message : String(e)
      })
      .finally(() => {
        this.loading = null
      })
    return this.loading
  }

  /**
   * Ubah satu centang APD Wajib (T89). Item lain diambil dari katalog terkini dan katalog
   * diganti jawaban server, jadi perubahan berikutnya tidak menimpa yang ini. Galat diteruskan
   * ke pemanggil; katalog tetap status server terakhir.
   */
  async setRequired(key: string, required: boolean): Promise<void> {
    const res = await api.setPpeActive(requiredMap(this.items, key, required))
    this.items = res.items
  }

  replace(items: PpeItem[]): void {
    this.items = items
  }
}

export const catalog = new CatalogStore()
