#!/usr/bin/env sh
# Peluncur DEPRO (Digital Safety Protection) untuk Linux/macOS (padanan start_system.bat).
# Environment Python 3.12 (docs/INSTALASI.md bagian 1). Urutan pencarian:
#   1. SAFEGUARD_VENV bila diisi (folder venv atau env conda; mis. systemd)
#   2. env conda DEPRO_CONDA_ENV (bawaan "apd_detection") yang sedang aktif
#   3. env conda itu di lokasi instal Miniconda/Anaconda yang umum
#   4. venv lama ~/.venvs/apd_py312
# Konfigurasi dibaca dari backend/.env.
set -eu

DEPRO_CONDA_ENV="${DEPRO_CONDA_ENV:-apd_detection}"

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
    CANDIDATES="$CANDIDATES
$HOME/.venvs/apd_py312"
fi

PYEXE=""
# Satu kandidat per baris (jalur boleh berspasi)
while IFS= read -r env_dir; do
    [ -n "$env_dir" ] && [ -x "$env_dir/bin/python" ] || continue
    # Env yang bukan Python 3.12 (mis. env lama yang belum dibuat ulang) dilewati
    if "$env_dir/bin/python" -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))" >/dev/null 2>&1; then
        PYEXE="$env_dir/bin/python"
        break
    fi
    echo "[INFO] Dilewati, bukan Python 3.12: $env_dir/bin/python" >&2
done <<EOF
$CANDIDATES
EOF

if [ -z "$PYEXE" ]; then
    echo "[GALAT] Environment Python tidak ditemukan (SAFEGUARD_VENV / env conda \"$DEPRO_CONDA_ENV\")." >&2
    echo "Buat sekali dari akar repo:" >&2
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
