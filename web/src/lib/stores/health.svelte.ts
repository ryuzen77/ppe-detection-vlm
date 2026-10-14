/**
 * Store reaktif untuk data kesehatan sistem & VLM cadangan (GET /api/health).
 */
import { api } from '../api/client'
import type { Health, LocalVlmHealth } from '../api/types'
import { HEALTH_POLL } from '../settings'

class HealthStore {
  data = $state<Health | null>(null)
  error = $state('')
  private timer: ReturnType<typeof setInterval> | null = null

  get localVlm(): LocalVlmHealth | null {
    return this.data?.local_vlm ?? null
  }

  async load(): Promise<void> {
    try {
      this.data = await api.health()
      this.error = ''
    } catch (e: unknown) {
      this.error = e instanceof Error ? e.message : String(e)
    }
  }

  start(intervalMs: number = HEALTH_POLL.intervalMs): void {
    if (this.timer) return
    void this.load()
    this.timer = setInterval(() => {
      void this.load()
    }, intervalMs)
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
    this.data = null
  }
}

export const health = new HealthStore()
