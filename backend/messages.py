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
API_SNAPSHOT_NOT_FOUND = "Snapshot image not found"

# --- Prompt VLM ---
# Prompt sistem dirakit dari item APD aktif (ppe_rules); di sini hanya kerangkanya.
VLM_SYSTEM_PROMPT = (
    "\nAnda adalah AI Inspektur K3 (Keselamatan dan Kesehatan Kerja) profesional.\n"
    "Tugas Anda adalah memeriksa kelengkapan Alat Pelindung Diri (APD) pada orang "
    "dalam gambar yang dikirimkan.\n\n"
    "Aturan Penilaian APD:\n"
    "{rules}\n\n"
    "{completeness_number}. {completeness_rule}\n\n"
    "Kembalikan hasil dalam format JSON yang valid persis seperti bentuk berikut:\n"
    "{json_shape}\n"
)
VLM_USER_PROMPT = "Periksa kelengkapan APD pekerja pada gambar ini sesuai instruksi K3. Berikan output JSON."
# Panggilan termurah untuk uji latensi & pemanasan
VLM_PING_PROMPT = "Ping. Jawab 'PONG'."

# --- VLM tidak tersedia (utama & cadangan gagal) ---
VLM_NOT_CONFIGURED = "VLM belum dikonfigurasi (utama & cadangan tidak aktif)"
VLM_NO_DECISION_NOTES = ("[SISTEM GANGGUAN] Tidak ada VLM yang menjawab ({reason}). Belum ada keputusan; "
                         "pekerja diminta menunggu dan diperiksa ulang otomatis.")

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
