/**
 * Angka perilaku UI baru — satu tempat, padanan backend/config.py untuk sisi
 * browser. Nilai yang juga dipakai backend (mis. ambang keypoint) TIDAK ditulis
 * di sini melainkan dibaca dari telemetri, supaya keduanya tidak menyimpang.
 */

export const URLS = {
  /** Tampilan lama (cadangan) selama redesign belum lengkap */
  legacy: '/legacy/',
} as const

export const TELEMETRY = {
  /** Jeda sambung ulang WebSocket: mulai, lalu dikali factor hingga max */
  reconnectInitialMs: 1500,
  reconnectFactor: 1.5,
  reconnectMaxMs: 10000,
} as const

export const TOASTS = {
  lifetimeMs: 8000,
  maxVisible: 4,
} as const

export const CAMERA_POLL = {
  /** Menunggu kamera terbuka setelah dipilih: interval & batas percobaan */
  connectPollMs: 1000,
  connectMaxTries: 25,
  scanPollMs: 1500,
} as const

export const CLOCK = {
  tickMs: 1000,
  locale: 'id-ID',
} as const

/** Geometri overlay video (proporsi terhadap kotak video) */
export const HUD = {
  shadeAlpha: 0.45,
  laneDash: [6, 6] as number[],
  laneLineWidth: 1.5,
  zoneWidthRatio: 0.65,
  zoneHeightRatio: 0.14,
  zoneMaxHeightPx: 90,
  zoneBottomGapPx: 16,
  bracketRatio: 0.14,
  bracketLineWidth: 2.5,
  keypointRadiusPx: 2.5,
  badgeHeightPx: 20,
  badgePaddingPx: 14,
  badgeGapPx: 4,
  badgeStripePx: 3,
  badgeAlpha: 0.85,
  /** Tebal & ukuran; keluarga font dari token --font-sans */
  badgeFont: '600 12px',
  zoneFont: '600 11px',
} as const

/** Kunci penyimpanan browser (dipakai bersama UI lama: jangan diganti tanpa migrasi) */
export const STORAGE = {
  adminToken: 'safeguard_admin_token',
  guidesVisible: 'safeguard_guides_visible',
} as const
