/**
 * Klien REST backend. Satu tempat untuk URL, header admin, dan penanganan galat,
 * menggantikan fetch yang tersebar di app.js lama.
 */
import type {
  CameraCatalog,
  CameraMode,
  Health,
  LightTestAction,
  MonitorStatus,
  PingResult,
  PpeCatalog,
  ReportsPage,
  ReportStatusFilter,
  VlmInfo,
} from './types'
import { STORAGE } from '../settings'

/** Kunci yang sama dengan UI lama, supaya token admin berlaku di kedua UI. */
export const ADMIN_TOKEN_STORAGE_KEY = STORAGE.adminToken

export class ApiError extends Error {
  readonly status: number
  readonly body: unknown

  constructor(status: number, message: string, body: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

/** Token admin dari penyimpanan browser; aman bila penyimpanan diblokir. */
export function readAdminToken(storage: Pick<Storage, 'getItem'> | undefined = globalThis.localStorage): string {
  try {
    return storage?.getItem(ADMIN_TOKEN_STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function writeAdminToken(token: string, storage: Pick<Storage, 'setItem' | 'removeItem'> | undefined = globalThis.localStorage): void {
  try {
    if (token) storage?.setItem(ADMIN_TOKEN_STORAGE_KEY, token)
    else storage?.removeItem(ADMIN_TOKEN_STORAGE_KEY)
  } catch {
    // Penyimpanan diblokir (mode privat): token berlaku selama halaman terbuka saja
  }
}

export interface ApiClientOptions {
  /** Awalan URL backend; kosong = asal yang sama (disajikan FastAPI atau proxy Vite) */
  baseUrl?: string
  fetch?: typeof globalThis.fetch
  getAdminToken?: () => string
}

export class ApiClient {
  private readonly baseUrl: string
  private readonly fetchImpl: typeof globalThis.fetch
  private readonly getAdminToken: () => string

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? '').replace(/\/$/, '')
    this.fetchImpl = options.fetch ?? globalThis.fetch.bind(globalThis)
    this.getAdminToken = options.getAdminToken ?? (() => readAdminToken())
  }

  url(path: string): string {
    return `${this.baseUrl}${path}`
  }

  private async request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = {}
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    // Header admin hanya untuk perintah yang mengubah state (sama dengan UI lama)
    if (method === 'POST') {
      const token = this.getAdminToken()
      if (token) headers['X-Admin-Token'] = token
    }
    const response = await this.fetchImpl(this.url(path), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    const text = await response.text()
    let data: unknown = text
    try {
      data = text ? JSON.parse(text) : null
    } catch {
      // Balasan bukan JSON: teks mentah diteruskan dalam galat
    }
    if (!response.ok) {
      const detail = typeof data === 'object' && data !== null
        ? ((data as Record<string, unknown>).detail ?? (data as Record<string, unknown>).message)
        : undefined
      throw new ApiError(response.status, String(detail ?? `HTTP ${response.status}`), data)
    }
    return data as T
  }

  // --- Sistem
  health = () => this.request<Health>('GET', '/api/health')
  reset = () => this.request<{ status: string; message: string }>('POST', '/api/reset')
  setCorridor = (enabled: boolean) =>
    this.request<{ status: string; enabled: boolean }>('POST', '/api/config/corridor', { enabled })
  testLight = (action: LightTestAction) =>
    this.request<{ status: string; action: string; light_state: string }>('POST', '/api/iot/test', { action })
  getAudio = () => this.request<{ muted: boolean }>('GET', '/api/config/audio')
  setAudioMuted = (muted: boolean) =>
    this.request<{ status: string; muted: boolean }>('POST', '/api/config/audio', { muted })

  // --- APD
  ppeRules = () => this.request<PpeCatalog>('GET', '/api/ppe-rules')
  setPpeActive = (active: Record<string, boolean>) =>
    this.request<PpeCatalog>('POST', '/api/ppe-rules/active', { active })

  // --- VLM
  vlmInfo = () => this.request<VlmInfo>('GET', '/api/config/vlm')
  setVlmKey = (apiKey: string) =>
    this.request<VlmInfo & { status: string; message?: string }>('POST', '/api/config/vlm-key', { api_key: apiKey })
  monitoring = () => this.request<MonitorStatus>('GET', '/api/monitoring/status')
  pingVlm = () => this.request<PingResult>('POST', '/api/monitoring/ping')

  // --- Kamera
  cameras = () => this.request<CameraCatalog>('GET', '/api/cameras')
  scanCameras = () => this.request<{ status: string; scanning: boolean; message: string }>('POST', '/api/cameras/scan')
  selectCamera = (index: number | null, mode?: CameraMode | null) =>
    this.request<{ status: string; pending_index: number | null; message: string }>(
      'POST', '/api/config/camera', { index, mode: mode ?? null })

  // --- Laporan
  reports = (params: { limit?: number; offset?: number; status?: ReportStatusFilter; date?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.limit !== undefined) q.set('limit', String(params.limit))
    if (params.offset !== undefined) q.set('offset', String(params.offset))
    if (params.status) q.set('status', params.status)
    if (params.date) q.set('date', params.date)
    const qs = q.toString()
    return this.request<ReportsPage>('GET', `/api/reports${qs ? `?${qs}` : ''}`)
  }
  snapshotUrl = (filename: string) => this.url(`/api/reports/snapshots/${encodeURIComponent(filename)}`)
  exportCsvUrl = () => this.url('/api/reports/export')
  streamUrl = () => this.url('/api/stream')
}

export const api = new ApiClient()
