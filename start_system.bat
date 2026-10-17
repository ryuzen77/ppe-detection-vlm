@echo off
title DEPRO - Digital Safety Protection
echo ========================================================
echo  DEPRO - Digital Safety Protection
echo  Backend: FastAPI + YOLO26s-Pose + VLM (Server-Side)
echo  Frontend: Modern Real-time Dashboard (WebSocket)
echo ========================================================
echo.

rem Environment Python 3.12 (docs\INSTALASI.md bagian 1). Urutan pencarian:
rem   1. SAFEGUARD_VENV bila diisi (folder venv atau env conda)
rem   2. env conda DEPRO_CONDA_ENV (bawaan "apd_detection") yang sedang aktif
rem   3. env conda itu di lokasi instal Miniconda/Anaconda yang umum
rem   4. venv lama %USERPROFILE%\.venvs\apd_py312
rem Autostart tidak menjalankan "conda activate", jadi langkah 3 yang biasanya terpakai.
if not defined DEPRO_CONDA_ENV set "DEPRO_CONDA_ENV=apd_detection"
set "PYEXE="

if defined SAFEGUARD_VENV (
    call :try_env "%SAFEGUARD_VENV%"
    if not defined PYEXE (
        echo [GALAT] SAFEGUARD_VENV tidak berisi Python 3.12: %SAFEGUARD_VENV%
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
if not defined PYEXE call :try_env "%USERPROFILE%\.venvs\apd_py312"

if not defined PYEXE (
    echo [GALAT] Environment Python "%DEPRO_CONDA_ENV%" tidak ditemukan.
    echo Buat sekali dari akar repo, di Anaconda Prompt:
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

rem Env conda menaruh python.exe di akar env; venv di Scripts\. Env yang bukan
rem Python 3.12 (mis. env lama yang belum dibuat ulang) dilewati.
:try_env
set "CANDIDATE="
if exist "%~1\python.exe" set "CANDIDATE=%~1\python.exe"
if not defined CANDIDATE if exist "%~1\Scripts\python.exe" set "CANDIDATE=%~1\Scripts\python.exe"
if not defined CANDIDATE exit /b
"%CANDIDATE%" -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Dilewati, bukan Python 3.12: %CANDIDATE%
    exit /b
)
set "PYEXE=%CANDIDATE%"
exit /b
