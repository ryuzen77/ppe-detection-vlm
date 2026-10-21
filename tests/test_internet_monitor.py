"""T72: probe soket tiruan, konfirmasi status, dan cek segera yang berbatas waktu."""

import errno
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

import httpx
import pytest

from backend import internet_monitor as net
from backend.config import cfg


@pytest.mark.parametrize(
    "samples,route,expected,latency",
    [
        ((20, 40, 60), True, net.NORMAL, 40),
        ((600, 800), True, net.SLOW, 700),
        ((200, 200), True, net.NORMAL, 200),
        ((200.01, 200.01), True, net.SLOW, 200.01),
        ((500, 500), True, net.SLOW, 500),
        ((20, None, 40), True, net.SLOW, 30),
        ((None, None), True, net.DISCONNECTED, None),
        ((20, 30), False, net.DISCONNECTED, 25),
    ],
)
def test_classification_is_pure(samples, route, expected, latency):
    assert net.classify(net.ProbeResult(samples, route), 200) == (expected, latency)


def test_monitor_uses_configured_200_ms_threshold_without_network(monkeypatch):
    monkeypatch.setattr(cfg, "INTERNET_SLOW_MS", 200)
    monitor = net.InternetMonitor(probe=lambda: net.ProbeResult((200, 200)))
    monitor.configure(True)
    monitor.check_once()
    assert monitor.status()["state"] == net.NORMAL
    monitor._probe = lambda: net.ProbeResult((201, 201))
    for _ in range(cfg.INTERNET_CONFIRM_CHECKS):
        monitor.check_once()
    assert monitor.status()["state"] == net.SLOW and monitor.status()["median_ms"] == 201


def test_two_consecutive_checks_and_recovery():
    state = net.Confirmation()
    assert state.observe(net.SLOW, 2) == net.NORMAL
    assert state.observe(net.DISCONNECTED, 2) == net.NORMAL
    assert state.observe(net.DISCONNECTED, 2) == net.DISCONNECTED
    assert state.observe(net.NORMAL, 2) == net.DISCONNECTED
    assert state.observe(net.NORMAL, 2) == net.NORMAL


def test_connection_failure_immediately_confirms_only_disconnection():
    state = net.Confirmation()
    assert state.observe(net.SLOW, 2, connection_failure=True) == net.NORMAL
    assert state.observe(net.DISCONNECTED, 2, connection_failure=True) == net.DISCONNECTED


@pytest.mark.parametrize(
    "error,expected",
    [
        (httpx.ConnectError("tiruan"), True),
        (httpx.ConnectTimeout("tiruan"), True),
        (OSError(errno.ENETUNREACH, "tiruan"), True),
        (OSError(errno.EHOSTUNREACH, "tiruan"), True),
        (RuntimeError("httpx.ConnectError 429 connection refused"), False),
        (httpx.ReadTimeout("tiruan"), False),
        (TimeoutError(), False),
        (ValueError("JSON rusak"), False),
    ],
)
def test_connection_errors_use_type_instead_of_text(error, expected):
    assert net.is_connection_failure(error) is expected


def test_wrapped_connection_failure_and_cyclic_exception_chain():
    error = RuntimeError("pembungkus SDK")
    error.__cause__ = httpx.ConnectError("tiruan")
    assert net.is_connection_failure(error)
    error.__cause__ = error
    assert not net.is_connection_failure(error)


def test_windows_socket_error_aliases_are_supported():
    code = getattr(errno, "WSAENETUNREACH", errno.ENETUNREACH)
    assert code in net.NO_ROUTE_ERRORS
    error = OSError(0, "tiruan")
    error.winerror = code
    assert net.is_connection_failure(error)


class FakeSocket:
    def __init__(self, family, kind, errors, calls, barrier=None):
        self.kind, self.errors, self.calls, self.barrier = kind, errors, calls, barrier

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def settimeout(self, timeout):
        assert timeout == cfg.INTERNET_CHECK_TIMEOUT_SECONDS

    def connect(self, address):
        self.calls.append((self.kind, address))
        if self.kind == socket.SOCK_STREAM and self.barrier is not None:
            self.barrier.wait(timeout=1)
        error = self.errors.get((self.kind, address[0]))
        if error is not None:
            raise error

    def send(self, *args):
        pytest.fail("probe UDP tidak boleh mengirim paket")


def _sockets(monkeypatch, errors=None, barrier=None):
    calls = []
    monkeypatch.setattr(
        net.socket, "socket", lambda family, kind: FakeSocket(family, kind, errors or {}, calls, barrier)
    )
    return calls


@pytest.mark.parametrize("code", [errno.ENETUNREACH, errno.EHOSTUNREACH])
def test_no_route_uses_udp_without_packets_and_skips_tcp(monkeypatch, code):
    errors = {(socket.SOCK_DGRAM, host): OSError(code, "tiruan") for host, _ in cfg.INTERNET_CHECK_TARGETS}
    calls = _sockets(monkeypatch, errors)
    assert net.classify(net.probe_internet(), cfg.INTERNET_SLOW_MS)[0] == net.DISCONNECTED
    assert all(kind == socket.SOCK_DGRAM for kind, _ in calls)


def test_tcp_targets_run_in_parallel(monkeypatch):
    targets = cfg.INTERNET_CHECK_TARGETS
    calls = _sockets(monkeypatch, barrier=threading.Barrier(len(targets)))
    assert net.classify(net.probe_internet(), cfg.INTERNET_SLOW_MS)[0] == net.NORMAL
    assert sum(kind == socket.SOCK_STREAM for kind, _ in calls) == len(targets)


@pytest.mark.parametrize("failed,expected", [(1, net.SLOW), (3, net.DISCONNECTED)])
def test_failed_tcp_connections_are_classified(monkeypatch, failed, expected):
    errors = {(socket.SOCK_STREAM, host): TimeoutError() for host, _ in cfg.INTERNET_CHECK_TARGETS[:failed]}
    _sockets(monkeypatch, errors)
    assert net.classify(net.probe_internet(), cfg.INTERNET_SLOW_MS)[0] == expected


def test_monitor_disabled_does_no_io_and_reports_null():
    monitor = net.InternetMonitor(probe=lambda: pytest.fail("I/O tidak boleh dijalankan"))
    monitor.configure(False)
    monitor.check_once()
    assert monitor.request_check() == {"state": None, "median_ms": None, "checked_at": None}


def test_stale_probe_from_old_configuration_is_discarded():
    monitor = net.InternetMonitor()
    monitor.configure(True)
    old_generation = monitor._generation
    monitor.configure(False)
    monitor.configure(True)
    monitor._accept_result(net.ProbeResult((None, None)), old_generation)
    assert monitor.status() == {"state": net.NORMAL, "median_ms": None, "checked_at": None}


def test_immediate_check_is_bounded_and_coalesces_requests(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def probe():
        entered.set()
        release.wait(1)
        return net.ProbeResult((None, None))

    monkeypatch.setattr(cfg, "INTERNET_CHECK_TIMEOUT_SECONDS", 0.05)
    monitor = net.InternetMonitor(probe=probe)
    monitor.configure(True)
    monitor.start()
    try:
        assert entered.wait(1)
        start = perf_counter()
        with ThreadPoolExecutor(max_workers=5) as pool:
            statuses = list(pool.map(lambda _: monitor.request_check(), range(5)))
        assert perf_counter() - start < 0.5
        assert all(status["state"] == net.NORMAL for status in statuses)
        release.set()
        monitor.stop()
        assert monitor.status()["state"] == net.DISCONNECTED
    finally:
        release.set()
        monitor.stop()
