"""Perakitan prompt dan metadata profil VLM, tanpa pemanggilan penyedia."""

import logging
from typing import Optional

from ..config import cfg
from .. import messages, ppe_rules
from . import selection as vlm_selection
from ..vlm_providers import profiles as vlm_profiles

logger = logging.getLogger(__name__)
USER_PROMPT = messages.VLM_USER_PROMPT


def build_system_prompt(items=None, zoom: bool = False) -> str:
    """Prompt inspektur K3, dirakit dari item APD yang sedang aktif.

    Sebelumnya prompt ini ditulis tangan sehingga setiap perubahan item APD
    harus disunting manual di sini, terpisah dari tempat lain yang menyimpan
    daftar item yang sama. Kini dirakit ulang setiap kali operator menghidupkan
    atau mematikan item, jadi item mati tidak pernah ditanyakan ke model.
    """
    items = items if items is not None else ppe_rules.get_active_items()
    prompt = messages.VLM_SYSTEM_PROMPT.format(
        rules=ppe_rules.build_prompt_rules(items),
        json_shape=ppe_rules.build_json_shape(items),
    )
    return prompt + (_zoom_note() if zoom else "")


def _zoom_note() -> str:
    """Penjelas panel perbesaran (T86), hanya untuk gambar berpanel (lihat vlm_selection.uses_zoom)."""
    return messages.VLM_ZOOM_NOTE if cfg.VLM_ZOOM_HAND_PANELS else messages.VLM_ZOOM_NOTE_HEAD


def confirmation_prompts(item, zoom: bool = False) -> tuple[str, str]:
    """(prompt sistem, prompt pengguna) konfirmasi kedua satu larangan (T58)."""
    return messages.VLM_CONFIRM_SYSTEM_PROMPT + (
        _zoom_note() if zoom else ""
    ), f"{item.confirm_prompt}\n{messages.VLM_CONFIRM_SHAPE}"


def parse_confirmation(data) -> tuple[bool, str]:
    """(larangan benar terlihat, benda yang disebut model). Selain `true` tegas = tidak terlihat."""
    if not isinstance(data, dict):
        return False, ""
    return data.get("detected") is True, str(data.get("seen") or "")


def thinking_option(provider_name: str, level: str) -> Optional[str]:
    """Nilai mode berpikir untuk adaptor; peringatan bila tidak dikenal/tidak didukung (T39b)."""
    if level not in vlm_profiles.THINKING_LEVELS:
        logger.warning(
            messages.VLM_THINKING_INVALID.format(value=level, choices=", ".join(vlm_profiles.THINKING_LEVELS))
        )
        level = "off"
    value = vlm_profiles.thinking_value(provider_name, level)
    if value is None and level != "off":
        logger.warning(messages.VLM_THINKING_UNSUPPORTED.format(value=level, provider=provider_name))
    return value


def profile_warnings(provider_name: str, model: str, who: str) -> list[str]:
    """Peringatan katalog profil & validasi model. Gerbang tetap menyala (keputusan pengguna)."""
    warnings = []
    profile = vlm_profiles.get_profile(provider_name)
    if profile is not None and profile.support == vlm_profiles.EXPERIMENTAL:
        warnings.append(messages.VLM_PROVIDER_EXPERIMENTAL.format(who=who))
    version = vlm_selection.prompt_version_for(provider_name)
    status = vlm_profiles.validation_status(provider_name, model, version)
    record = vlm_profiles.find_validation(provider_name, model, version)
    if status == vlm_profiles.UNVALIDATED:
        warnings.append(messages.VLM_MODEL_UNVALIDATED.format(who=who))
        return warnings
    assert record is not None or status == vlm_profiles.VALIDATED, "status lain berasal dari catatan validasi"
    if status == vlm_profiles.UNSAFE and record is not None:
        warnings.append(messages.VLM_MODEL_UNSAFE.format(who=who, missed=record.missed, photos=record.photos))
    elif status == vlm_profiles.OUTDATED and record is not None:
        warnings.append(messages.VLM_MODEL_OUTDATED.format(who=who, old=record.prompt_version, current=version))
    elif status == vlm_profiles.PARTIAL and record is not None:
        warnings.append(messages.VLM_MODEL_PARTIAL.format(who=who, note=record.note))
    return warnings
