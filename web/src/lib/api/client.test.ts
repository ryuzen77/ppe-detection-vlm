import { describe, expect, it } from 'vitest'
import { ADMIN_TOKEN_STORAGE_KEY, ApiClient, ApiError, HTTP_UNAUTHORIZED, readAdminToken, writeAdminToken } from './client'

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
    const api = new ApiClient({ fetch: fn, getAdminToken: () => 'rahasia' })
    await expect(api.getAudio()).resolves.toEqual({ muted: true })
    expect(calls[0].url).toBe('/api/config/audio')
    expect(calls[0].init.method).toBe('GET')
    expect((calls[0].init.headers as Record<string, string>)['X-Admin-Token']).toBeUndefined()
  })

  it('POST mengirim JSON dan token admin bila ada', async () => {
    const { fn, calls } = fakeFetch(200, { status: 'success', muted: false })
    const api = new ApiClient({ fetch: fn, getAdminToken: () => 'rahasia' })
    await api.setAudioMuted(false)
    const headers = calls[0].init.headers as Record<string, string>
    expect(headers['X-Admin-Token']).toBe('rahasia')
    expect(headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(calls[0].init.body as string)).toEqual({ muted: false })
  })

  it('POST tanpa token tidak mengirim header admin kosong', async () => {
    const { fn, calls } = fakeFetch(200, { status: 'success' })
    await new ApiClient({ fetch: fn, getAdminToken: () => '' }).reset()
    expect((calls[0].init.headers as Record<string, string>)['X-Admin-Token']).toBeUndefined()
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
    await api.reports({ limit: 20, offset: 40, status: 'incomplete', date: '2026-09-24' })
    expect(calls[0].url).toBe('http://gerbang:8000/api/reports?limit=20&offset=40&status=incomplete&date=2026-09-24')
    expect(api.snapshotUrl('a b/../x.jpg')).toBe('http://gerbang:8000/api/reports/snapshots/a%20b%2F..%2Fx.jpg')
  })

  it('memilih kamera null berarti melepas kamera', async () => {
    const { fn, calls } = fakeFetch(200, { status: 'scheduled', pending_index: null })
    await new ApiClient({ fetch: fn }).selectCamera(null)
    expect(JSON.parse(calls[0].init.body as string)).toEqual({ index: null, mode: null })
  })
})

describe('token admin', () => {
  it('dibaca & ditulis dengan kunci yang sama seperti UI lama', () => {
    const map = new Map<string, string>()
    const storage = {
      getItem: (k: string) => map.get(k) ?? null,
      setItem: (k: string, v: string) => void map.set(k, v),
      removeItem: (k: string) => void map.delete(k),
    }
    writeAdminToken('abc', storage)
    expect(map.get(ADMIN_TOKEN_STORAGE_KEY)).toBe('abc')
    expect(readAdminToken(storage)).toBe('abc')
    writeAdminToken('', storage)
    expect(map.has(ADMIN_TOKEN_STORAGE_KEY)).toBe(false)
  })

  it('penyimpanan yang diblokir tidak membuat galat', () => {
    const blocked = {
      getItem: () => { throw new Error('SecurityError') },
      setItem: () => { throw new Error('SecurityError') },
      removeItem: () => { throw new Error('SecurityError') },
    }
    expect(readAdminToken(blocked)).toBe('')
    expect(() => writeAdminToken('x', blocked)).not.toThrow()
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

  it('token disimpan tanpa spasi tepi; isian kosong/spasi menghapus', () => {
    const data = new Map<string, string>()
    const storage = {
      setItem: (k: string, v: string) => void data.set(k, v),
      removeItem: (k: string) => void data.delete(k),
    }
    writeAdminToken('  rahasia\n', storage)
    expect(data.get(ADMIN_TOKEN_STORAGE_KEY)).toBe('rahasia')
    writeAdminToken('   ', storage)
    expect(data.has(ADMIN_TOKEN_STORAGE_KEY)).toBe(false)
  })
})

describe('cadangan memori token', () => {
  const blocked = {
    getItem: (): string | null => { throw new Error('diblokir') },
    setItem: (): void => { throw new Error('diblokir') },
    removeItem: (): void => { throw new Error('diblokir') },
  }

  it('penyimpanan diblokir: token tetap terbaca selama halaman terbuka', () => {
    writeAdminToken('rahasia', blocked)
    expect(readAdminToken(blocked)).toBe('rahasia')
    writeAdminToken('', blocked)
    expect(readAdminToken(blocked)).toBe('')
  })

  it('penyimpanan pulih: cadangan memori dilepas', () => {
    const data = new Map<string, string>()
    const ok = {
      getItem: (k: string) => data.get(k) ?? null,
      setItem: (k: string, v: string) => void data.set(k, v),
      removeItem: (k: string) => void data.delete(k),
    }
    writeAdminToken('lama', blocked)
    writeAdminToken('baru', ok)
    expect(readAdminToken(ok)).toBe('baru')
    data.delete(ADMIN_TOKEN_STORAGE_KEY) // dihapus dari tab/UI lain
    expect(readAdminToken(ok)).toBe('')
  })
})
