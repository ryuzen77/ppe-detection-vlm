"""Indeks titik pose COCO-17 keluaran YOLO pose — satu definisi untuk backend.

Setiap titik berbentuk [x, y, keyakinan]. Sejak T41 detector, zone, frame_quality,
dan readiness memakai modul ini; tes penjaga menolak indeks yang ditulis ulang.
"""
NOSE = 0
LEFT_EYE, RIGHT_EYE = 1, 2
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
LEFT_KNEE, RIGHT_KNEE = 13, 14
LEFT_ANKLE, RIGHT_ANKLE = 15, 16
X, Y, CONFIDENCE = 0, 1, 2   # posisi nilai di dalam satu titik [x, y, keyakinan]
