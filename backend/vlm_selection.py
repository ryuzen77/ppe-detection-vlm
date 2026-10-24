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
import threading
import time
from dataclasses import asdict, dataclass
from typing import Optional

from . import messages, runtime_settings, security_log
from .config import cfg, provider_api_key
from .vlm_providers import profiles
from .internet_monitor import DISCONNECTED, SLOW
from .api_monitor import ROLE_EMERGENCY
from .vlm_providers.model_list import ModelListCache, credential_signature

logger = logging.getLogger(__name__)
LOCAL_FALLBACK_SOURCE_PREFIX = "VLM_DARURAT:"

SETTINGS_KEY = "vlm_selection"
SOURCE_ENV = "env"
SOURCE_DASHBOARD = "dashboard"
NO_BACKUP = "none"
ROLE_PRIMARY = "utama"
ROLE_BACKUP = "cadangan"
MODEL_LIST_ROLES = {"primary": ROLE_PRIMARY, "backup": ROLE_BACKUP, "local": ROLE_EMERGENCY}
model_lists = ModelListCache()


class RecentModelTests:
    def __init__(self):
        self._lock = threading.Lock()
        self._passed: dict[tuple, tuple] = {}

    def record(self, role: str, choice: "Choice", result: dict, signature=None):
        key = (role, choice.provider, choice.model)
        with self._lock:
            self._passed.pop(key, None)
            if result.get("ok") is True and result.get("json_ok") is True and not result.get("error"):
                self._passed[key] = (
                    signature or _test_signature(choice, role),
                    time.monotonic() + cfg.VLM_TEST_FRESH_SECONDS,
                )

    def fresh(self, role: str, choice: "Choice") -> bool:
        with self._lock:
            passed = self._passed.get((role, choice.provider, choice.model))
        return bool(passed and passed[0] == _test_signature(choice, role) and time.monotonic() < passed[1])


recent_tests = RecentModelTests()


def _test_signature(choice: "Choice", role: str) -> tuple:
    return credential_signature(
        api_key_for(choice.provider, role), base_url_for(choice.provider, role)
    ), prompt_version_for(choice.provider)


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
    local_fallback: Optional[Choice] = None

    def stored_form(self) -> dict:
        return {
            "primary": asdict(self.primary),
            "backup": asdict(self.backup) if self.backup else None,
            "local_fallback": asdict(self.local_fallback) if self.local_fallback else None,
        }


class SelectionError(Exception):
    """Pilihan ditolak; `code` stabil untuk UI, pesan untuk manusia."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --- Key & alamat: hanya dari .env ---


def _role_value(provider: str, role: str, primary_value: str, backup_value: str) -> str:
    # Rambu T28: override peran hanya milik penyedia yang ditetapkan .env untuk peran itu.
    if role == ROLE_PRIMARY and provider == cfg.VLM_PROVIDER:
        return primary_value
    if role == ROLE_BACKUP and provider == cfg.VLM_BACKUP_PROVIDER:
        return backup_value
    return ""


def api_key_for(provider: str, role: str) -> str:
    """Override peran dahulu, lalu key milik penyedia; darurat lokal selalu tanpa key."""
    if role == ROLE_EMERGENCY:
        return ""
    return _role_value(provider, role, cfg.VLM_API_KEY, cfg.VLM_BACKUP_API_KEY) or provider_api_key(provider)


def base_url_for(provider: str, role: str) -> str:
    """Override alamat peran; kosong berarti memakai alamat bawaan profil penyedia."""
    return _role_value(provider, role, cfg.VLM_BASE_URL, cfg.VLM_BACKUP_BASE_URL)


MISSING_KEY = "key"
MISSING_BASE_URL = "base_url"


def missing_setting(profile: profiles.ProviderProfile, role: Optional[str] = None) -> Optional[str]:
    """Isian .env yang masih kurang (key lebih dulu), None bila siap. UI perlu
    membedakannya: vLLM lokal tidak butuh key, hanya alamat. Tanpa role = katalog bersama:
    siap jika salah satu peran dapat dipakai; validasi pilihan selalu mengirim role."""
    if role is None:
        missing = [missing_setting(profile, candidate) for candidate in (ROLE_PRIMARY, ROLE_BACKUP)]
        return None if None in missing else missing[0]
    if not profile.is_local and not api_key_for(profile.name, role):
        return MISSING_KEY
    if profile.api != profiles.API_GEMINI and not (profile.base_url or base_url_for(profile.name, role)):
        return MISSING_BASE_URL
    return None


def is_ready(provider: str, role: Optional[str] = None) -> bool:
    """Penyedia bisa dipakai tanpa menyentuh .env: key ada (atau lokal) & alamat diketahui."""
    profile = profiles.get_profile(provider)
    return profile is not None and missing_setting(profile, role) is None


REDACTED = "***"
# Penyedia sering mengutip key yang disamarkan di pesan galat (mis. OpenAI:
# "Incorrect API key provided: sk-ab***wxyz"); potongan seperti itu tetap bocoran.
_MASKED_SECRET = re.compile(r"\S*\*{3,}\S*")


def redact(text: str, api_key: str) -> str:
    """Pesan galat penyedia tanpa key utuh maupun potongan key yang disamarkan."""
    if api_key:
        text = text.replace(api_key, REDACTED)
    return _MASKED_SECRET.sub(REDACTED, text)


# --- Gambar berpanel & versi prompt per penyedia (T86) ---


def uses_zoom(provider_name: str) -> bool:
    """Panel perbesaran kepala hanya untuk VLM online.

    Validasi 21-10: model lokal qwen2.5vl:7b meloloskan APD kurang dengan gambar berpanel di setiap
    varian (helm DIPEGANG no_16, kaos kuning no_47; tiap ukuran panel gagal di foto berbeda), sedangkan
    tanpa panel 84/84 aman (T58). Gemini benar dengan & tanpa panel.
    """
    return cfg.VLM_ZOOM_ENABLED and not profiles.is_local(provider_name)


def prompt_version_for(provider_name: str) -> str:
    """Versi prompt yang benar-benar dikirim ke penyedia ini (tanpa panel = isi T58 persis)."""
    return messages.PROMPT_VERSION if uses_zoom(provider_name) else messages.PROMPT_VERSION_NO_ZOOM


def requires_local_route(internet_state, median_ms=None) -> bool:
    return internet_state == DISCONNECTED or (
        internet_state == SLOW and median_ms is not None and median_ms > cfg.INTERNET_VERY_SLOW_MS
    )


def inspection_route(internet_state, primary, backup, local_fallback, median_ms=None) -> tuple:
    """Tabel T72, O(1): hanya status tersimpan & referensi engine, tanpa I/O."""
    local = local_fallback or (backup if backup is not None and backup.is_local else None)
    if primary is not None and primary.is_local:
        candidates = (primary, backup)
    elif requires_local_route(internet_state, median_ms):
        candidates = (local,)
    elif internet_state == SLOW:
        candidates = (primary, local)
    else:
        candidates = (primary, backup, local_fallback)
    return tuple(engine for engine in candidates if engine is not None)


# --- Aturan pilihan ---


def validation_of(choice: Choice) -> tuple[str, Optional[profiles.ModelValidation]]:
    status = profiles.validation_status(choice.provider, choice.model, prompt_version_for(choice.provider))
    return status, profiles.find_validation(choice.provider, choice.model)


def check_choice(choice: Choice, confirm_unvalidated: bool, role: str = ROLE_PRIMARY):
    """Melempar SelectionError bila pilihan tidak boleh dipakai di gerbang."""
    profile = profiles.get_profile(choice.provider)
    if profile is None:
        raise SelectionError("unknown_provider", messages.VLM_SELECT_UNKNOWN_PROVIDER.format(provider=choice.provider))
    if not choice.model:
        raise SelectionError("missing_model", messages.VLM_SELECT_MISSING_MODEL.format(provider=choice.provider))
    missing = missing_setting(profile, role)
    if missing == MISSING_KEY:
        raise SelectionError(
            "missing_key",
            messages.VLM_SELECT_MISSING_KEY.format(provider=choice.provider, key_env=profile.key_env or "VLM_API_KEY"),
        )
    if missing == MISSING_BASE_URL:
        raise SelectionError("missing_base_url", messages.VLM_SELECT_MISSING_BASE_URL.format(provider=choice.provider))
    _check_validation(choice, confirm_unvalidated)


def _check_validation(choice: Choice, confirm_unvalidated: bool):
    status, record = validation_of(choice)
    if status == profiles.UNSAFE:
        assert record is not None, "status UNSAFE selalu berasal dari catatan validasi"
        raise SelectionError(
            "unsafe_model",
            messages.VLM_SELECT_UNSAFE.format(
                provider=choice.provider, model=choice.model, missed=record.missed, photos=record.photos
            ),
        )
    if status in NEEDS_CONFIRMATION and not confirm_unvalidated:
        raise SelectionError(
            "needs_confirmation",
            messages.VLM_SELECT_NEEDS_CONFIRMATION.format(
                provider=choice.provider, model=choice.model, prompt=prompt_version_for(choice.provider), status=status
            ),
        )


# --- Sumber pilihan: .env atau dashboard ---


def env_selection() -> Selection:
    backup = (
        Choice(cfg.VLM_BACKUP_PROVIDER, cfg.VLM_BACKUP_MODEL)
        if cfg.VLM_BACKUP_PROVIDER and cfg.VLM_BACKUP_PROVIDER != NO_BACKUP
        else None
    )
    fallback = (
        Choice(cfg.VLM_LOCAL_FALLBACK_PROVIDER, cfg.VLM_LOCAL_FALLBACK_MODEL)
        if cfg.VLM_LOCAL_FALLBACK_PROVIDER != NO_BACKUP
        else None
    )
    try:
        check_local_fallback(backup, fallback)
    except SelectionError as error:
        logger.warning(messages.VLM_LOCAL_FALLBACK_ENV_IGNORED.format(reason=error.message))
        fallback = None
    return Selection(Choice(cfg.VLM_PROVIDER, cfg.VLM_MODEL), backup, SOURCE_ENV, fallback)


def check_local_fallback(backup: Optional[Choice], fallback: Optional[Choice]):
    if fallback is None:
        return
    if backup is not None and profiles.is_local(backup.provider):
        raise SelectionError("local_fallback_with_local_backup", messages.VLM_LOCAL_FALLBACK_WITH_LOCAL_BACKUP)
    if not profiles.is_local(fallback.provider):
        raise SelectionError("local_fallback_not_local", messages.VLM_LOCAL_FALLBACK_NOT_LOCAL)


def check_selection(selection: Selection, confirm_unvalidated: bool):
    check_local_fallback(selection.backup, selection.local_fallback)
    for role, choice in (
        (ROLE_PRIMARY, selection.primary),
        (ROLE_BACKUP, selection.backup),
        (ROLE_EMERGENCY, selection.local_fallback),
    ):
        if choice is not None:
            check_choice(choice, confirm_unvalidated, role)


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
    fallback = Choice.parse(data.get("local_fallback"))
    try:
        if primary is None:
            raise SelectionError("missing_primary", "VLM utama kosong")
        check_selection(Selection(primary, backup, SOURCE_DASHBOARD, fallback), confirm_unvalidated=True)
    except SelectionError as e:
        logger.warning(messages.VLM_SELECT_STORED_IGNORED.format(reason=e.message))
        return None
    return Selection(primary, backup, SOURCE_DASHBOARD, fallback)


def effective_selection() -> Selection:
    return stored_selection() or env_selection()


def save(selection: Selection) -> bool:
    return runtime_settings.update(SETTINGS_KEY, selection.stored_form())


def clear() -> bool:
    return runtime_settings.update(SETTINGS_KEY, None)


# --- Jejak pergantian ---


def record_change(
    role: str, before: Optional[Choice], after: Optional[Choice], source: str, client: str, user: str = ""
):
    """Satu baris JSON per peran yang berubah, di-fsync seperti audit inspeksi."""
    status = validation_of(after)[0] if after else None
    logger.warning(
        messages.VLM_SELECT_APPLIED.format(
            role=role,
            before=before.label() if before else NO_BACKUP,
            after=after.label() if after else NO_BACKUP,
            status=status or "-",
            client=f"{user}@{client}" if user else client,
        )
    )
    security_log.record(
        security_log.VLM_CHANGE,
        role=role,
        **{"from": asdict(before) if before else None, "to": asdict(after) if after else None},
        validated=status,
        source=source,
        user=user,
        client=client,
    )


# --- Katalog untuk Pengaturan admin ---


def provider_catalog(in_use: list[Choice]) -> list[dict]:
    """Semua penyedia di katalog profil + model yang dikenal & yang sedang dipakai. Tanpa API key."""
    return [
        _provider_entry(profile, [c.model for c in in_use if c.provider == name])
        for name, profile in profiles.PROFILES.items()
    ]


def _provider_entry(profile: profiles.ProviderProfile, models_in_use: list[str]) -> dict:
    known = [v.model for v in profiles.VALIDATIONS if v.provider == profile.name]
    names = list(dict.fromkeys(filter(None, [*known, profile.default_model, *models_in_use])))
    return {
        "name": profile.name,
        "label": profile.label or profile.name,
        "support": profile.support,
        "is_local": profile.is_local,
        "has_key": is_ready(profile.name),
        "missing": missing_setting(profile),
        "data_location": profile.data_location,
        "default_model": profile.default_model,
        "models": [_model_entry(Choice(profile.name, m)) for m in names],
    }


def _model_entry(choice: Choice) -> dict:
    status, record = validation_of(choice)
    return {
        "model": choice.model,
        "validated": status,
        "photos": record.photos if record else None,
        "missed": record.missed if record else None,
        "false_rejects": record.false_rejects if record else None,
        "median_seconds": record.median_seconds if record else None,
    }


def available_models(provider: str, role: str, refresh: bool = False, in_use=()) -> dict:
    internal_role = MODEL_LIST_ROLES[role]
    api_key = api_key_for(provider, internal_role)
    result = model_lists.get(provider, internal_role, api_key, base_url_for(provider, internal_role), refresh)
    known = {entry.model for entry in profiles.VALIDATIONS if entry.provider == provider}
    known.update(choice.model for choice in in_use if choice.provider == provider)
    default = profiles.default_model(provider)
    if default:
        known.add(default)
    names = {name for name in known | set(result.names) if redact(name, api_key) == name}
    models = [
        {**_model_entry(Choice(provider, name)), "available": None if result.error else name in result.names}
        for name in names
    ]
    models.sort(
        key=lambda entry: (
            entry["validated"] not in (profiles.VALIDATED, profiles.PARTIAL),
            entry["model"].casefold(),
            entry["model"],
        )
    )
    return {
        "provider": provider,
        "role": role,
        "source": "catalog" if result.error else "provider",
        "fetched_at": result.fetched_at,
        "error": result.error,
        "models": models,
    }


def check_apply_models(selection: Selection):
    for role, choice in (
        ("primary", selection.primary),
        ("backup", selection.backup),
        ("local", selection.local_fallback),
    ):
        if choice is None:
            continue
        listing = available_models(choice.provider, role)
        found = any(entry["model"] == choice.model and entry["available"] is True for entry in listing["models"])
        if listing["source"] == "provider" and not found:
            raise SelectionError(
                "model_not_found",
                messages.VLM_SELECT_MODEL_NOT_FOUND.format(model=choice.model, provider=choice.provider, role=role),
            )
        if validation_of(choice)[0] in NEEDS_CONFIRMATION and not recent_tests.fresh(MODEL_LIST_ROLES[role], choice):
            raise SelectionError(
                "test_required",
                messages.VLM_SELECT_TEST_REQUIRED.format(
                    model=choice.model, provider=choice.provider, role=role, seconds=cfg.VLM_TEST_FRESH_SECONDS
                ),
            )
