/**
 * Klien REST backend. Satu tempat untuk URL, header admin, dan penanganan galat,
 * menggantikan fetch yang tersebar di app.js lama.
 */
import type {
  Zone,
  CameraCatalog,
  CameraMode,
  Health,
  LightTestAction,
  MonitorStatus,
  PingResult,
  PpeCatalog,
  ReportsPage, ReportSummary, ReportPeriod,
  ReportStatusFilter,
  VlmInfo,
  VlmProvidersResponse,
  VlmApplyRequest,
  VlmTestRequest,
  VlmTestResponse,
  VlmSelection,
  SessionStatus,
  SetupRequest,
  LoginRequest,
  PasswordChangeRequest,
  CreateAccountRequest,
  ResetPasswordRequest,
  AuthResponse,
  AccountInfo,
  Worker,
  WorkersResponse,
  NewWorkerRequest,
  UpdateWorkerRequest,
  TemplateCondition,
  AddTemplateResponse,
  EnrollmentHoldResponse,
} from './types'

export const WS_CLOSE_LOGIN_REQUIRED = 4401



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

/** HTTP 401: server menolak karena token admin kosong/salah */
export const HTTP_UNAUTHORIZED = 401


export interface ApiClientOptions {
  /** Awalan URL backend; kosong = asal yang sama (disajikan FastAPI atau proxy Vite) */
  baseUrl?: string
  fetch?: typeof globalThis.fetch
}

export class ApiClient {
  private readonly baseUrl: string
  private readonly fetchImpl: typeof globalThis.fetch
  /** Dipanggil saat server menolak token admin, sebelum galatnya dilempar (mis. membuka isian token) */
  onUnauthorized: ((error: ApiError) => void) | null = null

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? '').replace(/\/$/, '')
    this.fetchImpl = options.fetch ?? globalThis.fetch.bind(globalThis)
  }

  url(path: string): string {
    return `${this.baseUrl}${path}`
  }

  private async request<T>(method: 'GET' | 'POST' | 'PATCH' | 'DELETE', path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = {}
    if (body !== undefined) headers['Content-Type'] = 'application/json'
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
      const error = new ApiError(response.status, String(detail ?? `HTTP ${response.status}`), data)
      if (response.status === HTTP_UNAUTHORIZED) this.onUnauthorized?.(error)
      throw error
    }
    return data as T
  }


  // --- Auth & Accounts (T51)
  session = () => this.request<SessionStatus>('GET', '/api/session')
  setup = (req: SetupRequest) => this.request<AuthResponse>('POST', '/api/setup', req)
  login = (req: LoginRequest) => this.request<AuthResponse>('POST', '/api/login', req)
  logout = () => this.request<void>('POST', '/api/logout')
  changePassword = (req: PasswordChangeRequest) => this.request<void>('POST', '/api/account/password', req)
  
  accounts = () => this.request<AccountInfo[]>('GET', '/api/accounts')
  createAccount = (req: CreateAccountRequest) => this.request<AccountInfo>('POST', '/api/accounts', req)
  resetAccountPassword = (username: string, req: ResetPasswordRequest) => this.request<void>('POST', `/api/accounts/${encodeURIComponent(username)}/password`, req)
  deleteAccount = (username: string) => this.request<void>('DELETE', `/api/accounts/${encodeURIComponent(username)}`)

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
  getVlmProviders = () => this.request<VlmProvidersResponse>('GET', '/api/config/vlm/providers')
  testVlmProvider = (req: VlmTestRequest) => this.request<VlmTestResponse>('POST', '/api/config/vlm/test', req)
  applyVlmSelection = (req: VlmApplyRequest) => this.request<VlmSelection>('POST', '/api/config/vlm/apply', req)
  resetVlmSelection = () => this.request<VlmSelection>('DELETE', '/api/config/vlm/selection')
  monitoring = () => this.request<MonitorStatus>('GET', '/api/monitoring/status')
  pingVlm = () => this.request<PingResult>('POST', '/api/monitoring/ping')

  // --- Kamera
  cameras = () => this.request<CameraCatalog>('GET', '/api/cameras')
  scanCameras = () => this.request<{ status: string; scanning: boolean; message: string }>('POST', '/api/cameras/scan')
  selectCamera = (index: number | null, mode?: CameraMode | null) =>
    this.request<{ status: string; pending_index: number | null; message: string }>(
      'POST', '/api/config/camera', { index, mode: mode ?? null })

  // --- Zona Titik Berdiri (T36d)
  zone = () => this.request<Zone>('GET', '/api/config/zone')
  setZone = (cfg: Partial<Zone>) => this.request<Zone>('POST', '/api/config/zone', cfg)
  calibrateZone = () => this.request<Zone>('POST', '/api/config/zone/calibrate')

  // --- Laporan
  reportsSummary = (params: { period?: ReportPeriod; date?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.period) q.set('period', params.period)
    if (params.date) q.set('date', params.date)
    const qs = q.toString()
    return this.request<ReportSummary>('GET', `/api/reports/summary${qs ? `?${qs}` : ''}`)
  }
  reports = (params: { limit?: number; offset?: number; status?: ReportStatusFilter; from?: string; to?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.limit !== undefined) q.set('limit', String(params.limit))
    if (params.offset !== undefined) q.set('offset', String(params.offset))
    if (params.status) q.set('status', params.status)
    if (params.from) q.set('from', params.from)
    if (params.to) q.set('to', params.to)
    const qs = q.toString()
    return this.request<ReportsPage>('GET', `/api/reports${qs ? `?${qs}` : ''}`)
  }
  snapshotUrl = (filename: string) => this.url(`/api/reports/snapshots/${encodeURIComponent(filename)}`)
  exportCsvUrl = (from?: string, to?: string) => {
    const q = new URLSearchParams()
    if (from) q.set('from', from)
    if (to) q.set('to', to)
    const qs = q.toString()
    return this.url(`/api/reports/export${qs ? `?${qs}` : ''}`)
  }
  streamUrl = () => this.url('/api/stream')

  // --- Pekerja & Identitas Wajah (T34)
  workers = () => this.request<WorkersResponse>('GET', '/api/workers')
  createWorker = (body: NewWorkerRequest) => this.request<Worker>('POST', '/api/workers', body)
  deactivateWorker = (id: number) => this.request<Worker>('POST', `/api/workers/${id}/deactivate`)
  activateWorker = (id: number) => this.request<Worker>('POST', `/api/workers/${id}/activate`)
  deleteWorkerFace = (id: number) => this.request<void>('DELETE', `/api/workers/${id}/face`)
  deleteWorkerTemplate = (workerId: number, templateId: number) =>
    this.request<void>('DELETE', `/api/workers/${workerId}/templates/${templateId}`)
  updateWorker = (id: number, body: UpdateWorkerRequest) =>
    this.request<Worker>('PATCH', `/api/workers/${id}`, body)
  addWorkerTemplate = (workerId: number, condition: TemplateCondition) =>
    this.request<AddTemplateResponse>('POST', `/api/workers/${workerId}/templates`, { condition })
  holdEnrollment = () => this.request<EnrollmentHoldResponse>('POST', '/api/workers/enrollment')
  releaseEnrollment = () => this.request<void>('DELETE', '/api/workers/enrollment')
}

export const api = new ApiClient()
