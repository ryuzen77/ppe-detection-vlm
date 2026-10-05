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

# --- Status kamera ---
CAMERA_FALLBACK_NAME = "Kamera {index}"
CAMERA_OPEN_FAILED = "Kamera index {index} tidak dapat dibuka"
CAMERA_NO_FRAMES = "Kamera index {index} terbuka tetapi tidak mengirim frame"
CAMERA_UNPLUGGED = "Kamera dicabut dari sistem"
CAMERA_DISCONNECTED = "Kamera terputus atau dicabut"
CAMERA_STALLED = "Kamera berhenti mengirim frame wajar"

# --- Layar tunggu (frame sintetis) ---
FRAME_TITLE = "ZONA INSPEKSI K3 (STANDBY)"
FRAME_NO_CAMERA = "Kamera fisik belum terhubung - Mode Simulasi Kamera"
FRAME_OPTIMIZING = "Mengoptimalkan kamera - mengukur resolusi terbaik..."
FRAME_SELECT_SOURCE = "Pilih sumber kamera di dashboard untuk memulai"
FRAME_WAITING_DEVICE = "Kamera terputus - menunggu perangkat tersambung..."
FRAME_RECONNECTING = "Kamera terputus - mencoba menyambung ulang..."

# --- HUD di atas video ---
HUD_CORRIDOR_BANNER = "=== JALUR INSPEKSI K3 (BERDIRI DI TENGAH) ==="
HUD_OUTSIDE_ZONE = "ID #{track_id} | DI LUAR ZONA"
HUD_FULL_BODY = "ID #{track_id} | FULL BODY"
HUD_STEP_BACK = "ID #{track_id} | MUNDUR"
HUD_HEADER = "FPS: {fps:.1f} | {device}"
HUD_LIGHT = "LIGHT: {state}"

# --- Balasan API ---
API_INVALID_ADMIN_TOKEN = "Token admin tidak valid"
API_STATE_RESET = "State reset"
API_KEY_EMPTY = "API key cannot be empty"
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
# Uji lampu gerbang (T47)
API_LIGHT_TEST_BUSY = "Ada pekerja di jalur pemeriksaan; uji lampu ditunda supaya tidak terlihat sebagai keputusan."
API_LIGHT_TEST_INVALID = "Aksi uji lampu harus salah satu dari: {actions}."

# --- Prompt VLM ---
# Prompt sistem dirakit dari item APD aktif (ppe_rules); di sini hanya kerangkanya.
# Jawaban ringkas (hanya nilai per item) — lihat ppe_rules.build_json_shape.
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

# --- Suara gerbang (dibangkitkan jadi MP3 oleh generate_audio.py) ---
# Sengaja singkat (T36b): suara hasil ikut menentukan kapan pekerja melangkah,
# jadi tiap detik suara menambah waktu antrean. Suara per item APD ada di katalog
# ppe_rules (`audio_missing_text`).
VOICE_TEXTS = {
    "mundur": "Mundur sampai seluruh tubuh terlihat.",
    "mundur_kepala": "Mundur sedikit, kepala terpotong.",
    "mundur_kaki": "Mundur satu langkah, kaki belum terlihat.",
    "posisi_pas": "Posisi tepat. Mohon tunggu.",
    "lengkap": "APD lengkap. Silakan masuk.",
    "tidak_lengkap": "APD tidak lengkap. Akses ditolak.",
    "sedang_analisa": "Mohon tunggu.",
    # Utama & cadangan VLM gagal (T27): belum ada keputusan, pemeriksaan diulang otomatis
    "sistem_gangguan": "Sistem sedang gangguan. Mohon tunggu, pemeriksaan diulang otomatis.",
}

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

# --- Penjaga model lokal (T38) ---
LOCAL_MODEL_PARTIAL_GPU = "VLM {who} hanya {pct}% di GPU (sisanya CPU, inspeksi sangat lambat); memuat ulang model."
LOCAL_MODEL_RELOADED = "VLM {who} dimuat ulang: {pct}% di GPU."
LOCAL_MODEL_RELOAD_FAILED = ("VLM {who} tetap {pct}% di GPU setelah dimuat ulang; periksa VRAM/driver "
                             "atau nyalakan ulang Ollama.")
LOCAL_MODEL_CHECK_FAILED = "Pemeriksaan porsi GPU VLM lokal gagal: {error}"

# --- VLM tidak tersedia (utama & cadangan gagal) ---
VLM_NOT_CONFIGURED = "VLM belum dikonfigurasi (utama & cadangan tidak aktif)"
VLM_NO_DECISION_NOTES = ("[SISTEM GANGGUAN] Tidak ada VLM yang menjawab ({reason}). Belum ada keputusan; "
                         "pekerja diminta menunggu dan diperiksa ulang otomatis.")

# --- Lampu gerbang fisik (T47) ---
IOT_CONNECTED = "Lampu gerbang tersambung di {port}."
IOT_OPEN_FAILED = "Port lampu gerbang {port} tidak bisa dibuka: {error}. Dicoba lagi otomatis."
IOT_LINK_LOST = "Sambungan lampu gerbang terputus: {error}. Dicoba lagi otomatis."
IOT_NO_ACK = "Papan lampu gerbang belum membalas."
IOT_TYPE_UNSUPPORTED = ("IOT_TYPE={iot_type} tidak didukung; lampu fisik dimatikan. "
                        "Pakai IOT_TYPE=serial (ESP32 lewat USB).")

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

STARTUP_INSECURE_LAN = "Server berjalan di jaringan terbuka (HOST={host}) tanpa ADMIN_TOKEN. Untuk mencegah pihak lain mengubah pengaturan gerbang, buat ADMIN_TOKEN di .env. Jika Anda yakin ini hanya demo aman, set ALLOW_INSECURE_DEMO=true di .env."

PAYLOAD_TOO_LARGE = "Payload Too Large"
INSECURE_DEMO_WARNING = "Menjalankan mode demo tidak aman di LAN karena ALLOW_INSECURE_DEMO aktif."
