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
  /** Larangan (mis. rokok: detected = true berarti melanggar) */
  prohibited: boolean
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

export type ClipType = 'OPTIMAL' | 'HEAD_CLIPPED' | 'FEET_CLIPPED' | 'TOO_FAR' | 'TOO_CLOSE' | 'NOT_STANDING' | string

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

export interface TrackIdentity {
  status: 'recognized' | 'unknown' | 'disabled'
  name: string | null
  employee_no: string | null
  score: number | null
}

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
  identity?: TrackIdentity | null
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
  camera_fault: 'lost' | 'blocked' | 'frozen' | 'system' | null   // 'system' = pengolah gambar galat (T77b)
  enrollment?: EnrollmentStatus
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
  /** Identitas wajah (T34c1) + snapshot divisi/perusahaan saat pemeriksaan (T79) */
  worker_id?: number | null
  employee_no?: string | null
  worker_name?: string | null
  fr_status?: 'recognized' | 'unknown' | 'disabled' | string | null
  fr_score?: number | null
  department?: string | null
  company?: string | null
}

/** Saringan identitas laporan (T79); kosong = semua */
export interface ReportWhoFilter {
  worker_id?: number
  department?: string
  company?: string
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

export interface ApiErrorDetail {
  code?: string
  message?: string
}

export interface LoginErrorBody {
  detail?: string | ApiErrorDetail
  retry_after_s?: number
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


export type LocalVlmState = 'ok' | 'slow' | 'partial_gpu' | 'unknown'

export interface LocalVlmHealth {
  state: LocalVlmState
  gpu_ratio: number | null
  slow_streak: number
  last_latency_s: number | null
  other_gpu_apps: string[]
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
  local_vlm?: LocalVlmHealth
}

export interface PingEngineResult {
  role: 'utama' | 'cadangan'
  ok: boolean
  latency_ms: number
  error?: string
  // T86: diukur dengan gambar contoh seukuran pemeriksaan; dibandingkan dengan batas waktu engine
  is_local?: boolean
  timeout_ms?: number
}

export interface PingResult {
  status: 'ONLINE' | 'ERROR' | 'OFFLINE' | 'BUSY'
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

export type VlmMissingSetting = 'key' | 'base_url' | null

export interface VlmProviderEntry {
  name: string
  label: string
  support: 'official' | 'experimental'
  is_local: boolean
  has_key: boolean
  missing: VlmMissingSetting
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

// --- Pekerja & Identitas Wajah (T34) -------------------------------------------

export type TemplateCondition = 'bare' | 'glasses' | 'helmet' | 'helmet_glasses'

export interface WorkerTemplate {
  id: number
  condition: TemplateCondition | string
  model_version: string
  created_at: string
}

export interface WorkerTemplateQuality {
  face_width_px: number
  interocular_px: number
  det_score: number
}

export interface AddTemplateResponse extends WorkerTemplate {
  quality: WorkerTemplateQuality
}

/** Mode pendaftaran wajah (T75): POST /api/workers/enrollment (mulai/denyut) */
export interface EnrollmentHoldResponse {
  active: boolean
  /** Jeda selesai sendiri bila tanpa denyut selama ini (detik, dari backend) */
  hold_s: number
}

/** Pendaftaran terpandu (T76): GET /api/workers/enrollment/plan — urutan dari config backend */
export interface EnrollmentPlan {
  shots_per_condition: number
  /** Arah kepala per foto = kunci suara petunjuk */
  poses: string[]
  condition_sets: { no_glasses: TemplateCondition[]; glasses: TemplateCondition[] }
  /** Minimal piksel (mutu embedding); maksimal sebagai bagian dari tinggi frame kamera */
  interocular: { min_px: number; max_ratio: number }
  /** Tinggi frame kamera minimal untuk pendaftaran (di bawahnya fit = 'low_resolution') */
  min_frame_height: number
  prompts: {
    condition_switch: string
    fit: Partial<Record<EnrollmentFit, string>>
    done: string
  }
}

export type EnrollmentFit = 'ok' | 'no_face' | 'too_far' | 'too_close' | 'multiple_faces' | 'low_resolution'

/** GET /api/workers/enrollment/preview — hanya deteksi wajah, tidak disimpan */
export interface EnrollmentPreview {
  fit: EnrollmentFit
  faces: number
  interocular_px: number | null
}

/** Telemetri `enrollment`: gerbang jeda selama admin memotret wajah */
export interface EnrollmentStatus {
  active: boolean
  remaining_s: number | null
}

export interface WorkerConsent {
  at: string
  by: string
  version: string
}

export interface Worker {
  id: number
  employee_no: string
  name: string
  active: boolean
  consent: WorkerConsent
  created_at: string
  deactivated_at: string | null
  delete_after: string | null
  face_deleted_at: string | null
  nickname?: string
  gender?: 'male' | 'female' | string
  salutation?: string
  voice_ready?: boolean
  templates: WorkerTemplate[]
  /** T79: opsional sampai backend T79a digabung */
  department?: OrgRef | null
  company?: OrgRef
  /** Pemeriksaan terakhir di audit (T79) */
  last_seen?: { at: string; is_complete: boolean } | null
}

export interface WorkersResponse {
  face_ready: boolean
  limit: {
    tested: number
    count: number
    over: boolean
  }
  workers: Worker[]
}

export interface NewWorkerRequest {
  /** T79: kosong = nomor otomatis dari backend (format config) */
  employee_no: string
  name: string
  consent: boolean
  nickname?: string
  gender?: 'male' | 'female' | string
  department_id?: number | null
  company_id?: number
}

export interface UpdateWorkerRequest {
  nickname?: string
  gender?: 'male' | 'female' | string
  // employee_no sengaja tidak ada: terkunci setelah dibuat (T84, server membalas 409 employee_no_locked)
  department_id?: number | null
  company_id?: number
}

// --- Halaman Pekerja (kontrak T79) ------------------------------------------------------

export interface OrgRef {
  id: number
  name: string
}

export type OrgKind = 'departments' | 'companies'

/** GET /api/org/{kind}: `workers` = jumlah pekerja aktif */
export interface OrgEntry extends OrgRef {
  workers: number
  /** Perusahaan bawaan ("Internal"): tidak bisa dihapus, terpilih otomatis di form */
  builtin: boolean
}

/** GET /api/workers/{id}/inspections */
export interface WorkerInspection {
  id: number
  timestamp: string
  is_complete: boolean
  missing_items: string[]
  fr_score: number | null
  snapshot_filename: string
}

export interface WorkerInspectionsPage {
  items: WorkerInspection[]
  next_before: number | null
}

