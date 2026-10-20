/**
 * Seluruh teks yang dilihat operator di UI baru — satu tempat, padanan
 * backend/messages.py. Komponen dan logika tampilan tidak menulis kalimat
 * sendiri, supaya istilah seragam dan mudah diganti tanpa menyentuh logika.
 * Teks per item APD tetap berasal dari katalog backend (ppe_rules).
 */
import type { CameraState, VlmMode } from './api/types'
import { LOCALE, REPORTS as REPORTS_SETTINGS, MIN_PASSWORD_LENGTH } from './settings'

export const BRAND = {
  name: 'DEPRO',
  tagline: 'Digital Safety Protection',
  full: 'DEPRO — Digital Safety Protection',
} as const

export const NAV = {
  label: 'Navigasi utama',
  monitoring: 'Monitoring',
  laporan: 'Laporan',
  pekerja: 'Pekerja',
  pengaturan: 'Pengaturan',
} as const

// --- Status di bilah atas ----------------------------------------------------------

export const CONNECTION = {
  lost: 'Server terputus',
  signedOut: 'Belum masuk',
} as const

export const CAMERA_CHIP: Record<CameraState | 'UNKNOWN', string> = {
  OK: 'Kamera',
  IDLE: 'Kamera belum dipilih',
  OPENING: 'Kamera menyiapkan',
  OPTIMIZING: 'Kamera menyiapkan',
  LOST: 'Kamera terputus',
  BLOCKED: 'Kamera terhalang / buram',
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
// T71: cadangan mati (bawaan) — tetap hijau, tetapi operator tahu konsekuensinya
export const VLM_CHIP_NO_BACKUP = {
  text: 'VLM utama · tanpa cadangan',
  hint: 'Tanpa VLM cadangan: bila VLM utama gangguan atau kuota habis, pekerja diminta menunggu',
}


export const IOT_CHIP = {
  connected: 'Lampu gerbang: tersambung',
  disconnected: 'Lampu gerbang: terputus',
  disabled: 'Lampu gerbang: nonaktif'
} as const

// T88: menara lampu di Monitoring. Merah & hijau = lampu fisik nyata; kuning = perintah server
// bila perangkat tidak punya lampu kuning (relay USB 2 kanal) — keputusan pengguna 20-10.
export const LIGHT_TOWER = {
  title: 'Lampu gerbang',
  names: { red: 'Merah', yellow: 'Kuning', green: 'Hijau' } as Record<string, string>,
  states: { red: 'MERAH', yellow: 'KUNING', green: 'HIJAU', off: 'MATI' } as Record<string, string>,
  unknown: 'tidak diketahui',
  sourcePhysical: 'lampu fisik',
  sourcePlan: 'perintah server',
  noPhysical: 'Tanpa lampu fisik — tampilan mengikuti perintah server.',
  disconnected: 'Lampu fisik tidak terbaca: pekerja mungkin tidak melihat lampu. Tampilan merah/hijau tidak bisa dipastikan.',
  mismatch: (command: string) => `Lampu fisik belum sesuai perintah server (${command}).`,
  yellowPlanOnly: 'Kuning hanya di layar: perangkat lampu tidak punya lampu kuning.',
} as const

export const SYSTEM_STATUS = {
  ready: 'Sistem siap',
  issues: (n: number) => `${n} perlu perhatian`,
  title: 'Status sistem',
  open: 'Lihat status sistem',
} as const

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
  enrollment: {
    title: 'Mode pendaftaran wajah',
    detail: 'Pemeriksaan APD dijeda sementara oleh admin; gerbang memeriksa lagi saat foto selesai.',
  },
} as const

/** Kalimat panel keputusan saat kamera belum siap, per status kamera */
export const CAMERA_NOT_READY: Record<CameraState, string> = {
  IDLE: 'Pilih sumber kamera untuk memulai pemeriksaan.',
  OPENING: 'Membuka kamera…',
  OPTIMIZING: 'Mengukur mode terbaik kamera…',
  LOST: 'Kamera terputus, menyambung ulang…',
  SYNTHETIC: 'Kamera tidak dapat dibuka.',
  OK: '',
  BLOCKED: 'Kamera terhalang / buram.',
}

/** Arahan posisi per jenis potongan tubuh dari detektor (clip_type) */
export const POSITION: Record<string, { title: string; detail: string }> = {
  HEAD_CLIPPED: { title: 'Mundur sedikit', detail: 'Kepala terlalu dekat dengan kamera.' },
  FEET_CLIPPED: { title: 'Mundur satu langkah', detail: 'Kepala hingga kaki harus terlihat di kamera.' },
  TOO_FAR: { title: 'Silakan mendekat', detail: 'Posisi pekerja terlalu jauh dari kamera.' },
  TOO_CLOSE: { title: 'Silakan mundur', detail: 'Terlalu dekat ke kamera.' },
  NOT_STANDING: { title: 'Berdiri tegak', detail: 'Silakan berdiri tegak menghadap kamera.' },
}
export const POSITION_FALLBACK = { title: 'Silakan mundur', detail: 'Seluruh tubuh harus terlihat di kamera.' }

// --- Overlay video -----------------------------------------------------------------------

export const HUD = {
  standHere: 'BERDIRI DI SINI',
  outsideLane: 'di luar jalur',
  positionOk: 'posisi pas',
  badge: (trackId: number, label: string) => `#${trackId} · ${label}`,
  clip: { HEAD_CLIPPED: 'mundur sedikit', FEET_CLIPPED: 'mundur 1 langkah', TOO_FAR: 'mendekat', NOT_STANDING: 'berdiri tegak' } as Record<string, string>,
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
  ms == null || !Number.isFinite(ms)
    ? '-'
    : `${(ms / 1000).toLocaleString(LOCALE, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} dtk`

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
  BLOCKED: 'Kamera terhalang / buram.',
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
  capabilityNotScanned: 'kemampuan belum dipindai',
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

// --- Laporan (T33 langkah 2) --------------------------------------------------------------------

export const REPORTS = {
  title: 'Laporan',
  subtitle: 'Riwayat pemeriksaan gerbang, foto bukti, dan statistik kepatuhan APD.',
  refresh: 'Muat ulang',
  exportCsv: 'Ekspor CSV',
  exportHint: 'Unduh seluruh audit sebagai CSV',
  period: {
    ariaLabel: 'Pilih periode laporan',
    options: { day: 'Harian', week: 'Mingguan', month: 'Bulanan' } as Record<string, string>,
    prev: 'Sebelumnya',
    next: 'Berikutnya',
    today: 'Hari ini',
    jumpToDate: 'Lompat ke tanggal',
    formatDate: (d: string) => shortDate(d),
  },
  charts: {
    passed: 'Lolos',
    rejected: 'Ditolak',
    missingItemsTitle: 'Item APD terbanyak yang kurang',
    complianceTitle: 'Kepatuhan & Volume Inspeksi',
    noData: 'Tidak ada data untuk periode ini.',
  },
  stats: {
    ariaLabel: 'Statistik kepatuhan',
    scopeAll: 'Seluruh riwayat',
    scopeSinceStart: 'Sejak server menyala',
    total: 'Total pemeriksaan',
    passed: 'Lolos',
    denied: 'Ditolak',
    compliance: 'Tingkat kepatuhan',
    backup: 'Dinilai VLM cadangan',
    outages: 'Gangguan sistem',
    outagesHint: 'Pemeriksaan tanpa keputusan karena VLM utama & cadangan tidak menjawab',
  },
  filters: {
    ariaLabel: 'Saring riwayat',
    status: { all: 'Semua', complete: 'Lolos', incomplete: 'Ditolak' } as Record<'all' | 'complete' | 'incomplete', string>,
    date: 'Tanggal',
    clearDate: 'Semua tanggal',
    worker: 'Pekerja',
    allWorkers: 'Semua pekerja',
    department: 'Divisi',
    allDepartments: 'Semua divisi',
    company: 'Perusahaan',
    allCompanies: 'Semua perusahaan',
  },
  table: {
    ariaLabel: 'Riwayat pemeriksaan',
    photo: 'Foto',
    time: 'Waktu',
    worker: 'Pekerja',
    result: 'Hasil',
    ppe: 'APD',
    source: 'Dinilai oleh',
    duration: 'Durasi',
    worker_id: (id: number) => `#${id}`,
    unknownWorker: 'Tidak dikenali',
    unknownHint: 'Wajah tidak cocok dengan pekerja terdaftar',
    noPhoto: 'Tanpa foto',
    openPhoto: (id: number) => `Perbesar foto pekerja #${id}`,
    missing: (items: string[]) => (items.length ? `Kurang: ${items.join(', ')}` : ''),
  },
  result: { passed: 'Lolos', denied: 'Ditolak', unverified: 'Tidak terverifikasi' },
  source: { utama: 'VLM utama', cadangan: 'VLM cadangan', gangguan: 'Tanpa keputusan', lama: 'Data lama' },
  loading: 'Memuat riwayat…',
  empty: 'Belum ada pemeriksaan.',
  emptyFiltered: 'Tidak ada pemeriksaan yang cocok dengan saringan.',
  emptyPeriod: 'Belum ada pemeriksaan pada periode ini.',
  loadFailed: 'Gagal memuat riwayat',
  page: {
    ariaLabel: 'Halaman riwayat',
    range: (from: number, to: number, total: number) => `${from}–${to} dari ${total}`,
    prev: 'Sebelumnya',
    next: 'Berikutnya',
  },
  photo: {
    title: (id: number) => `Foto bukti pekerja #${id}`,
    caption: (date: string, time: string, result: string) => `${date} ${time} · ${result}`,
    close: 'Tutup',
  },
} as const

/** Tanggal audit 'YYYY-MM-DD' → '25 Sep 2026'; teks tak dikenal dikembalikan apa adanya */
export function shortDate(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00`)
  return Number.isNaN(d.getTime()) ? isoDate : d.toLocaleDateString(LOCALE, REPORTS_SETTINGS.dateFormat)
}
/** Angka hitungan berformat Indonesia (1.284) */
export const count = (n: number | null | undefined): string => (n ?? 0).toLocaleString(LOCALE)
/** Persen berformat Indonesia (78,8%) */
export const percent = (n: number | null | undefined): string =>
  `${(n ?? 0).toLocaleString(LOCALE, { maximumFractionDigits: 1 })}%`

// --- Pengaturan (T33 langkah 3) -------------------------------------------------------------

export const SETTINGS_TAB = {
  diagnostics: 'Diagnostik',
  serverConnected: 'Server terhubung',
  serverDisconnectedSince: (time: string) => `Server terputus sejak ${time}`,
  serverDisconnected: 'Server terputus',
  zone: 'Titik Berdiri',
  zoneEnabled: 'Gunakan zona titik berdiri',
  zoneCalibrate: 'Jadikan Titik Berdiri',
  zoneSource: (s: string) => `Sumber: ${s}`,
  running: 'Menjalankan...',
  success: 'Berhasil',
  lightOnFailed: 'Gagal menyalakan lampu',
  lightOffFailed: 'Gagal mematikan lampu',
  pingFailed: 'Gagal ping VLM',
  ppeUpdateFailed: 'Gagal mengubah aturan APD',
  pingResult: (status: string, ms: number, msg: string) =>
    `${status === 'ONLINE' ? 'VLM menjawab' : 'VLM tidak menjawab'} dalam ${seconds(ms)}${msg ? ` — ${msg}` : ''}`,
  zoneSaveFailed: 'Gagal mengubah zona',
  zoneRangeFailed: 'Gagal mengubah batas zona',
  zoneCalibrateFailed: 'Gagal kalibrasi',
  zoneCalibrated: 'Titik berdiri berhasil dikalibrasi.',
  zoneNoPerson: 'Tidak ada orang / kaki tidak terlihat.',
  sliderTop: (v: string) => `Atas (y_min: ${v})`,
  sliderBottom: (v: string) => `Bawah (y_max: ${v})`,
  zoneTopLabel: (pct: number) => `Batas atas ${pct}% tinggi gambar`,
  zoneBottomLabel: (pct: number) => `Batas bawah ${pct}% tinggi gambar`,
  zoneTopPercentAria: 'Batas atas persentase',
  zoneBottomPercentAria: 'Batas bawah persentase',
  zoneInvalidBand: 'Pita zona tidak sah atau terlalu sempit',
  zoneLoading: 'Memuat pengaturan zona...',
  camera: 'Kamera',
  pickCamera: 'Pilih Kamera',
  ppeRequired: 'APD Wajib',
  vlm: 'VLM (Visual Language Model)',
  mainModel: 'Model Utama',
  backupModel: 'Model Cadangan',
  lightTest: 'Lampu & Tes',
  testLightBtn: 'Tes hijau',
  testRedBtn: 'Tes merah',
  testYellowBtn: 'Tes kuning',
  latencyTestBtn: 'Uji kecepatan VLM',
  // T78: kelompok & daftar isi
  groups: { gerbang: 'Gerbang', vlm: 'VLM', akun: 'Akun', diagnostik: 'Diagnostik' },
  groupHints: {
    gerbang: 'Kamera, titik berdiri, APD yang diperiksa, dan lampu.',
    vlm: 'Model yang menilai APD.',
    akun: 'Siapa yang bisa masuk ke dashboard.',
    diagnostik: 'Pemeriksaan sambungan server dan VLM.',
  },
  cameraNone: 'Belum ada kamera dipilih.',
  lightTestHint: 'Lampu menyala sebentar lalu padam kembali.',
} as const

// --- Halaman yang belum dipindahkan (T33 langkah 3) ---------------------------------------

export const PAGES = {
  pengaturan: { title: 'Pengaturan', description: 'Kamera, aturan APD wajib, lampu gerbang, VLM, dan diagnostik.' },
  notMigrated: 'Bagian ini belum dipindahkan ke tampilan baru. Sementara itu gunakan tampilan lama:',
  openLegacy: 'Buka tampilan lama',
} as const

export const LOGIN = {
  title: 'Login Admin',
  username: 'Nama Pengguna',
  password: 'Kata Sandi',
  loginBtn: 'Masuk',
  logoutBtn: 'Keluar',
  errorTitle: 'Galat Login',
  waitInfo: 'Coba lagi dalam {s} detik',
}

// --- Auth & Setup (T51) -------------------------------------------------------------------------

export const AUTH = {
  loadingAccounts: 'Memuat akun...',
  loadingSession: 'Memuat sesi...',
  accounts: 'Akun Pengguna',
  listAccounts: 'Daftar Akun',
  username: 'Nama Pengguna',
  role: 'Peran',
  lastLogin: 'Login Terakhir',
  createdAt: 'Dibuat',
  actions: 'Aksi',
  addAccount: 'Tambah Akun',
  password: 'Kata Sandi',
  showPassword: 'Tampilkan sandi',
  hidePassword: 'Sembunyikan sandi',
  passwordMin: `Sandi (min. ${MIN_PASSWORD_LENGTH})`,
  addBtn: 'Tambah',
  resetPassword: 'Reset Sandi',
  deleteBtn: 'Hapus',
  changeOwnPassword: 'Ganti Sandi Sendiri',
  currentPassword: 'Sandi saat ini',
  newPassword: `Sandi baru (min. ${MIN_PASSWORD_LENGTH})`,
  repeatNewPassword: 'Ulangi sandi baru',
  repeatPassword: 'Ulangi sandi',
  saveNewPassword: 'Simpan Sandi Baru',
  you: '(Anda)',
  
  errorPasswordLength: `Kata sandi minimal ${MIN_PASSWORD_LENGTH} karakter`,
  errorPasswordMismatch: 'Konfirmasi kata sandi tidak cocok',
  successPasswordChange: 'Kata sandi berhasil diubah.',
  
  deleteConfirmTitle: 'Hapus Akun',
  deleteConfirmPrompt: 'Hapus akun {user}?',
  cancelBtn: 'Batal',
  resetConfirmTitle: 'Reset Sandi',
  resetSuccess: 'Sandi untuk {user} berhasil direset.',
  resetFailed: 'Gagal mereset sandi: {err}',
  
  setupTitle: 'Setup Akun Admin',
  setupInfo: 'Sistem membutuhkan akun admin pertama.',
  setupNotAllowed: 'Demi keamanan, setup admin pertama hanya dapat dilakukan langsung dari mesin gerbang.',
  setupUrlInfo: 'Buka {url} di mesin gerbang untuk melakukan setup pertama kali.',
  setupBtn: 'Buat Akun',
} as const

export const APP = {
  loadingSession: 'Memuat sesi...',
}

export const VLM_SETTINGS = {
  loading: 'Memuat...',
  activeSource: 'Diatur dari',
  sourceDashboard: 'Dashboard',
  sourceEnv: 'berkas konfigurasi server',
  resetToEnvBtn: 'Kembali ke berkas konfigurasi',
  resetConfirmTitle: 'Kembali ke pengaturan di berkas konfigurasi server?',
  
  primaryTitle: 'VLM Utama',
  backupTitle: 'VLM Cadangan',
  providerLabel: 'Penyedia',
  modelLabel: 'Model',
  noBackup: '(Tanpa cadangan)',
  // T70: cadangan mati = model keluar dari GPU; aktif lagi = menunggu model siap
  noBackupHint:
    'Cadangan mati: bila VLM utama gangguan, pekerja diminta menunggu (tidak pernah lolos tanpa diperiksa). Model cadangan dikeluarkan dari GPU.',
  disableBackupConfirm:
    'Matikan VLM cadangan? Model cadangan dikeluarkan dari GPU. Bila VLM utama gangguan, pekerja diminta menunggu sampai VLM utama pulih. Mengaktifkan lagi nanti perlu menunggu model disiapkan di GPU.',
  applyingLocalBackup:
    'Menyiapkan model cadangan di GPU (bisa sampai sekitar 1 menit). Gerbang tetap memakai pilihan lama sampai model siap...',
  missingKey: '(API key belum diisi di berkas konfigurasi server)',
  missingBaseUrl: '(alamat VLM_BASE_URL belum diisi di berkas konfigurasi server)',
  
  dataLocation: 'Lokasi Data',
  stats: (photos: number | null, missed: number | null, falseRejects: number | null, medianSeconds: number | null) => 
    `Diuji ${photos ?? 0} foto: APD kurang lolos ${missed ?? 0}, patuh salah ditolak ${falseRejects ?? 0}, ±${medianSeconds ?? 0} dtk per pemeriksaan`,
  
  testBtn: 'Uji Penyedia',
  testingBtn: 'Menguji...',
  testResultPrimary: 'Hasil Uji Utama',
  testResultBackup: 'Hasil Uji Cadangan',
  testSuccess: (latency: number | null, isJson: boolean) => 
    `Berhasil (${latency}ms, valid JSON: ${isJson ? 'Ya' : 'Tidak'})`,
    
  applyBtn: 'Terapkan',
  applying: 'Menyiapkan...',
  applySuccess: 'Berhasil diterapkan',
  
  warningTitle: 'Peringatan',
  cancelBtn: 'Batal',
  confirmBtn: 'Saya Yakin, Lanjutkan',
  
  errLoad: 'Gagal memuat',
  errApply: 'Gagal menerapkan',
  errTest: 'Gagal uji',
  errReset: 'Gagal mereset',
}

export const LOCAL_VLM = {
  cardTitle: 'Kesehatan VLM Cadangan',
  statusLabel: 'Status',
  gpuRatioLabel: 'Porsi GPU',
  latencyLabel: 'Latensi Terakhir',
  slowStreakLabel: 'Lambat Berturut-turut',
  otherAppsLabel: 'Aplikasi Lain di GPU',
  noApps: 'Tidak ada',
  emptyValue: '—',
  closeAppsHint: 'Tutup aplikasi ini agar VLM cadangan tidak macet.',
  states: {
    ok: 'Normal',
    slow: 'Lambat',
    partial_gpu: 'Sebagian di CPU',
    unknown: 'Belum diketahui',
  },
  chips: {
    slow: {
      text: 'VLM cadangan lambat',
      hint: 'Panggilan VLM cadangan lambat atau habis waktu berturut-turut',
    },
    partial_gpu: {
      text: 'VLM cadangan di CPU',
      hint: 'Sebagian model VLM cadangan dimuat di CPU',
    },
  },
} as const

export const WORKERS = {
  sectionTitle: 'Pekerja & Identitas Wajah',
  sectionSubtitle: 'Data pekerja untuk pencatatan nama di audit APD dan suara sambutan.',
  faceDisabledBanner: 'Fitur pengenalan wajah belum aktif: FACE_DATA_KEY di backend/.env kosong atau tidak valid.',
  generateKeyHint: 'Buat kunci di terminal gerbang: python -m backend.face_crypto generate-key',
  limitOverWarning: (count: number, tested: number) =>
    `Jumlah pekerja aktif (${count}) melebihi batas yang teruji (${tested}). Akurasi pengenalan wajah dapat menurun.`,
  addWorkerBtn: 'Tambah Pekerja',
  emptyList: 'Belum ada data pekerja yang didaftarkan.',
  tableHeaderNo: 'No. Pegawai',
  tableHeaderName: 'Nama & Sapaan',
  tableHeaderStatus: 'Status',
  tableHeaderTemplates: 'Foto Wajah',
  tableHeaderAction: 'Tindakan',
  modalAddTitle: 'Daftarkan Pekerja Baru',
  modalEditTitle: 'Ubah Profil Pekerja',
  fieldEmployeeNo: 'Nomor Pegawai',
  fieldEmployeeNoPlaceholder: 'mis. P-0001',
  // T84: nomor terkunci setelah tersimpan (keputusan pengguna 20-10)
  employeeNoLockedHint: 'Nomor pegawai tidak bisa diubah setelah tersimpan.',
  fieldName: 'Nama Lengkap',
  fieldNamePlaceholder: 'mis. Muhammad Zen Fikri',
  fieldNickname: 'Nama Panggilan',
  fieldNicknamePlaceholder: 'mis. Zen',
  fieldNicknameHint: 'Nama yang diucapkan oleh sistem suara gerbang saat lolos.',
  fieldGender: 'Jenis Kelamin & Sapaan',
  genderMale: 'Laki-laki (Pak)',
  genderFemale: 'Perempuan (Bu)',
  fieldConsent: 'Persetujuan Tertulis (UU PDP)',
  fieldConsentLabel: 'Pekerja telah menandatangani persetujuan tertulis pemrosesan data biometrik wajah.',
  fieldConsentRequired: 'Persetujuan tertulis wajib dicentang sebelum pendaftaran dapat diproses.',
  fieldRequired: (name: string) => `${name} wajib diisi.`,
  fieldSelectRequired: (name: string) => `${name} wajib dipilih.`,
  cancelBtn: 'Batal',
  submitBtn: 'Daftarkan',
  saveBtn: 'Simpan',
  deleteFaceBtn: 'Hapus Data Wajah',
  deleteTemplateBtn: 'Hapus Foto',
  deactivateBtn: 'Nonaktifkan',
  activateBtn: 'Aktifkan',
  editBtn: 'Ubah Profil',
  confirmDeleteFaceTitle: 'Hapus Data Wajah',
  confirmDeleteFaceMsg: 'Hapus seluruh templat data wajah pekerja ini? Tindakan ini permanen dan tidak dapat dibatalkan (hak hapus UU PDP). Riwayat nama pada audit lama tetap dipertahankan.',
  confirmDeleteTemplateTitle: 'Hapus Satu Foto',
  confirmDeleteTemplateMsg: 'Hapus templat foto wajah ini?',
  statusActive: 'Aktif',
  statusInactive: 'Nonaktif',
  statusReenroll: 'Perlu foto ulang',
  faceNone: 'Belum ada foto',
  groupNoHelmet: 'Tanpa helm',
  groupHelmet: 'Dengan helm',
  orgNone: '—',
  statusFaceDeleted: 'Data wajah terhapus',
  deleteSchedule: (dateStr: string) => `Dihapus pada ${dateStr}`,
  photoCount: (n: number) => `${n} foto`,
  addPhotoBtn: 'Ambil Foto',
  modalPhotoTitle: 'Ambil Foto Wajah',
  modalPhotoSubtitle: 'Foto diambil langsung dari kamera gerbang untuk pengenalan pekerja.',
  conditionBare: 'Wajah Polos (tanpa APD)',
  conditionGlasses: 'Kacamata',
  conditionHelmet: 'Helm',
  conditionHelmetGlasses: 'Helm & Kacamata',
  takePhotoBtn: 'Ambil Foto Sekarang',
  takingPhoto: 'Mengambil foto dari kamera…',
  cameraPreviewTitle: 'Pratinjau Kamera Gerbang',
  qualityBadge: (interocularPx: number) => `Jarak mata ${interocularPx} px`,
  recognizedLabel: 'Dikenali',
  recognizedName: (name: string) => `Dikenali: ${name}`,
  loading: 'Memuat data pekerja…',
  errLoad: 'Gagal memuat data pekerja',
  errAdd: 'Gagal mendaftarkan pekerja',
  errStatus: 'Gagal mengubah status pekerja',
  errDeleteFace: 'Gagal menghapus data wajah',
  errDeleteTemplate: 'Gagal menghapus foto templat',
  errUpdate: 'Gagal memperbarui profil pekerja',
  errTakePhoto: 'Gagal mengambil foto wajah dari kamera',
  enrollmentHoldHint: 'Pemeriksaan gerbang dijeda selama jendela ini terbuka.',
  errEnrollmentHold: 'Gerbang gagal dijeda: foto bisa ditolak bila ada orang di jalur pemeriksaan.',
} as const


// --- Halaman Pekerja (T79) --------------------------------------------------------------

export const WORKERS_PAGE = {
  title: 'Pekerja',
  subtitle: 'Data pekerja, pendaftaran wajah, dan riwayat pemeriksaan APD per orang.',
  searchLabel: 'Cari pekerja',
  searchPlaceholder: 'Cari nomor atau nama…',
  statusLabel: 'Status',
  statusOptions: { active: 'Aktif', inactive: 'Nonaktif', all: 'Semua status' },
  departmentLabel: 'Divisi',
  companyLabel: 'Perusahaan',
  allDepartments: 'Semua divisi',
  allCompanies: 'Semua perusahaan',
  manageOrg: 'Kelola divisi & perusahaan',
  shown: (n: number, total: number) => (n === total ? `${total} pekerja` : `${n} dari ${total} pekerja`),
  noMatch: 'Tidak ada pekerja yang cocok dengan pencarian ini.',
  colNo: 'Nomor',
  colName: 'Nama',
  colOrg: 'Divisi · Perusahaan',
  colFace: 'Foto wajah',
  colLastSeen: 'Terakhir lewat',
  colStatus: 'Status',
  lastSeenNever: 'Belum pernah',
  lastSeenPass: 'lolos',
  lastSeenFail: 'APD kurang',
  pickHint: 'Pilih pekerja di daftar untuk melihat data, foto wajah, dan riwayatnya.',
  closeDetail: 'Tutup detail',
  sectionProfile: 'Data diri',
  sectionFace: 'Foto wajah',
  sectionHistory: 'Riwayat pemeriksaan',
  profileNickname: 'Nama panggilan',
  profileSalutation: 'Sapaan',
  profileConsent: 'Persetujuan',
  consentText: (date: string, by: string) => `${date} oleh ${by}`,
  enrollBtn: 'Daftarkan wajah',
  historyEmpty: 'Belum ada pemeriksaan tercatat untuk pekerja ini.',
  historyUnavailable: 'Riwayat belum tersedia di server ini.',
  historyMore: 'Muat lebih lama',
  historyPass: 'Lolos',
  historyFail: 'APD kurang',
  historyScore: (score: number) => `wajah ${score.toFixed(2)}`,
  historyPhoto: 'Foto bukti',
  fieldDepartmentNone: 'Tanpa divisi',
  employeeNoAutoHint: 'Terisi otomatis; boleh diganti nomor dari HR. Tidak bisa diubah setelah disimpan.',
  employeeNoAutoEmpty: 'Kosongkan untuk nomor otomatis. Tidak bisa diubah setelah disimpan.',
  errOrgLoad: 'Gagal memuat daftar divisi & perusahaan',
} as const

export const ORG_MANAGER = {
  title: 'Divisi & perusahaan',
  subtitle: 'Daftar pilihan saat menambah atau mengubah pekerja. Nama dipakai di laporan.',
  departments: 'Divisi',
  companies: 'Perusahaan',
  addPlaceholder: { departments: 'Nama divisi baru', companies: 'Nama perusahaan / kontraktor baru' },
  addBtn: 'Tambah',
  renameBtn: 'Ubah nama',
  saveBtn: 'Simpan',
  deleteBtn: 'Hapus',
  close: 'Tutup',
  workers: (n: number) => `${n} pekerja aktif`,
  builtin: 'bawaan',
  empty: 'Belum ada.',
  errSave: 'Gagal menyimpan',
  errDelete: 'Gagal menghapus',
} as const

// --- Pendaftaran wajah terpandu (T76) ---------------------------------------------------

export const ENROLLMENT_GUIDE = {
  askGlasses: 'Apakah pekerja memakai kacamata sehari-hari?',
  askGlassesHint: 'Pekerja berdiri di posisi pemeriksaan. Diambil 5 foto tanpa helm, lalu 5 foto dengan helm.',
  glassesYes: 'Ya, berkacamata',
  glassesNo: 'Tidak',
  step: (n: number, total: number) => `Foto ${n} dari ${total}`,
  poses: {
    daftar_lurus: 'Lihat lurus ke kamera',
    daftar_kiri: 'Toleh sedikit ke kiri',
    daftar_kanan: 'Toleh sedikit ke kanan',
    daftar_menunduk: 'Menunduk sedikit, mata tetap ke kamera',
  } as Record<string, string>,
  conditionSwitch: 'Minta pekerja memakai helm sekarang.',
  fit: {
    ok: 'Jarak pas',
    no_face: 'Wajah belum terlihat',
    too_far: 'Terlalu jauh, minta pekerja maju sedikit',
    too_close: 'Terlalu dekat, minta pekerja mundur ke posisi pemeriksaan',
    multiple_faces: 'Ada lebih dari satu wajah di kamera',
    low_resolution: 'Resolusi kamera terlalu rendah: buka pemilih kamera, tekan "Pindai kemampuan"',
  },
  autoHint: 'Foto diambil otomatis saat jarak pas dan wajah diam.',
  holdStill: 'tahan posisi',
  helmetWaiting: (seconds: number) => `Pekerja memakai helm; foto otomatis dilanjutkan setelah ${seconds} detik.`,
  autoStopped: 'Foto otomatis berhenti karena foto ditolak. Perbaiki penyebabnya lalu tekan Ambil Foto.',
  fitMeasured: (px: number) => `jarak antar-mata ${Math.round(px)} px`,
  speakPose: 'Ucapkan arahan',
  speakFit: 'Ucapkan arahan jarak',
  saved: (n: number, total: number) => `Foto ${n} dari ${total} tersimpan.`,
  doneTitle: 'Pendaftaran wajah selesai',
  doneDetail: (n: number) => `${n} foto tersimpan untuk pekerja ini.`,
  finish: 'Selesai',
  mirrorHint: 'Pratinjau ditampilkan seperti cermin; foto yang disimpan tetap asli.',
  errPlan: 'Gagal memuat rencana pendaftaran',
  errPrompt: 'Suara petunjuk gagal diputar di speaker gerbang',
  checkingFit: 'Memeriksa jarak wajah…',
  fitUnavailable: 'Jarak wajah belum bisa diperiksa: pastikan kamera gerbang aktif di Monitoring.',
} as const
