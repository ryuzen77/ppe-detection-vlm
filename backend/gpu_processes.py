"""Proses lain yang memakai GPU NVIDIA (T56), untuk petunjuk operator.

Uji 14-10: aplikasi biasa (browser, Discord, IDE) di GPU NVIDIA memenuhi VRAM 8 GB
sehingga VLM lokal macet tanpa tanda di `ollama ps`. Nama proses itu ditampilkan
supaya operator tahu apa yang harus ditutup. Sumbernya `nvidia-smi` (ada di Windows
dan Linux bersama driver NVIDIA); tanpa `nvidia-smi` daftarnya kosong, tidak gagal.
"""

import os
import shutil
import subprocess

from .config import cfg


def parse_gpu_apps(text: str, own_pids: set[int]) -> list[str]:
    """Nama proses (tanpa path) dari keluaran `--query-compute-apps=pid,process_name`."""
    names = set()
    for line in text.splitlines():
        pid_text, _, path = line.partition(",")
        try:
            pid = int(pid_text.strip())
        except ValueError:
            continue
        name = path.strip().replace("\\", "/").rsplit("/", 1)[-1]
        lowered = name.lower()
        if (
            not name
            or pid in own_pids
            or lowered in cfg.LOCAL_GPU_IGNORED_APPS
            or lowered.startswith(cfg.LOCAL_GPU_OWN_NAMES)
        ):
            continue
        names.add(name)
    return sorted(names, key=str.lower)


def other_gpu_apps() -> list[str]:
    """Proses lain di GPU NVIDIA; [] bila `nvidia-smi` tidak ada atau gagal."""
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return []
    try:
        out = subprocess.run(
            [exe, "--query-compute-apps=pid,process_name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=cfg.NVIDIA_SMI_TIMEOUT_SECONDS,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_gpu_apps(out.stdout, {os.getpid()})
