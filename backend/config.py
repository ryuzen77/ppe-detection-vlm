import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent

# Jalur .env ditulis eksplisit supaya tidak bergantung pada direktori kerja
# atau pada cara modul ini diimpor.
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    """Nilai variabel lingkungan; kosong dianggap tidak diisi.

    `.env` hasil salinan `.env.example` sering berisi baris seperti `GEMINI_MODEL=`.
    `os.getenv` mengembalikan string kosong untuk baris itu, bukan nilai bawaan,
    sehingga nama model, port, atau sakelar diam-diam menjadi kosong.
    """
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


# Model bawaan per penyedia bila VLM_MODEL kosong. Penyedia cloud lain wajib
# menyebut modelnya sendiri karena daftar model vision mereka sering berganti.
_DEFAULT_VLM_MODELS = {
    "gemini": "gemini-3.5-flash-lite",
    # T26 (84 foto): satu-satunya model lokal yang tidak meloloskan APD kurang
    # (0/58, akurasi 94%); qwen2.5vl:3b lebih cepat tetapi meloloskan 11/58.
    "ollama": "qwen2.5vl:7b",
}
# Penyedia yang berjalan di mesin sendiri: tanpa API key dan tanpa kuota
LOCAL_VLM_PROVIDERS = ("ollama", "vllm")


def _resolve_data_dir(value: str) -> Path:
    """Jalur relatif dihitung dari akar repo, bukan dari direktori kerja terminal."""
    path = Path(value).expanduser() if value else REPO_ROOT / "data"
    return (path if path.is_absolute() else REPO_ROOT / path).resolve()


class Config:
    # Server Settings
    HOST: str = _env("HOST", "0.0.0.0")
    PORT: int = int(_env("PORT", "8000"))
    # Default dibatasi ke localhost. `allow_origins=["*"]` bersama
    # `allow_credentials=True` ditolak browser sesuai spesifikasi CORS.
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in _env(
            "CORS_ORIGINS",
            "http://localhost:8000,http://127.0.0.1:8000"
        ).split(",")
        if origin.strip()
    ]

    # Guard opsional untuk endpoint yang mengubah state. Kosong = guard non-aktif,
    # supaya demo lokal tidak terhambat. Isi kalau server dipakai di jaringan bersama.
    ADMIN_TOKEN: str = _env("ADMIN_TOKEN", "")

    # Camera Settings (Webcam / USB Camera default: 0)
    CAMERA_INDEX: int = int(_env("CAMERA_INDEX", "0"))
    FRAME_WIDTH: int = int(_env("FRAME_WIDTH", "1280"))
    FRAME_HEIGHT: int = int(_env("FRAME_HEIGHT", "720"))
    FPS: int = int(_env("FPS", "30"))

    # Pemilihan mode kamera otomatis. Setiap perangkat punya batas berbeda, jadi
    # resolusi diukur lalu dipilih, bukan dipaksa seragam. Kelancaran diutamakan:
    # panduan posisi terasa tidak responsif di bawah ~15 FPS, sedangkan inferensi
    # YOLO masih sangat longgar (~15 ms per frame).
    # Kamera TIDAK dibuka saat server menyala. Operator memilih sumbernya lebih
    # dulu lewat dashboard, baru video tersambung — tidak ada perangkat yang
    # terlanjur dibuka lalu diganti. Set true untuk langsung memakai pilihan
    # terakhir tanpa bertanya (mis. kios yang menyala sendiri).
    CAMERA_AUTOSTART: bool = _env("CAMERA_AUTOSTART", "false").lower() == "true"
    CAMERA_AUTO_MODE: bool = _env("CAMERA_AUTO_MODE", "true").lower() == "true"
    CAMERA_TARGET_FPS: float = 25.0        # Sudah dianggap cukup lancar
    # Permintaan bawaan saat kamera dibuka tanpa mode tersimpan. Dipilih karena
    # resolusi rendah hampir selalu berjalan penuh di kamera mana pun, dan
    # pengukuran menunjukkan permintaan ini menghasilkan 848x480@30 di webcam
    # laptop serta 640x480@25 di kamera USB penguji — dua-duanya lancar.
    # Mode yang lebih baik dicari lewat tombol "Pindai kamera", bukan saat membuka,
    # karena pengukuran yang akurat butuh belasan detik.
    CAMERA_DEFAULT_REQ_WIDTH: int = 854
    CAMERA_DEFAULT_REQ_HEIGHT: int = 480
    # Sebagian kamera USB baru mencapai laju stabilnya beberapa detik setelah dibuka
    # (kamera penguji: 1 FPS di detik pertama, 26 FPS baru di detik keempat).
    CAMERA_SETTLE_SECONDS: float = 3.5
    CAMERA_MIN_HEIGHT: int = 400           # Di bawah ini, crop untuk VLM terlalu kecil
    CAMERA_TARGET_ASPECT: float = 16 / 9   # Cocok dengan viewport dashboard
    CAMERA_ASPECT_TOLERANCE: float = 0.05
    # Crop VLM di bawah tinggi ini ditandai di UI sebagai penurunan kualitas
    CAMERA_QUALITY_WARN_HEIGHT: int = 540
    # Kegagalan baca berturut-turut sebelum kamera dianggap lepas.
    # Ini saja TIDAK cukup: sebagian driver USB tetap mengembalikan frame "berhasil"
    # berisi sampah scanline setelah kamera dicabut, jadi dua penanda berikut
    # dipakai bersamaan.
    CAMERA_LOST_THRESHOLD: int = 30
    # Penanda 1 - laju frame ambruk. Kamera USB penguji jatuh dari 25 ke 1,1 FPS
    # saat dicabut sementara pembacaan tetap "berhasil".
    CAMERA_STALL_SECONDS: float = 3.0      # Lama laju harus tetap ambruk sebelum divonis
    CAMERA_STALL_FPS_RATIO: float = 0.25   # Ambang relatif terhadap laju normal kamera itu
    CAMERA_STALL_MIN_BASELINE: float = 8.0 # Mode yang memang lambat tidak diawasi cara ini
    # Penanda 2 - perangkat hilang dari daftar sistem operasi. Paling tegas, tetapi
    # enumerasi DirectShow tidak murah sehingga dijalankan di thread pengawas sendiri.
    CAMERA_PRESENCE_CHECK_SECONDS: float = 2.0
    # Jeda antar upaya menyambung ulang kamera yang lepas
    CAMERA_RECONNECT_INTERVAL_SECONDS: float = 2.0
    # Indeks tertinggi yang dicoba saat pemindaian bila nama perangkat tidak bisa
    # dibaca dari sistem operasi (bila bisa, jumlah perangkat itu yang dipakai)
    CAMERA_SCAN_MAX_INDEX: int = 6

    # Ritme thread kamera & inferensi
    CAMERA_READ_RETRY_SECONDS: float = 0.03      # Jeda setelah satu pembacaan frame gagal
    STATUS_FRAME_INTERVAL_SECONDS: float = 0.1   # Frame pesan saat kamera belum dipilih/terputus
    SYNTHETIC_FRAME_INTERVAL_SECONDS: float = 0.033  # Frame pengganti saat tidak ada kamera (~30 FPS)
    INFERENCE_POLL_SECONDS: float = 0.005        # Jeda saat inferensi menunggu frame baru
    THREAD_STOP_TIMEOUT_SECONDS: float = 5.0     # Batas tunggu thread kamera/inferensi saat shutdown
    FPS_SMOOTHING: float = 0.1                   # Bobot frame terbaru pada rata-rata FPS (EMA)

    # Aliran video & telemetri ke dashboard
    STREAM_JPEG_QUALITY: int = 80                # Mutu JPEG aliran MJPEG
    STREAM_INTERVAL_SECONDS: float = 0.033       # Jeda antar frame MJPEG (~30 FPS)
    TELEMETRY_INTERVAL_SECONDS: float = 0.05     # Jeda antar pesan WebSocket (20 Hz)
    TELEMETRY_HISTORY_RECORDS: int = 8           # Riwayat inspeksi yang ikut tiap pesan telemetri

    # Model Settings. Harus model pose (keypoint dipakai gerbang full-body).
    # Satu-satunya bobot yang disertakan: yolo26s-pose.pt (YOLO26 Small Pose).
    # Diselesaikan relatif terhadap BASE_DIR, bukan direktori kerja, agar berkas
    # bobot model ditemukan dari mana pun `python -m backend` dijalankan; jalur
    # absolut di YOLO_MODEL_PATH dipakai apa adanya.
    YOLO_MODEL_PATH: str = str(BASE_DIR / _env("YOLO_MODEL_PATH", "yolo26s-pose.pt"))
    YOLO_CONF: float = 0.60
    YOLO_IOU: float = 0.45
    TRACKER_TYPE: str = "bytetrack.yaml"


    # Virtual Inspection Corridor (Membatasi 1 Orang di Tengah)
    # Area aktif lorong inspeksi (rasio dari lebar frame)
    ENABLE_CORRIDOR_FILTER: bool = True
    CORRIDOR_LEFT_RATIO: float = 0.28   # Batas kiri lorong (~358px pada 1280px)
    CORRIDOR_RIGHT_RATIO: float = 0.72  # Batas kanan lorong (~922px pada 1280px)

    # HUD koridor & bounding box sudah digambar canvas di frontend (hud_overlay.js).
    # Biarkan False agar tidak ada overlay ganda; set True jika canvas tidak sejajar video.
    ENABLE_SERVER_HUD: bool = _env("ENABLE_SERVER_HUD", "false").lower() == "true"

    # Full Body Filter Rules (Toleransi Adaptif Tinggi Badan Pekerja)
    # Margin fleksibel pada tepi frame (orang tinggi vs orang pendek)
    # Dinyatakan sebagai rasio tinggi frame, bukan piksel: 15px berarti 2,1% pada
    # 720p tapi 3,1% pada 480p, sehingga ambang piksel absolut membuat panduan
    # "kaki terpotong" lebih cerewet begitu kamera resolusi rendah dipakai.
    BORDER_MARGIN_TOP_RATIO: float = 0.021     # ≈15px pada 720p
    BORDER_MARGIN_BOTTOM_RATIO: float = 0.021  # ≈15px pada 720p
    HEAD_TOUCH_TOP_RATIO: float = 0.007        # ≈5px pada 720p
    ANKLE_TOUCH_BOTTOM_RATIO: float = 0.011    # ≈8px pada 720p
    KNEE_ONLY_BOTTOM_RATIO: float = 0.042      # ≈30px pada 720p
    # Rentang tinggi orang relatif terhadap frame (35% s/d 96%)
    MIN_PERSON_HEIGHT_RATIO: float = 0.35
    MAX_PERSON_HEIGHT_RATIO: float = 0.96
    # Ambang kepercayaan deteksi keypoint pose tubuh (mata, bahu, lutut, kaki)
    KEYPOINT_CONF_THRESHOLD: float = 0.35

    # --- VLM, bebas penyedia (T23) ---
    # gemini, openai, openrouter, qwen, deepseek, ollama, vllm, openai-compatible.
    # Nama lama GEMINI_API_KEY / GEMINI_MODEL tetap dibaca agar .env lama tidak rusak.
    VLM_PROVIDER: str = _env("VLM_PROVIDER", "gemini").lower()
    # GEMINI_API_KEY lama hanya berlaku untuk Gemini: tanpa syarat ini, beralih
    # ke penyedia lain tanpa VLM_API_KEY akan mengirim kunci Gemini ke pihak lain.
    VLM_API_KEY: str = _env("VLM_API_KEY", _env("GEMINI_API_KEY", "") if VLM_PROVIDER == "gemini" else "")
    VLM_MODEL: str = _env(
        "VLM_MODEL",
        _env("GEMINI_MODEL", _DEFAULT_VLM_MODELS["gemini"]) if VLM_PROVIDER == "gemini"
        else _DEFAULT_VLM_MODELS.get(VLM_PROVIDER, ""),
    )
    # Kosong = alamat bawaan penyedia (lihat vlm_providers/openai_compatible.py)
    VLM_BASE_URL: str = _env("VLM_BASE_URL", "")
    # Minta jawaban JSON lewat response_format (OpenAI-compatible); matikan untuk
    # server yang tidak mengenalnya
    VLM_JSON_MODE: bool = _env("VLM_JSON_MODE", "true").lower() == "true"
    VLM_IS_LOCAL: bool = VLM_PROVIDER in LOCAL_VLM_PROVIDERS
    # Khusus Gemini. minimal / low / medium / high; kosong = tidak dikirim.
    GEMINI_THINKING_LEVEL: str = _env("GEMINI_THINKING_LEVEL", "minimal")

    # --- VLM cadangan (T27) ---
    # Dipakai OTOMATIS saat VLM utama gagal, di inspeksi yang sama. Bawaannya VLM
    # lokal lewat Ollama bila utama berada di cloud; "none" = tanpa cadangan.
    # Lokasi tanpa internet cukup menjadikan VLM lokal sebagai utama.
    VLM_BACKUP_PROVIDER: str = _env("VLM_BACKUP_PROVIDER", "none" if VLM_IS_LOCAL else "ollama").lower()
    VLM_BACKUP_MODEL: str = _env("VLM_BACKUP_MODEL", _DEFAULT_VLM_MODELS.get(VLM_BACKUP_PROVIDER, ""))
    VLM_BACKUP_BASE_URL: str = _env("VLM_BACKUP_BASE_URL", "")
    VLM_BACKUP_API_KEY: str = _env("VLM_BACKUP_API_KEY", "")

    # Batas waktu satu panggilan, menurut letak modelnya. Cloud dibuat pendek
    # (2x p95 Gemini ~2 dtk) supaya saat penyedia bermasalah pekerja cepat
    # dialihkan ke cadangan; lokal longgar karena qwen2.5vl:7b di RTX 4060
    # Laptop median 7,9 / p95 9,2 dtk bersama YOLO (T26). Batas yang sama
    # dipasang pada klien HTTP, sehingga panggilan yang lewat batas benar-benar
    # dibatalkan dan tidak menyandera thread (Gemini sempat menggantung ~60 dtk).
    VLM_CLOUD_TIMEOUT_SECONDS: float = float(_env("VLM_CLOUD_TIMEOUT_SECONDS", "4.0"))
    VLM_LOCAL_TIMEOUT_SECONDS: float = float(_env("VLM_LOCAL_TIMEOUT_SECONDS", "12.0"))
    # Batas pemanasan saat startup (memuat model lokal bisa ~40 dtk pertama kali)
    VLM_WARMUP_TIMEOUT_SECONDS: float = float(_env("VLM_WARMUP_TIMEOUT_SECONDS", "120"))
    # Setelah sekian kegagalan utama berturut-turut, utama dianggap terputus:
    # inspeksi langsung ke cadangan tanpa membuang waktu mencoba utama. Utama
    # dicoba lagi pada pekerja nyata setelah jeda (tanpa panggilan uji berkala
    # yang menghabiskan kuota harian free tier).
    VLM_PRIMARY_FAILURES_BEFORE_DOWN: int = int(_env("VLM_PRIMARY_FAILURES_BEFORE_DOWN", "2"))
    VLM_PRIMARY_RETRY_AFTER_SECONDS: float = float(_env("VLM_PRIMARY_RETRY_AFTER_SECONDS", "60"))
    # Bila utama dan cadangan sama-sama gagal, pekerja TIDAK diputuskan: diminta
    # menunggu, lalu diperiksa ulang otomatis setelah jeda ini selama masih di jalur.
    VLM_SYSTEM_RETRY_SECONDS: float = float(_env("VLM_SYSTEM_RETRY_SECONDS", "15"))
    VLM_IMAGE_MAX_SIZE: int = 640            # Maksimum resolusi crop VLM (~35KB)
    VLM_JPEG_QUALITY: int = 75               # Kompresi JPEG hemat kuota & cepat upload
    # Jeda minimum antar panggilan ke VLM cloud untuk menjaga kuota (free tier
    # Gemini 15 RPM). Model lokal tidak berkuota, jadi tanpa jeda.
    VLM_MIN_INTERVAL_SECONDS: float = float(_env("VLM_MIN_INTERVAL_SECONDS", "4.0"))
    # Analisa VLM yang boleh berjalan bersamaan (pool pemanggil di state_manager)
    VLM_MAX_CONCURRENT: int = 2
    # Riwayat latensi API untuk rata-rata di panel monitoring
    API_LATENCY_HISTORY: int = 5
    # Panjang maksimum pesan galat yang diteruskan ke dashboard
    ERROR_MESSAGE_MAX_CHARS: int = 120

    # Anti-Spam & Fast-Queue Settings
    # Jumlah frame tubuh-utuh berturut-turut yang dikumpulkan sebelum analisa;
    # dari kandidat ini SATU frame terbaik dikirim ke VLM (frame_quality, T25a).
    STABLE_FRAMES_REQUIRED: int = int(_env("STABLE_FRAMES_REQUIRED", "3"))
    # Audio warning "Silakan mundur" debounce in seconds per person
    AUDIO_STEP_BACK_DEBOUNCE_SECONDS: float = 6.0
    # Maximum times the step-back voice prompt plays for the same person
    AUDIO_STEP_BACK_MAX_REPEATS: int = 2
    # Jeda minimum suara hasil (lengkap / kurang item) dan suara "sedang menganalisa"
    AUDIO_RESULT_DEBOUNCE_SECONDS: float = 3.0
    AUDIO_ANALYZING_DEBOUNCE_SECONDS: float = 2.0
    # Jeda pengulangan pengumuman "sistem sedang gangguan, mohon tunggu"
    AUDIO_SYSTEM_WAIT_DEBOUNCE_SECONDS: float = 20.0
    # Lama jalur inspeksi harus kosong sebelum sesi gerbang berakhir dan sistem
    # kembali ke tahap 1. Selama sesi berjalan keputusan terkunci; jeda ini juga
    # menyerap orang yang tertutup sesaat agar tidak dianggap sudah pergi.
    STANDBY_RESET_DELAY_SECONDS: float = float(_env("STANDBY_RESET_DELAY_SECONDS", "3.0"))
    # Maximum history records kept in memory
    MAX_HISTORY_RECORDS: int = int(_env("MAX_HISTORY_RECORDS", "30"))

    # Data runtime: audit, foto bukti, dan pilihan operator. Disimpan di luar
    # direktori kode supaya deploy ulang (menimpa/menghapus backend/) tidak ikut
    # menghapusnya. Untuk produksi, arahkan DATA_DIR ke jalur absolut di luar repo.
    DATA_DIR: Path = _resolve_data_dir(_env("DATA_DIR", ""))
    REPORTS_DIR: Path = DATA_DIR / "reports"
    SNAPSHOTS_DIR: Path = REPORTS_DIR / "snapshots"
    DB_PATH: Path = REPORTS_DIR / "audit.db"
    CAMERA_STATE_PATH: Path = DATA_DIR / "camera_state.json"
    RUNTIME_SETTINGS_PATH: Path = DATA_DIR / "runtime_settings.json"

    # Logging: konsol + berkas berotasi (5 MB x 5 berkas) di DATA_DIR/logs
    LOG_LEVEL: str = _env("LOG_LEVEL", "INFO").upper()
    LOG_TO_FILE: bool = _env("LOG_TO_FILE", "true").lower() == "true"
    LOG_DIR: Path = DATA_DIR / "logs"
    LOG_MAX_BYTES: int = 5 * 1024 * 1024
    LOG_BACKUP_COUNT: int = 5

    # Laporan & arsip foto
    SNAPSHOT_JPEG_QUALITY: int = 80           # Mutu foto bukti (~30-50 KB per foto)
    DB_TIMEOUT_SECONDS: float = 10.0          # Tunggu kunci SQLite sebelum menyerah

    # Audio Settings. MP3 adalah aset rilis (dilacak git, dibangkitkan dari
    # katalog APD), bukan data lapangan, jadi tetap berada di direktori kode.
    AUDIO_DIR: Path = BASE_DIR / "audio"
    AUDIO_VOLUME: float = 1.0

    # IoT / Hardware Output (Ready for Stage 2)
    IOT_ENABLED: bool = _env("IOT_ENABLED", "false").lower() == "true"
    IOT_TYPE: str = _env("IOT_TYPE", "serial")  # "serial", "http", or "mqtt"
    IOT_SERIAL_PORT: str = _env("IOT_SERIAL_PORT", "COM3")
    IOT_SERIAL_BAUD: int = 9600
    IOT_SERIAL_TIMEOUT_SECONDS: float = 1.0
    IOT_HTTP_TIMEOUT_SECONDS: float = 1.5
    IOT_HTTP_URL: str = _env("IOT_HTTP_URL", "http://192.168.1.50")

cfg = Config()
