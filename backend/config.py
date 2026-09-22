import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

class Config:
    # Server Settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "*").split(",")
        if origin.strip()
    ]

    # Camera Settings (Webcam / USB Camera default: 0)
    CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", "0"))
    FRAME_WIDTH: int = int(os.getenv("FRAME_WIDTH", "1280"))
    FRAME_HEIGHT: int = int(os.getenv("FRAME_HEIGHT", "720"))
    FPS: int = int(os.getenv("FPS", "30"))

    # Model Settings (Small version for speed & accuracy)
    # Menggunakan yolo26s-pose.pt (YOLO26 Small Pose - Versi Terbaru)
    YOLO_MODEL_PATH: str = os.getenv("YOLO_MODEL_PATH", "yolo26s-pose.pt")
    YOLO_CONF: float = 0.60
    YOLO_IOU: float = 0.45
    TRACKER_TYPE: str = "bytetrack.yaml"


    # Virtual Inspection Corridor (Membatasi 1 Orang di Tengah)
    # Area aktif lorong inspeksi (rasio dari lebar frame)
    ENABLE_CORRIDOR_FILTER: bool = True
    CORRIDOR_LEFT_RATIO: float = 0.28   # Batas kiri lorong (~358px pada 1280px)
    CORRIDOR_RIGHT_RATIO: float = 0.72  # Batas kanan lorong (~922px pada 1280px)

    # Full Body Filter Rules (Toleransi Adaptif Tinggi Badan Pekerja)
    # Margin fleksibel pada tepi frame (orang tinggi vs orang pendek)
    BORDER_MARGIN_TOP_PX: int = 15
    BORDER_MARGIN_BOTTOM_PX: int = 15
    # Rentang tinggi orang relatif terhadap frame (35% s/d 96%)
    MIN_PERSON_HEIGHT_RATIO: float = 0.35
    MAX_PERSON_HEIGHT_RATIO: float = 0.96
    # Ambang kepercayaan deteksi keypoint pose tubuh (mata, bahu, lutut, kaki)
    KEYPOINT_CONF_THRESHOLD: float = 0.35

    # Gemini VLM & Hybrid Engine Settings (Server-side only)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_TIMEOUT_SECONDS: float = 2.0       # Timeout ketat agar antrean tidak macet
    USE_MOCK_VLM_IF_NO_KEY: bool = True
    ENABLE_LOCAL_FAST_PASS: bool = True       # Tier 1 Local Engine di GPU RTX 4060 (~15ms)
    VLM_IMAGE_MAX_SIZE: int = 640            # Maksimum resolusi crop VLM (~35KB)
    VLM_JPEG_QUALITY: int = 75               # Kompresi JPEG hemat kuota & cepat upload
    FREE_TIER_MIN_INTERVAL_SECONDS: float = 4.0 # Jeda minimum antar panggilan API (Anti-Spam Free Tier 15 RPM)

    # Anti-Spam & Fast-Queue Settings
    # 2 frame berturut-turut cukup untuk memastikan subjek stabil (~66ms pada 30 FPS)
    STABLE_FRAMES_REQUIRED: int = 2
    # Cooldown in seconds before the same track ID can be re-evaluated
    TRACK_COOLDOWN_SECONDS: int = 300
    # Audio warning "Silakan mundur" debounce in seconds per person
    AUDIO_STEP_BACK_DEBOUNCE_SECONDS: float = 3.5
    # Stale track purge timeout in seconds
    TRACK_TIMEOUT_SECONDS: float = float(os.getenv("TRACK_TIMEOUT_SECONDS", "15.0"))
    # Standby reset delay when corridor is empty
    STANDBY_RESET_DELAY_SECONDS: float = float(os.getenv("STANDBY_RESET_DELAY_SECONDS", "4.0"))
    # Maximum history records kept in memory
    MAX_HISTORY_RECORDS: int = int(os.getenv("MAX_HISTORY_RECORDS", "30"))

    # Local Fast-Pass Vision Thresholds (HSV & Area Ratios)
    HSV_ORANGE_LOWER: tuple[int, int, int] = (5, 80, 80)
    HSV_ORANGE_UPPER: tuple[int, int, int] = (22, 255, 255)
    HSV_YELLOW_LOWER: tuple[int, int, int] = (22, 70, 80)
    HSV_YELLOW_UPPER: tuple[int, int, int] = (42, 255, 255)
    HSV_SILVER_LOWER: tuple[int, int, int] = (0, 0, 210)
    HSV_SILVER_UPPER: tuple[int, int, int] = (180, 60, 255)
    HSV_SKIN_LOWER: tuple[int, int, int] = (0, 30, 60)
    HSV_SKIN_UPPER: tuple[int, int, int] = (25, 170, 255)
    HI_VIS_MIN_RATIO: float = 0.06
    SKIN_MAX_RATIO: float = 0.18

    # Audio Settings
    AUDIO_DIR: Path = BASE_DIR / "audio"
    AUDIO_VOLUME: float = 1.0

    # IoT / Hardware Output (Ready for Stage 2)
    IOT_ENABLED: bool = os.getenv("IOT_ENABLED", "false").lower() == "true"
    IOT_TYPE: str = os.getenv("IOT_TYPE", "serial")  # "serial", "http", or "mqtt"
    IOT_SERIAL_PORT: str = os.getenv("IOT_SERIAL_PORT", "COM3")
    IOT_SERIAL_BAUD: int = 9600
    IOT_HTTP_URL: str = os.getenv("IOT_HTTP_URL", "http://192.168.1.50")

cfg = Config()
