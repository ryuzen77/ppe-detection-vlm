@echo off
title DEPRO - Digital Safety Protection
echo ========================================================
echo  DEPRO - Digital Safety Protection
echo  Backend: FastAPI + YOLO26s-Pose + VLM (Server-Side)
echo  Frontend: Modern Real-time Dashboard (WebSocket)
echo ========================================================
echo.

rem Environment Python 3.12 yang dibangun dari backend\requirements-dev.lock.
rem Lokasi bisa diganti lewat variabel SAFEGUARD_VENV.
if not defined SAFEGUARD_VENV set "SAFEGUARD_VENV=%USERPROFILE%\.venvs\apd_py312"
set "PYEXE=%SAFEGUARD_VENV%\Scripts\python.exe"

if not exist "%PYEXE%" (
    echo [GALAT] Environment Python tidak ditemukan: %SAFEGUARD_VENV%
    echo Buat sekali dengan perintah berikut dari akar repo:
    echo   uv venv --python 3.12 "%SAFEGUARD_VENV%"
    echo   uv pip sync --python "%PYEXE%" --torch-backend cu132 backend\requirements-dev.lock
    pause
    exit /b 1
)

echo Menjalankan backend server pada http://localhost:8000...
cd /d "%~dp0"
"%PYEXE%" -m backend
pause
