import os
from pathlib import Path
from dotenv import load_dotenv

from .vlm_providers import profiles as vlm_profiles

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


# Model bawaan & letak (lokal/cloud) tiap penyedia VLM ada di katalog profil (T39b).
# Penyedia yang berjalan di mesin sendiri: tanpa API key dan tanpa kuota.
LOCAL_VLM_PROVIDERS = tuple(name for name, p in vlm_profiles.PROFILES.items() if p.is_local)


def provider_api_key(provider: str) -> str:
    """API key penyedia dari variabel .env miliknya sendiri (mis. OPENAI_API_KEY), T28.

    Dibaca saat dipanggil, bukan sekali saat impor, supaya key yang baru ditulis di
    lingkungan proses (tes) ikut terbaca. Penyedia lokal / tanpa `key_env` = kosong.
    """
    profile = vlm_profiles.get_profile(provider)
    return _env(profile.key_env, "") if profile is not None and profile.key_env else ""


def _legacy_thinking(gemini_level: str) -> str:
    """GEMINI_THINKING_LEVEL lama -> VLM_THINKING umum ("minimal" = berpikir dimatikan)."""
    level = gemini_level.strip().lower()
    return "off" if level == "minimal" else level


def _resolve_data_dir(value: str) -> Path:
    """Jalur relatif dihitung dari akar repo, bukan dari direktori kerja terminal."""
    path = Path(value).expanduser() if value else REPO_ROOT / "data"
    return (path if path.is_absolute() else REPO_ROOT / path).resolve()


class Config:
    # Server Settings
    HOST: str = _env("HOST", "0.0.0.0")
    PORT: int = int(_env("PORT", "8000"))
    # Batas tunggu koneksi saat server berhenti. Tanpa batas, satu koneksi yang
    # di-reset klien di Windows (Python 3.12, asyncio proactor melewatkan
    # Server._detach) membuat shutdown menggantung selamanya dan Ctrl+C kedua
    # pun tidak menolong. Setelah batas ini koneksi yang tersisa diputus.
    SHUTDOWN_TIMEOUT_SECONDS: float = float(_env("SHUTDOWN_TIMEOUT_SECONDS", "5"))
    LOCALHOST_IPS: set[str] = {'127.0.0.1', '::1', 'localhost'}
    MAX_PAYLOAD_BYTES: int = int(_env("MAX_PAYLOAD_BYTES", str(1 * 1024 * 1024)))
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

    # Akun pengguna (T51) menggantikan ADMIN_TOKEN: login selalu wajib, akun pertama
    # dibuat dari mesin gerbang. ADMIN_TOKEN lama hanya dideteksi untuk peringatan
    # "tidak dipakai lagi"; nilainya tidak disimpan.
    LEGACY_ADMIN_TOKEN_SET: bool = bool(_env("ADMIN_TOKEN", ""))
    SESSION_HOURS: float = float(_env("SESSION_HOURS", "8"))
    LOGIN_MAX_FAILURES: int = 5
    LOGIN_LOCKOUT_SECONDS: float = 60.0
    # Kata sandi diingat manusia (keputusan pengguna 07-10: minimal 12)
    ACCOUNT_PASSWORD_MIN_LENGTH: int = 12
    ACCOUNT_PASSWORD_MAX_LENGTH: int = 128
    ACCOUNT_USERNAME_MIN_LENGTH: int = 3
    ACCOUNT_USERNAME_MAX_LENGTH: int = 32
    # scrypt (bawaan Python): ~16 MB & puluhan ms per hash; parameter ikut tersimpan di
    # hash, jadi bisa dinaikkan kelak tanpa merusak akun lama.
    PASSWORD_SCRYPT_N: int = 2 ** 14
    PASSWORD_SCRYPT_R: int = 8
    PASSWORD_SCRYPT_P: int = 1

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
    # Kamera yang dibuka otomatis, DIPILIH LEWAT NAMA (T29). Kosong = pilihan terakhir operator.
    # Indeks tidak pernah dipakai: kamera USB eksternal berpindah indeks, dan Windows bisa
    # butuh ±30 dtk memunculkannya — gerbang menunggu, bukan membuka kamera lain.
    CAMERA_NAME: str = _env("CAMERA_NAME", "")
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
    # Kesehatan gambar (T45). Tertutup = rata-rata kecerahan di luar rentang atau
    # nyaris seragam (simpangan baku kecil) pada gambar kecil skala abu-abu (0-255).
    CAMERA_HEALTH_SAMPLE_WIDTH: int = 64
    CAMERA_HEALTH_SAMPLE_HEIGHT: int = 36
    CAMERA_DARK_MEAN: float = float(_env("CAMERA_DARK_MEAN", "25"))
    CAMERA_BRIGHT_MEAN: float = float(_env("CAMERA_BRIGHT_MEAN", "235"))
    CAMERA_UNIFORM_STD: float = float(_env("CAMERA_UNIFORM_STD", "6"))
    # Buram/terhalang (T57): ketajaman (variansi Laplacian) & porsi tepi Canny pada
    # gambar abu-abu 320x180. Uji C920 13-10: jelas >= 368 / >= 0,08; tertutup <= 17 / ~0.
    # Ukur ulang di lokasi gerbang dengan tools/camera_probe.py bila ruangan jauh berbeda.
    CAMERA_DETAIL_WIDTH: int = 320
    CAMERA_DETAIL_HEIGHT: int = 180
    CAMERA_CANNY_LOW: int = 50
    CAMERA_CANNY_HIGH: int = 150
    CAMERA_MIN_SHARPNESS: float = float(_env("CAMERA_MIN_SHARPNESS", "80"))
    CAMERA_MIN_EDGE_RATIO: float = float(_env("CAMERA_MIN_EDGE_RATIO", "0.01"))
    # 1,5 dtk: uji fisik 06-10 — 3 dtk terasa terlalu lama bagi pengguna
    CAMERA_BLOCKED_SECONDS: float = float(_env("CAMERA_BLOCKED_SECONDS", "1.5"))
    # Membeku = cuplikan berjarak (tanpa dirata-rata, derau sensor terlihat) identik
    CAMERA_FROZEN_SAMPLE_STEP: int = 4
    CAMERA_FROZEN_SECONDS: float = float(_env("CAMERA_FROZEN_SECONDS", "3.0"))
    # Gambar harus sehat selama ini sebelum gangguan dianggap selesai
    CAMERA_HEALTHY_SECONDS: float = 1.0
    # Suara gangguan tidak diulang dalam selang ini, walau gangguan putus-sambung (T45b)
    CAMERA_FAULT_SOUND_COOLDOWN_SECONDS: float = 30.0
    # Selang log "masih menunggu kamera" selama kamera belum dicolok ulang (T45b)
    CAMERA_WAITING_LOG_SECONDS: float = 10.0
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
    # Geometri kepala untuk cek kepala terpotong (T41: dulu tertulis di detector.py).
    # Bahu tak terlihat -> diperkirakan sekian tinggi kotak dari atas kotak.
    POSE_SHOULDER_FALLBACK_RATIO: float = 0.20
    # Skala kepala (jarak hidung-bahu) minimal / bila hidung tak terlihat, relatif tinggi kotak
    POSE_HEAD_SCALE_MIN_RATIO: float = 0.12
    POSE_HEAD_SCALE_FALLBACK_RATIO: float = 0.15
    # Puncak helm diperkirakan sekian kali skala kepala di atas hidung; harus masih di dalam gambar
    POSE_HELMET_HEADROOM_FACTOR: float = 0.65
    # Tepi tambahan potongan orang untuk VLM (konteks helm & sepatu), relatif ukuran kotak
    CROP_MARGIN_Y_RATIO: float = 0.05
    CROP_MARGIN_X_RATIO: float = 0.08

    # Zona titik berdiri (T36d): pita posisi kaki relatif tinggi gambar (0 atas,
    # 1 bawah). Bawaan nonaktif; diaktifkan lewat kalibrasi/Pengaturan.
    ZONE_Y_MIN_DEFAULT: float = 0.70
    ZONE_Y_MAX_DEFAULT: float = 0.85
    # Toleransi atas-bawah saat kalibrasi dari orang yang berdiri di titik (±)
    ZONE_CALIBRATE_MARGIN: float = float(_env("ZONE_CALIBRATE_MARGIN", "0.06"))
    # Pita tersempit yang diterima, agar zona tidak mustahil dipenuhi
    ZONE_MIN_HEIGHT: float = 0.04
    # Lama posisi kaki terakhir yang jelas dipakai saat pergelangan kaki tertutup
    FOOT_MEMORY_SECONDS: float = float(_env("FOOT_MEMORY_SECONDS", "2.0"))

    # --- VLM, bebas penyedia (T23) ---
    # gemini, openai, openrouter, qwen, deepseek, ollama, vllm, openai-compatible.
    # Nama lama GEMINI_API_KEY / GEMINI_MODEL tetap dibaca agar .env lama tidak rusak.
    VLM_PROVIDER: str = _env("VLM_PROVIDER", "gemini").lower()
    # VLM_API_KEY (bila diisi) menang; bila kosong, key milik penyedia itu sendiri
    # (GEMINI_API_KEY, OPENAI_API_KEY, ..., lihat profil `key_env`, T28). Key satu
    # penyedia tidak pernah dikirim ke penyedia lain.
    VLM_API_KEY: str = _env("VLM_API_KEY", provider_api_key(VLM_PROVIDER))
    VLM_MODEL: str = _env(
        "VLM_MODEL",
        _env("GEMINI_MODEL", vlm_profiles.default_model("gemini")) if VLM_PROVIDER == "gemini"
        else vlm_profiles.default_model(VLM_PROVIDER),
    )
    # Kosong = alamat bawaan penyedia (lihat vlm_providers/openai_compatible.py)
    VLM_BASE_URL: str = _env("VLM_BASE_URL", "")
    # Minta jawaban JSON lewat response_format (OpenAI-compatible); matikan untuk
    # server yang tidak mengenalnya
    VLM_JSON_MODE: bool = _env("VLM_JSON_MODE", "true").lower() == "true"
    VLM_IS_LOCAL: bool = VLM_PROVIDER in LOCAL_VLM_PROVIDERS
    # Mode "berpikir" model, umum untuk semua penyedia (T39b): off / low / medium / high.
    # Diterjemahkan profil ke parameter penyedia; penyedia yang tidak bisa diatur
    # mengabaikannya. Nama lama GEMINI_THINKING_LEVEL tetap dibaca.
    VLM_THINKING: str = _env("VLM_THINKING", _legacy_thinking(_env("GEMINI_THINKING_LEVEL", "minimal"))).lower()
    # Suhu sampling VLM. Rendah = jawaban konsisten untuk foto yang sama
    # (penilaian APD bukan tugas kreatif). Berlaku untuk semua penyedia.
    VLM_TEMPERATURE: float = float(_env("VLM_TEMPERATURE", "0.1"))
    # Batas token jawaban Claude (wajib di Messages API). Model Claude terbaru
    # berpikir dulu dan pikirannya ikut dihitung, jadi dibuat longgar dari ukuran JSON APD.
    VLM_ANTHROPIC_MAX_TOKENS: int = int(_env("VLM_ANTHROPIC_MAX_TOKENS", "4096"))
    # Sisi gambar sintetis untuk tombol "Uji" penyedia di Pengaturan (T28)
    VLM_TEST_IMAGE_PX: int = 256

    # --- VLM cadangan (T27) ---
    # Dipakai OTOMATIS saat VLM utama gagal, di inspeksi yang sama. Bawaannya VLM
    # lokal lewat Ollama bila utama berada di cloud; "none" = tanpa cadangan.
    # Lokasi tanpa internet cukup menjadikan VLM lokal sebagai utama.
    VLM_BACKUP_PROVIDER: str = _env("VLM_BACKUP_PROVIDER", "none" if VLM_IS_LOCAL else "ollama").lower()
    VLM_BACKUP_MODEL: str = _env("VLM_BACKUP_MODEL", vlm_profiles.default_model(VLM_BACKUP_PROVIDER))
    VLM_BACKUP_BASE_URL: str = _env("VLM_BACKUP_BASE_URL", "")
    VLM_BACKUP_API_KEY: str = _env("VLM_BACKUP_API_KEY", provider_api_key(VLM_BACKUP_PROVIDER))

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
    # Penjaga model lokal (T38): model dianggap sehat bila porsi GPU >= ini;
    # diperiksa berkala dan setelah VLM lokal gagal, dimuat ulang bila kurang.
    LOCAL_MIN_GPU_RATIO: float = 0.99
    LOCAL_GPU_CHECK_SECONDS: float = float(_env("LOCAL_GPU_CHECK_SECONDS", "60"))
    # Lama menunggu jeda antar-inspeksi sebelum memuat ulang (jangan putus pekerja)
    LOCAL_GPU_REPAIR_WAIT_SECONDS: float = 30.0
    # Versi Ollama tempat model lokal divalidasi (06-10); berbeda = peringatan saat start (T29)
    OLLAMA_VALIDATED_VERSION: str = _env("OLLAMA_VALIDATED_VERSION", "0.34.4")
    STARTUP_CHECK_TIMEOUT_SECONDS: float = 2.0
    # Penjaga proses (T29): jeda nyala ulang setelah crash, berlipat bila crash beruntun
    SUPERVISOR_RESTART_DELAY_SECONDS: float = 5.0
    SUPERVISOR_MAX_DELAY_SECONDS: float = 60.0
    SUPERVISOR_STABLE_SECONDS: float = 60.0   # hidup selama ini = bukan crash beruntun
    SUPERVISOR_LOG_FILE: str = "supervisor.log"
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
    # Pekerja siap dipotret (T46): tubuh utuh, menghadap kamera, dan diam selama
    # ini. Uji nyata 28-09: tanpa syarat waktu, foto diambil saat masih melangkah.
    READY_HOLD_SECONDS: float = float(_env("READY_HOLD_SECONDS", "1.0"))
    # "Diam" = titik tengah / tinggi tubuh bergeser kurang dari ini (relatif tinggi
    # tubuh) terhadap awal jendela. Goyangan kotak YOLO orang berdiri ~1-2%.
    READY_MAX_DRIFT: float = float(_env("READY_MAX_DRIFT", "0.05"))
    # Kedua bahu harus terlihat (pekerja tidak menyamping)
    READY_REQUIRE_SHOULDERS: bool = _env("READY_REQUIRE_SHOULDERS", "true").lower() == "true"
    # Kandidat terakhir yang dinilai frame_quality; membatasi memori & waktu penilaian
    READY_MAX_CANDIDATES: int = 10
    # Audio warning "Silakan mundur" debounce in seconds per person
    AUDIO_STEP_BACK_DEBOUNCE_SECONDS: float = 6.0
    # Maximum times the step-back voice prompt plays for the same person
    AUDIO_STEP_BACK_MAX_REPEATS: int = 2
    # Jeda minimum suara hasil (lengkap / kurang item) dan suara "sedang menganalisa"
    AUDIO_RESULT_DEBOUNCE_SECONDS: float = 3.0
    AUDIO_ANALYZING_DEBOUNCE_SECONDS: float = 2.0
    # Jeda pengulangan pengumuman "sistem sedang gangguan, mohon tunggu"
    AUDIO_SYSTEM_WAIT_DEBOUNCE_SECONDS: float = 20.0
    # Selang cek antrean & channel pemutar suara (T36b)
    AUDIO_POLL_SECONDS: float = 0.05
    # Lama jalur inspeksi harus kosong sebelum sesi gerbang berakhir dan sistem
    # kembali ke tahap 1. Selama sesi berjalan keputusan terkunci; jeda ini juga
    # menyerap orang yang tertutup sesaat agar tidak dianggap sudah pergi.
    # 1,5 dtk sejak T36c (sebelumnya 3): jeda ini menahan antrean tiap pekerja,
    # sedangkan orang yang sama yang muncul lagi ditangani ingatan keputusan di bawah.
    STANDBY_RESET_DELAY_SECONDS: float = float(_env("STANDBY_RESET_DELAY_SECONDS", "1.5"))
    # Lama keputusan LOLOS per ID pelacak diingat setelah sesinya berakhir: orang
    # yang lolos lalu keluar jalur sesaat (ID sama) tidak diperiksa ulang. Keputusan
    # ditolak tidak diingat, jadi pekerja yang memperbaiki APD selalu diperiksa ulang (T36c).
    DECIDED_TRACK_MEMORY_SECONDS: float = float(_env("DECIDED_TRACK_MEMORY_SECONDS", "10"))
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
    # Akun pengguna (T51), terpisah dari audit.db supaya retensi/ekspor audit tidak menyentuhnya
    ACCOUNTS_DB_PATH: Path = DATA_DIR / "accounts.db"
    # Catatan hidup server: kapan terakhir hidup & apakah berhenti rapi (T37)
    UPTIME_STATE_PATH: Path = DATA_DIR / "uptime.json"
    UPTIME_HEARTBEAT_SECONDS: float = 30.0

    # Logging (T53): application log (konsol + berkas) & security log (JSONL) di
    # DATA_DIR/logs. Audit inspeksi tetap di SQLite (retensi T20), bukan di sini.
    LOG_LEVEL: str = _env("LOG_LEVEL", "INFO").upper()
    LOG_TO_FILE: bool = _env("LOG_TO_FILE", "true").lower() == "true"
    LOG_DIR: Path = DATA_DIR / "logs"
    LOG_FILE: str = "safeguard.log"
    SECURITY_LOG_FILE: str = "security.jsonl"
    # Tiap berkas dibatasi ukuran (berkas aktif + salinan) DAN umur salinan, supaya
    # disk tidak pernah penuh oleh log dan data pribadi (IP, nama akun) tidak disimpan selamanya.
    LOG_MAX_BYTES: int = int(_env("LOG_MAX_BYTES", str(5 * 1024 * 1024)))
    LOG_BACKUP_COUNT: int = int(_env("LOG_BACKUP_COUNT", "5"))
    LOG_RETENTION_DAYS: int = int(_env("LOG_RETENTION_DAYS", "30"))
    SECURITY_LOG_RETENTION_DAYS: int = int(_env("SECURITY_LOG_RETENTION_DAYS", "90"))
    # Penulisan log lewat antrean: jalur inspeksi tidak menunggu disk. Antrean penuh
    # = catatan dibuang & dihitung (lebih baik kehilangan log daripada gerbang macet).
    LOG_QUEUE_SIZE: int = 10_000
    # Pesan yang sama persis dicatat sekali per jendela ini, lalu "terulang N kali"
    LOG_REPEAT_WINDOW_SECONDS: float = float(_env("LOG_REPEAT_WINDOW_SECONDS", "60"))
    LOG_REPEAT_MAX_KEYS: int = 1_000
    # Log akses HTTP rutin (40% isi log, kebanyakan polling); galat server tetap tercatat
    LOG_ACCESS_LEVEL: str = _env("LOG_ACCESS_LEVEL", "WARNING").upper()
    # Penjaga disk (T53): sisa ruang DATA_DIR di bawah batas → log berkas dikurangi/dihentikan
    DISK_WARN_FREE_GB: float = float(_env("DISK_WARN_FREE_GB", "5"))
    DISK_CRITICAL_FREE_GB: float = float(_env("DISK_CRITICAL_FREE_GB", "1"))
    DISK_CHECK_SECONDS: float = float(_env("DISK_CHECK_SECONDS", "60"))

    # Laporan & arsip foto
    SNAPSHOT_JPEG_QUALITY: int = 80           # Mutu foto bukti (~30-50 KB per foto)
    DB_TIMEOUT_SECONDS: float = 10.0          # Tunggu kunci SQLite sebelum menyerah
    CSV_EXPORT_BATCH_ROWS: int = 500          # Baris per potongan ekspor CSV bertahap (T43)
    # Keputusan pengguna (27-09): baris audit tidak boleh hilang walau listrik
    # padam mendadak. Pragma ini berlaku per koneksi, jadi disetel di tiap koneksi.
    AUDIT_DB_SYNCHRONOUS: str = "FULL"

    # Retensi Data (T20)
    # Lama simpan foto wajah pekerja (hari) sebelum dihapus (hanya fotonya yang terhapus).
    RETENTION_PHOTO_DAYS: int = int(_env("RETENTION_PHOTO_DAYS", "30"))
    # Lama simpan baris audit (hari) sebelum dihapus total.
    RETENTION_AUDIT_DAYS: int = int(_env("RETENTION_AUDIT_DAYS", "365"))
    # Batas kapasitas total folder foto (GB). Foto tertua dihapus bila batas ini terlampaui.
    RETENTION_MAX_PHOTO_GB: float = float(_env("RETENTION_MAX_PHOTO_GB", "2.0"))
    # Interval pemeriksaan retensi di latar belakang (jam)
    RETENTION_INTERVAL_HOURS: int = int(_env("RETENTION_INTERVAL_HOURS", "24"))

    # Audio Settings. MP3 adalah aset rilis (dilacak git, dibangkitkan dari
    # katalog APD), bukan data lapangan, jadi tetap berada di direktori kode.
    AUDIO_DIR: Path = BASE_DIR / "audio"
    AUDIO_VOLUME: float = 1.0

    # IoT / Hardware Output (Ready for Stage 2)
    IOT_ENABLED: bool = _env("IOT_ENABLED", "false").lower() == "true"
    # "serial" (ESP32 lewat USB, T47) atau "usb_relay" (relay USB HID dcttech, T54).
    # HTTP/Wi-Fi tanpa tanda tangan dibuang di T47.
    IOT_TYPE: str = _env("IOT_TYPE", "serial")
    # Relay USB (T54): kanal (1-based) tiap lampu; serial kosong = papan USBRelay pertama.
    # Hanya dua lampu: kuning tidak ada, keadaan peringatan = semua lampu mati.
    IOT_RELAY_GREEN_CHANNEL: int = int(_env("IOT_RELAY_GREEN_CHANNEL", "1"))
    IOT_RELAY_RED_CHANNEL: int = int(_env("IOT_RELAY_RED_CHANNEL", "2"))
    IOT_RELAY_SERIAL: str = _env("IOT_RELAY_SERIAL", "")
    IOT_SERIAL_PORT: str = _env("IOT_SERIAL_PORT", "COM3")
    IOT_SERIAL_BAUD: int = 9600
    IOT_SERIAL_TIMEOUT_SECONDS: float = 1.0
    # Heartbeat lampu (T47): keadaan dikirim ulang tiap ini; firmware menyalakan
    # kuning berkedip bila 3 dtk tanpa perintah, jadi nilai ini harus jauh di bawahnya.
    IOT_HEARTBEAT_SECONDS: float = 1.0
    IOT_ACK_TIMEOUT_SECONDS: float = 3.0      # tanpa balasan "OK:" selama ini = terputus
    IOT_RECONNECT_SECONDS: float = 2.0        # jeda mencoba membuka ulang port
    IOT_RX_MAX_BYTES: int = 256               # sisa data tanpa baris baru yang disimpan

cfg = Config()
