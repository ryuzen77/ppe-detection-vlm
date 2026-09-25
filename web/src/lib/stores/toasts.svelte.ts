/** Antrean notifikasi singkat (toast). */
import type { GateEvent } from '../notify'
import { TOASTS } from '../settings'

export interface Toast extends GateEvent {
  id: number
}

class ToastStore {
  items = $state<Toast[]>([])
  private seq = 0

  push(event: GateEvent): void {
    const toast = { ...event, id: ++this.seq }
    this.items = [toast, ...this.items].slice(0, TOASTS.maxVisible)
    setTimeout(() => this.dismiss(toast.id), TOASTS.lifetimeMs)
  }

  dismiss(id: number): void {
    this.items = this.items.filter((t) => t.id !== id)
  }

  clear(): void {
    this.items = []
  }
}

export const toasts = new ToastStore()
