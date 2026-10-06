/**
 * Store reaktif telemetri (Svelte 5 runes). Satu koneksi WebSocket untuk
 * seluruh aplikasi; komponen cukup membaca `telemetry.data` / `telemetry.status`.
 */
import { TelemetryClient, telemetryUrl, type ConnectionStatus } from '../api/telemetry'
import type { Telemetry } from '../api/types'
import { session } from './session.svelte'

class TelemetryStore {
  data = $state<Telemetry | null>(null)
  status = $state<ConnectionStatus>('connecting')
  lastMessageAt = $state<number | null>(null)
  private client: TelemetryClient | null = null

  start(url: string = telemetryUrl()): void {
    if (this.client) return
    this.client = new TelemetryClient(url, {
      onMessage: (d) => {
        this.data = d
        this.lastMessageAt = Date.now()
      },
      onStatus: (s) => {
        this.status = s
      },
      onLoginRequired: () => {
        session.clear()
      },
    })
    this.client.start()
  }

  stop(): void {
    this.client?.stop()
    this.client = null
    this.data = null
    this.status = 'disconnected'
  }
}

export const telemetry = new TelemetryStore()
