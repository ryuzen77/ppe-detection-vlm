"""Enumerasi, probing, dan pemilihan mode kamera.

Sistem harus bisa dijalankan dengan webcam bawaan laptop maupun kamera USB, dan
setiap perangkat punya batas yang berbeda. Memaksa satu resolusi untuk semua
kamera menghasilkan hasil yang buruk: webcam laptop pada mesin pengembangan
hanya mampu 9,9 FPS di 1280x720 (format YUY2 tak terkompresi) padahal sanggup
29,7 FPS di 848x480 dengan rasio 16:9 yang sama.

Karena itu mode tidak ditebak, melainkan diukur: setiap kandidat resolusi dibuka
lalu laju frame sebenarnya dihitung. Nilai `CAP_PROP_FPS` yang dilaporkan driver
tidak dipercaya karena sering berbeda jauh dari kenyataan.
"""

import logging
import json
import sys
import threading
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

import cv2

from .config import cfg

logger = logging.getLogger(__name__)

# Backend OpenCV per OS. Backend bawaan kerap lebih lambat membuka perangkat atau
# salah memilih API (mis. MSMF di Windows), jadi dipilih eksplisit; bila gagal,
# `open_capture` jatuh ke backend bawaan.
if sys.platform == "win32":
    CAPTURE_BACKEND, CAPTURE_BACKEND_NAME = cv2.CAP_DSHOW, "DirectShow"
elif sys.platform.startswith("linux"):
    CAPTURE_BACKEND, CAPTURE_BACKEND_NAME = cv2.CAP_V4L2, "V4L2"
elif sys.platform == "darwin":
    CAPTURE_BACKEND, CAPTURE_BACKEND_NAME = cv2.CAP_AVFOUNDATION, "AVFoundation"
else:
    CAPTURE_BACKEND, CAPTURE_BACKEND_NAME = cv2.CAP_ANY, "bawaan"

# Direktori sysfs perangkat video Linux (dapat diganti untuk pengujian)
LINUX_V4L_SYSFS = Path("/sys/class/video4linux")


def open_capture(index: int) -> cv2.VideoCapture:
    """Membuka kamera dengan backend OS ini; jatuh ke backend bawaan OpenCV bila gagal."""
    cap = cv2.VideoCapture(index, CAPTURE_BACKEND)
    if cap.isOpened() or CAPTURE_BACKEND == cv2.CAP_ANY:
        return cap
    cap.release()
    logger.warning(f"{CAPTURE_BACKEND_NAME} gagal untuk index {index}, mencoba backend bawaan...")
    return cv2.VideoCapture(index)


# Pilihan kamera operator disimpan supaya tidak perlu dipilih ulang setiap
# server dijalankan — merepotkan saat gladi resik menjelang demo.
STATE_PATH = cfg.CAMERA_STATE_PATH

# Daftar PERMINTAAN resolusi, bukan hasil. Driver DirectShow kerap mengembalikan
# resolusi terdekat yang didukung, jadi hasil aktual selalu dibaca balik.
#
# Angka yang diminta penting, bukan sekadar hasilnya: pada webcam mesin pengembangan,
# meminta 848x480 menghasilkan 19,9 FPS sedangkan meminta 800x600 atau 854x480
# menghasilkan 29,7 FPS — padahal ketiganya sama-sama menghasilkan frame 848x480.
# Driver memilih media type yang berbeda tergantung angka permintaannya. Karena itu
# permintaan yang menghasilkan pengukuran terbaik disimpan dan diulang persis.
CANDIDATE_RESOLUTIONS: list[tuple[int, int]] = [
    (1920, 1080),
    (1280, 720),
    (960, 540),
    (854, 480),
    (800, 600),
    (640, 480),
    (640, 360),
]

# MJPG sering membuka laju frame tinggi pada resolusi besar untuk kamera USB.
# Sebagian driver menolaknya dan tetap memakai format bawaan; itu terdeteksi
# saat fourcc aktual dibaca kembali.
FOURCC_MJPG = cv2.VideoWriter_fourcc(*"MJPG")


def _fourcc_to_text(value: int) -> str:
    """Mengubah kode fourcc menjadi teks, atau string kosong bila tidak terbaca.

    Sebagian driver DirectShow mengembalikan nilai yang bukan fourcc ASCII sama
    sekali (potongan GUID subtype), yang kalau dipaksa menjadi karakter akan
    tampil sebagai sampah di UI. Lebih baik kosong daripada menyesatkan.
    """
    try:
        text = "".join(chr((int(value) >> (8 * i)) & 0xFF) for i in range(4))
    except Exception:
        return ""
    if all(ch.isalnum() or ch == " " for ch in text):
        return text.strip()
    return ""


@dataclass
class CameraMode:
    width: int          # Hasil aktual dari kamera
    height: int
    fps: float          # Laju frame terukur, bukan yang dilaporkan driver
    fourcc: str
    req_width: int = 0  # Permintaan yang menghasilkan pengukuran ini
    req_height: int = 0

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 0.0

    def label(self) -> str:
        return f"{self.width}x{self.height} @{self.fps:.0f} FPS"


def list_device_names() -> list[str]:
    """Nama perangkat, terurut sesuai indeks yang dipakai OpenCV (daftar[i] = kamera i).

    Nama asli diutamakan karena indeks saja menyesatkan dan tidak stabil — pada
    mesin pengembangan indeks 1 adalah "OBS Virtual Camera", bukan kamera fisik
    kedua. Bila nama tidak bisa dibaca, daftar kosong dan pemanggil memakai label
    generik "Kamera N".
    """
    try:
        if sys.platform == "win32":
            # pygrabber khusus Windows dan bukan dependensi keras
            import comtypes
            from pygrabber.dshow_graph import FilterGraph

            # COM wajib diinisialisasi per thread. comtypes hanya melakukannya di
            # thread yang pertama kali mengimpornya, sehingga pemanggil dari
            # thread lain (pembaca kamera, pemantau, API) gagal acak dengan
            # "CoInitialize has not been called" (terjadi nyata 24-09). Aman
            # dipanggil berulang pada thread yang sama.
            comtypes.CoInitialize()
            return list(FilterGraph().get_input_devices())
        if sys.platform.startswith("linux"):
            return linux_device_names()
        return []
    except Exception as e:
        logger.warning(f"Nama perangkat tidak tersedia ({e}); memakai label generik.")
        return []


def linux_device_names(sysfs: Optional[Path] = None) -> list[str]:
    """Nama kamera V4L2 dari sysfs; posisi ke-N = /dev/videoN = indeks OpenCV N.

    Satu kamera USB di Linux biasanya punya dua node: node video (atribut
    `index` 0) dan node metadata. Node selain yang utama diberi label berbeda
    supaya pencarian ulang berdasarkan nama (`resolve_saved_index`) tidak
    tertukar ke node yang tidak bisa merekam. Nomor yang kosong diisi label
    generik agar posisi tetap sama dengan indeks.
    """
    root = sysfs or LINUX_V4L_SYSFS
    if not root.is_dir():
        return []
    nodes = {}
    for d in root.iterdir():
        suffix = d.name[len("video"):]
        if not d.name.startswith("video") or not suffix.isdigit():
            continue
        n = int(suffix)
        name_file = d / "name"
        name = name_file.read_text(encoding="utf-8", errors="replace").strip() if name_file.exists() else ""
        index_file = d / "index"
        node_index = index_file.read_text().strip() if index_file.exists() else "0"
        name = name or f"Kamera {n}"
        nodes[n] = name if node_index in ("", "0") else f"{name} (node {n})"
    if not nodes:
        return []
    return [nodes.get(n, f"Kamera {n}") for n in range(max(nodes) + 1)]


def _keep_fastest(found: dict, mode: CameraMode):
    """Menyimpan mode ke katalog, mempertahankan yang tercepat bila hasilnya kembar.

    Dua permintaan berbeda bisa menghasilkan resolusi aktual yang sama dengan laju
    frame yang jauh berbeda, jadi yang lebih lambat tidak boleh menimpa yang cepat.
    """
    key = (mode.width, mode.height, mode.fourcc)
    existing = found.get(key)
    if existing is None or mode.fps > existing.fps:
        found[key] = mode


def probe_modes(index: int, measure_seconds: float = 0.8) -> list[CameraMode]:
    """Mengukur mode yang benar-benar didukung sebuah kamera.

    Kamera dibuka SEKALI lalu resolusinya diganti pada handle yang sama. Membuka
    ulang untuk tiap kandidat berarti menanggung waktu settle berkali-kali, dan
    hasilnya pun salah: kamera USB penguji melaporkan 1 FPS pada detik pertama
    setelah dibuka dan baru mencapai 26 FPS di detik keempat.

    Mengembalikan daftar kosong jika perangkat tidak bisa dibuka, termasuk ketika
    sedang dipakai proses lain.
    """
    found: dict = {}

    cap = open_capture(index)
    if not cap.isOpened():
        cap.release()
        return []

    try:
        cap.set(cv2.CAP_PROP_FPS, 30)

        # Settle sekali di awal, sebelum kandidat mana pun diukur
        t0 = time.time()
        while time.time() - t0 < cfg.CAMERA_SETTLE_SECONDS:
            if not cap.read()[0]:
                time.sleep(0.05)

        for req_w, req_h in CANDIDATE_RESOLUTIONS:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, req_w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, req_h)

            # Renegosiasi mode butuh beberapa frame, jauh lebih singkat daripada
            # settle penuh karena perangkatnya sudah aktif.
            ok, frame = False, None
            for _ in range(5):
                ok, frame = cap.read()
            if not ok or frame is None:
                continue

            actual_h, actual_w = frame.shape[:2]

            t0 = time.time()
            frames = 0
            while time.time() - t0 < measure_seconds:
                if cap.read()[0]:
                    frames += 1
            elapsed = time.time() - t0
            fps = frames / elapsed if elapsed > 0 else 0.0

            _keep_fastest(found, CameraMode(
                width=actual_w,
                height=actual_h,
                fps=round(fps, 1),
                fourcc=_fourcc_to_text(cap.get(cv2.CAP_PROP_FOURCC)),
                req_width=req_w,
                req_height=req_h,
            ))
    finally:
        cap.release()

    return list(found.values())


def pick_best_mode(modes: list[CameraMode]) -> Optional[CameraMode]:
    """Memilih mode dengan prioritas kelancaran, lalu rasio, lalu resolusi.

    Rasio 16:9 adalah preferensi, BUKAN syarat mutlak. Sebuah kamera USB penguji
    hanya mampu 7 FPS di 1280x720 (16:9) tetapi 25 FPS di 640x480 (4:3);
    memperlakukan rasio sebagai syarat akan memilih yang 7 FPS dan membuat video
    tersendat parah. Frame 4:3 sendiri aman karena overlay canvas dashboard sudah
    menyesuaikan diri terhadap letterbox.
    """
    if not modes:
        return None

    def aspect_ok(m: CameraMode) -> bool:
        return abs(m.aspect - cfg.CAMERA_TARGET_ASPECT) <= cfg.CAMERA_ASPECT_TOLERANCE

    usable = [m for m in modes if m.height >= cfg.CAMERA_MIN_HEIGHT]

    # 1. Di antara mode yang sudah cukup lancar, baru utamakan rasio lalu resolusi
    smooth = [m for m in usable if m.fps >= cfg.CAMERA_TARGET_FPS]
    if smooth:
        return max(smooth, key=lambda m: (aspect_ok(m), m.height, m.fps))

    # 2. Tidak ada yang mencapai target: ambil yang tercepat, rasio dikesampingkan
    if usable:
        return max(usable, key=lambda m: (m.fps, aspect_ok(m), m.height))

    # 3. Semua di bawah resolusi minimum: tetap pilih yang tercepat daripada gagal
    return max(modes, key=lambda m: (m.fps, m.height))


def load_saved_selection() -> Optional[dict]:
    """Membaca pilihan kamera terakhir; None jika belum ada atau berkasnya rusak."""
    try:
        if STATE_PATH.exists():
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "index" in data:
                return data
    except Exception as e:
        logger.warning(f"Gagal membaca {STATE_PATH.name}: {e}")
    return None


def autostart_target() -> tuple[str, Optional[dict], Optional[int]]:
    """Kamera yang dibuka otomatis (T29): (nama, mode, petunjuk indeks untuk tampilan).

    `CAMERA_NAME` menang atas pilihan terakhir. Mode tersimpan hanya dipakai bila
    milik kamera yang sama.
    """
    saved = load_saved_selection() or {}
    name = cfg.CAMERA_NAME or saved.get("name", "")
    same = bool(name) and saved.get("name") == name
    return name, (saved.get("mode") if same else None), (saved.get("index") if same else None)


def save_selection(index: int, mode: Optional[dict], name: str = ""):
    """Menyimpan pilihan kamera. Kegagalan di sini tidak boleh menghentikan sistem.

    Nama ikut disimpan karena indeks tidak stabil: mencolokkan kamera USB
    menggeser perangkat lain (pada mesin penguji, OBS Virtual Camera berpindah
    dari indeks 1 ke 2), sehingga indeks saja bisa menunjuk perangkat yang salah.
    """
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(
            json.dumps({"index": int(index), "name": name, "mode": mode}, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"Gagal menyimpan {STATE_PATH.name}: {e}")


def resolve_saved_index(saved: dict) -> Optional[int]:
    """Menentukan indeks yang benar untuk pilihan tersimpan, mengikuti nama perangkat.

    Indeks tidak stabil: mencolokkan kamera USB menggeser perangkat lain (pada
    mesin penguji, OBS Virtual Camera berpindah dari indeks 1 ke 2). Karena itu
    nama yang menentukan, bukan angkanya.

    Mengembalikan None bila kamera tersimpan sudah tidak ada. Indeks lamanya
    sengaja TIDAK dipakai sebagai cadangan: mencabut kamera USB membuat indeks
    itu ditempati perangkat lain, sehingga memakainya berarti diam-diam membuka
    kamera yang salah. Pemanggil harus kembali ke kamera bawaan.
    """
    index = int(saved.get("index", 0))
    name = saved.get("name") or ""

    names = list_device_names()
    if not name or not names:
        return index

    if 0 <= index < len(names) and names[index] == name:
        return index

    if name in names:
        new_index = names.index(name)
        logger.info(f"'{name}' berpindah dari indeks {index} ke {new_index} "
                    f"(daftar perangkat berubah); mengikuti namanya.")
        return new_index

    logger.warning(f"Kamera tersimpan '{name}' sudah tidak terhubung; "
                   f"kembali ke kamera bawaan.")
    return None


class CameraManager:
    """Katalog kamera beserta mode terukurnya.

    Probing satu kamera butuh beberapa detik, jadi dijalankan di thread latar dan
    hasilnya di-cache. Endpoint HTTP mengembalikan katalog terakhir seketika,
    dengan penanda `scanning` selama pemindaian berjalan.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.devices: list[dict] = []
        self.scanning: bool = False
        self.last_scan_time: str = "-"
        self._thread: Optional[threading.Thread] = None

    def start_scan(self, skip_index: Optional[int] = None) -> bool:
        """Memulai pemindaian di latar. Mengembalikan False jika sudah berjalan."""
        with self.lock:
            if self.scanning:
                return False
            self.scanning = True

        self._thread = threading.Thread(
            target=self._scan_worker, args=(skip_index,), daemon=True, name="CameraScan"
        )
        self._thread.start()
        return True

    def _scan_worker(self, skip_index: Optional[int]):
        try:
            names = list_device_names()
            limit = len(names) if names else cfg.CAMERA_SCAN_MAX_INDEX
            results: list[dict] = []

            for idx in range(limit):
                name = names[idx] if idx < len(names) else f"Kamera {idx}"

                if skip_index is not None and idx == skip_index:
                    # Perangkat terkunci oleh aliran video yang sedang berjalan.
                    # Datanya diisi pemanggil dari service yang aktif.
                    results.append({
                        "index": idx,
                        "name": name,
                        "available": True,
                        "scanned": True,
                        "in_use": True,
                        "modes": [],
                        "selected_mode": None,
                    })
                    continue

                modes = probe_modes(idx)
                best = pick_best_mode(modes)
                results.append({
                    "index": idx,
                    "name": name,
                    "available": bool(modes),
                    "scanned": True,
                    "in_use": False,
                    "modes": [asdict(m) for m in modes],
                    "selected_mode": asdict(best) if best else None,
                })

            with self.lock:
                self.devices = results
                self.last_scan_time = time.strftime("%H:%M:%S")
        except Exception as e:
            logger.exception(f"Pemindaian gagal: {e}")
        finally:
            with self.lock:
                self.scanning = False

    def record_device_modes(self, index: int, name: str, modes: list, best):
        """Menyimpan hasil pengukuran kamera aktif ke katalog.

        Kamera yang sedang dipakai dilewati oleh pemindaian latar karena
        perangkatnya terkunci, jadi hasilnya dititipkan lewat jalur ini oleh
        thread pembaca yang memegang handle-nya.
        """
        entry = {
            "index": index,
            "name": name,
            "available": bool(modes),
            "scanned": True,
            "in_use": True,
            "modes": [asdict(m) for m in modes],
            "selected_mode": asdict(best) if best else None,
        }
        with self.lock:
            for i, d in enumerate(self.devices):
                if d["index"] == index:
                    self.devices[i] = entry
                    break
            else:
                self.devices.append(entry)
                self.devices.sort(key=lambda d: d["index"])
            self.last_scan_time = time.strftime("%H:%M:%S")

    def get_catalog(self) -> dict:
        with self.lock:
            return {
                "scanning": self.scanning,
                "last_scan_time": self.last_scan_time,
                "devices": [dict(d) for d in self.devices],
            }

    def get_device(self, index: int) -> Optional[dict]:
        with self.lock:
            for d in self.devices:
                if d["index"] == index:
                    return dict(d)
        return None


camera_mgr = CameraManager()
