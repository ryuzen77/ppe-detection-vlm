"""Pengenalan pekerja dalam sesi (T34c1): siapa yang berdiri di gerbang, untuk audit & suara nama.

- Galeri templat pekerja AKTIF dimuat ke memori dan dimuat ulang otomatis setiap data
  pekerja berubah (revisi `worker_store`); pencarian = satu perkalian matriks.
- Nama hanya diberikan bila FACE_VOTES_REQUIRED dari FACE_VOTE_FRAMES frame terbaik
  menunjuk orang yang SAMA di atas ambang (keputusan pengguna 18-10: 2 dari 3).
  Salah nama lebih buruk daripada tanpa nama: ragu = "unknown".
- FR tidak pernah menghambat keputusan APD: galat apa pun = "disabled"/"unknown".
"""

import logging
import threading
from dataclasses import dataclass
from typing import Optional

import numpy as np

from . import face_engine, messages, security_log, worker_store
from .config import cfg

logger = logging.getLogger(__name__)

RECOGNIZED, UNKNOWN, DISABLED = "recognized", "unknown", "disabled"


@dataclass(frozen=True)
class Identity:
    status: str
    worker_id: Optional[int] = None
    name: Optional[str] = None
    employee_no: Optional[str] = None
    score: Optional[float] = None

    def payload(self) -> dict:
        """Bentuk telemetri (kontrak T34c1); nama hanya bila dikenali."""
        return {
            "status": self.status,
            "name": self.name,
            "employee_no": self.employee_no,
            "score": None if self.score is None else round(self.score, 3),
        }


@dataclass(frozen=True)
class GalleryView:
    worker_ids: np.ndarray
    vectors: np.ndarray
    workers: dict  # id -> (nama, nomor pegawai)


Match = Optional[tuple[int, float]]


def best_match(vector: np.ndarray, gallery: GalleryView) -> Match:
    """Templat paling mirip di seluruh galeri (pekerja dengan beberapa templat: yang terbaik)."""
    if gallery.vectors.shape[0] == 0:
        return None
    scores = gallery.vectors @ vector
    row = int(np.argmax(scores))
    return int(gallery.worker_ids[row]), float(scores[row])


def vote(matches: list[Match], threshold: float, required: int) -> Match:
    """Pekerja yang dipilih >= `required` frame dengan skor >= ambang; skor = rata-rata frame itu.
    Dua pekerja berbeda yang sama-sama mencapai syarat = ragu = None."""
    agreeing: dict[int, list[float]] = {}
    for match in matches:
        if match is not None and match[1] >= threshold:
            agreeing.setdefault(match[0], []).append(match[1])
    winners = [(wid, scores) for wid, scores in agreeing.items() if len(scores) >= required]
    if len(winners) != 1:
        return None
    worker_id, scores = winners[0]
    return worker_id, float(np.mean(scores))


class FaceIdentifier:
    def __init__(self, store: Optional[worker_store.SqliteWorkerStore] = None, engine=None):
        self._store_override = store
        self._engine_override = engine
        self._lock = threading.Lock()
        self._gallery: Optional[GalleryView] = None
        self._revision = -1

    @property
    def store(self) -> worker_store.SqliteWorkerStore:
        return self._store_override or worker_store.store

    @property
    def engine(self):
        return self._engine_override or face_engine.engine

    def gallery(self) -> GalleryView:
        """Galeri terkini; dimuat ulang hanya bila data pekerja berubah sejak muat terakhir."""
        with self._lock:
            store = self.store
            if self._gallery is None or self._revision != store.revision:
                revision = store.revision
                self._gallery = self._load(store)
                self._revision = revision
            return self._gallery

    @staticmethod
    def _load(store: worker_store.SqliteWorkerStore) -> GalleryView:
        loaded = store.load_gallery(cfg.FACE_MODEL_VERSION)
        if loaded.unreadable:
            logger.warning(messages.FACE_TEMPLATE_UNREADABLE.format(count=loaded.unreadable))
            security_log.record(security_log.FACE_KEY_ERROR, unreadable=loaded.unreadable, ok=False)
        workers = {w.id: (w.name, w.employee_no) for w in store.all() if w.active}
        logger.info(messages.LOG_FACE_GALLERY_LOADED.format(templates=len(loaded.worker_ids), workers=len(workers)))
        return GalleryView(loaded.worker_ids, loaded.vectors, workers)

    def identify(self, crops: list[np.ndarray], session_id: int = 0) -> Identity:
        """Identitas dari potongan pekerja terbaik sesi. Tidak pernah melempar galat."""
        try:
            if not crops or not self.store.face_ready():
                return Identity(DISABLED)
            gallery = self.gallery()
            vectors = self.engine.subject_embeddings(crops)
        except Exception as e:  # FR tidak boleh menghambat keputusan APD
            logger.error(messages.LOG_FACE_FAILED.format(error=e))
            return Identity(DISABLED)
        matches = [None if v is None else best_match(v, gallery) for v in vectors]
        winner = vote(matches, cfg.FACE_MATCH_THRESHOLD, cfg.FACE_VOTES_REQUIRED)
        if winner is None or winner[0] not in gallery.workers:
            faces = sum(v is not None for v in vectors)
            best = max((m[1] for m in matches if m is not None), default=None)
            logger.info(messages.LOG_FACE_UNKNOWN.format(
                session=session_id, faces=faces, frames=len(crops), best="-" if best is None else f"{best:.2f}"))
            return Identity(UNKNOWN)
        worker_id, score = winner
        name, employee_no = gallery.workers[worker_id]
        votes = sum(1 for m in matches if m is not None and m[0] == worker_id and m[1] >= cfg.FACE_MATCH_THRESHOLD)
        logger.info(
            messages.LOG_FACE_RECOGNIZED.format(
                session=session_id, employee_no=employee_no, score=score, votes=votes, frames=len(crops)
            )
        )
        return Identity(RECOGNIZED, worker_id, name, employee_no, score)

    def similar_worker(self, vector: np.ndarray, worker_id: int) -> Optional[tuple[str, float]]:
        """Pekerja LAIN (aktif) yang wajahnya melewati ambang pengenalan: (nomor pegawai, skor).

        T76: satu orang yang terdaftar sebagai dua pekerja membuat setiap pengenalan "ragu"
        (dua pekerja cocok = tanpa nama), jadi foto seperti itu ditolak saat pendaftaran.
        """
        gallery = self.gallery()
        others = gallery.worker_ids != worker_id
        match = best_match(vector, GalleryView(gallery.worker_ids[others], gallery.vectors[others], gallery.workers))
        if match is None or match[1] < cfg.FACE_MATCH_THRESHOLD:
            return None
        return gallery.workers.get(match[0], ("", "?"))[1], match[1]


identifier = FaceIdentifier()
