@echo off
title SAFEGUARD AI - PPE Compliance Real-time System
echo ========================================================
echo  SAFEGUARD AI - PPE Detection Real-time System
echo  Backend: FastAPI + YOLOv8s-Pose + Gemini VLM (Server-Side)
echo  Frontend: Modern Real-time Dashboard (WebSocket)
echo ========================================================
echo.
echo Mengaktifkan conda environment apd_detection...
call conda activate apd_detection

echo Menjalankan backend server pada http://localhost:8000...
cd /d "%~dp0"
python -m backend
pause
