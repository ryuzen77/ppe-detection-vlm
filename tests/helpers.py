"""Gambar uji sintetis bersama."""
import numpy as np


def person_crop(vest: bool = True, helmet: bool = True, long_pants: bool = True,
                closed_shoes: bool = True) -> np.ndarray:
    """Crop orang 200x400 (BGR) dengan pembagian ROI yang dipakai engine lokal."""
    img = np.zeros((400, 200, 3), dtype=np.uint8)
    img[:, :] = (40, 40, 40)
    skin = (140, 170, 220)

    # Kepala (0-20%)
    img[0:80, 70:130] = (200, 200, 200) if helmet else skin
    # Badan (20-55%)
    if vest:
        img[80:220, 40:160] = (0, 140, 255)      # Rompi oranye
        img[140:150, 40:160] = (230, 230, 230)   # Strip reflektif
    else:
        img[80:220, 40:160] = (180, 50, 50)      # Kemeja biru biasa
    # Kaki (55-88%)
    img[220:350, 50:150] = (80, 60, 40) if long_pants else skin
    # Alas kaki (88-100%)
    img[350:400, 50:150] = (20, 20, 20) if closed_shoes else skin
    return img
