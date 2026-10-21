/** Katalog item APD dari backend, dimuat sekali untuk seluruh aplikasi. */
import { api } from '../api/client'
import type { PpeItem } from '../api/types'
import { activeItems } from '../ppe'

class CatalogStore {
  items = $state<PpeItem[]>([])
  error = $state('')
  /** T89: penyimpanan gagal DAN status server belum bisa dibaca ulang — pilihan di layar tidak bisa dipercaya */
  unconfirmed = $state(false)
  private loading: Promise<void> | null = null
  /** Bertambah saat perubahan dimulai dan selesai; GET yang dimulai sebelumnya sudah basi */
  private epoch = 0

  get active(): PpeItem[] {
    return activeItems(this.items)
  }

  /**
   * Ambil katalog dari server. Panggilan yang bersamaan memakai satu permintaan; setelah selesai
   * panggilan berikutnya mengambil ulang — dulu janji yang berhasil disimpan selamanya sehingga
   * katalog tidak pernah diperbarui (bug T89).
   */
  load(): Promise<void> {
    this.loading ??= this.fetchLatest()
      .then(() => undefined)
      .finally(() => {
        this.loading = null
      })
    return this.loading
  }

  /**
   * Ubah satu centang APD Wajib (T89). Hanya item itu yang dikirim: backend menggabungkannya di
   * bawah gembok, jadi katalog basi (tab lain, GET terlambat) tidak bisa menimpa pilihan lain.
   * Gagal → status server dibaca ulang, sebab POST bisa sudah tersimpan walau jawabannya hilang.
   */
  async setRequired(key: string, required: boolean): Promise<void> {
    // Mulai & selesai perubahan sama-sama membuat GET yang sudah berjalan basi: GET itu bisa
    // membaca status sebelum POST tersimpan (tinjauan Codex 22-10, juga saat POST gagal)
    this.epoch++
    try {
      const res = await api.setPpeActive({ [key]: required })
      this.epoch++
      this.items = res.items
      this.unconfirmed = false
    } catch (e) {
      this.epoch++
      this.unconfirmed = !(await this.fetchLatest())
      throw e
    }
  }

  /** Baca ulang status server tanpa memakai GET yang sedang berjalan; true bila berhasil. */
  async refresh(): Promise<boolean> {
    const ok = await this.fetchLatest()
    if (ok) this.unconfirmed = false
    return ok
  }

  /** GET katalog; jawaban dibuang bila sejak GET dimulai ada perubahan yang dimulai/selesai. */
  private async fetchLatest(): Promise<boolean> {
    const startedAt = this.epoch
    try {
      const c = await api.ppeRules()
      if (this.epoch === startedAt) this.items = c.items
      this.error = ''
      return true
    } catch (e: unknown) {
      this.error = e instanceof Error ? e.message : String(e)
      return false
    }
  }

  replace(items: PpeItem[]): void {
    this.items = items
  }
}

export const catalog = new CatalogStore()
