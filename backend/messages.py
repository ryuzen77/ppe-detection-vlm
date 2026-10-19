"""Teks operasional yang dibaca operator dan pekerja.

Satu tempat untuk seluruh kalimat yang tampil di dashboard, lampu gerbang,
layar video, dan ekspor CSV, supaya bahasa atau istilah lokasi bisa diganti
tanpa menyentuh logika. Label per item APD tetap di `ppe_rules.py`.

Teks yang digambar ke frame video (HUD_*, FRAME_*) sebaiknya tetap ASCII,
karena dirender oleh OpenCV yang tidak menjamin huruf di luar Latin dasar.
"""

# --- Lampu gerbang (notifier) ---
LIGHT_BOOT = "Standby"
LIGHT_IDLE = "Standby - Menunggu Pekerja"
LIGHT_GRANTED_DEFAULT = "Akses Diizinkan - APD Lengkap"
LIGHT_DENIED_DEFAULT = "Akses Ditolak - APD Tidak Lengkap"
LIGHT_GRANTED = "AKSES DIIZINKAN - APD LENGKAP"
LIGHT_DENIED_MISSING = "AKSES DITOLAK - Belum memakai: {missing}"
LIGHT_POSITION_WARNING = "Peringatan: {reason}"
LIGHT_SYSTEM_WAIT = "SISTEM GANGGUAN - Mohon tunggu, pemeriksaan dilanjutkan otomatis"
# Gangguan kamera (T45): kuning, bukan merah — tidak ada pekerja yang ditolak
# Suara per jenis gangguan (kunci VOICE_TEXTS); membeku ditangani seperti terputus
CAMERA_FAULT_SOUND = {"lost": "kamera_terputus", "frozen": "kamera_terputus", "blocked": "kamera_terhalang"}
LIGHT_CAMERA_FAULT = {
    "lost": "KAMERA TERPUTUS - Gerbang berhenti memeriksa, mohon tunggu petugas",
    "blocked": "KAMERA TERHALANG / BURAM / TERLALU GELAP - Gerbang berhenti memeriksa, mohon tunggu petugas",
    "frozen": "GAMBAR KAMERA MEMBEKU - Menyambung ulang, mohon tunggu",
}
LIGHT_TEST_GREEN = "Uji Coba Manual - Lampu Hijau"
LIGHT_TEST_RED = "Uji Coba Manual - Lampu Merah"
LIGHT_TEST_YELLOW = "Uji Coba Manual - Lampu Kuning"

# --- Arahan posisi dari detektor full-body ---
POSE_OK = "Full body terdeteksi sempurna"
POSE_OUTSIDE_CORRIDOR = "Di luar jalur inspeksi (silakan berdiri di tengah)"
POSE_TOO_FAR = "Terlalu jauh, silakan mendekat ke area gerbang"
POSE_TOO_CLOSE = "Terlalu dekat ke kamera (silakan mundur)"
POSE_HEAD_CLIPPED = "Kepala/Helm terpotong (silakan mundur sedikit)"
POSE_FEET_CLIPPED = "Kaki/Sepatu terpotong (silakan mundur satu langkah)"
POSE_FEET_NOT_VISIBLE = "Kaki belum terlihat (silakan mundur satu langkah)"
POSE_HEAD_CLIPPED_EDGE = "Kepala/Helm terpotong di tepi atas"
POSE_FEET_CLIPPED_EDGE = "Kaki terpotong di tepi bawah"
# T73: orang duduk/jongkok tidak dikirim ke VLM
POSE_NOT_STANDING = "Belum berdiri tegak (silakan berdiri menghadap kamera)"

# --- Status kamera ---
CAMERA_FALLBACK_NAME = "Kamera {index}"
CAMERA_OPEN_FAILED = "Kamera index {index} tidak dapat dibuka"
CAMERA_NO_FRAMES = "Kamera index {index} terbuka tetapi tidak mengirim frame"
CAMERA_UNPLUGGED = "Kamera dicabut dari sistem"
CAMERA_DISCONNECTED = "Kamera terputus atau dicabut"
CAMERA_STALLED = "Kamera berhenti mengirim frame wajar"
CAMERA_FROZEN = "Gambar kamera membeku (frame identik); menyambung ulang"
LOG_CAMERA_RECONNECT = "{reason}. Menunggu untuk disambung ulang."
# T67: tombol Pindai tanpa kamera aktif hanya memindai daftar kamera, tidak mengoptimasi apa pun
LOG_CAMERA_OPTIMIZE_NO_CAMERA = "Optimasi kamera dilewati: belum ada kamera aktif."
LOG_CAMERA_WAITING = "Masih menunggu kamera '{name}' ({seconds:.0f} dtk); perangkat yang terlihat sistem: {seen}"
LOG_CAMERA_FAULT_START = "Gangguan kamera ({fault}): pemeriksaan dihentikan, lampu kuning."
LOG_CAMERA_FAULT_END = "Gangguan kamera ({fault}) selesai setelah {seconds:.0f} dtk; gerbang siaga lagi."

# --- Layar tunggu (frame sintetis) ---
FRAME_TITLE = "ZONA INSPEKSI K3 (STANDBY)"
FRAME_NO_CAMERA = "Kamera fisik belum terhubung - Mode Simulasi Kamera"
FRAME_OPTIMIZING = "Mengoptimalkan kamera - mengukur resolusi terbaik..."
FRAME_SELECT_SOURCE = "Pilih sumber kamera di dashboard untuk memulai"
FRAME_WAITING_DEVICE = "Kamera terputus - colok ulang (port USB lain bila tidak muncul dalam 30 dtk)"
FRAME_RECONNECTING = "Kamera terputus - mencoba menyambung ulang..."

# --- HUD di atas video ---
HUD_CORRIDOR_BANNER = "=== JALUR INSPEKSI K3 (BERDIRI DI TENGAH) ==="
HUD_OUTSIDE_ZONE = "ID #{track_id} | DI LUAR ZONA"
HUD_FULL_BODY = "ID #{track_id} | FULL BODY"
HUD_STEP_BACK = "ID #{track_id} | MUNDUR"
HUD_HEADER = "FPS: {fps:.1f} | {device}"
HUD_LIGHT = "LIGHT: {state}"

# --- Balasan API ---
API_STATE_RESET = "State reset"
API_SCAN_STARTED = ("Pemindaian berjalan. Kamera aktif diukur ulang, "
                    "video sementara berpindah ke layar tunggu.")
API_CAMERA_RELEASED = "Melepas kamera, silakan pilih sumber baru."
API_CAMERA_INDEX_INVALID = "Indeks kamera tidak valid"
API_CAMERA_SWITCHING = "Berpindah ke kamera index {index}..."
API_PPE_ACTIVE_FORMAT = 'Format: {"active": {"<kunci_item>": true/false}}'
# Zona titik berdiri (T36d)
ZONE_INVALID_RANGE = "Batas zona harus memenuhi 0 ≤ y_min < y_max ≤ 1."
ZONE_TOO_NARROW = "Zona terlalu sempit (minimal {min:g} tinggi gambar)."
ZONE_CALIBRATE_NO_PERSON = "Tidak ada orang di lorong pemeriksaan untuk dijadikan titik berdiri."
ZONE_CALIBRATE_NO_FEET = "Kaki orang di titik berdiri belum terlihat kamera."
ZONE_BODY_INVALID = "Isi harus objek JSON: {\"enabled\"?: bool, \"y_min\"?: angka, \"y_max\"?: angka}"
API_SNAPSHOT_NOT_FOUND = "Snapshot image not found"
# Ringkasan laporan (T49)
API_REPORT_PERIOD_INVALID = "Periode harus salah satu dari: {periods}."
API_REPORT_DATE_INVALID = "Tanggal harus berformat YYYY-MM-DD."
WEEKDAY_SHORT = ("Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min")   # Senin = 0 (date.weekday)
REPORT_CSV_FILENAME = "laporan_inspeksi_apd_{suffix}.csv"
# Uji lampu gerbang (T47)
API_LIGHT_TEST_BUSY = "Ada pekerja di jalur pemeriksaan; uji lampu ditunda supaya tidak terlihat sebagai keputusan."
API_LIGHT_TEST_INVALID = "Aksi uji lampu harus salah satu dari: {actions}."
# Login admin (T30)
API_LOGIN_REQUIRED = "Silakan login terlebih dahulu."
API_LOGIN_FAILED = "Nama pengguna atau kata sandi salah."
API_FORBIDDEN = "Akun ini tidak berhak melakukan tindakan tersebut."
# Akun pengguna (T51)
ACCOUNT_INVALID_USERNAME = ("Nama pengguna harus {min}-{max} karakter: huruf kecil, angka, titik, garis bawah, "
                            "atau tanda hubung.")
ACCOUNT_WEAK_PASSWORD = "Kata sandi minimal {min} karakter (maksimal {max}) dan tidak sama dengan nama pengguna."
ACCOUNT_WRONG_PASSWORD = "Kata sandi saat ini salah."
ACCOUNT_USERNAME_TAKEN = "Nama pengguna '{username}' sudah dipakai."
ACCOUNT_NOT_FOUND = "Akun '{username}' tidak ditemukan."
ACCOUNT_LAST = "Akun terakhir tidak bisa dihapus; gerbang harus selalu punya admin."
ACCOUNT_SELF_DELETE = "Akun yang sedang dipakai tidak bisa dihapus sendiri."
ACCOUNT_SETUP_LOCAL_ONLY = ("Akun admin pertama hanya bisa dibuat dari mesin gerbang: buka "
                            "http://localhost:{port} di komputer gerbang.")
ACCOUNT_SETUP_DONE = "Akun admin sudah ada; silakan login."
ACCOUNT_CLI_CREATED = "Akun '{username}' dibuat."
ACCOUNT_CLI_RESET = "Kata sandi '{username}' diganti. Sesi lamanya berakhir saat server dinyalakan ulang."
ACCOUNT_CLI_MISMATCH = "Kedua kata sandi tidak sama."
ACCOUNT_CLI_PROMPT = "Kata sandi baru untuk '{username}': "
ACCOUNT_CLI_PROMPT_AGAIN = "Ulangi kata sandi: "
ACCOUNT_CLI_EMPTY = "Belum ada akun. Buka http://localhost:{port} di mesin gerbang untuk membuat admin pertama."
STARTUP_ADMIN_TOKEN_UNUSED = ("ADMIN_TOKEN di backend/.env tidak dipakai lagi (T51): login memakai akun. "
                              "Hapus baris itu dari .env.")
STARTUP_NO_ACCOUNT = "Belum ada akun. Buat admin pertama dari mesin gerbang: http://localhost:{port}"
API_LOGIN_LOCKED = "Terlalu banyak percobaan login. Coba lagi sebentar lagi."

# --- Prompt VLM ---
# Prompt sistem dirakit dari item APD aktif (ppe_rules); di sini hanya kerangkanya.
# Jawaban ringkas (hanya nilai per item) — lihat ppe_rules.build_json_shape.
# Versi prompt VLM. NAIKKAN setiap kali isi prompt atau aturan item berubah:
# validasi model di vlm_providers/profiles.py berlaku untuk versi tertentu (T39b).
PROMPT_VERSION = "T58"

VLM_SYSTEM_PROMPT = (
    "Anda inspektur K3. Nilai APD orang di gambar. "
    "Jawab HANYA JSON sesuai bentuk di bawah, tanpa teks lain.\n\n"
    "{rules}\n\n"
    "Bentuk JSON:\n"
    "{json_shape}"
)
VLM_USER_PROMPT = "Nilai gambar ini. JSON saja."
# Panggilan termurah untuk uji latensi & pemanasan
VLM_PING_PROMPT = "Ping. Jawab 'PONG'."
# Konfirmasi kedua larangan (T58): dikirim HANYA bila jawaban pertama menyatakan larangan
# terlihat. Pertanyaan per item ada di katalog (`PPEItem.confirm_prompt`). Bench 13-10:
# qwen2.5vl:7b menilai tangan bernoda semen sebagai "rokok menyala"; ditanya khusus -> "tangan kosong".
VLM_CONFIRM_SYSTEM_PROMPT = "Anda pemeriksa larangan K3. Jawab HANYA JSON, tanpa teks lain."
VLM_CONFIRM_SHAPE = 'Bentuk JSON: {"detected": true/false, "seen": "<benda yang terlihat di tangan dan mulut>"}'

# --- Suara gerbang (dibangkitkan jadi MP3 oleh generate_audio.py) ---
# Sengaja singkat (T36b): suara hasil ikut menentukan kapan pekerja melangkah,
# jadi tiap detik suara menambah waktu antrean. Suara per item APD ada di katalog
# ppe_rules (`audio_missing_text`).
VOICE_TEXTS = {
    "mundur": "Mundur sampai seluruh tubuh terlihat.",
    "mundur_kepala": "Mundur sedikit, kepala terpotong.",
    "mundur_kaki": "Mundur satu langkah, kaki belum terlihat.",
    # T73: orang duduk/jongkok di jalur
    "berdiri_tegak": "Silakan berdiri tegak menghadap kamera.",
    "posisi_pas": "Posisi tepat. Mohon tunggu.",
    "lengkap": "APD lengkap. Silakan masuk.",
    "tidak_lengkap": "APD tidak lengkap. Akses ditolak.",
    "sedang_analisa": "Mohon tunggu.",
    # Utama & cadangan VLM gagal (T27): belum ada keputusan, pemeriksaan diulang otomatis
    "sistem_gangguan": "Sistem sedang gangguan. Mohon tunggu, pemeriksaan diulang otomatis.",
    # Gangguan kamera (T45/T45b): terputus dan terhalang dibedakan, diputar sekali per kejadian
    "kamera_terputus": "Kamera gerbang terputus. Mohon tunggu petugas.",
    "kamera_terhalang": "Kamera gerbang terhalang atau buram. Mohon singkirkan penghalang dan bersihkan lensa kamera.",
}

# --- Berjalan sendiri (T29) ---
SUPERVISOR_START = "Penjaga proses gerbang mulai; server dinyalakan ulang otomatis bila crash."
SUPERVISOR_RESTART = "Server berhenti tidak wajar (kode {code}) setelah {ran:.0f} dtk; dinyalakan ulang dalam {delay:.0f} dtk."
SUPERVISOR_CLEAN_EXIT = "Server berhenti rapi; penjaga proses selesai."
SUPERVISOR_STOPPED = "Penjaga proses dihentikan operator."
STARTUP_NO_CUDA = "CUDA tidak tersedia: YOLO berjalan di CPU, pemeriksaan sangat lambat. Periksa driver/mode GPU."
STARTUP_OLLAMA_UNREACHABLE = "Ollama (VLM cadangan) tidak terjangkau saat start; dicoba lagi saat inspeksi. Pastikan aplikasi Ollama menyala."
STARTUP_OLLAMA_VERSION = ("Versi Ollama {found} berbeda dari versi validasi {expected}: kecepatan & akurasi VLM lokal "
                          "belum terjamin. Kembalikan versinya atau validasi ulang (tools/bench_vlm.py).")
STARTUP_CAMERA_MISSING = "Kamera '{name}' belum terlihat sistem (terlihat: {seen}); gerbang menunggu kamera itu."
STARTUP_NO_BACKUP = ("Tanpa VLM cadangan (bawaan): bila VLM utama gangguan atau kuota habis, gerbang berhenti "
                     "menerima pekerja (pekerja diminta menunggu). Aktifkan cadangan di Pengaturan bila perlu.")
STARTUP_ALL_OK = "Pemeriksaan saat start: semua baik."
CAMERA_AUTOSTART_NO_NAME = ("CAMERA_AUTOSTART aktif tetapi belum ada nama kamera (CAMERA_NAME kosong & belum pernah "
                            "dipilih); menunggu operator memilih kamera.")
CAMERA_AUTOSTART_OPENED = "Kamera otomatis: '{name}'."
CAMERA_AUTOSTART_WAITING = "Kamera '{name}' belum terlihat sistem; menunggu (tidak membuka kamera lain)."

# --- Catatan hidup server (T37) ---
UPTIME_CLEAN_RESTART = "Server menyala. Sebelumnya berhenti rapi pada {since}; gerbang tidak aktif {down}."
UPTIME_UNCLEAN_RESTART = ("Server menyala setelah BERHENTI MENDADAK (listrik padam/crash). "
                          "Terakhir hidup {since}; gerbang tidak aktif sekitar {down}.")
UPTIME_WRITE_FAILED = "Gagal menulis catatan hidup server: {error}"
DURATION_HOURS = "{h} jam {m} menit"
DURATION_MINUTES = "{m} menit {s} detik"
DURATION_SECONDS = "{s} detik"
SNAPSHOT_WRITE_FAILED = "Gagal menyimpan foto bukti {name}: {error}"
SNAPSHOT_TMP_REMOVED = "Membuang {count} foto bukti setengah jadi dari penghentian mendadak sebelumnya."

# --- Profil penyedia & validasi model (T39b) ---
VLM_PROVIDER_EXPERIMENTAL = ("Penyedia VLM {who} eksperimental: belum pernah diuji di gerbang ini. "
                             "Uji dulu dengan tools/bench_vlm.py sebelum dipakai di lapangan.")
VLM_MODEL_UNVALIDATED = ("Model VLM {who} BELUM TERVALIDASI dengan foto berlabel; keputusan APD-nya "
                         "belum terbukti aman (lihat vlm_providers/profiles.py).")
VLM_MODEL_PARTIAL = "Model VLM {who} baru tervalidasi sebagian: {note}."
VLM_MODEL_OUTDATED = ("Model VLM {who} tervalidasi untuk prompt {old}, sekarang {current}; "
                      "ulangi uji foto berlabel.")
VLM_MODEL_UNSAFE = ("Model VLM {who} pernah MELOLOSKAN pekerja ber-APD kurang ({missed} dari {photos} foto). "
                    "Jangan dipakai di gerbang.")
VLM_THINKING_INVALID = "VLM_THINKING={value} tidak dikenal (pilihan: {choices}); dianggap off."
VLM_THINKING_UNSUPPORTED = "VLM_THINKING={value} diabaikan: penyedia {provider} tidak bisa mengatur mode berpikir."

# --- Ganti penyedia VLM dari dashboard (T28) ---
VLM_SELECT_UNKNOWN_PROVIDER = "Penyedia VLM '{provider}' tidak dikenal."
VLM_SELECT_MISSING_MODEL = "Nama model untuk penyedia {provider} belum diisi."
VLM_SELECT_MISSING_KEY = "API key {provider} belum ada: isi {key_env} di backend/.env lalu nyalakan ulang server."
VLM_SELECT_MISSING_BASE_URL = "Alamat server {provider} belum ada: isi VLM_BASE_URL di backend/.env."
VLM_SELECT_UNSAFE = ("Model {provider}/{model} pernah MELOLOSKAN pekerja ber-APD kurang "
                     "({missed} dari {photos} foto) dan tidak boleh dipakai di gerbang.")
VLM_SELECT_NEEDS_CONFIRMATION = ("Model {provider}/{model} belum tervalidasi untuk prompt {prompt} "
                                 "(status: {status}). Konfirmasi dulu bila tetap ingin dipakai.")
VLM_SELECT_LANE_BUSY = "Ada pekerja di jalur inspeksi; penyedia VLM diganti setelah jalur kosong."
VLM_SELECT_ENGINE_FAILED = "VLM {role} {provider}/{model} gagal disiapkan ({error}); penyedia lama tetap dipakai."
VLM_SELECT_STORED_IGNORED = "Pilihan VLM tersimpan dari dashboard diabaikan ({reason}); memakai .env."
VLM_SELECT_APPLIED = "VLM {role} diganti dari dashboard: {before} -> {after} (status validasi {status}, dari {client})."

# --- Penjaga model lokal (T38) ---
LOCAL_MODEL_PARTIAL_GPU = "VLM {who} hanya {pct}% di GPU (sisanya CPU, inspeksi sangat lambat); memuat ulang model."
LOCAL_MODEL_RELOADED = "VLM {who} dimuat ulang: {pct}% di GPU."
LOCAL_MODEL_RELOAD_FAILED = ("VLM {who} tetap {pct}% di GPU setelah dimuat ulang; periksa VRAM/driver "
                             "atau nyalakan ulang Ollama.")
LOCAL_MODEL_CHECK_FAILED = "Pemeriksaan porsi GPU VLM lokal gagal: {error}"
# --- Kesehatan VLM lokal (T56) ---
LOCAL_MODEL_SLOW = ("VLM {who} lambat/habis waktu {n}x berturut-turut (terakhir {latency}); memuat ulang model. "
                    "Aplikasi lain di GPU: {apps}. Tutup aplikasi itu atau atur ke 'Power saving' (GPU Intel).")
LOCAL_LATENCY_TIMEOUT = "habis waktu"
LOCAL_MODEL_WARMUP_IMAGE = "Pemanasan gambar VLM {who} selesai dalam {seconds:.1f} dtk."

# --- VLM tidak tersedia (utama & cadangan gagal) ---
VLM_NOT_CONFIGURED = "VLM belum dikonfigurasi (utama & cadangan tidak aktif)"
VLM_NO_DECISION_NOTES = ("[SISTEM GANGGUAN] Tidak ada VLM yang menjawab ({reason}). Belum ada keputusan; "
                         "pekerja diminta menunggu dan diperiksa ulang otomatis.")

# --- Kesiapan pemotretan (T46) ---
LOG_SESSION_READY = ("Sesi #{session}: pekerja siap setelah diam {held:.1f} dtk "
                     "(jendela diam diulang {restarts}x, {frames} frame).")

# --- Akhir sesi (T59) ---
# Teks lama "jalur kosong" dipertahankan: dicari saat analisa log uji nyata
LOG_SESSION_LANE_EMPTY = "Sesi #{session_id} selesai: jalur kosong. Gerbang standby."
LOG_SESSION_SUBJECT_LEFT = ("Sesi #{session_id} selesai: pekerja yang diputuskan meninggalkan jalur "
                            "(orang/benda lain di koridor tidak mewarisi keputusan). Gerbang standby.")

# --- Lampu gerbang fisik (T47) ---
IOT_CONNECTED = "Lampu gerbang tersambung di {port}."
IOT_OPEN_FAILED = "Port lampu gerbang {port} tidak bisa dibuka: {error}. Dicoba lagi otomatis."
IOT_LINK_LOST = "Sambungan lampu gerbang terputus: {error}. Dicoba lagi otomatis."
IOT_NO_ACK = "Papan lampu gerbang belum membalas."
IOT_TYPE_UNSUPPORTED = ("IOT_TYPE={iot_type} tidak didukung; lampu fisik dimatikan. "
                        "Pakai IOT_TYPE=serial (ESP32 lewat USB) atau usb_relay (relay USB HID).")
# Relay USB HID (T54)
IOT_RELAY_CONNECTED = "Relay lampu gerbang tersambung ({product}, serial {serial})."
IOT_RELAY_NOT_FOUND = "Relay lampu gerbang ({target}) tidak ditemukan. Dicoba lagi otomatis."
IOT_RELAY_ANY_BOARD = "papan USBRelay pertama"
IOT_RELAY_REASON_STOP = "server berhenti"
IOT_RELAY_REASON_EXIT = "server keluar dengan kode {code}"
IOT_RELAY_MISMATCH = "Relay lampu gerbang tidak mengikuti perintah (diminta {wanted:#04b}, terbaca {actual:#04b})."
IOT_RELAY_ALL_OFF = "Lampu relay dimatikan ({reason})."
IOT_RELAY_ALL_OFF_FAILED = "Gagal mematikan lampu relay ({reason}): {error}"
IOT_RELAY_CHANNEL_INVALID = ("Kanal relay lampu tidak sah (hijau {green}, merah {red}, papan {count} kanal); "
                             "lampu fisik dimatikan.")

# --- Ekspor CSV audit ---
CSV_HEADER_LEADING = ["No", "Tanggal", "Waktu", "ID Pekerja", "Status Kelulusan"]
CSV_HEADER_TRAILING = ["Item Kurang / Pelanggaran", "Sumber Analisis", "Waktu Proses (ms)",
                       "Catatan", "Nama File Snapshot"]
CSV_STATUS_COMPLETE = "LENGKAP (Akses Diizinkan)"
CSV_STATUS_INCOMPLETE = "TIDAK LENGKAP (Ditolak)"
CSV_WORKER_ID = "Pekerja #{track_id}"
CSV_EMPTY = "-"
CSV_ITEM_OK = "OK"
CSV_ITEM_OK_COLOR = "OK ({color})"
CSV_ITEM_NOT_ASSESSED = "TIDAK DINILAI"


PAYLOAD_TOO_LARGE = "Payload Too Large"

# --- Manajemen log & penjaga disk (T53) ---
LOG_REPEATED = "{message} (terulang {count}x dalam {seconds:.0f} dtk terakhir)"
LOG_DROPPED = "{count} catatan log dibuang karena antrean log penuh (disk lambat atau banjir log)."
LOG_FILE_DISABLED = "Log berkas {path} nonaktif, hanya konsol: {error}"
DISK_LOW = ("Sisa disk data tinggal {free_gb:.1f} GB (batas peringatan {limit_gb:.1f} GB): log berkas hanya "
            "WARNING ke atas. Kosongkan disk atau kurangi masa simpan foto (RETENTION_*).")
DISK_CRITICAL = ("Sisa disk data KRITIS {free_gb:.1f} GB (batas {limit_gb:.1f} GB): log berkas aplikasi dihentikan "
                 "supaya audit & foto bukti masih bisa disimpan. Security log tetap ditulis.")
DISK_OK = "Sisa disk data kembali cukup ({free_gb:.1f} GB): log berkas normal lagi."
DISK_CHECK_FAILED = "Gagal memeriksa sisa disk {path}: {error}"
LOG_PRUNED = "{count} salinan log lama (melewati masa simpan) dihapus dari {path}."

# --- Data pekerja & templat wajah (T34b) ---
WORKER_CONSENT_REQUIRED = "Centang dulu bahwa persetujuan tertulis pekerja sudah ditandatangani."
WORKER_INVALID_NAME = "Nama pekerja wajib diisi (maksimal {max} karakter)."
WORKER_INVALID_EMPLOYEE_NO = ("Nomor pegawai wajib diisi (maksimal {max} karakter: huruf, angka, titik, garis bawah, "
                              "garis miring, atau tanda hubung).")
WORKER_EMPLOYEE_NO_TAKEN = "Nomor pegawai '{employee_no}' sudah terdaftar."
WORKER_NOT_FOUND = "Pekerja #{worker_id} tidak ditemukan."
WORKER_TEMPLATE_NOT_FOUND = "Foto wajah #{template_id} milik pekerja #{worker_id} tidak ditemukan."
WORKER_INVALID_CONDITION = "Kondisi foto harus salah satu dari: {conditions}."
WORKER_INACTIVE = "Pekerja #{worker_id} nonaktif; aktifkan dulu sebelum menambah foto wajah."
WORKER_FACE_NOT_READY = ("Fitur pengenalan wajah belum aktif: FACE_DATA_KEY di backend/.env kosong atau tidak valid. "
                         "Buat kunci dengan: python -m backend.face_crypto generate-key")
FACE_KEY_MISSING = "FACE_DATA_KEY kosong: pengenalan wajah mati, gerbang berjalan tanpa nama pekerja."
FACE_KEY_INVALID = ("FACE_DATA_KEY tidak valid (harus base64 dari {size} byte): pengenalan wajah mati. "
                    "Buat kunci baru dengan: python -m backend.face_crypto generate-key")
FACE_KEY_GENERATED = ("Salin baris berikut ke backend/.env. Simpan juga cadangannya di tempat aman: kunci hilang = "
                      "semua pekerja harus didaftarkan ulang. Jangan dikirim lewat chat/email.")
FACE_TEMPLATE_UNREADABLE = ("{count} templat wajah tidak bisa dibuka (kunci FACE_DATA_KEY berbeda dari saat "
                            "pendaftaran?); pekerja terkait tidak akan dikenali sampai didaftarkan ulang.")
FACE_GALLERY_OVER_LIMIT = ("Pekerja aktif berwajah terdaftar {count} melewati batas teruji {limit}: risiko pekerja "
                           "tidak dikenali naik tajam. Evaluasi ulang model/galeri (docs/RENCANA.md T34).")
FACE_RETENTION_PURGED = "Retensi wajah: data wajah {count} pekerja nonaktif lebih dari {days} hari dihapus."
WORKER_NO_FACE = "Tidak ada wajah terdeteksi. Minta pekerja menghadap kamera di posisi pemeriksaan lalu ulangi."
WORKER_MULTIPLE_FACES = "Terdeteksi {count} wajah. Pastikan hanya pekerja yang didaftarkan terlihat di kamera."
WORKER_FACE_TOO_SMALL = ("Wajah terlalu kecil di kamera (jarak antar-mata {measured:.0f} px, minimal {minimum:.0f} px). "
                         "Naikkan resolusi kamera atau minta pekerja lebih dekat lalu ulangi.")
WORKER_CAMERA_BUSY = "Ada orang di jalur pemeriksaan. Ambil foto pendaftaran saat gerbang tidak sedang memeriksa."
WORKER_CAMERA_UNAVAILABLE = "Kamera belum aktif. Pilih kamera di Pengaturan lalu ulangi."
FACE_ENGINE_LOAD_FAILED = "Mesin pengenalan wajah gagal dimuat dari {path}: {error}"
# Pengenalan dalam sesi (T34c1); log memakai nomor pegawai, bukan nama (minimisasi data)
LOG_FACE_RECOGNIZED = "Sesi #{session}: wajah dikenali, pegawai {employee_no} (skor {score:.2f}, {votes}/{frames} frame)."
# T76: skor terbaik ikut dicatat untuk kalibrasi ambang (bukan nama/nomor pegawai)
LOG_FACE_UNKNOWN = ("Sesi #{session}: wajah tidak dikenali ({faces}/{frames} frame berwajah cukup besar, "
                    "skor terbaik {best}).")
LOG_FACE_FAILED = "Pengenalan wajah gagal, sesi dilanjutkan tanpa nama: {error}"
LOG_FACE_TIMEOUT = "Sesi #{session}: pengenalan wajah melewati {seconds:g} dtk; audit dicatat tanpa nama."
LOG_FACE_GALLERY_LOADED = "Galeri wajah dimuat: {templates} templat dari {workers} pekerja aktif."
CSV_HEADER_WORKER_NAME = "Nama Pekerja (pengenalan wajah)"
CSV_FACE_RECOGNIZED = "{name} ({employee_no})"
CSV_FACE_UNKNOWN = "Tidak dikenali"
# --- VLM cadangan dimatikan (T70) ---
LOG_VLM_LOCAL_UNLOADED = "Model {who} dikeluarkan dari GPU (tidak dipakai lagi)."
LOG_VLM_STALE_CHECK_SKIPPED = "Pemeriksaan model {who} sisa sesi lalu dilewati (Ollama tidak terjangkau): {error}"
LOG_VLM_LOCAL_UNLOAD_FAILED = "Gagal mengeluarkan model {who} dari GPU: {error}. VRAM baru lega setelah Ollama dimulai ulang."

# --- Suara nama pekerja (T34d) ---
# Sapaan dari jenis kelamin yang diisi saat pendaftaran (keputusan pengguna 19-10)
SALUTATIONS = {"male": "Pak", "female": "Bu"}
# Kalimat bernama diturunkan dari suara "lengkap" supaya isinya tidak pernah berbeda
VOICE_PASS_NAMED = VOICE_TEXTS["lengkap"].rstrip(".") + ", {salutation} {nickname}."
WORKER_INVALID_GENDER = "Jenis kelamin wajib dipilih (untuk sapaan Pak/Bu)."
WORKER_INVALID_NICKNAME = "Nama panggilan wajib diisi (maksimal {max} karakter, satu baris), mis. Zen untuk Muhammad Zen Fikri."
LOG_VOICE_CREATED = "Suara nama pekerja #{worker_id} dibuat."
LOG_VOICE_FAILED = ("Suara nama pekerja #{worker_id} gagal dibuat (layanan suara butuh internet): {error}. "
                    "Saat lolos, suara umum dipakai; ubah data pekerja untuk mencoba lagi.")

# --- Mode pendaftaran wajah (T75): gerbang jeda selama admin memotret, kuning (tidak ada yang lolos) ---
LIGHT_ENROLLMENT = "MODE PENDAFTARAN WAJAH - Pemeriksaan APD dijeda sementara oleh admin"
LOG_ENROLLMENT_HOLD_START = "Mode pendaftaran wajah dimulai: pemeriksaan APD dijeda."
LOG_ENROLLMENT_HOLD_END = "Mode pendaftaran wajah selesai: gerbang siaga lagi."
LOG_ENROLLMENT_HOLD_EXPIRED = "Mode pendaftaran wajah berakhir otomatis (tanpa denyut dari modal foto): gerbang siaga lagi."

# --- Pendaftaran wajah terpandu (T76) ---
# Petunjuk lewat speaker gerbang untuk pekerja yang berdiri jauh dari layar (teks tetap, tanpa data pekerja)
ENROLLMENT_VOICE_TEXTS = {
    "daftar_lurus": "Lihat lurus ke kamera.",
    "daftar_kiri": "Toleh sedikit ke kiri.",
    "daftar_kanan": "Toleh sedikit ke kanan.",
    "daftar_menunduk": "Menunduk sedikit, mata tetap ke kamera.",
    "daftar_pakai_helm": "Silakan pakai helm, lalu lihat ke kamera.",
    "daftar_mendekat": "Maju sedikit mendekati kamera.",
    "daftar_menjauh": "Mundur sedikit dari kamera.",
    "daftar_selesai": "Pendaftaran wajah selesai. Terima kasih.",
}
VOICE_TEXTS.update(ENROLLMENT_VOICE_TEXTS)
# Peran suara di alur terpandu (dikirim lewat rencana pendaftaran, UI tidak menyalin kuncinya)
ENROLLMENT_PROMPT_KEYS = {
    "condition_switch": "daftar_pakai_helm",
    "fit": {"too_far": "daftar_mendekat", "too_close": "daftar_menjauh"},
    "done": "daftar_selesai",
}
WORKER_FACE_TOO_CLOSE = ("Wajah terlalu dekat ke kamera (jarak antar-mata {measured:.0f} px, maksimal {maximum:.0f} px). "
                         "Minta pekerja mundur ke posisi pemeriksaan: wajah di jalur jauh lebih kecil.")
WORKER_CAMERA_LOW_RESOLUTION = ("Resolusi kamera {height} px terlalu rendah untuk pendaftaran wajah (minimal {minimum} px): "
                                "wajah di jalur terlalu kecil untuk dikenali. Buka pemilih kamera, tekan 'Pindai kemampuan', lalu ulangi.")
WORKER_FACE_MATCHES_OTHER = ("Wajah ini mirip pekerja {employee_no} (skor {score:.2f}). Satu orang hanya boleh punya satu "
                             "data pekerja; bila memang orang yang sama, tambahkan foto di data pekerja itu.")
WORKER_ENROLLMENT_INACTIVE = "Mode pendaftaran wajah tidak aktif. Buka lagi jendela Ambil Foto."
WORKER_INVALID_PROMPT = "Petunjuk suara tidak dikenal: {prompt}."
