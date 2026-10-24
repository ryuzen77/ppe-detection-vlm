"""T96: hanya reset soket 10054 pada callback penutupan Proactor yang diabaikan."""

# ruff: noqa: F811
import io
import logging
import sys

import pytest

from backend import logging_setup as logs
from test_logging import configured, log_cfg  # noqa: F401 (fixture)

CALLBACK_MESSAGE = "Exception in callback " + logs.PROACTOR_CLOSE_CALLBACK + "(None)"


def error_record(error=None, module=logs.PROACTOR_MODULE, nested=False):
    error = error if error is not None else ConnectionResetError("reset soket tiruan")
    setattr(error, "winerror", logs.CONNECTION_RESET_WINERROR)
    namespace = {"__name__": module, "error": error}
    source = """
class _ProactorBasePipeTransport:
    def _call_connection_lost(self, exc):
        raise error
"""
    if nested:
        source = source.replace("raise error", "protocol_error()") + "\ndef protocol_error():\n    raise error\n"
    exec(compile(source, "proactor_test.py", "exec"), namespace)
    try:
        namespace["_ProactorBasePipeTransport"]()._call_connection_lost(None)
    except Exception:
        return logging.LogRecord(logs.ASYNCIO_LOGGER, logging.ERROR, __file__, 1, CALLBACK_MESSAGE, (), sys.exc_info())
    raise AssertionError("callback tiruan harus melempar")


def test_only_proactor_close_reset_is_filtered():
    record = error_record()
    assert logs.ProactorDisconnectFilter().filter(record) is False


@pytest.mark.parametrize(
    "change",
    [
        "logger",
        "level",
        "winerror",
        "no_winerror",
        "type",
        "module",
        "callback",
        "protocol",
        "no_exception",
        "no_traceback",
    ],
)
def test_other_asyncio_errors_remain_visible(change):
    record = error_record(
        error=OSError("galat tiruan") if change == "type" else None,
        module="backend.protocol" if change == "module" else logs.PROACTOR_MODULE,
        nested=change == "protocol",
    )
    assert record.exc_info is not None and record.exc_info[1] is not None
    if change == "logger":
        record.name = "backend.camera"
    elif change == "level":
        record.levelno = logging.WARNING
    elif change == "winerror":
        setattr(record.exc_info[1], "winerror", 10053)
    elif change == "no_winerror":
        delattr(record.exc_info[1], "winerror")
    elif change == "callback":
        record.msg = "Exception in callback another_callback(None)"
    elif change == "no_exception":
        record.exc_info = None
    elif change == "no_traceback":
        record.exc_info = (ConnectionResetError, record.exc_info[1], None)
    assert logs.ProactorDisconnectFilter().filter(record) is True


def test_filter_applies_before_queue_and_preserves_real_errors(configured):
    console = logs._listeners[0].handlers[0]
    assert isinstance(console, logging.StreamHandler)
    captured = io.StringIO()
    console.setStream(captured)
    logger = logging.getLogger(logs.ASYNCIO_LOGGER)
    logger.handle(error_record())
    other = error_record(nested=True)
    logger.handle(other)
    logs.stop_logging()
    output = captured.getvalue()
    text = (configured.LOG_DIR / configured.LOG_FILE).read_text(encoding="utf-8")
    assert output.count(CALLBACK_MESSAGE) == text.count(CALLBACK_MESSAGE) == 1
    assert "protocol_error" in output and "Traceback" in text
    assert not any(isinstance(item, logs.ProactorDisconnectFilter) for item in logger.filters)
