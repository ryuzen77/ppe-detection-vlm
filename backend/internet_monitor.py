"""T72: status internet tersimpan; klasifikasi murni terpisah dari probe soket."""

import errno
import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from statistics import median
from typing import Optional

import httpx

from . import messages
from .config import cfg

NORMAL, SLOW, DISCONNECTED = "normal", "lambat", "putus"


def _error_codes(*names):
    return {
        value for name in names for alias in (name, f"WSA{name}") if (value := getattr(errno, alias, None)) is not None
    }


NO_ROUTE_ERRORS = _error_codes("ENETUNREACH", "EHOSTUNREACH")
CONNECTION_ERRORS = NO_ROUTE_ERRORS | _error_codes("ENETDOWN", "ECONNREFUSED", "ECONNRESET", "ETIMEDOUT")
MILLISECONDS_PER_SECOND = 1000
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProbeResult:
    samples_ms: tuple[Optional[float], ...]
    route_available: bool = True


def classify(result: ProbeResult, slow_ms: float) -> tuple[str, Optional[float]]:
    connected = [sample for sample in result.samples_ms if sample is not None]
    latency = median(connected) if connected else None
    if not result.route_available or latency is None:
        return DISCONNECTED, latency
    if len(connected) != len(result.samples_ms) or latency > slow_ms:
        return SLOW, latency
    return NORMAL, latency


class Confirmation:
    def __init__(self, state: str = NORMAL):
        self.state, self.pending, self.streak = state, state, 0

    def observe(self, candidate: str, required: int, connection_failure: bool = False) -> str:
        self.streak = self.streak + 1 if candidate == self.pending else 1
        self.pending = candidate
        if self.streak >= required or (connection_failure and candidate == DISCONNECTED):
            self.state = candidate
        return self.state


def is_connection_failure(error: Optional[BaseException]) -> bool:
    visited = set()
    while error is not None and id(error) not in visited:
        visited.add(id(error))
        if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError)):
            return True
        if isinstance(error, OSError) and _has_code(error, CONNECTION_ERRORS):
            return True
        error = error.__cause__ or error.__context__
    return False


def _has_code(error: OSError, codes: set) -> bool:
    return error.errno in codes or getattr(error, "winerror", None) in codes


def _address(target: tuple[str, int]) -> tuple[int, tuple]:
    host, port = target
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    socket.inet_pton(family, host)  # Alamat numerik saja: batas waktu tidak disandera resolver DNS.
    return family, (host, port)


def route_available(targets: tuple) -> bool:
    for target in targets:
        try:
            family, address = _address(target)
            with socket.socket(family, socket.SOCK_DGRAM) as conn:
                conn.settimeout(cfg.INTERNET_CHECK_TIMEOUT_SECONDS)
                conn.connect(address)  # UDP connect hanya memilih rute; tidak mengirim paket.
            return True
        except OSError as error:
            if not _has_code(error, NO_ROUTE_ERRORS):
                return True  # Kegagalan lain diputuskan dari TCP, bukan dianggap tidak ada rute.
    return False


def tcp_probe(target: tuple[str, int]) -> Optional[float]:
    start = time.monotonic()
    try:
        family, address = _address(target)
        with socket.socket(family, socket.SOCK_STREAM) as conn:
            conn.settimeout(cfg.INTERNET_CHECK_TIMEOUT_SECONDS)
            conn.connect(address)
        return (time.monotonic() - start) * MILLISECONDS_PER_SECOND
    except OSError:
        return None


def probe_internet() -> ProbeResult:
    targets = cfg.INTERNET_CHECK_TARGETS
    if not route_available(targets):
        return ProbeResult((), False)
    deadline = time.monotonic() + cfg.INTERNET_CHECK_TIMEOUT_SECONDS
    pool = ThreadPoolExecutor(max_workers=max(1, len(targets)), thread_name_prefix="InternetProbe")
    try:
        futures = [pool.submit(tcp_probe, target) for target in targets]
        samples = []
        for future in futures:
            try:
                samples.append(future.result(timeout=max(0, deadline - time.monotonic())))
            except TimeoutError:
                samples.append(None)
        return ProbeResult(tuple(samples))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


class InternetMonitor:
    def __init__(self, probe=probe_internet, on_change=None):
        self._probe, self._on_change = probe, on_change
        self._condition = threading.Condition()
        self._wake, self._stop = threading.Event(), threading.Event()
        self._thread = None
        self._enabled = False
        self._generation = 0
        self._requested = self._completed = 0
        self._confirmation = Confirmation()
        self._status = {"state": None, "median_ms": None, "checked_at": None}

    def configure(self, enabled: bool):
        with self._condition:
            self._generation += 1
            self._enabled = enabled
            self._confirmation = Confirmation()
            self._status = {"state": NORMAL if enabled else None, "median_ms": None, "checked_at": None}
            self._requested = self._completed = 0
        self._notify()

    def status(self) -> dict:
        with self._condition:
            return dict(self._status)

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            self._wake.set()
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="InternetMonitor", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=cfg.THREAD_STOP_TIMEOUT_SECONDS)

    def request_check(self) -> dict:
        with self._condition:
            if not self._enabled:
                return dict(self._status)
            self._requested += 1
            ticket = self._requested
            self._wake.set()
            self._condition.wait_for(
                lambda: self._completed >= ticket or self._stop.is_set(), timeout=cfg.INTERNET_CHECK_TIMEOUT_SECONDS
            )
            return dict(self._status)

    def check_once(self):
        with self._condition:
            if not self._enabled:
                return
            generation = self._generation
        try:
            result = self._probe()
        except Exception as error:
            logger.warning(messages.LOG_INTERNET_PROBE_FAILED.format(error=type(error).__name__))
            result = ProbeResult(())
        self._accept_result(result, generation)

    def _accept_result(self, result: ProbeResult, generation: int):
        candidate, latency = classify(result, cfg.INTERNET_SLOW_MS)
        with self._condition:
            if not self._enabled or generation != self._generation:
                return
            previous = self._confirmation.state
            state = self._confirmation.observe(
                candidate, cfg.INTERNET_CONFIRM_CHECKS, self._requested > self._completed
            )
            self._status = {
                "state": state,
                "median_ms": latency,
                "checked_at": time.strftime(cfg.TELEMETRY_TIME_FORMAT),
            }
            self._completed = self._requested
            self._wake.clear()
            self._condition.notify_all()
        if state != previous:
            logger.info(messages.LOG_INTERNET_STATE.format(state=state, median_ms=latency))
        self._notify()

    def _notify(self):
        if self._on_change is not None:
            self._on_change(self.status())

    def _run(self):
        while not self._stop.is_set():
            self._wake.clear()
            self.check_once()
            self._wake.wait(cfg.INTERNET_CHECK_INTERVAL_SECONDS)
