"""Akun pengguna dashboard (T51), menggantikan kata sandi tunggal `ADMIN_TOKEN`.

- Kata sandi hanya disimpan sebagai hash `scrypt` (bawaan Python) dengan garam acak
  per akun; tidak pernah dicatat, dikirim balik, atau ditulis ke jejak.
- Akun di `accounts.db` sendiri (bukan `audit.db`), supaya retensi & ekspor audit
  tidak menyentuhnya.
- Semua akun berperan `admin` untuk demo; kolom `role` disiapkan untuk peran
  operator kelak (rencana jangka panjang).

Perintah di mesin gerbang (mis. lupa kata sandi admin terakhir):
    python -m backend.accounts list
    python -m backend.accounts create <nama>
    python -m backend.accounts reset-password <nama>
"""
import argparse
import base64
import functools
import getpass
import hashlib
import hmac
import logging
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import messages, security_log
from .config import cfg

logger = logging.getLogger(__name__)

ROLE_ADMIN = "admin"
_USERNAME_CHARS = re.compile(r"[a-z0-9._-]+")
_HASH_SCHEME = "scrypt"
_SALT_BYTES = 16
_KEY_BYTES = 32


class AccountError(Exception):
    """Permintaan akun ditolak; `code` stabil untuk UI (kontrak T51)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Account:
    username: str
    role: str
    created_at: str
    last_login_at: Optional[str]


# --- Hash kata sandi ---

def hash_password(password: str) -> str:
    n, r, p = cfg.PASSWORD_SCRYPT_N, cfg.PASSWORD_SCRYPT_R, cfg.PASSWORD_SCRYPT_P
    salt = secrets.token_bytes(_SALT_BYTES)
    key = _scrypt(password, salt, n, r, p)
    return "$".join([_HASH_SCHEME, str(n), str(r), str(p), _b64(salt), _b64(key)])


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, key = stored.split("$")
        expected = base64.b64decode(key)
        actual = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    # compare_digest: lama perbandingan tidak membocorkan berapa byte yang cocok
    return scheme == _HASH_SCHEME and hmac.compare_digest(actual, expected)


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    # maxmem dinaikkan sedikit di atas kebutuhan 128*n*r supaya parameter bawaan diterima
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=_KEY_BYTES,
                          maxmem=256 * n * r)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


@functools.cache
def _dummy_hash() -> str:
    """Hash tiruan untuk nama yang tidak ada: login tetap menghitung scrypt, jadi lama
    jawaban tidak membocorkan nama pengguna mana yang terdaftar. Dibuat saat pertama
    dipakai, bukan saat impor."""
    return hash_password(secrets.token_urlsafe(16))


# --- Aturan nama & kata sandi ---

def normalize_username(raw: object) -> str:
    username = str(raw or "").strip().lower()
    if not (cfg.ACCOUNT_USERNAME_MIN_LENGTH <= len(username) <= cfg.ACCOUNT_USERNAME_MAX_LENGTH
            and _USERNAME_CHARS.fullmatch(username)):
        raise AccountError("invalid_username", messages.ACCOUNT_INVALID_USERNAME.format(
            min=cfg.ACCOUNT_USERNAME_MIN_LENGTH, max=cfg.ACCOUNT_USERNAME_MAX_LENGTH))
    return username


def check_password(password: object, username: str) -> str:
    text = password if isinstance(password, str) else ""
    if (not cfg.ACCOUNT_PASSWORD_MIN_LENGTH <= len(text) <= cfg.ACCOUNT_PASSWORD_MAX_LENGTH
            or text.strip().lower() == username):
        raise AccountError("weak_password", messages.ACCOUNT_WEAK_PASSWORD.format(
            min=cfg.ACCOUNT_PASSWORD_MIN_LENGTH, max=cfg.ACCOUNT_PASSWORD_MAX_LENGTH))
    return text


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# --- Penyimpanan ---

class AccountStore:
    def __init__(self, path: Optional[Path] = None):
        self._path_override = path
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        # Dibaca saat dipakai (bukan saat impor) supaya tes bisa mengarahkan ke folder sementara
        return self._path_override or cfg.ACCOUNTS_DB_PATH

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = FULL;")
        conn.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, "
                     "role TEXT NOT NULL, created_at TEXT NOT NULL, password_changed_at TEXT NOT NULL, "
                     "last_login_at TEXT)")
        return conn

    def _run(self, fn):
        """Satu transaksi tulis eksklusif (BEGIN IMMEDIATE): cek & ubah tidak bisa disela."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                result = fn(conn)
                conn.execute("COMMIT")
                return result
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def count(self) -> int:
        return self._run(lambda c: c.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def all(self) -> list[Account]:
        rows = self._run(lambda c: c.execute(
            "SELECT username, role, created_at, last_login_at FROM users ORDER BY username").fetchall())
        return [Account(*row) for row in rows]

    def create(self, username: object, password: object, role: str = ROLE_ADMIN,
               only_if_empty: bool = False) -> Account:
        """Akun baru. `only_if_empty`: setup admin pertama — gagal bila sudah ada akun."""
        name = normalize_username(username)
        password_hash = hash_password(check_password(password, name))

        def insert(conn):
            if only_if_empty and conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                raise AccountError("setup_done", messages.ACCOUNT_SETUP_DONE)
            if conn.execute("SELECT 1 FROM users WHERE username = ?", (name,)).fetchone():
                raise AccountError("username_taken", messages.ACCOUNT_USERNAME_TAKEN.format(username=name))
            now = _now()
            conn.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, NULL)", (name, password_hash, role, now, now))
            return Account(name, role, now, None)
        return self._run(insert)

    def verify(self, username: object, password: object) -> Optional[Account]:
        """Akun bila nama & kata sandi cocok; None bila tidak (tanpa membedakan sebabnya)."""
        name = str(username or "").strip().lower()
        row = self._run(lambda c: c.execute(
            "SELECT role, created_at, last_login_at, password_hash FROM users WHERE username = ?",
            (name,)).fetchone())
        ok = verify_password(password if isinstance(password, str) else "", row[3] if row else _dummy_hash())
        return Account(name, *row[:3]) if ok and row else None

    def authenticate(self, username: object, password: object) -> Optional[Account]:
        """Login: seperti `verify`, dan waktu login terakhir dicatat."""
        account = self.verify(username, password)
        if account is None:
            return None
        now = _now()
        self._run(lambda c: c.execute("UPDATE users SET last_login_at = ? WHERE username = ?",
                                      (now, account.username)))
        return Account(account.username, account.role, account.created_at, now)

    def set_password(self, username: str, password: object):
        password_hash = hash_password(check_password(password, username))

        def update(conn):
            changed = conn.execute("UPDATE users SET password_hash = ?, password_changed_at = ? WHERE username = ?",
                                   (password_hash, _now(), username)).rowcount
            if not changed:
                raise AccountError("not_found", messages.ACCOUNT_NOT_FOUND.format(username=username))
        self._run(update)

    def delete(self, username: str, actor: str):
        if username == actor:
            raise AccountError("self_delete", messages.ACCOUNT_SELF_DELETE)

        def remove(conn):
            if not conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                raise AccountError("not_found", messages.ACCOUNT_NOT_FOUND.format(username=username))
            if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] <= 1:
                raise AccountError("last_account", messages.ACCOUNT_LAST)
            conn.execute("DELETE FROM users WHERE username = ?", (username,))
        self._run(remove)


store = AccountStore()


# --- Jejak ---

def record_event(event: str, username: str = "", actor: str = "", client: str = "", ok: bool = True):
    """Kejadian akun ke security log (T53). Tanpa kata sandi maupun hash."""
    security_log.record(event, username=username, actor=actor, client=client, ok=ok)


# --- Perintah di mesin gerbang ---

def _ask_password(username: str) -> str:
    first = getpass.getpass(messages.ACCOUNT_CLI_PROMPT.format(username=username))
    if first != getpass.getpass(messages.ACCOUNT_CLI_PROMPT_AGAIN):
        raise SystemExit(messages.ACCOUNT_CLI_MISMATCH)
    return first


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.accounts")
    parser.add_argument("command", choices=("list", "create", "reset-password"))
    parser.add_argument("username", nargs="?")
    args = parser.parse_args(argv)
    if args.command == "list":
        accounts = store.all()
        for a in accounts:
            print(f"{a.username}	{a.role}	dibuat {a.created_at}	login terakhir {a.last_login_at or '-'}")
        if not accounts:
            print(messages.ACCOUNT_CLI_EMPTY.format(port=cfg.PORT))
        return 0
    if not args.username:
        parser.error("nama pengguna wajib")
    try:
        username = normalize_username(args.username)
        if args.command == "create":
            store.create(username, _ask_password(username))
            message = messages.ACCOUNT_CLI_CREATED
        else:
            store.set_password(username, _ask_password(username))
            message = messages.ACCOUNT_CLI_RESET
    except AccountError as e:
        raise SystemExit(e.message)
    record_event(args.command.replace("-", "_"), username=username, actor="terminal", client="localhost")
    print(message.format(username=username))
    return 0


if __name__ == "__main__":
    from . import logging_setup
    logging_setup.setup_security_log(cfg)   # kejadian dari terminal ikut tercatat
    try:
        raise SystemExit(main())
    finally:
        logging_setup.stop_logging()
