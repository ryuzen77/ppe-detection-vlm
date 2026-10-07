/**
 * Bentuk data dari backend FastAPI.
 *
 * Ditulis tangan dari kode backend (state_manager.get_telemetry, api_monitor,
 * vlm_analyzer.provider_info, report_manager, routes_*). Bila bentuk di backend
 * berubah, ubah juga di sini — svelte-check lalu menunjukkan setiap pemakai
 * yang ikut terdampak, hal yang dulu baru ketahuan saat dijalankan.
 */

export interface Zone {
  enabled: boolean
  y_min: number
  y_max: number
  source: string
}

// --- Katalog APD (GET /api/ppe-rules) --------------------------------------

export interface PpeQualifier {
  key: string
  fail_label: string
}

export interface PpeItem {
  key: string
  label: string
  short_label: string
  /** Emoji (UI lama) */
  icon: string
  /** Nama ikon garis untuk UI baru, kunci registri ikon (mis. "hard-hat") */
  icon_name: string
  ok_label: string
  fail_label: string
  reports_color: boolean
  /** Item sedang diwajibkan (diperiksa) */
  required: boolean
  qualifier: PpeQualifier | null
}

export interface PpeCatalog {
  items: PpeItem[]
}

// --- Hasil inspeksi VLM ------------------------------------------------------

/** Hasil satu item; qualifier (mis. is_valid_color, is_closed_shoes) ikut sebagai field tambahan. */
export interface ItemResult {
  detected: boolean
  color: string
  description: string
  [qualifier: string]: boolean | string | undefined
}

export type DecidedBy = 'utama' | 'cadangan' | ''

export interface InspectionResult {
  items: Record<string, ItemResult>
  is_complete: boolean
  missing_items: string[]
  notes: string
  /** VLM_LIVE:<penyedia>/<model> (utama), VLM_CADANGAN:... (cadangan), VLM_GANGGUAN */
  inference_source: string
  inference_time_ms: number
  decided_by: DecidedBy
  /** Utama & cadangan gagal: TIDAK ada keputusan */
  is_system_unavailable: boolean
}

// --- VLM utama & cadangan (GET /api/config/vlm) ---------------------------------

export interface VlmEngineInfo {
  role: 'utama' | 'cadangan'
  provider: string
  model: string
  is_local: boolean
  needs_key: boolean
  has_key: boolean
  is_live: boolean
  timeout_s: number
  error: string
}

export interface VlmInfo extends VlmEngineInfo {
  backup: VlmEngineInfo | null
  primary_down: boolean
}

// --- Kesehatan VLM (GET /api/monitoring/status, telemetry.api_monitor) ------------

export type VlmMode = 'UTAMA' | 'CADANGAN' | 'GANGGUAN'

export interface VlmEngineStats {
  configured: boolean
  provider: string
  model: string
  is_local: boolean
  status: 'BELUM_DIPAKAI' | 'OK' | 'GAGAL'
  latency_ms: number
  avg_latency_ms: number
  calls: number
  failures: number
  timeouts: number
  rate_limited: number
  consecutive_failures: number
  last_error: string
  last_checked: string
}

export interface MonitorStatus {
  mode: VlmMode
  primary_down: boolean
  primary: VlmEngineStats
  backup: VlmEngineStats
  decisions_primary: number
  decisions_backup: number
  no_decisions: number
  last_no_decision_reason: string
  is_locked: boolean
  latency_ms: number
  avg_latency_ms: number
}

// --- Telemetri WebSocket (/ws) ---------------------------------------------------------

export type ClipType = 'OPTIMAL' | 'HEAD_CLIPPED' | 'FEET_CLIPPED' | 'TOO_FAR' | 'TOO_CLOSE' | string

export interface Detection {
  track_id: number
  bbox: [number, number, number, number]
  is_full_body: boolean
  is_inside_corridor: boolean
  reason: string
  clip_type: ClipType
  conf: number
  /** Keypoint pose [x, y, conf] per titik, atau null */
  keypoints: number[][] | null
  foot_y: number | null
  in_zone: boolean
}

export type TrackState =
  | 'INITIAL'
  | 'STEP_BACK_WARNING'
  | 'STABILIZING'
  | 'ANALYZING'
  | 'ANALYZED'
  | 'WAITING_SYSTEM'

export interface ActiveTrack {
  track_id: number
  session_id: number
  state: TrackState
  is_full_body: boolean
  reason: string
  clip_type: ClipType
  stable_frames: number
  /** Detik sampai pemeriksaan diulang; hanya saat WAITING_SYSTEM */
  retry_in_s: number | null
  vlm_result: InspectionResult | null
}

export type LightState = 'OFF' | 'GREEN' | 'RED' | 'YELLOW'

export interface LightStatus {
  light_state: LightState
  message: string
  timestamp: number
}

export interface HistoryRecord {
  track_id: number
  timestamp: string
  is_complete: boolean
  items: Record<string, ItemResult>
  missing_items: string[]
  notes: string
  inference_source: string
  inference_time_ms: number
  decided_by: DecidedBy
  snapshot_filename: string
}

export type CameraState = 'IDLE' | 'OPENING' | 'OK' | 'OPTIMIZING' | 'LOST' | 'SYNTHETIC' | 'BLOCKED'

export interface CameraMode {
  width: number
  height: number
  fps: number
  fourcc: string
  req_width?: number
  req_height?: number
}

export interface CameraStatus {
  index: number | null
  name: string
  selected: boolean
  status: CameraState
  error: string
  mode: CameraMode | null
  optimizing: boolean
  width: number
  height: number
  fps: number
  is_synthetic: boolean
}

export interface Telemetry {
  timestamp: number
  frame_width: number
  frame_height: number
  has_person: boolean
  active_track: ActiveTrack | null
  detections: Detection[]
  corridor: { enabled: boolean; left_ratio: number; right_ratio: number }
  zone: Omit<Zone, 'source'>
  light: LightStatus
  iot: { enabled: boolean; connected: boolean; last_ack_age_s: number | null; error: string | null }
  camera_fault: 'lost' | 'blocked' | 'frozen' | null
  history: HistoryRecord[]
  stable_frames_required: number
  /** Ambang keyakinan titik pose — sama dengan detektor backend */
  keypoint_conf_threshold: number
  is_live_vlm: boolean
  vlm: VlmInfo
  api_monitor: MonitorStatus
  fps: number
  audio_muted: boolean
  camera: CameraStatus
}

// --- Laporan (GET /api/reports) ----------------------------------------------------------

export type ReportPeriod = 'day' | 'week' | 'month'

export interface ReportRange {
  from: string
  to: string
}

export interface ReportTotals {
  total: number
  passed: number
  rejected: number
  compliance_rate: number | null
}

export interface ReportBucket {
  start: string
  label: string
  passed: number
  rejected: number
}

export interface MissingItemStat {
  key: string | null
  label: string
  count: number
}

export interface ReportSummary {
  period: ReportPeriod
  range: ReportRange
  totals: ReportTotals
  buckets: ReportBucket[]
  missing_items: MissingItemStat[]
}


export interface ReportRecord {
  id: number
  track_id: number
  timestamp: string
  date_str: string
  time_str: string
  is_complete: boolean
  items: Record<string, ItemResult>
  missing_items: string[]
  notes: string
  inference_source: string
  inference_time_ms: number
  snapshot_filename: string
}

export interface ReportsPage {
  total_all: number
  complete_count: number
  violation_count: number
  compliance_rate: number
  backup_count: number
  system_outages: number
  filtered_total: number
  page_records: ReportRecord[]
}

export type ReportStatusFilter = 'all' | 'complete' | 'incomplete'

// --- Kamera (GET /api/cameras) -----------------------------------------------------------

export interface CameraDevice {
  index: number
  name: string
  available: boolean
  scanned: boolean
  in_use: boolean
  modes: CameraMode[]
  selected_mode: CameraMode | null
}

export interface CameraCatalog {
  scanning: boolean
  /** Jam pemindaian terakhir "HH:MM:SS", atau "-" bila belum pernah */
  last_scan_time: string | null
  devices: CameraDevice[]
  saved: { index: number; name?: string; mode?: CameraMode | null } | null
  active: CameraStatus
  quality_warning: boolean
}

// --- Lain-lain -------------------------------------------------------------------------------

export interface User {
  username: string
  role: string
}

export interface SessionStatus {
  authenticated: boolean
  setup_required: boolean
  setup_allowed: boolean
  user: User | null
  expires_in_s: number | null
}

export interface AccountInfo {
  username: string
  role: string
  created_at: string
  last_login_at: string | null
}

export interface AuthResponse {
  user: User
  expires_in_s: number
}

export interface SetupRequest {
  username: string
  password: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface PasswordChangeRequest {
  current_password: string
  new_password: string
}

export interface CreateAccountRequest {
  username: string
  password: string
}

export interface ResetPasswordRequest {
  new_password: string
}


export interface Health {
  status: string
  fps: number
  is_live_vlm: boolean
  vlm: VlmInfo
  camera_selected: boolean
  camera_index: number | null
  camera_name: string
  camera_status: CameraState
  resolution: string
  is_synthetic_camera: boolean
}

export interface PingEngineResult {
  role: 'utama' | 'cadangan'
  ok: boolean
  latency_ms: number
  error?: string
}

export interface PingResult {
  status: 'ONLINE' | 'ERROR' | 'OFFLINE'
  latency_ms: number
  message: string
  engines?: PingEngineResult[]
}

export type LightTestAction = 'green' | 'red' | 'yellow' | 'off'

// --- Pilihan VLM (T28) -------------------------------------------------------------

export interface VlmChoice {
  provider: string
  model: string
}

export interface VlmChoiceWithSource extends VlmChoice {
  source: 'env' | 'dashboard'
}

export interface VlmSelection {
  primary: VlmChoiceWithSource | null
  backup: VlmChoiceWithSource | null
}

export type VlmValidationStatus = 'validated' | 'partial' | 'outdated' | 'unvalidated' | 'unsafe' | null

export interface VlmModelEntry {
  model: string
  validated: VlmValidationStatus
  photos: number | null
  missed: number | null
  false_rejects: number | null
  median_seconds: number | null
}

export interface VlmProviderEntry {
  name: string
  label: string
  support: 'official' | 'experimental'
  is_local: boolean
  has_key: boolean
  data_location: string
  default_model: string
  models: VlmModelEntry[]
}

export interface VlmProvidersResponse {
  current: VlmSelection
  prompt_version: string
  providers: VlmProviderEntry[]
}

export interface VlmApplyRequest {
  primary: VlmChoice
  backup: VlmChoice | null
  confirm_unvalidated: boolean
}

export interface VlmTestRequest extends VlmChoice {
  role: 'primary' | 'backup'
}

export interface VlmTestResponse {
  ok: boolean
  json_ok: boolean
  latency_ms: number | null
  error: string
}
