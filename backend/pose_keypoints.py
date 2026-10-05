"""Indeks titik pose COCO-17 keluaran YOLO pose — satu definisi untuk backend.

Setiap titik berbentuk [x, y, keyakinan]. Modul lama yang masih menulis indeks
sendiri (`detector.py`, `zone.py`) dipindah ke sini di T41.
"""
NOSE = 0
LEFT_EYE, RIGHT_EYE = 1, 2
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
LEFT_KNEE, RIGHT_KNEE = 13, 14
LEFT_ANKLE, RIGHT_ANKLE = 15, 16
CONFIDENCE = 2   # posisi nilai keyakinan di dalam satu titik
