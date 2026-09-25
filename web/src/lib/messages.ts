/**
 * Seluruh teks yang dilihat operator di UI baru — satu tempat, padanan
 * backend/messages.py. Komponen dan logika tampilan tidak menulis kalimat
 * sendiri, supaya istilah seragam dan mudah diganti tanpa menyentuh logika.
 * Teks per item APD tetap berasal dari katalog backend (ppe_rules).
 */
import type { CameraState, VlmMode } from './api/types'

export const BRAND = {
  name: 'DEPRO',
  tagline: 'Digital Safety Protection',
  full: 'DEPRO — Digital Safety Protection',
} as const

export const NAV = {
  label: 'Navigasi utama',
  monitoring: 'Monitoring',
  laporan: 'Laporan',
  pengaturan: 'Pengaturan',
} as const

// --- Status di bilah atas ----------------------------------------------------------

export const CONNECTION = {
  lost: 'Server terputus',
} as const

export const CAMERA_CHIP: Record<CameraState | 'UNKNOWN', string> = {
  OK: 'Kamera',
  IDLE: 'Kamera belum dipilih',
  OPENING: 'Kamera menyiapkan',
  OPTIMIZING: 'Kamera menyiapkan',
  LOST: 'Kamera terputus',
  SYNTHETIC: 'Kamera tidak dapat dibuka',
  UNKNOWN: 'Kamera',
}
export const cameraChipOk = (fps: number) => `${CAMERA_CHIP.OK} · ${Math.round(fps)} fps`

export const VLM_CHIP: Record<VlmMode | 'UNKNOWN', { text: string; hint: string }> = {
  UTAMA: { text: 'VLM utama', hint: 'Penilaian APD oleh VLM utama' },
  CADANGAN: { text: 'VLM cadangan', hint: 'VLM utama tidak menjawab; penilaian oleh VLM cadangan' },
  GANGGUAN: { text: 'VLM gangguan', hint: 'VLM utama & cadangan tidak menjawab' },
  UNKNOWN: { text: 'VLM', hint: '' },
}

export const GATE_CHIP = {
  title: 'Buka Monitoring',
  text: (title: string, trackId: number | null) => `Gerbang: ${title}${trackId ? ` · #${trackId}` : ''}`,
} as const

// --- Panel keputusan gerbang ----------------------------------------------------------

export const GATE = {
  ariaLabel: 'Keputusan gerbang',
  subject: (id: number) => `Pekerja #${id}`,
  offline: { title: 'Server tidak terhubung', detail: 'Menyambung ulang ke server secara otomatis…' },
  noCamera: { title: 'Kamera belum siap' },
  standby: { title: 'Menunggu pekerja', detail: 'Pekerja silakan berdiri di dalam jalur inspeksi.' },
  waiting: {
    title: 'Mohon tunggu',
    detail: 'Sistem pemeriksaan sedang gangguan.',
    retry: (s: number) => ` Diperiksa ulang otomatis dalam ${Math.ceil(s)} dtk.`,
  },
  granted: { title: 'Lolos', detail: 'APD lengkap — akses diizinkan.' },
  denied: { title: 'Ditolak', detail: 'APD belum lengkap — akses ditolak.' },
  analyzing: { title: 'Menganalisis APD…', detail: 'Posisi sudah pas. Pekerja mohon diam sejenak.' },
  holding: { title: 'Posisi pas', detail: 'Menahan posisi sebelum dianalisis…' },
} as const

/** Kalimat panel keputusan saat kamera belum siap, per status kamera */
export const CAMERA_NOT_READY: Record<CameraState, string> = {
  IDLE: 'Pilih sumber kamera untuk memulai pemeriksaan.',
  OPENING: 'Membuka kamera…',
  OPTIMIZING: 'Mengukur mode terbaik kamera…',
  LOST: 'Kamera terputus, menyambung ulang…',
  SYNTHETIC: 'Kamera tidak dapat dibuka.',
  OK: '',
}

/** Arahan posisi per jenis potongan tubuh dari detektor (clip_type) */
export const POSITION: Record<string, { title: string; detail: string }> = {
  HEAD_CLIPPED: { title: 'Mundur sedikit', detail: 'Kepala terlalu dekat dengan kamera.' },
  FEET_CLIPPED: { title: 'Mundur satu langkah', detail: 'Kepala hingga kaki harus terlihat di kamera.' },
  TOO_FAR: { title: 'Silakan mendekat', detail: 'Posisi pekerja terlalu jauh dari kamera.' },
  TOO_CLOSE: { title: 'Silakan mundur', detail: 'Terlalu dekat ke kamera.' },
}
export const POSITION_FALLBACK = { title: 'Silakan mundur', detail: 'Seluruh tubuh harus terlihat di kamera.' }

// --- Overlay video -----------------------------------------------------------------------

export const HUD = {
  standHere: 'BERDIRI DI SINI',
  outsideLane: 'di luar jalur',
  positionOk: 'posisi pas',
  badge: (trackId: number, label: string) => `#${trackId} · ${label}`,
  clip: { HEAD_CLIPPED: 'mundur sedikit', FEET_CLIPPED: 'mundur 1 langkah', TOO_FAR: 'mendekat' } as Record<string, string>,
  clipFallback: 'mundur',
} as const

// --- Checklist APD & riwayat ------------------------------------------------------------------

export const CHECKLIST = {
  title: 'Kelengkapan APD',
  pending: 'Belum dinilai',
  loading: 'Memuat daftar APD…',
  backupBadge: 'Dinilai VLM cadangan',
  backupHint: 'VLM utama tidak menjawab; penilaian oleh VLM cadangan',
} as const

export const HISTORY = {
  title: 'Riwayat terakhir',
  ariaLabel: 'Riwayat pemeriksaan',
  allReports: 'Semua laporan',
  empty: 'Belum ada pemeriksaan sejak server menyala.',
  passed: 'Lolos',
  denied: 'Ditolak',
  complete: 'APD lengkap',
  incomplete: 'APD belum lengkap',
  backup: 'cadangan',
} as const

/** Detik → "3,2 dtk" (format Indonesia) */
export const seconds = (ms: number | null | undefined): string =>
  ms == null || !Number.isFinite(ms) ? '-' : `${(ms / 1000).toFixed(1).replace('.', ',')} dtk`

// --- Panel video & dialog kamera ---------------------------------------------------------------

export const VIDEO = {
  ariaLabel: 'Kamera inspeksi',
  alt: 'Video kamera gerbang',
  waitingServer: 'Menunggu server…',
  placeholder: {
    IDLE: 'Kamera belum dipilih',
    LOST: 'Kamera terputus — menyambung ulang…',
    SYNTHETIC: 'Kamera tidak dapat dibuka',
    OPENING: 'Menyiapkan kamera…',
    OPTIMIZING: 'Menyiapkan kamera…',
    OK: '',
  } as Record<CameraState, string>,
  pickCamera: 'Pilih kamera',
  changeCamera: 'Ganti kamera',
  guides: 'Panduan',
  guidesHint: 'Tampilkan jalur inspeksi & area pijakan',
  sound: 'Suara',
  muted: 'Senyap',
  reset: 'Mulai ulang',
  resetHint: 'Mulai ulang sesi pemeriksaan',
  soundFailed: 'Gagal mengubah suara',
  resetFailed: 'Gagal memulai ulang',
} as const

export const CAMERA_PICKER = {
  title: 'Pilih sumber kamera',
  hintBefore: 'Pilih kamera yang dipakai untuk inspeksi, lalu tekan',
  confirm: 'Gunakan kamera ini',
  connecting: 'Menyambungkan…',
  listLabel: 'Kamera',
  none: 'Tidak ada kamera terdeteksi. Colokkan kamera lalu tekan Pindai.',
  deviceFallback: (index: number) => `Kamera ${index}`,
  index: (index: number) => `index ${index}`,
  notScanned: 'belum dipindai',
  unavailable: 'tidak tersedia',
  inUse: 'sedang dipakai',
  lastUsed: 'terakhir dipakai',
  lowQuality: 'Resolusi kamera rendah: video lebih lancar, tetapi potongan gambar untuk VLM lebih kecil '
    + 'sehingga penilaian helm dan sepatu bisa kurang teliti.',
  scanning: 'Mengukur kemampuan kamera…',
  lastScan: (time: string) => `Pemindaian terakhir pukul ${time}.`,
  scanOptional: 'Pemindaian bersifat opsional; kamera tetap bisa langsung dipakai.',
  opening: 'Membuka kamera…',
  cannotOpen: 'Kamera itu tidak dapat dibuka. Pilih sumber lain.',
  released: 'Kamera dilepas. Pilih sumber baru.',
  scan: 'Pindai kemampuan',
  scanBusy: 'Memindai…',
  release: 'Lepas kamera',
  close: 'Tutup',
  loadFailed: 'Gagal memuat daftar kamera',
  connectFailed: 'Gagal menyambungkan',
  scanFailed: 'Gagal memulai pemindaian',
  releaseFailed: 'Gagal melepas kamera',
} as const

export const modeLabel = (m: { width: number; height: number; fps: number } | null): string =>
  m ? `${m.width}×${m.height}${m.fps ? ` @${Math.round(m.fps)} fps` : ''}` : ''

/** "Pesan dasar: detail galat" dari objek galat apa pun */
export const withError = (base: string, e: unknown): string =>
  `${base}: ${e instanceof Error ? e.message : String(e)}`

/** Tooltip chip status: teks chip + keterangan (tetap terbaca saat chip tinggal ikon) */
export const chipTitle = (text: string, hint: string): string => (hint ? `${text} · ${hint}` : text)

// --- Notifikasi ----------------------------------------------------------------------------------

export const NOTIFY = {
  close: 'Tutup notifikasi',
  denied: (id: number) => `Pekerja #${id} ditolak`,
  missing: (items: string[]) => (items.length ? `Kurang: ${items.join(', ')}` : HISTORY.incomplete),
  outageTitle: 'Sistem gangguan',
  outageDetail: 'VLM utama & cadangan tidak menjawab; pekerja diminta menunggu.',
  recoveredTitle: 'Sistem pulih',
  recoveredDetail: (mode: VlmMode) => `VLM ${mode === 'UTAMA' ? 'utama' : 'cadangan'} kembali menilai.`,
} as const

// --- Halaman yang belum dipindahkan (T33 langkah 2 & 3) ---------------------------------------

export const PAGES = {
  laporan: { title: 'Laporan', description: 'Riwayat pemeriksaan, foto bukti, statistik kepatuhan, dan ekspor CSV.' },
  pengaturan: { title: 'Pengaturan', description: 'Kamera, aturan APD wajib, lampu gerbang, VLM, dan diagnostik.' },
  notMigrated: 'Bagian ini belum dipindahkan ke tampilan baru. Sementara itu gunakan tampilan lama:',
  openLegacy: 'Buka tampilan lama',
} as const
