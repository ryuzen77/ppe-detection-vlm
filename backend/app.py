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
    routes_zone,
    websocket,
)

logger = logging.getLogger(__name__)

def insecure_network_reason(host: str, token: str, allow_demo: bool) -> str | None:
    from .config import cfg
    from .messages import STARTUP_INSECURE_LAN, INSECURE_DEMO_WARNING
    if host not in cfg.LOCALHOST_IPS and not token:
        if not allow_demo:
            return STARTUP_INSECURE_LAN.format(host=host)
        else:
            logger.warning(INSECURE_DEMO_WARNING)
    return None

class PayloadTooLargeError(Exception):
    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    reason = insecure_network_reason(cfg.HOST, cfg.ADMIN_TOKEN, cfg.ALLOW_INSECURE_DEMO)
    if reason:
        raise RuntimeError(reason)
            
    # Model, kamera, audio, IoT, dan basis data dibuka di sini, bukan saat impor
    runtime.start()
    base = f"http://localhost:{cfg.PORT}"
    if web_dist_dir.exists():
        logger.info("Dashboard: %s/", base)
    yield
    runtime.stop()

app = FastAPI(title="DEPRO - Digital Safety Protection API", version="1.0.0", lifespan=lifespan)

# Enable CORS for decoupled frontend.
# Kredensial hanya diizinkan kalau daftar origin eksplisit; browser menolak
# kombinasi wildcard + credentials.
_allow_wildcard_origin = "*" in cfg.CORS_ORIGINS

class LimitPayloadSizeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        from .messages import PAYLOAD_TOO_LARGE
        
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
            
        content_length = None
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    content_length = int(value)
                except ValueError:
                    pass
                break
                
        if content_length is not None and content_length > cfg.MAX_PAYLOAD_BYTES:
            await self._send_413(send, PAYLOAD_TOO_LARGE)
            return
            
        received_bytes = 0
        async def custom_receive():
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > cfg.MAX_PAYLOAD_BYTES:
                    raise PayloadTooLargeError(PAYLOAD_TOO_LARGE)
            return message
            
        try:
            return await self.app(scope, custom_receive, send)
        except PayloadTooLargeError as e:
            await self._send_413(send, str(e))
            return
            
    async def _send_413(self, send, detail):
        import json
        body = json.dumps({"detail": detail}).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("utf-8"))],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })

app.add_middleware(LimitPayloadSizeMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.CORS_ORIGINS,
    allow_credentials=not _allow_wildcard_origin,
    allow_methods=["*"],
    allow_headers=["*"],
)

for _module in (routes_system, routes_vlm, routes_cameras, routes_ppe,
                routes_reports, routes_stream, routes_zone, websocket):
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
# halaman utama di "/"; Dipasang setelah semua router, karena mount "/" menangkap semua path sisa.
web_dist_dir = Path(__file__).resolve().parent.parent / "web" / "dist"


if web_dist_dir.exists():
    app.mount("/", RevalidatingStaticFiles(directory=str(web_dist_dir), html=True), name="web")

def run():
    """Menjalankan server. Dipanggil dari `python -m backend` (lihat `__main__.py`)."""
    reason = insecure_network_reason(cfg.HOST, cfg.ADMIN_TOKEN, cfg.ALLOW_INSECURE_DEMO)
    if reason:
        import sys
        print(reason, file=sys.stderr)
        sys.exit(1)

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
                            log_level=cfg.LOG_LEVEL.lower(), log_config=None,
                            timeout_graceful_shutdown=cfg.SHUTDOWN_TIMEOUT_SECONDS)
    server = GracefulServer(config)
    try:
        server.run()
    except (KeyboardInterrupt, SystemExit):
        pass
    logger.info("Shutdown selesai secara bersih. Sampai jumpa!")
