/** Katalog item APD dari backend, dimuat sekali untuk seluruh aplikasi. */
import { api } from '../api/client'
import type { PpeItem } from '../api/types'
import { activeItems } from '../ppe'

class CatalogStore {
  items = $state<PpeItem[]>([])
  error = $state('')
  private loading: Promise<void> | null = null

  get active(): PpeItem[] {
    return activeItems(this.items)
  }

  load(): Promise<void> {
    this.loading ??= api.ppeRules()
      .then((c) => {
        this.items = c.items
        this.error = ''
      })
      .catch((e: unknown) => {
        this.error = e instanceof Error ? e.message : String(e)
        this.loading = null // coba lagi pada pemanggilan berikutnya
      })
    return this.loading
  }

  replace(items: PpeItem[]): void {
    this.items = items
  }
}

export const catalog = new CatalogStore()
