@echo off
title DEPRO - Digital Safety Protection
echo ========================================================
echo  DEPRO - Digital Safety Protection
echo  Backend: FastAPI + YOLO26s-Pose + VLM (Server-Side)
echo  Frontend: Modern Real-time Dashboard (WebSocket)
echo ========================================================
echo.

rem Environment Python 3.12 (docs\INSTALASI.md bagian 1). Urutan pencarian:
rem   1. SAFEGUARD_VENV bila diisi (jalur env conda di lokasi tidak umum)
rem   2. env conda DEPRO_CONDA_ENV (bawaan "ppe_detection") yang sedang aktif
rem   3. env conda itu di lokasi instal Miniconda/Anaconda yang umum
rem Hanya env conda; venv lama (~/.venvs) sengaja tidak dicari supaya tidak bentrok.
rem Autostart tidak menjalankan "conda activate", jadi langkah 3 yang biasanya terpakai.
if not defined DEPRO_CONDA_ENV set "DEPRO_CONDA_ENV=ppe_detection"
set "PYEXE="

if defined SAFEGUARD_VENV (
    call :try_env "%SAFEGUARD_VENV%"
    if not defined PYEXE (
        echo [GALAT] SAFEGUARD_VENV bukan Python 3.12 dengan paket terpasang: %SAFEGUARD_VENV%
        pause
        exit /b 1
    )
)
if not defined PYEXE if /i "%CONDA_DEFAULT_ENV%"=="%DEPRO_CONDA_ENV%" call :try_env "%CONDA_PREFIX%"
if not defined PYEXE call :try_env "%USERPROFILE%\miniconda3\envs\%DEPRO_CONDA_ENV%"
if not defined PYEXE call :try_env "%USERPROFILE%\anaconda3\envs\%DEPRO_CONDA_ENV%"
if not defined PYEXE call :try_env "%LOCALAPPDATA%\miniconda3\envs\%DEPRO_CONDA_ENV%"
if not defined PYEXE call :try_env "%ProgramData%\miniconda3\envs\%DEPRO_CONDA_ENV%"
if not defined PYEXE call :try_env "%ProgramData%\anaconda3\envs\%DEPRO_CONDA_ENV%"

if not defined PYEXE (
    echo [GALAT] Env conda "%DEPRO_CONDA_ENV%" tidak ditemukan atau paketnya belum lengkap.
    echo Dari akar repo, di Anaconda Prompt ^(lewati baris pertama bila env sudah ada^):
    echo   conda env create -f environment.yml
    echo   conda activate %DEPRO_CONDA_ENV%
    echo   uv pip sync --torch-backend cu132 backend\requirements.lock
    echo Miniconda di lokasi lain: isi SAFEGUARD_VENV dengan jalur env-nya ^(conda env list^).
    pause
    exit /b 1
)

echo Python: %PYEXE%
echo Menjalankan backend server pada http://localhost:8000...
echo Server dinyalakan ulang otomatis bila crash. Hentikan dengan Ctrl+C.
cd /d "%~dp0"
"%PYEXE%" -m backend.supervisor
pause
exit /b

rem Env conda menaruh python.exe di akar env (Scripts\ hanya jaga-jaga). Env yang bukan
rem Python 3.12 atau belum berisi paket (torch, fastapi) dilewati, mis. env yang
rem baru dibuat tetapi uv pip sync belum selesai.
:try_env
set "CANDIDATE="
if exist "%~1\python.exe" set "CANDIDATE=%~1\python.exe"
if not defined CANDIDATE if exist "%~1\Scripts\python.exe" set "CANDIDATE=%~1\Scripts\python.exe"
if not defined CANDIDATE exit /b
"%CANDIDATE%" -c "import sys, importlib.util as u; sys.exit(sys.version_info[:2] != (3, 12) or not all(u.find_spec(m) for m in ('torch', 'fastapi')))" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Dilewati, bukan Python 3.12 atau paket belum terpasang: %CANDIDATE%
    exit /b
)
set "PYEXE=%CANDIDATE%"
exit /b
