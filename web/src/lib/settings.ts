/**
 * Angka perilaku UI baru — satu tempat, padanan backend/config.py untuk sisi
 * browser. Nilai yang juga dipakai backend (mis. ambang keypoint) TIDAK ditulis
 * di sini melainkan dibaca dari telemetri, supaya keduanya tidak menyimpang.
 */

/** Bahasa & format angka/tanggal/jam di seluruh UI */
export const LOCALE = 'id-ID'

export const URLS = {
  /** Tampilan lama (cadangan) selama redesign belum lengkap */
} as const

/**
 * Saat UI dibuka lewat Vite dev server, tautan setup harus menunjuk backend
 * (proxy Vite hanya meneruskan /api, bukan halaman setup).
 */
export const DEV_SERVER = {
  vitePort: '5173',
  backendUrl: 'http://localhost:8000',
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
  locale: LOCALE,
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

/** Halaman Laporan */
/** T80: warna tingkat pengenalan wajah (0..1) di laporan kehadiran. T83 ("wajib terdaftar")
 *  baru masuk akal bila angka ini tinggi di gerbang nyata. */
export const ATTENDANCE_RATE = {
  good: 0.9,
  fair: 0.7,
}

export const REPORTS = {
  pageSize: 25,
  /** Ambang warna meter kepatuhan (%): >= good hijau, >= warn kuning, di bawahnya merah */
  complianceGood: 95,
  complianceWarn: 80,
  /** Jeda sebelum memuat ulang saat ada pemeriksaan baru (menghindari muat beruntun) */
  refreshDebounceMs: 800,
  /** Format tanggal di tabel riwayat (25 Sep 2026) */
  dateFormat: { day: '2-digit', month: 'short', year: 'numeric' } as Intl.DateTimeFormatOptions,
  thumbPx: 44,
} as const

/** Kunci penyimpanan browser (dipakai bersama UI lama: jangan diganti tanpa migrasi) */
export const STORAGE = {
  adminToken: 'safeguard_admin_token',
  guidesVisible: 'safeguard_guides_visible',
} as const

export const STAND_ZONE = {
  minHeight: 0.04,          // sama dengan ZONE_MIN_HEIGHT di backend/config.py
  sliderStep: 0.01,
  outsideAlpha: 0.4,        // redup untuk deteksi di luar zona
  successMessageMs: 3000,
} as const;

export const LIGHT_TEST = {
  offDelayMs: 2000,
} as const;

export const CHART = {
  height: 240,
  barWidth: 32,
  missingItemHeight: 32,
  gap: 16,
  paddingY: 24,
  axisXStart: 40,
  missingLabelWidth: 150,
  minWidth: 600,
  maxMissingItems: 5,
} as const

export const MIN_PASSWORD_LENGTH = 12;

export const HEALTH_POLL = {
  intervalMs: 10000,
} as const;

/** Mode pendaftaran wajah (T75): denyut per batas waktu jeda (batasnya dari backend, `hold_s`) */
export const ENROLLMENT_HOLD = {
  beatsPerHold: 3,
  /** Indikator jarak (T76): jeda antar-pemeriksaan wajah di kamera gerbang */
  previewIntervalMs: 1000,
} as const;

/** Foto pendaftaran otomatis (T76): diambil sendiri saat jarak pas & wajah diam */
export const ENROLLMENT_AUTO = {
  /** Pemeriksaan jarak "pas" berturut-turut sebelum memotret (× previewIntervalMs) */
  stablePolls: 2,
  /** Perubahan jarak antar-mata antar-pemeriksaan yang masih dianggap diam (bagian) */
  maxSizeChange: 0.08,
  /** Waktu pekerja mendengar arahan & menoleh setelah foto sebelumnya */
  cooldownMs: 3000,
  /** Waktu memakai helm sebelum foto kondisi kedua: pekerja bisa mendaftar sendiri tanpa menekan tombol */
  switchCooldownMs: 10000,
} as const;

/** Halaman Pekerja (T79) */
export const WORKERS_PAGE = {
  /** Baris riwayat pemeriksaan per muatan ("Muat lebih lama" untuk berikutnya) */
  historyPageSize: 20,
} as const;
