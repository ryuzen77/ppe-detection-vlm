"""Bootstrap aplikasi: FastAPI, middleware, router, frontend statis, dan server."""
import logging
import sys

if not __package__:
    # Dijalankan sebagai `python backend/app.py`: impor relatif di bawah akan gagal
    sys.exit("Jalankan server dari akar repo dengan: python -m backend")

from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import cfg
from .logging_setup import setup_logging
from .shutdown import install_shutdown_hook
from . import runtime
from .api import (
    routes_cameras,
    routes_ppe,
    routes_reports,
    routes_stream,
    routes_system,
    routes_vlm,
    websocket,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Model, kamera, audio, IoT, dan basis data dibuka di sini, bukan saat impor
    runtime.start()
    yield
    runtime.stop()

app = FastAPI(title="PPE Detection VLM Backend", version="1.0.0", lifespan=lifespan)

# Enable CORS for decoupled frontend.
# Kredensial hanya diizinkan kalau daftar origin eksplisit; browser menolak
# kombinasi wildcard + credentials.
_allow_wildcard_origin = "*" in cfg.CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.CORS_ORIGINS,
    allow_credentials=not _allow_wildcard_origin,
    allow_methods=["*"],
    allow_headers=["*"],
)

for _module in (routes_system, routes_vlm, routes_cameras, routes_ppe,
                routes_reports, routes_stream, websocket):
    app.include_router(_module.router)


class RevalidatingStaticFiles(StaticFiles):
    """StaticFiles yang mewajibkan browser memvalidasi ulang setiap berkas.

    Tanpa `Cache-Control`, browser memakai cache heuristik dan terus menjalankan
    JS versi lama setelah server diperbarui — padahal bentuk data API ikut
    berubah. `no-cache` tetap memakai cache, hanya saja dicek dulu lewat ETag
    (304 bila tidak berubah), jadi biayanya kecil.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


# UI baru (Svelte + TypeScript, T33): hasil build web/dist disajikan di /app/
# selama migrasi. Dipasang sebelum "/" karena mount "/" menangkap semua path.
web_dist_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
if web_dist_dir.exists():
    app.mount("/app", RevalidatingStaticFiles(directory=str(web_dist_dir), html=True), name="web")

# UI lama tetap di "/" sebagai cadangan sampai UI baru lengkap. Dipasang setelah
# semua router, karena mount "/" menangkap setiap path yang belum dicocokkan.
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", RevalidatingStaticFiles(directory=str(frontend_dir), html=True), name="frontend")

def run():
    """Menjalankan server. Dipanggil dari `python -m backend` (lihat `__main__.py`)."""
    # Logging disiapkan sebelum uvicorn supaya baris startup-nya ikut tercatat.
    # Hook berhenti dipasang sebelum server dibuat: uvicorn mengikat penangan
    # sinyalnya saat mulai, jadi pemasangan sesudahnya tidak berpengaruh.
    setup_logging(cfg)
    install_shutdown_hook()

    import contextlib
    import signal
    import uvicorn
    from uvicorn.server import HANDLED_SIGNALS

    class GracefulServer(uvicorn.Server):
        """Custom Uvicorn Server that suppresses Windows SIGINT/CancelledError traceback on Ctrl+C."""
        @contextlib.contextmanager
        def capture_signals(self):
            original_handlers = {}
            for sig in HANDLED_SIGNALS:
                try:
                    original_handlers[sig] = signal.signal(sig, self.handle_exit)
                except (ValueError, OSError):
                    pass
            try:
                yield
            finally:
                for sig, handler in original_handlers.items():
                    try:
                        signal.signal(sig, handler)
                    except (ValueError, OSError):
                        pass
                # Intentionally avoid re-raising SIGINT on Windows so event loop exits with zero error trace

    # Objek app dioper langsung, bukan lewat string "backend.app:app". Bentuk
    # string membuat uvicorn mengimpor modul ini lewat jalur impornya sendiri;
    # begitu jalur itu berbeda dari cara modul ini dimuat, terbentuk dua salinan
    # modul: dua VideoCaptureService, dua app, dan dua SHUTTING_DOWN. Penangan
    # sinyal lalu menyetel penanda pada salinan yang salah, sehingga endpoint
    # streaming tidak pernah berhenti dan server menggantung di "Waiting for
    # connections to close".
    # log_config=None: uvicorn tidak memasang handler sendiri, sehingga lognya
    # mengalir ke root logger dan ikut tercatat di DATA_DIR/logs (lihat logging_setup).
    config = uvicorn.Config(app, host=cfg.HOST, port=cfg.PORT, reload=False,
                            log_level=cfg.LOG_LEVEL.lower(), log_config=None)
    server = GracefulServer(config)
    try:
        server.run()
    except (KeyboardInterrupt, SystemExit):
        pass
    logger.info("Shutdown selesai secara bersih. Sampai jumpa!")
