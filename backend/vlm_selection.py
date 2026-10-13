"""Pilihan penyedia & model VLM dari dashboard admin (T28).

`.env` tetap sumber key dan pilihan bawaan. Admin boleh memilih penyedia/model
lain dari Pengaturan; pilihan itu disimpan di `runtime_settings` dan menang atas
`.env` saat start, sampai dihapus ("kembali ke .env").

Rambu (rancangan T28 yang disetujui 06-10):
- dashboard tidak pernah menerima, menyimpan, atau menampilkan API key;
- key satu penyedia tidak pernah dikirim ke penyedia lain;
- model yang pernah meloloskan APD kurang (`unsafe`) selalu ditolak;
- model yang belum tervalidasi untuk prompt sekarang hanya dengan konfirmasi;
- setiap pergantian dicatat di log dan security log (T53).
"""
import logging
import re
from dataclasses import asdict, dataclass
from typing import Optional

from . import messages, runtime_settings, security_log
from .config import cfg, provider_api_key
from .vlm_providers import profiles

logger = logging.getLogger(__name__)

SETTINGS_KEY = "vlm_selection"
SOURCE_ENV = "env"
SOURCE_DASHBOARD = "dashboard"
NO_BACKUP = "none"

# Status validasi yang boleh dipakai hanya dengan konfirmasi admin
NEEDS_CONFIRMATION = (profiles.UNVALIDATED, profiles.OUTDATED)


@dataclass(frozen=True)
class Choice:
    provider: str
    model: str

    @staticmethod
    def parse(data) -> Optional["Choice"]:
        """Dari JSON {"provider", "model"}; None untuk null / tanpa cadangan."""
        if not isinstance(data, dict):
            return None
        provider = str(data.get("provider") or "").strip().lower()
        if not provider or provider == NO_BACKUP:
            return None
        return Choice(provider, str(data.get("model") or "").strip())

    def label(self) -> str:
        return f"{self.provider}/{self.model}"


@dataclass(frozen=True)
class Selection:
    primary: Choice
    backup: Optional[Choice]
    source: str

    def stored_form(self) -> dict:
        return {"primary": asdict(self.primary), "backup": asdict(self.backup) if self.backup else None}


class SelectionError(Exception):
    """Pilihan ditolak; `code` stabil untuk UI, pesan untuk manusia."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --- Key & alamat: hanya dari .env ---

def api_key_for(provider: str) -> str:
    """Key untuk penyedia ini. VLM_API_KEY / VLM_BACKUP_API_KEY hanya berlaku untuk
    penyedia yang dipilih `.env` pada peran itu, supaya tidak bocor ke penyedia lain."""
    if provider == cfg.VLM_PROVIDER and cfg.VLM_API_KEY:
        return cfg.VLM_API_KEY
    if provider == cfg.VLM_BACKUP_PROVIDER and cfg.VLM_BACKUP_API_KEY:
        return cfg.VLM_BACKUP_API_KEY
    return provider_api_key(provider)


def base_url_for(provider: str) -> str:
    """Alamat dari .env bila penyedia itu dipilih .env; kosong = alamat bawaan profil."""
    if provider == cfg.VLM_PROVIDER and cfg.VLM_BASE_URL:
        return cfg.VLM_BASE_URL
    if provider == cfg.VLM_BACKUP_PROVIDER and cfg.VLM_BACKUP_BASE_URL:
        return cfg.VLM_BACKUP_BASE_URL
    return ""


MISSING_KEY = "key"
MISSING_BASE_URL = "base_url"


def missing_setting(profile: profiles.ProviderProfile) -> Optional[str]:
    """Isian .env yang masih kurang (key lebih dulu), None bila siap. UI perlu
    membedakannya: vLLM lokal tidak butuh key, hanya alamat."""
    if not profile.is_local and not api_key_for(profile.name):
        return MISSING_KEY
    if profile.api != profiles.API_GEMINI and not (profile.base_url or base_url_for(profile.name)):
        return MISSING_BASE_URL
    return None


def is_ready(provider: str) -> bool:
    """Penyedia bisa dipakai tanpa menyentuh .env: key ada (atau lokal) & alamat diketahui."""
    profile = profiles.get_profile(provider)
    return profile is not None and missing_setting(profile) is None


REDACTED = "***"
# Penyedia sering mengutip key yang disamarkan di pesan galat (mis. OpenAI:
# "Incorrect API key provided: sk-ab***wxyz"); potongan seperti itu tetap bocoran.
_MASKED_SECRET = re.compile(r"\S*\*{3,}\S*")


def redact(text: str, api_key: str) -> str:
    """Pesan galat penyedia tanpa key utuh maupun potongan key yang disamarkan."""
    if api_key:
        text = text.replace(api_key, REDACTED)
    return _MASKED_SECRET.sub(REDACTED, text)


# --- Aturan pilihan ---

def validation_of(choice: Choice) -> tuple[str, Optional[profiles.ModelValidation]]:
    status = profiles.validation_status(choice.provider, choice.model, messages.PROMPT_VERSION)
    return status, profiles.find_validation(choice.provider, choice.model)


def check_choice(choice: Choice, confirm_unvalidated: bool):
    """Melempar SelectionError bila pilihan tidak boleh dipakai di gerbang."""
    profile = profiles.get_profile(choice.provider)
    if profile is None:
        raise SelectionError("unknown_provider", messages.VLM_SELECT_UNKNOWN_PROVIDER.format(provider=choice.provider))
    if not choice.model:
        raise SelectionError("missing_model", messages.VLM_SELECT_MISSING_MODEL.format(provider=choice.provider))
    missing = missing_setting(profile)
    if missing == MISSING_KEY:
        raise SelectionError("missing_key", messages.VLM_SELECT_MISSING_KEY.format(
            provider=choice.provider, key_env=profile.key_env or "VLM_API_KEY"))
    if missing == MISSING_BASE_URL:
        raise SelectionError("missing_base_url", messages.VLM_SELECT_MISSING_BASE_URL.format(provider=choice.provider))
    _check_validation(choice, confirm_unvalidated)


def _check_validation(choice: Choice, confirm_unvalidated: bool):
    status, record = validation_of(choice)
    if status == profiles.UNSAFE:
        raise SelectionError("unsafe_model", messages.VLM_SELECT_UNSAFE.format(
            provider=choice.provider, model=choice.model, missed=record.missed, photos=record.photos))
    if status in NEEDS_CONFIRMATION and not confirm_unvalidated:
        raise SelectionError("needs_confirmation", messages.VLM_SELECT_NEEDS_CONFIRMATION.format(
            provider=choice.provider, model=choice.model, prompt=messages.PROMPT_VERSION, status=status))


# --- Sumber pilihan: .env atau dashboard ---

def env_selection() -> Selection:
    backup = (Choice(cfg.VLM_BACKUP_PROVIDER, cfg.VLM_BACKUP_MODEL)
              if cfg.VLM_BACKUP_PROVIDER and cfg.VLM_BACKUP_PROVIDER != NO_BACKUP else None)
    return Selection(Choice(cfg.VLM_PROVIDER, cfg.VLM_MODEL), backup, SOURCE_ENV)


def stored_selection() -> Optional[Selection]:
    """Pilihan dashboard yang tersimpan, bila masih boleh dipakai.

    Diperiksa ulang saat start: katalog validasi bisa berubah sejak pilihan
    disimpan (mis. model kemudian terbukti tidak aman) dan key bisa dihapus dari
    .env. Konfirmasi admin dianggap sudah diberikan saat pilihan diterapkan.
    """
    data = runtime_settings.load().get(SETTINGS_KEY)
    if not isinstance(data, dict):
        return None
    primary, backup = Choice.parse(data.get("primary")), Choice.parse(data.get("backup"))
    try:
        if primary is None:
            raise SelectionError("missing_primary", "VLM utama kosong")
        for choice in filter(None, (primary, backup)):
            check_choice(choice, confirm_unvalidated=True)
    except SelectionError as e:
        logger.warning(messages.VLM_SELECT_STORED_IGNORED.format(reason=e.message))
        return None
    return Selection(primary, backup, SOURCE_DASHBOARD)


def effective_selection() -> Selection:
    return stored_selection() or env_selection()


def save(selection: Selection) -> bool:
    return runtime_settings.update(SETTINGS_KEY, selection.stored_form())


def clear() -> bool:
    return runtime_settings.update(SETTINGS_KEY, None)


# --- Jejak pergantian ---

def record_change(role: str, before: Optional[Choice], after: Optional[Choice], source: str, client: str,
                  user: str = ""):
    """Satu baris JSON per peran yang berubah, di-fsync seperti audit inspeksi."""
    status = validation_of(after)[0] if after else None
    logger.warning(messages.VLM_SELECT_APPLIED.format(
        role=role, before=before.label() if before else NO_BACKUP, after=after.label() if after else NO_BACKUP,
        status=status or "-", client=f"{user}@{client}" if user else client))
    security_log.record(security_log.VLM_CHANGE, role=role,
                        **{"from": asdict(before) if before else None, "to": asdict(after) if after else None},
                        validated=status, source=source, user=user, client=client)


# --- Katalog untuk Pengaturan admin ---

def provider_catalog(in_use: list[Choice]) -> list[dict]:
    """Semua penyedia di katalog profil + model yang dikenal & yang sedang dipakai. Tanpa API key."""
    return [_provider_entry(profile, [c.model for c in in_use if c.provider == name])
            for name, profile in profiles.PROFILES.items()]


def _provider_entry(profile: profiles.ProviderProfile, models_in_use: list[str]) -> dict:
    known = [v.model for v in profiles.VALIDATIONS if v.provider == profile.name]
    names = list(dict.fromkeys(filter(None, [*known, profile.default_model, *models_in_use])))
    return {"name": profile.name, "label": profile.label or profile.name, "support": profile.support,
            "is_local": profile.is_local, "has_key": is_ready(profile.name),
            "missing": missing_setting(profile),
            "data_location": profile.data_location, "default_model": profile.default_model,
            "models": [_model_entry(Choice(profile.name, m)) for m in names]}


def _model_entry(choice: Choice) -> dict:
    status, record = validation_of(choice)
    return {"model": choice.model, "validated": status,
            "photos": record.photos if record else None, "missed": record.missed if record else None,
            "false_rejects": record.false_rejects if record else None,
            "median_seconds": record.median_seconds if record else None}
