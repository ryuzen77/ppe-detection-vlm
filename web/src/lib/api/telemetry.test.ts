import { describe, expect, it } from 'vitest'
import { INITIAL_RECONNECT_MS, MAX_RECONNECT_MS, TelemetryClient, telemetryUrl, type SocketLike } from './telemetry'

class FakeSocket implements SocketLike {
  onopen: ((ev: unknown) => void) | null = null
  onmessage: ((ev: { data: unknown }) => void) | null = null
  onclose: ((ev: unknown) => void) | null = null
  onerror: ((ev: unknown) => void) | null = null
  closed = false
  close() {
    if (this.closed) return
    this.closed = true
    this.onclose?.({})
  }
}

function setup() {
  const sockets: FakeSocket[] = []
  const timers: { fn: () => void; ms: number }[] = []
  const messages: unknown[] = []
  const statuses: string[] = []
  const client = new TelemetryClient('ws://x/ws', {
    onMessage: (d) => messages.push(d),
    onStatus: (s) => statuses.push(s),
    createSocket: () => {
      const s = new FakeSocket()
      sockets.push(s)
      return s
    },
    setTimer: (fn, ms) => {
      timers.push({ fn, ms })
      return timers.length
    },
    clearTimer: () => {},
  })
  const runNextTimer = () => timers.shift()!.fn()
  return { client, sockets, timers, messages, statuses, runNextTimer }
}

describe('TelemetryClient', () => {
  it('meneruskan pesan JSON dan melaporkan status', () => {
    const { client, sockets, messages, statuses } = setup()
    client.start()
    sockets[0].onopen?.({})
    sockets[0].onmessage?.({ data: JSON.stringify({ fps: 30 }) })
    expect(messages).toEqual([{ fps: 30 }])
    expect(statuses).toEqual(['connecting', 'connected'])
  })

  it('pesan rusak atau bukan teks diabaikan tanpa memutus koneksi', () => {
    const { client, sockets, messages } = setup()
    client.start()
    sockets[0].onmessage?.({ data: '{rusak' })
    sockets[0].onmessage?.({ data: new ArrayBuffer(2) })
    sockets[0].onmessage?.({ data: '{"ok":1}' })
    expect(messages).toEqual([{ ok: 1 }])
    expect(sockets[0].closed).toBe(false)
  })

  it('menyambung ulang dengan jeda yang membesar sampai batas', () => {
    const { client, sockets, timers, runNextTimer } = setup()
    client.start()
    const delays: number[] = []
    for (let i = 0; i < 8; i++) {
      sockets[sockets.length - 1].close()
      delays.push(timers[0].ms)
      runNextTimer()
    }
    expect(delays[0]).toBe(INITIAL_RECONNECT_MS)
    expect(delays[1]).toBe(INITIAL_RECONNECT_MS * 1.5)
    expect(Math.max(...delays)).toBe(MAX_RECONNECT_MS)
    expect(sockets.length).toBe(9)
  })

  it('jeda kembali ke awal setelah berhasil tersambung', () => {
    const { client, sockets, timers, runNextTimer } = setup()
    client.start()
    sockets[0].close()
    runNextTimer()
    sockets[1].close()
    runNextTimer()
    sockets[2].onopen?.({})
    sockets[2].close()
    expect(timers[0].ms).toBe(INITIAL_RECONNECT_MS)
  })

  it('stop() menutup koneksi dan tidak menyambung ulang', () => {
    const { client, sockets, timers, statuses } = setup()
    client.start()
    client.stop()
    expect(sockets[0].closed).toBe(true)
    expect(timers).toHaveLength(0)
    expect(statuses.at(-1)).toBe('disconnected')
  })

  it('galat socket menutup koneksi lalu dijadwalkan sambung ulang', () => {
    const { client, sockets, timers } = setup()
    client.start()
    sockets[0].onerror?.({})
    expect(sockets[0].closed).toBe(true)
    expect(timers).toHaveLength(1)
  })
})

describe('telemetryUrl', () => {
  it('mengikuti protokol halaman', () => {
    expect(telemetryUrl({ protocol: 'http:', host: 'gerbang:8000' })).toBe('ws://gerbang:8000/ws')
    expect(telemetryUrl({ protocol: 'https:', host: 'gerbang' })).toBe('wss://gerbang/ws')
  })
})
