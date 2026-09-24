#!/usr/bin/env sh
# Peluncur SAFEGUARD AI untuk Linux/macOS (padanan start_system.bat).
# Environment Python 3.12 dari backend/requirements-dev.lock; lokasinya bisa
# diganti lewat variabel SAFEGUARD_VENV. Konfigurasi dibaca dari backend/.env.
set -eu

SAFEGUARD_VENV="${SAFEGUARD_VENV:-$HOME/.venvs/apd_py312}"
PYEXE="$SAFEGUARD_VENV/bin/python"

if [ ! -x "$PYEXE" ]; then
    echo "[GALAT] Environment Python tidak ditemukan: $SAFEGUARD_VENV" >&2
    echo "Buat sekali dengan perintah berikut dari akar repo:" >&2
    echo "  uv venv --python 3.12 \"$SAFEGUARD_VENV\"" >&2
    echo "  uv pip sync --python \"$PYEXE\" --torch-backend cu132 backend/requirements-dev.lock" >&2
    exit 1
fi

cd "$(dirname "$0")"
echo "Menjalankan SAFEGUARD AI pada http://localhost:${PORT:-8000} ..."
# exec: sinyal (Ctrl+C, SIGTERM dari systemd) langsung sampai ke server
exec "$PYEXE" -m backend
