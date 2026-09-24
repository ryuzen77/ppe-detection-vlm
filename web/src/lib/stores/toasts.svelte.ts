/** Antrean notifikasi singkat (toast). */
import type { GateEvent } from '../notify'

export interface Toast extends GateEvent {
  id: number
}

const LIFETIME_MS = 8000
const MAX_VISIBLE = 4

class ToastStore {
  items = $state<Toast[]>([])
  private seq = 0

  push(event: GateEvent): void {
    const toast = { ...event, id: ++this.seq }
    this.items = [toast, ...this.items].slice(0, MAX_VISIBLE)
    setTimeout(() => this.dismiss(toast.id), LIFETIME_MS)
  }

  dismiss(id: number): void {
    this.items = this.items.filter((t) => t.id !== id)
  }

  clear(): void {
    this.items = []
  }
}

export const toasts = new ToastStore()
