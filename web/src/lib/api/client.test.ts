import { describe, expect, it } from 'vitest'
import { ApiClient, ApiError, HTTP_UNAUTHORIZED } from './client'

type Call = { url: string; init: RequestInit }

function fakeFetch(status: number, body: unknown) {
  const calls: Call[] = []
  const fn = (async (url: string, init: RequestInit) => {
    calls.push({ url, init })
    const text = typeof body === 'string' ? body : JSON.stringify(body)
    return new Response(text, { status })
  }) as unknown as typeof fetch
  return { fn, calls }
}

describe('ApiClient', () => {
  it('GET tanpa header admin dan mengurai JSON', async () => {
    const { fn, calls } = fakeFetch(200, { muted: true })
    const api = new ApiClient({ fetch: fn })
    await expect(api.getAudio()).resolves.toEqual({ muted: true })
    expect(calls[0].url).toBe('/api/config/audio')
    expect(calls[0].init.method).toBe('GET')
  })

  it('POST mengirim JSON', async () => {
    const { fn, calls } = fakeFetch(200, { status: 'success', muted: false })
    const api = new ApiClient({ fetch: fn })
    await api.setAudioMuted(false)
    const headers = calls[0].init.headers as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(calls[0].init.body as string)).toEqual({ muted: false })
  })

  it('status galat menjadi ApiError dengan pesan dari backend', async () => {
    const { fn } = fakeFetch(403, { detail: 'Token admin tidak valid' })
    const err = await new ApiClient({ fetch: fn }).reset().catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(403)
    expect(err.message).toBe('Token admin tidak valid')
  })

  it('balasan galat bukan JSON tetap menjadi ApiError', async () => {
    const { fn } = fakeFetch(500, 'Internal Server Error')
    const err = await new ApiClient({ fetch: fn }).health().catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.body).toBe('Internal Server Error')
  })

  it('parameter laporan dan URL berkas dibentuk dengan aman', async () => {
    const { fn, calls } = fakeFetch(200, { page_records: [] })
    const api = new ApiClient({ fetch: fn, baseUrl: 'http://gerbang:8000/' })
    await api.reports({ limit: 20, offset: 40, status: 'incomplete', from: '2026-09-24', to: '2026-09-24' })
    expect(calls[0].url).toBe(
      'http://gerbang:8000/api/reports?limit=20&offset=40&status=incomplete&from=2026-09-24&to=2026-09-24',
    )
    expect(api.snapshotUrl('a b/../x.jpg')).toBe('http://gerbang:8000/api/reports/snapshots/a%20b%2F..%2Fx.jpg')
  })

  it('memilih kamera null berarti melepas kamera', async () => {
    const { fn, calls } = fakeFetch(200, { status: 'scheduled', pending_index: null })
    await new ApiClient({ fetch: fn }).selectCamera(null)
    expect(JSON.parse(calls[0].init.body as string)).toEqual({ index: null, mode: null })
  })
})

describe('penolakan token admin', () => {
  it('401 memanggil onUnauthorized lalu tetap melempar ApiError', async () => {
    const { fn } = fakeFetch(HTTP_UNAUTHORIZED, { detail: 'Token admin tidak valid' })
    const api = new ApiClient({ fetch: fn })
    const seen: ApiError[] = []
    api.onUnauthorized = (e) => seen.push(e)
    const err = await api.reset().catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(seen).toHaveLength(1)
    expect(seen[0]).toBe(err)
  })

  it('galat lain tidak memanggil onUnauthorized', async () => {
    const { fn } = fakeFetch(403, { detail: 'dilarang' })
    const api = new ApiClient({ fetch: fn })
    let called = false
    api.onUnauthorized = () => (called = true)
    await api.reset().catch(() => undefined)
    expect(called).toBe(false)
  })
})
