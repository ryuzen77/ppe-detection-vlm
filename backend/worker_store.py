"""Pekerja & templat wajah terenkripsi (T34b). Kontrak: docs/RENCANA.md, Rancangan T34 -> T34b.

- `workers.db` sendiri (bukan audit.db/accounts.db): cadangan & ekspor audit tidak
  membawa data biometrik.
- Hanya templat (embedding) terenkripsi AES-GCM yang disimpan, tidak pernah foto.
- Penghapusan benar-benar menghapus: `secure_delete` menimpa isi halaman dengan nol
  dan WAL di-checkpoint, jadi ciphertext lama tidak tertinggal di berkas (hak hapus UU PDP).
- Akses lewat `WorkerRepository`: implementasi PostgreSQL + pgvector kelak cukup
  memenuhi antarmuka yang sama (rencana panjang di RENCANA).
"""

import logging
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

import numpy as np

from . import face_crypto, messages, security_log
from .config import cfg

logger = logging.getLogger(__name__)

SECONDS_PER_DAY = 24 * 60 * 60
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"  # waktu lokal gerbang, sama dengan audit (kontrak T51)
_EMPLOYEE_NO_CHARS = re.compile(r"[A-Za-z0-9._/-]+")
_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS workers (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "employee_no TEXT NOT NULL UNIQUE COLLATE NOCASE, name TEXT NOT NULL, active INTEGER NOT NULL, "
    "consent_at TEXT NOT NULL, consent_by TEXT NOT NULL, consent_version TEXT NOT NULL, "
    "created_at TEXT NOT NULL, created_by TEXT NOT NULL, deactivated_at TEXT, face_deleted_at TEXT)",
    "CREATE TABLE IF NOT EXISTS face_templates (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "worker_id INTEGER NOT NULL REFERENCES workers(id), condition TEXT NOT NULL, model_version TEXT NOT NULL, "
    "dim INTEGER NOT NULL, nonce BLOB NOT NULL, ciphertext BLOB NOT NULL, created_at TEXT NOT NULL, "
    "created_by TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_face_templates_worker ON face_templates(worker_id)",
)
_WORKER_COLUMNS = (
    "id, employee_no, name, active, consent_at, consent_by, consent_version, created_at, "
    "deactivated_at, face_deleted_at, nickname, gender"
)
# Kolom profil suara (T34d); workers.db dari T34b1 belum punya, ditambahkan saat dibuka
_PROFILE_COLUMNS = ("nickname", "gender")


class WorkerError(Exception):
    """Permintaan ditolak; `code` stabil untuk UI (kontrak T34b)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Template:
    id: int
    condition: str
    model_version: str
    created_at: str


@dataclass(frozen=True)
class Worker:
    id: int
    employee_no: str
    name: str
    active: bool
    consent_at: str
    consent_by: str
    consent_version: str
    created_at: str
    deactivated_at: Optional[str]
    face_deleted_at: Optional[str]
    nickname: str = ""
    gender: Optional[str] = None
    templates: tuple[Template, ...] = ()

    @property
    def salutation(self) -> Optional[str]:
        """Sapaan untuk suara nama (T34d): Pak/Bu dari jenis kelamin; None bila belum diisi."""
        return messages.SALUTATIONS.get(self.gender or "")

    @property
    def delete_after(self) -> Optional[str]:
        """Kapan templat wajah dihapus retensi; None bila aktif atau sudah terhapus."""
        if self.active or self.deactivated_at is None or self.face_deleted_at is not None:
            return None
        deactivated = time.mktime(time.strptime(self.deactivated_at, TIME_FORMAT))
        return _format(deactivated + cfg.FACE_RETENTION_DAYS * SECONDS_PER_DAY)


@dataclass(frozen=True)
class Gallery:
    """Templat siap dicari: baris ke-i `vectors` milik `worker_ids[i]` (satu pekerja bisa beberapa baris)."""

    worker_ids: np.ndarray
    vectors: np.ndarray
    unreadable: int


class WorkerRepository(Protocol):
    """Antarmuka penyimpanan pekerja; SQLite sekarang, PostgreSQL + pgvector kelak."""

    def face_ready(self) -> bool: ...
    def all(self) -> list[Worker]: ...
    def get(self, worker_id: int) -> Worker: ...
    def create(self, employee_no: object, name: object, consent: bool, actor: str, nickname: object = "",
               gender: object = None) -> Worker: ...
    def update_profile(self, worker_id: int, nickname: object = None, gender: object = None) -> Worker: ...
    def deactivate(self, worker_id: int) -> Worker: ...
    def activate(self, worker_id: int) -> Worker: ...
    def delete_face(self, worker_id: int) -> int: ...
    def delete_template(self, worker_id: int, template_id: int) -> None: ...
    def add_template(
        self, worker_id: int, condition: str, model_version: str, vector: np.ndarray, actor: str
    ) -> Template: ...
    def load_gallery(self, model_version: str) -> Gallery: ...
    def purge_expired(self, now: Optional[float] = None) -> list[int]: ...


def _format(seconds: float) -> str:
    return time.strftime(TIME_FORMAT, time.localtime(seconds))


def _now() -> str:
    return _format(time.time())


def normalize_name(raw: object) -> str:
    name = " ".join(str(raw or "").split())  # spasi ganda & karakter kontrol baris dirapikan
    if not 1 <= len(name) <= cfg.WORKER_NAME_MAX_LENGTH or not name.isprintable():
        raise WorkerError("invalid_name", messages.WORKER_INVALID_NAME.format(max=cfg.WORKER_NAME_MAX_LENGTH))
    return name


def normalize_employee_no(raw: object) -> str:
    number = str(raw or "").strip()
    if not (len(number) <= cfg.WORKER_EMPLOYEE_NO_MAX_LENGTH and _EMPLOYEE_NO_CHARS.fullmatch(number)):
        raise WorkerError(
            "invalid_employee_no", messages.WORKER_INVALID_EMPLOYEE_NO.format(max=cfg.WORKER_EMPLOYEE_NO_MAX_LENGTH)
        )
    return number


def _check_condition(condition: str) -> None:
    if condition not in cfg.FACE_CONDITIONS:
        raise WorkerError(
            "invalid_condition", messages.WORKER_INVALID_CONDITION.format(conditions=", ".join(cfg.FACE_CONDITIONS))
        )


def _check_active(worker: "Worker") -> None:
    if not worker.active:
        raise WorkerError("inactive", messages.WORKER_INACTIVE.format(worker_id=worker.id))


def normalize_gender(raw: object) -> str:
    gender = str(raw or "").strip().lower()
    if gender not in cfg.WORKER_GENDERS:
        raise WorkerError("invalid_gender", messages.WORKER_INVALID_GENDER)
    return gender


def normalize_nickname(raw: object) -> str:
    """Nama panggilan untuk suara (T34d), WAJIB diisi admin. Tidak ditebak dari nama lengkap:
    nama Indonesia tidak berpola nama depan/belakang ("Muhammad Zen Fikri" dipanggil "Zen")."""
    nickname = " ".join(str(raw or "").split())
    if not 1 <= len(nickname) <= cfg.WORKER_NICKNAME_MAX_LENGTH or not nickname.isprintable():
        raise WorkerError("invalid_nickname", messages.WORKER_INVALID_NICKNAME.format(max=cfg.WORKER_NICKNAME_MAX_LENGTH))
    return nickname


def _not_found(worker_id: int) -> WorkerError:
    return WorkerError("not_found", messages.WORKER_NOT_FOUND.format(worker_id=worker_id))


class SqliteWorkerStore:
    def __init__(self, path: Optional[Path] = None, key: Optional[str] = None):
        self._path_override = path
        self._key_override = key
        self._lock = threading.Lock()
        # Naik setiap penulisan: galeri pengenalan di memori (T34c1) tahu kapan harus dimuat ulang
        self.revision = 0

    @property
    def path(self) -> Path:
        # Dibaca saat dipakai (bukan saat impor) supaya tes bisa mengarahkan ke folder sementara
        return self._path_override or cfg.WORKERS_DB_PATH

    def _key_text(self) -> str:
        return cfg.FACE_DATA_KEY if self._key_override is None else self._key_override

    def _cipher(self) -> face_crypto.FaceCipher:
        try:
            key = face_crypto.parse_key(self._key_text())
        except face_crypto.FaceKeyError:
            key = None
        if key is None:
            raise WorkerError("face_not_ready", messages.WORKER_FACE_NOT_READY)
        return face_crypto.FaceCipher(key)

    def face_ready(self) -> bool:
        try:
            return face_crypto.parse_key(self._key_text()) is not None
        except face_crypto.FaceKeyError:
            return False

    # --- Koneksi & transaksi ---

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=cfg.DB_TIMEOUT_SECONDS, isolation_level=None)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = FULL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA secure_delete = ON;")
        for statement in _SCHEMA:
            conn.execute(statement)
        existing = {row[1] for row in conn.execute("PRAGMA table_info(workers)")}
        for column in _PROFILE_COLUMNS:
            if column not in existing:
                conn.execute(f"ALTER TABLE workers ADD COLUMN {column} TEXT")
        return conn

    def _run(self, fn, checkpoint: bool = False, mutates: bool = False):
        """Satu transaksi tulis eksklusif (BEGIN IMMEDIATE): cek & ubah tidak bisa disela.
        `checkpoint`: setelah menghapus data wajah, WAL dikosongkan supaya salinan lama ikut hilang."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                result = fn(conn)
                conn.execute("COMMIT")
                if mutates:
                    self.revision += 1
                if checkpoint:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                return result
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    # --- Baca ---

    @staticmethod
    def _templates(conn: sqlite3.Connection, worker_ids: list[int]) -> dict[int, tuple[Template, ...]]:
        found: dict[int, list[Template]] = {wid: [] for wid in worker_ids}
        marks = ",".join("?" * len(worker_ids))
        rows = (
            conn.execute(
                f"SELECT worker_id, id, condition, model_version, created_at FROM face_templates "
                f"WHERE worker_id IN ({marks}) ORDER BY id",
                worker_ids,
            )
            if worker_ids
            else []
        )
        for worker_id, *fields in rows:
            found[worker_id].append(Template(*fields))
        return {wid: tuple(items) for wid, items in found.items()}

    def _fetch(self, conn: sqlite3.Connection, where: str = "", params: tuple = ()) -> list[Worker]:
        rows = conn.execute(f"SELECT {_WORKER_COLUMNS} FROM workers {where} ORDER BY name, id", params).fetchall()
        templates = self._templates(conn, [row[0] for row in rows])
        return [Worker(row[0], row[1], row[2], bool(row[3]), *row[4:], templates=templates[row[0]]) for row in rows]

    def _get(self, conn: sqlite3.Connection, worker_id: int) -> Worker:
        found = self._fetch(conn, "WHERE id = ?", (worker_id,))
        if not found:
            raise _not_found(worker_id)
        return found[0]

    def all(self) -> list[Worker]:
        return self._run(self._fetch)

    def get(self, worker_id: int) -> Worker:
        return self._run(lambda c: self._get(c, worker_id))

    def active_count(self) -> int:
        return self._run(lambda c: c.execute("SELECT COUNT(*) FROM workers WHERE active = 1").fetchone()[0])

    # --- Ubah ---

    def create(self, employee_no: object, name: object, consent: bool, actor: str, nickname: object = "",
               gender: object = None) -> Worker:
        """Pekerja baru; persetujuan tertulis wajib dicentang admin (keputusan pengguna 18-10).
        Nama panggilan & jenis kelamin wajib (suara nama "Pak/Bu <nama panggilan>", T34d)."""
        if consent is not True:
            raise WorkerError("consent_required", messages.WORKER_CONSENT_REQUIRED)
        number, clean_name = normalize_employee_no(employee_no), normalize_name(name)
        profile = (normalize_nickname(nickname), normalize_gender(gender))
        self._cipher()  # tanpa kunci, pekerja tidak bisa diberi wajah: tolak sejak awal

        def insert(conn):
            if conn.execute("SELECT 1 FROM workers WHERE employee_no = ?", (number,)).fetchone():
                raise WorkerError("employee_no_taken", messages.WORKER_EMPLOYEE_NO_TAKEN.format(employee_no=number))
            now = _now()
            cursor = conn.execute(
                "INSERT INTO workers (employee_no, name, active, consent_at, consent_by, consent_version, "
                "created_at, created_by, nickname, gender) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)",
                (number, clean_name, now, actor, cfg.FACE_CONSENT_VERSION, now, actor, *profile),
            )
            return self._get(conn, int(cursor.lastrowid or 0))

        return self._run(insert, mutates=True)

    def update_profile(self, worker_id: int, nickname: object = None, gender: object = None) -> Worker:
        """Ubah nama panggilan / jenis kelamin (T34d); None = tidak diubah. Suara nama dibuat ulang pemanggil."""
        def update(conn):
            current = self._get(conn, worker_id)
            new_nickname = current.nickname if nickname is None else normalize_nickname(nickname)
            new_gender = current.gender if gender is None else normalize_gender(gender)
            conn.execute("UPDATE workers SET nickname = ?, gender = ? WHERE id = ?", (new_nickname, new_gender, worker_id))
            return self._get(conn, worker_id)

        return self._run(update, mutates=True)

    def deactivate(self, worker_id: int) -> Worker:
        """Nonaktif: masa retensi berjalan sejak saat pertama dinonaktifkan (diulang tidak memperpanjang)."""

        def update(conn):
            self._get(conn, worker_id)
            conn.execute(
                "UPDATE workers SET active = 0, deactivated_at = COALESCE(deactivated_at, ?) WHERE id = ?",
                (_now(), worker_id),
            )
            return self._get(conn, worker_id)

        return self._run(update, mutates=True)

    def activate(self, worker_id: int) -> Worker:
        """Aktif lagi: penghapusan terjadwal batal. Bila wajah sudah terhapus, foto harus diambil ulang."""

        def update(conn):
            self._get(conn, worker_id)
            conn.execute("UPDATE workers SET active = 1, deactivated_at = NULL WHERE id = ?", (worker_id,))
            return self._get(conn, worker_id)

        return self._run(update, mutates=True)

    def delete_face(self, worker_id: int) -> int:
        """Hapus semua templat wajah pekerja sekarang (hak hapus). Jumlah templat yang dihapus."""

        def remove(conn):
            self._get(conn, worker_id)
            return self._erase_templates(conn, [worker_id])

        return self._run(remove, checkpoint=True, mutates=True)

    @staticmethod
    def _erase_templates(conn: sqlite3.Connection, worker_ids: list[int]) -> int:
        marks = ",".join("?" * len(worker_ids))
        deleted = conn.execute(f"DELETE FROM face_templates WHERE worker_id IN ({marks})", worker_ids).rowcount
        conn.execute(f"UPDATE workers SET face_deleted_at = ? WHERE id IN ({marks})", (_now(), *worker_ids))
        return deleted

    def delete_template(self, worker_id: int, template_id: int) -> None:
        def remove(conn):
            self._get(conn, worker_id)
            if not conn.execute(
                "DELETE FROM face_templates WHERE id = ? AND worker_id = ?", (template_id, worker_id)
            ).rowcount:
                raise WorkerError(
                    "template_not_found",
                    messages.WORKER_TEMPLATE_NOT_FOUND.format(template_id=template_id, worker_id=worker_id),
                )

        self._run(remove, checkpoint=True, mutates=True)

    def add_template(
        self, worker_id: int, condition: str, model_version: str, vector: np.ndarray, actor: str
    ) -> Template:
        """Templat baru terenkripsi; hanya untuk pekerja aktif. Menghapus tanda `face_deleted_at`."""
        _check_condition(condition)
        cipher, flat = self._cipher(), np.asarray(vector, dtype=np.float32).ravel()

        def insert(conn):
            _check_active(self._get(conn, worker_id))
            nonce, sealed = cipher.encrypt(flat, face_crypto.template_aad(worker_id, model_version))
            now = _now()
            cursor = conn.execute(
                "INSERT INTO face_templates (worker_id, condition, model_version, dim, nonce, ciphertext, "
                "created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (worker_id, condition, model_version, flat.size, nonce, sealed, now, actor),
            )
            conn.execute("UPDATE workers SET face_deleted_at = NULL WHERE id = ?", (worker_id,))
            return Template(int(cursor.lastrowid or 0), condition, model_version, now)

        return self._run(insert, mutates=True)

    def check_template_target(self, worker_id: int, condition: str) -> None:
        """Cek sebelum mengambil foto (T34b2): kondisi sah & pekerja ada lagi aktif, supaya kamera
        tidak dipakai untuk permintaan yang pasti ditolak. Dicek ulang saat menyimpan."""
        _check_condition(condition)
        _check_active(self.get(worker_id))

    # --- Galeri & retensi ---

    def load_gallery(self, model_version: str) -> Gallery:
        """Templat pekerja AKTIF untuk satu versi model, terbuka di memori. Templat yang gagal
        dibuka (kunci berbeda / rusak) dilewati dan dihitung, server tidak berhenti."""
        cipher = self._cipher()
        rows = self._run(
            lambda c: c.execute(
                "SELECT t.worker_id, t.dim, t.nonce, t.ciphertext FROM face_templates t "
                "JOIN workers w ON w.id = t.worker_id WHERE w.active = 1 AND t.model_version = ? ORDER BY t.id",
                (model_version,),
            ).fetchall()
        )
        ids, vectors, unreadable = [], [], 0
        for worker_id, dim, nonce, sealed in rows:
            try:
                vectors.append(cipher.decrypt(nonce, sealed, face_crypto.template_aad(worker_id, model_version), dim))
                ids.append(worker_id)
            except face_crypto.FaceKeyError:
                unreadable += 1
        matrix = np.stack(vectors) if vectors else np.zeros((0, 0), np.float32)
        return Gallery(np.array(ids, dtype=np.int64), matrix, unreadable)

    def purge_expired(self, now: Optional[float] = None) -> list[int]:
        """Templat pekerja yang nonaktif >= FACE_RETENTION_DAYS dihapus. Kembali: id pekerja."""
        cutoff = _format((time.time() if now is None else now) - cfg.FACE_RETENTION_DAYS * SECONDS_PER_DAY)

        def purge(conn):
            ids = [
                row[0]
                for row in conn.execute(
                    "SELECT id FROM workers WHERE active = 0 AND face_deleted_at IS NULL AND deactivated_at <= ?",
                    (cutoff,),
                )
            ]
            if ids:
                self._erase_templates(conn, ids)
            return ids

        return self._run(purge, checkpoint=True, mutates=True)


store = SqliteWorkerStore()


def gallery_limit(active: int) -> dict:
    """Status batas galeri teruji untuk API & peringatan admin (T34m2)."""
    return {"tested": cfg.FACE_GALLERY_TESTED_LIMIT, "count": active, "over": active > cfg.FACE_GALLERY_TESTED_LIMIT}


def run_retention(repository: Optional[SqliteWorkerStore] = None) -> list[int]:
    """Dipanggil siklus retensi (runtime). Setiap penghapusan dicatat di security log."""
    repository = repository or store
    try:
        purged = repository.purge_expired()
    except Exception as e:  # retensi lain tetap berjalan walau berkas pekerja bermasalah
        logger.error(f"Retensi data wajah gagal: {e}")
        return []
    for worker_id in purged:
        security_log.record(
            security_log.WORKER_FACE_DELETED, worker_id=worker_id, reason="retention", actor="system", ok=True
        )
    if purged:
        logger.info(messages.FACE_RETENTION_PURGED.format(count=len(purged), days=cfg.FACE_RETENTION_DAYS))
    return purged


def log_key_status() -> None:
    """Saat server menyala: kunci kosong = info (fitur sengaja mati), kunci rusak = peringatan.
    Isi kunci tidak pernah dicatat."""
    try:
        if face_crypto.parse_key(cfg.FACE_DATA_KEY) is None:
            logger.info(messages.FACE_KEY_MISSING)
    except face_crypto.FaceKeyError as e:
        logger.warning(str(e))
