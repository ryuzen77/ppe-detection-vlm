"""Kebijakan akses terpisah dari hasil APD; pembacaan jalur inspeksi tanpa I/O disk."""

import threading

from . import face_identity, runtime_settings

SETTINGS_KEY = "require_registered"
UNREGISTERED = "unregistered"
FR_UNAVAILABLE = "fr_unavailable"
POLICY_CHANGED = "registration_policy_changed"


def fr_ready() -> bool:
    identifier = face_identity.identifier
    return getattr(identifier, "ready", identifier.store.face_ready)()


class RegistrationPolicy:
    def __init__(self):
        self._lock = threading.Lock()
        self._enabled = runtime_settings.load().get(SETTINGS_KEY) is True
        if self._enabled:
            face_identity.identifier.check_ready()

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def save(self, enabled: bool) -> bool:
        with self._lock:
            if not runtime_settings.update(SETTINGS_KEY, enabled):
                return False
            self._enabled = enabled
            return True

    def status(self) -> dict:
        return {"enabled": self.enabled, "fr_ready": fr_ready()}


policy = RegistrationPolicy()
