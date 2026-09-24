/**
 * Klien WebSocket telemetri dengan sambung ulang otomatis (backoff).
 *
 * Tidak bergantung pada Svelte maupun DOM, supaya bisa diuji dengan WebSocket
 * tiruan. Store reaktifnya ada di lib/stores/telemetry.svelte.ts.
 */
import type { Telemetry } from './types'

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

/** Bagian WebSocket yang dipakai klien ini (memudahkan penggantian saat uji). */
export interface SocketLike {
  onopen: ((ev: unknown) => void) | null
  onmessage: ((ev: { data: unknown }) => void) | null
  onclose: ((ev: unknown) => void) | null
  onerror: ((ev: unknown) => void) | null
  close(): void
}

export type SocketFactory = (url: string) => SocketLike

export interface TelemetryClientOptions {
  onMessage: (data: Telemetry) => void
  onStatus?: (status: ConnectionStatus) => void
  createSocket?: SocketFactory
  initialDelayMs?: number
  maxDelayMs?: number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (handle: unknown) => void
}

export const INITIAL_RECONNECT_MS = 1500
export const MAX_RECONNECT_MS = 10000

export class TelemetryClient {
  private readonly url: string
  private readonly opts: Required<Omit<TelemetryClientOptions, 'onStatus'>> & Pick<TelemetryClientOptions, 'onStatus'>
  private socket: SocketLike | null = null
  private timer: unknown = null
  private delay: number
  private stopped = false

  constructor(url: string, options: TelemetryClientOptions) {
    this.url = url
    this.opts = {
      createSocket: (u) => new WebSocket(u) as unknown as SocketLike,
      initialDelayMs: INITIAL_RECONNECT_MS,
      maxDelayMs: MAX_RECONNECT_MS,
      setTimer: (fn, ms) => setTimeout(fn, ms),
      clearTimer: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
      ...options,
    }
    this.delay = this.opts.initialDelayMs
  }

  /** Delay sambung ulang berikutnya (untuk tampilan & uji). */
  get nextDelayMs(): number {
    return this.delay
  }

  start(): void {
    this.stopped = false
    this.connect()
  }

  /** Menutup koneksi dan menghentikan sambung ulang. */
  stop(): void {
    this.stopped = true
    if (this.timer !== null) this.opts.clearTimer(this.timer)
    this.timer = null
    const s = this.socket
    this.socket = null
    if (s) {
      s.onclose = null
      s.close()
    }
    this.opts.onStatus?.('disconnected')
  }

  private connect(): void {
    if (this.stopped) return
    this.opts.onStatus?.('connecting')
    let socket: SocketLike
    try {
      socket = this.opts.createSocket(this.url)
    } catch {
      this.scheduleReconnect()
      return
    }
    this.socket = socket
    socket.onopen = () => {
      this.delay = this.opts.initialDelayMs
      this.opts.onStatus?.('connected')
    }
    socket.onmessage = (ev) => {
      if (typeof ev.data !== 'string') return
      let data: Telemetry
      try {
        data = JSON.parse(ev.data) as Telemetry
      } catch {
        return // Satu pesan rusak tidak memutus aliran
      }
      this.opts.onMessage(data)
    }
    socket.onerror = () => socket.close()
    socket.onclose = () => {
      if (this.socket === socket) this.socket = null
      this.opts.onStatus?.('disconnected')
      this.scheduleReconnect()
    }
  }

  private scheduleReconnect(): void {
    if (this.stopped) return
    if (this.timer !== null) this.opts.clearTimer(this.timer)
    const wait = this.delay
    this.delay = Math.min(this.delay * 1.5, this.opts.maxDelayMs)
    this.timer = this.opts.setTimer(() => {
      this.timer = null
      this.connect()
    }, wait)
  }
}

/** URL /ws pada asal halaman (ws:// atau wss:// mengikuti protokol halaman). */
export function telemetryUrl(loc: Pick<Location, 'protocol' | 'host'> = globalThis.location): string {
  const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${loc.host}/ws`
}
