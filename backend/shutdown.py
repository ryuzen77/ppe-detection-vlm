"""Penanda berhenti server yang dibagi oleh endpoint streaming dan WebSocket."""
import threading

# Disetel saat sinyal berhenti diterima. Endpoint streaming dan WebSocket
# memeriksanya supaya ikut berhenti; tanpa ini keduanya berputar selamanya dan
# uvicorn menggantung di "Waiting for connections to close" sampai dipaksa keluar.
SHUTTING_DOWN = threading.Event()


def install_shutdown_hook():
    """Menyisipkan penanda berhenti ke penangan sinyal uvicorn.

    Ditempelkan pada kelas Server, bukan hanya subkelas GracefulServer. Harus
    dipanggil sebelum server dibuat (lihat `app.run()`), karena uvicorn mengikat
    penangan sinyalnya saat mulai berjalan.
    """
    import uvicorn

    if getattr(uvicorn.Server, "_safeguard_hooked", False):
        return

    original = uvicorn.Server.handle_exit

    def handle_exit(self, sig, frame):
        SHUTTING_DOWN.set()
        original(self, sig, frame)

    uvicorn.Server.handle_exit = handle_exit
    uvicorn.Server._safeguard_hooked = True
