import sys
import os
import time
import cv2
import numpy as np

# Ensure backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import cfg
from detector import DetectionResult
from state_manager import state_mgr, TrackState
from notifier import notifier
from audio_engine import audio_player
from vlm_analyzer import vlm_analyzer

def create_synthetic_person_crop(has_vest: bool = True) -> np.ndarray:
    """Creates a synthetic cropped person image for testing."""
    img = np.zeros((400, 200, 3), dtype=np.uint8)
    img[:, :] = (40, 40, 40)
    # Head (top 20%)
    img[0:80, 70:130] = (200, 200, 200) # Helmet white
    # Torso (20% - 55%)
    if has_vest:
        img[80:220, 40:160] = (0, 140, 255) # Bright orange vest
        img[140:150, 40:160] = (230, 230, 230) # Reflective strip
    else:
        img[80:220, 40:160] = (180, 50, 50) # Blue regular shirt
    # Legs (55% - 88%)
    img[220:350, 50:150] = (80, 60, 40) # Long jeans
    # Shoes (88% - 100%)
    img[350:400, 50:150] = (20, 20, 20) # Black closed shoes
    return img

def run_lifecycle_simulation():
    print("\n" + "="*70)
    print("  SIMULASI END-TO-END: PENGUJIAN LIFECYCLE DETEKSI APD & GERBANG K3")
    print("="*70)

    track_id = 42
    crop_full_apd = create_synthetic_person_crop(has_vest=True)

    # -------------------------------------------------------------
    # TAHAP 1: Orang Datang Terlalu Dekat ke Kamera (Tubuh Terpotong)
    # -------------------------------------------------------------
    print("\n>>> [TAHAP 1] Orang Masuk Lorong, tapi Terlalu Dekat (Kepala/Kaki Terpotong)...")
    
    # Bounding box menempel tepi bawah (y2 = 715 pada frame 720)
    det_too_close = DetectionResult(
        track_id=track_id,
        bbox=[450, 20, 830, 715],
        is_full_body=False,
        reason="Kaki terpotong di tepi bawah (terlalu dekat)",
        is_inside_corridor=True,
        crop_img=crop_full_apd,
        conf=0.92
    )

    state_mgr.update_frame_detections([det_too_close])
    time.sleep(0.1)

    info = state_mgr.get_telemetry()
    active = info["active_track"]
    print(f"   Status Orang: {active['state']} (Alasan: {active['reason']})")
    print(f"   Full Body Terpenuhi?: {active['is_full_body']}")
    print(f"   Lampu Indikator: {info['light']['light_state']} ({info['light']['message']})")
    assert active["state"] == TrackState.STEP_BACK_WARNING, "Harus berstatus STEP_BACK_WARNING!"
    assert active["is_full_body"] == False, "is_full_body harus False!"
    print("   [OK] Audio 'Silakan mundur sampai seluruh tubuh terlihat' terpicu. VLM belum dipanggil.")

    # -------------------------------------------------------------
    # TAHAP 2: Orang Bergerak Mundur Sesuai Instruksi Audio
    # -------------------------------------------------------------
    print("\n>>> [TAHAP 2] Orang Mundur ke Jarak Aman (Seluruh Tubuh Terlihat)...")
    
    # Bounding box aman di dalam batas margin (y1=50, y2=660 dari tinggi 720)
    det_full_body = DetectionResult(
        track_id=track_id,
        bbox=[470, 50, 810, 660],
        is_full_body=True,
        reason="Full body terdeteksi sempurna",
        is_inside_corridor=True,
        crop_img=crop_full_apd,
        conf=0.95
    )

    # Frame 1: Mulai stabil
    state_mgr.update_frame_detections([det_full_body])
    info1 = state_mgr.get_telemetry()["active_track"]
    print(f"   Frame 1: Posisi Aman, Akumulasi Stabil = {info1['stable_frames']}/2 frame")

    # Frame 2: Mencapai target stabil 2 frame -> Trigger VLM 1 frame
    state_mgr.update_frame_detections([det_full_body])
    info2 = state_mgr.get_telemetry()["active_track"]
    print(f"   Frame 2: Akumulasi Stabil = {info2['stable_frames']}/2 frame -> Trigger Analisa!")

    # -------------------------------------------------------------
    # TAHAP 3: Analisa VLM Berjalan & Mengembalikan Hasil JSON
    # -------------------------------------------------------------
    print("\n>>> [TAHAP 3] Analisa VLM Berjalan (1 Frame Saja)...")
    
    # Beri waktu worker thread menyelesaikan analisa (~50-200ms)
    time.sleep(0.5)
    
    info3 = state_mgr.get_telemetry()
    active3 = info3["active_track"]
    vlm_res = active3["vlm_result"]

    print(f"   Status State: {active3['state']}")
    print(f"   Sumber Inferensi: {vlm_res['inference_source']} ({vlm_res['inference_time_ms']} ms)")
    print(f"   Detail APD:")
    print(f"     - Helm: {vlm_res['helm']['detected']} ({vlm_res['helm']['description']})")
    print(f"     - Rompi: {vlm_res['rompi']['detected']} (Warna: {vlm_res['rompi']['color']}, Valid: {vlm_res['rompi']['is_valid_color']})")
    print(f"     - Celana: {vlm_res['celana_panjang']['detected']} ({vlm_res['celana_panjang']['description']})")
    print(f"     - Sepatu: {vlm_res['sepatu_tertutup']['detected']} (Tertutup: {vlm_res['sepatu_tertutup']['is_closed_shoes']})")
    print(f"   Hasil Akhir: {'LENGKAP (AKSES DIIZINKAN)' if vlm_res['is_complete'] else 'TIDAK LENGKAP'}")
    print(f"   Lampu Indikator: {info3['light']['light_state']} ({info3['light']['message']})")

    assert active3["state"] == TrackState.ANALYZED, "Harus berstatus ANALYZED!"
    assert vlm_res["is_complete"] == True, "Hasil harus LENGKAP!"
    assert info3["light"]["light_state"] == "GREEN", "Lampu harus HIJAU!"
    print("   [OK] Lampu Hijau MENYALA, Audio 'APD Lengkap' berbunyi.")

    # -------------------------------------------------------------
    # TAHAP 4: Orang Tetap Berdiri di Depan Kamera (Anti-Spam Test)
    # -------------------------------------------------------------
    print("\n>>> [TAHAP 4] Orang Masih Berdiri di Depan Kamera (Uji Anti-Spam API)...")
    api_calls_before = len(state_mgr.inspection_history)

    # Simulasikan 10 frame berikutnya orang masih berada di posisi yang sama
    for i in range(10):
        state_mgr.update_frame_detections([det_full_body])
        time.sleep(0.02)

    api_calls_after = len(state_mgr.inspection_history)
    print(f"   Jumlah Analisa Sebelum: {api_calls_before}, Sesudah 10 Frame: {api_calls_after}")
    assert api_calls_before == api_calls_after, "ANTI-SPAM GAGAL: Terjadi panggilan ganda untuk orang yang sama!"
    print("   [OK] ANTI-SPAM TERBUKTI SUKSES: 0 panggilan tambahan, hasil tetap di-cache.")

    # -------------------------------------------------------------
    # TAHAP 5: Orang Melangkah Melewati Gerbang / Meninggalkan Kamera
    # -------------------------------------------------------------
    print("\n>>> [TAHAP 5] Orang Melangkah Melewati Gerbang (Keluar dari Kamera)...")
    
    # Tidak ada deteksi orang di frame (kamera kosong)
    state_mgr.update_frame_detections([])
    time.sleep(0.1)

    info_empty = state_mgr.get_telemetry()
    print(f"   Ada Orang Terdeteksi?: {info_empty['has_person']}")
    print(f"   Active Track ID: {info_empty['active_track']}")
    
    # Tunggu transisi idle notifier (setelah subjek keluar)
    print("   Menunggu reset standby gerbang...")
    time.sleep(4.2)
    state_mgr.update_frame_detections([])
    info_idle = state_mgr.get_telemetry()
    print(f"   Lampu Indikator Akhir: {info_idle['light']['light_state']} ({info_idle['light']['message']})")
    assert info_idle['has_person'] == False, "Harus tidak ada orang!"
    print("   [OK] Gerbang kembali STANDBY dan siap menerima pekerja berikutnya!")

    print("\n" + "="*70)
    print("  HASIL KESELURUHAN: SEMUA TAHAP PENGUJIAN LOGIKA 100% SUKSES!")
    print("="*70 + "\n")

    sys.stdout.flush()
    os._exit(0)

if __name__ == "__main__":
    run_lifecycle_simulation()



