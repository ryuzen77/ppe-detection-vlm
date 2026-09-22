"""
SAFEGUARD AI - IoT Hardware Diagnostic Script
Uji Coba Pengendalian Lampu Bulat Hijau & Merah Fisik via Serial COM
"""

import sys
import time
from pathlib import Path

# Load config from backend/.env if available
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.append(str(backend_dir))

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("\n[!] Paket 'pyserial' belum terpasang.")
    print("    Silakan jalankan: pip install pyserial\n")
    sys.exit(1)

def list_available_ports():
    ports = serial.tools.list_ports.comports()
    print("\n--- Port Serial / COM Terdeteksi di Komputer ---")
    if not ports:
        print("  [X] Tidak ada port COM yang terdeteksi. Pastikan kabel USB Arduino sudah terpasang.")
        return []
    for p in ports:
        print(f"  -> {p.device}: {p.description}")
    print("------------------------------------------------\n")
    return [p.device for p in ports]

def main():
    print("==================================================")
    print("    UJI COBA LAMPU FISIK GERBANG K3 (SERIAL)     ")
    print("==================================================")

    ports = list_available_ports()
    default_port = ports[0] if ports else "COM3"

    port_input = input(f"Masukkan nomor port COM Arduino [default: {default_port}]: ").strip()
    target_port = port_input if port_input else default_port

    baud_rate = 9600

    print(f"\n[1/4] Menghubungkan ke {target_port} ({baud_rate} baud)...")
    try:
        ser = serial.Serial(target_port, baud_rate, timeout=1)
        time.sleep(2.0)  # Beri waktu Arduino me-reboot serial DTR
        print(f"      [OK] Terhubung ke {target_port}!")
    except Exception as e:
        print(f"\n[ERROR] Gagal membuka port {target_port}: {e}")
        print("        Pastikan jendela Serial Monitor di Arduino IDE sudah DITUTUP.")
        sys.exit(1)

    try:
        print("\n[2/4] Menguji LAMPU BULAT HIJAU (Akses Diizinkan)...")
        ser.write(b"LIGHT_GREEN\n")
        print("      -> Perintah 'LIGHT_GREEN' terkirim. Lampu Hijau menyala selama 4 detik.")
        time.sleep(4.0)

        print("\n[3/4] Menguji LAMPU BULAT MERAH (Akses Ditolak)...")
        ser.write(b"LIGHT_RED\n")
        print("      -> Perintah 'LIGHT_RED' terkirim. Lampu Merah menyala selama 4 detik.")
        time.sleep(4.0)

        print("\n[4/4] Menguji MODE STANDBY (Semua Lampu Padam)...")
        ser.write(b"LIGHT_OFF\n")
        print("      -> Perintah 'LIGHT_OFF' terkirim. Lampu padam.")
        time.sleep(1.0)

        print("\n==================================================")
        print("  [SUCCESS] Seluruh pengujian lampu fisik selesai!")
        print("==================================================")
    except KeyboardInterrupt:
        print("\nPengujian dihentikan pengguna.")
        ser.write(b"LIGHT_OFF\n")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
