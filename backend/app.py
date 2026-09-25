"""Bootstrap aplikasi: FastAPI, middleware, router, frontend statis, dan server."""
import logging
import sys

if not __package__:
    # Dijalankan sebagai `python backend/app.py`: impor relatif di bawah akan gagal
    sys.exit("Jalankan server dari akar repo dengan: python -m backend")

from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
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
    base = f"http://localhost:{cfg.PORT}"
    if web_dist_dir.exists():
        logger.info("Dashboard: %s/  |  tampilan lama (cadangan): %s/legacy/", base, base)
    yield
    runtime.stop()

app = FastAPI(title="DEPRO - Digital Safety Protection API", version="1.0.0", lifespan=lifespan)

# Enable CORS for decoupled frontend.
# Kredensial hanya diizinkan kalau daftar origin eksplisit; browser menolak
# kombinasi wildcard + credentials.
_allow_wildcard_origin = "*" in cfg.CORS_ORIGINS
from fastapi import Request
from fastapi.responses import JSONResponse

@app.middleware("http")
async def limit_payload_size(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > cfg.MAX_PAYLOAD_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Payload Too Large"})
    return await call_next(request)

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


# Frontend (T33). UI baru (Svelte + TypeScript, hasil build web/dist) menjadi
# halaman utama di "/"; UI lama tetap utuh di "/legacy/" sebagai cadangan.
# Dipasang setelah semua router, karena mount "/" menangkap semua path sisa.
web_dist_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"


# Alamat lama UI baru selama migrasi (/app/) tetap berfungsi
@app.get("/app", include_in_schema=False)
@app.get("/app/", include_in_schema=False)
async def _app_redirect():
    return RedirectResponse("/")


if frontend_dir.exists():
    # Tanpa garis miring, rujukan relatif UI lama (css/, js/) salah alamat
    @app.get("/legacy", include_in_schema=False)
    async def _legacy_redirect():
        return RedirectResponse("/legacy/")

    app.mount("/legacy", RevalidatingStaticFiles(directory=str(frontend_dir), html=True), name="frontend")

if web_dist_dir.exists():
    app.mount("/", RevalidatingStaticFiles(directory=str(web_dist_dir), html=True), name="web")
elif frontend_dir.exists():
    # web/dist belum dibangun: UI lama tetap tersedia di akar
    app.mount("/", RevalidatingStaticFiles(directory=str(frontend_dir), html=True), name="frontend-root")

def run():
    """Menjalankan server. Dipanggil dari `python -m backend` (lihat `__main__.py`)."""
    # Logging disiapkan sebelum uvicorn supaya baris startup-nya ikut tercatat.
    # Hook berhenti dipasang sebelum server dibuat: uvicorn mengikat penangan
    # sinyalnya saat mulai, jadi pemasangan sesudahnya tidak berpengaruh.
    if cfg.HOST not in ("127.0.0.1", "localhost", "::1") and not cfg.ADMIN_TOKEN:
        if not cfg.ALLOW_UNSECURE_DEMO:
            from .messages import STARTUP_INSECURE_LAN
            sys.exit(STARTUP_INSECURE_LAN.format(host=cfg.HOST))
        else:
            logger.warning("Menjalankan mode demo tidak aman di LAN karena ALLOW_UNSECURE_DEMO aktif.")

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
                            log_level=cfg.LOG_LEVEL.lower(), log_config=None,
                            timeout_graceful_shutdown=cfg.SHUTDOWN_TIMEOUT_SECONDS)
    server = GracefulServer(config)
    try:
        server.run()
    except (KeyboardInterrupt, SystemExit):
        pass
    logger.info("Shutdown selesai secara bersih. Sampai jumpa!")
