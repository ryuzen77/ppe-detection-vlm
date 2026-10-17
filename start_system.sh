#!/usr/bin/env sh
# Peluncur DEPRO (Digital Safety Protection) untuk Linux/macOS (padanan start_system.bat).
# Environment Python 3.12 (docs/INSTALASI.md bagian 1). Urutan pencarian:
#   1. SAFEGUARD_VENV bila diisi (jalur env conda di lokasi tidak umum; mis. systemd)
#   2. env conda DEPRO_CONDA_ENV (bawaan "ppe_detection") yang sedang aktif
#   3. env conda itu di lokasi instal Miniconda/Anaconda yang umum
# Hanya env conda; venv lama (~/.venvs) sengaja tidak dicari supaya tidak bentrok.
# Konfigurasi dibaca dari backend/.env.
set -eu

DEPRO_CONDA_ENV="${DEPRO_CONDA_ENV:-ppe_detection}"

if [ -n "${SAFEGUARD_VENV:-}" ]; then
    CANDIDATES="$SAFEGUARD_VENV"
else
    CANDIDATES=""
    if [ "${CONDA_DEFAULT_ENV:-}" = "$DEPRO_CONDA_ENV" ] && [ -n "${CONDA_PREFIX:-}" ]; then
        CANDIDATES="$CONDA_PREFIX"
    fi
    for base in "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/miniforge3" /opt/conda /opt/miniconda3; do
        CANDIDATES="$CANDIDATES
$base/envs/$DEPRO_CONDA_ENV"
    done
fi

PYEXE=""
# Satu kandidat per baris (jalur boleh berspasi)
while IFS= read -r env_dir; do
    [ -n "$env_dir" ] && [ -x "$env_dir/bin/python" ] || continue
    # Env yang bukan Python 3.12 atau belum berisi paket (uv pip sync belum selesai) dilewati
    if "$env_dir/bin/python" -c "import sys, importlib.util as u; sys.exit(sys.version_info[:2] != (3, 12) or not all(u.find_spec(m) for m in ('torch', 'fastapi')))" >/dev/null 2>&1; then
        PYEXE="$env_dir/bin/python"
        break
    fi
    echo "[INFO] Dilewati, bukan Python 3.12 atau paket belum terpasang: $env_dir/bin/python" >&2
done <<EOF
$CANDIDATES
EOF

if [ -z "$PYEXE" ]; then
    echo "[GALAT] Env conda \"$DEPRO_CONDA_ENV\" tidak ditemukan atau paketnya belum lengkap." >&2
    echo "Dari akar repo (lewati baris pertama bila env sudah ada):" >&2
    echo "  conda env create -f environment.yml" >&2
    echo "  conda activate $DEPRO_CONDA_ENV" >&2
    echo "  uv pip sync --torch-backend cu132 backend/requirements.lock" >&2
    echo "Conda di lokasi lain: isi SAFEGUARD_VENV dengan jalur env-nya (conda env list)." >&2
    exit 1
fi

cd "$(dirname "$0")"
echo "Python: $PYEXE"
echo "Menjalankan DEPRO pada http://localhost:${PORT:-8000} ..."
# exec: sinyal (Ctrl+C, SIGTERM dari systemd) langsung sampai ke server
exec "$PYEXE" -m backend
