"""Penggambaran server-side di atas frame video: HUD inspeksi dan layar tunggu."""

import cv2
import numpy as np

from ..config import cfg
from .. import messages
from ..detector import detector
from ..notifier import notifier


def draw_synthetic_frame(width: int, height: int, message: str = messages.FRAME_NO_CAMERA) -> np.ndarray:
    """Pola uji saat tidak ada kamera, supaya aliran video tidak membeku."""
    w, h = width, height
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = (30, 30, 35)

    for y in range(0, h, 40):
        cv2.line(img, (0, y), (w, y), (40, 40, 45), 1)
    for x in range(0, w, 40):
        cv2.line(img, (x, 0), (x, h), (40, 40, 45), 1)

    # Teks ditengahkan dan diskalakan terhadap lebar frame agar terbaca wajar
    # pada rasio apa pun, termasuk kamera 4:3.
    scale_title = w / 1100.0
    scale_msg = w / 1500.0
    judul = messages.FRAME_TITLE
    (tw, th), _ = cv2.getTextSize(judul, cv2.FONT_HERSHEY_SIMPLEX, scale_title, 2)
    (mw, _), _ = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, scale_msg, 1)

    pad_x, pad_y = int(w * 0.04), int(h * 0.06)
    box_w = max(tw, mw) + pad_x * 2
    box_x = (w - box_w) // 2
    box_y = h // 2 - pad_y - th
    cv2.rectangle(img, (box_x, box_y), (box_x + box_w, box_y + pad_y * 2 + th), (0, 180, 255), 2)
    cv2.putText(
        img, judul, ((w - tw) // 2, box_y + pad_y + th // 2), cv2.FONT_HERSHEY_SIMPLEX, scale_title, (0, 180, 255), 2
    )
    cv2.putText(
        img,
        message,
        ((w - mw) // 2, box_y + pad_y * 2 + th + int(h * 0.06)),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale_msg,
        (150, 150, 150),
        1,
    )
    return img


def draw_hud(frame: np.ndarray, detections, fps: float) -> np.ndarray:
    # Koridor, bounding box, dan garis panduan sudah digambar oleh canvas
    # frontend (hud_overlay.js). Menggambarnya lagi di sini menghasilkan
    # overlay ganda dan membuat sakelar "Panduan Posisi" terasa rusak.
    if not cfg.ENABLE_SERVER_HUD:
        return frame

    out = frame.copy()
    if cfg.ENABLE_CORRIDOR_FILTER:
        _draw_corridor(out)
    _draw_border_guides(out)
    for det in detections:
        if getattr(det, "is_inside_corridor", True):
            _draw_subject(out, det)
        else:
            _draw_outsider(out, det)
    _draw_header(out, fps)
    return out


def _draw_corridor(out: np.ndarray) -> None:
    """Lorong inspeksi: sisi kiri-kanan digelapkan, batas lorong, dan judul di bawah."""
    h, w = out.shape[:2]
    cx1 = int(w * cfg.CORRIDOR_LEFT_RATIO)
    cx2 = int(w * cfg.CORRIDOR_RIGHT_RATIO)

    overlay = out.copy()
    cv2.rectangle(overlay, (0, 0), (cx1, h), (10, 10, 15), -1)
    cv2.rectangle(overlay, (cx2, 0), (w, h), (10, 10, 15), -1)
    cv2.addWeighted(overlay, 0.45, out, 0.55, 0, out)

    cv2.line(out, (cx1, 0), (cx1, h), (255, 200, 0), 2)
    cv2.line(out, (cx2, 0), (cx2, h), (255, 200, 0), 2)

    banner_text = messages.HUD_CORRIDOR_BANNER
    t_size = cv2.getTextSize(banner_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
    banner_x = cx1 + (cx2 - cx1 - t_size[0]) // 2
    cv2.putText(out, banner_text, (banner_x, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 0), 2)


def _draw_border_guides(out: np.ndarray) -> None:
    """Garis batas atas & bawah: tubuh harus utuh di antara keduanya."""
    h, w = out.shape[:2]
    margin_top = max(int(h * cfg.BORDER_MARGIN_TOP_RATIO), 1)
    margin_bottom = max(int(h * cfg.BORDER_MARGIN_BOTTOM_RATIO), 1)
    cv2.line(out, (0, margin_top), (w, margin_top), (0, 140, 255), 1)
    cv2.line(out, (0, h - margin_bottom), (w, h - margin_bottom), (0, 140, 255), 1)


def _draw_outsider(out: np.ndarray, det) -> None:
    """Orang di luar lorong: abu-abu redup, tidak diperiksa."""
    x1, y1, x2, y2 = det.bbox
    color = (130, 130, 130)
    cv2.rectangle(out, (x1, y1), (x2, y2), color, 1)
    label = messages.HUD_OUTSIDE_ZONE.format(track_id=det.track_id)
    cv2.putText(out, label, (x1, max(22, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def _draw_subject(out: np.ndarray, det) -> None:
    """Subjek di lorong: hijau bila tubuh utuh, merah-oranye + alasan bila terpotong."""
    x1, y1, x2, y2 = det.bbox
    color = (0, 255, 0) if det.is_full_body else (0, 69, 255)
    cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
    label = (messages.HUD_FULL_BODY if det.is_full_body else messages.HUD_STEP_BACK).format(track_id=det.track_id)
    cv2.putText(out, label, (x1, max(25, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    if not det.is_full_body:
        cv2.putText(out, f"! {det.reason}", (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 69, 255), 2)


def _draw_header(out: np.ndarray, fps: float) -> None:
    """FPS & perangkat inferensi di kiri atas, status lampu di kanan atas."""
    w = out.shape[1]
    header = messages.HUD_HEADER.format(fps=fps, device=detector.device_label)
    cv2.putText(out, header, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 200), 2)
    state = notifier.current_state
    status_color = (0, 255, 0) if state == "GREEN" else ((0, 0, 255) if state == "RED" else (180, 180, 180))
    cv2.putText(
        out, messages.HUD_LIGHT.format(state=state), (w - 200, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2
    )
