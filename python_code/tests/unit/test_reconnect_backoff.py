"""Unit tests for :meth:`pyjmri._transport.WSConnection._process_exception`.

Story 3.1 design pivot (2026-05-12): the ``websockets`` v16 API
``process_exception(exc) -> Exception | None`` controls retryable-vs-
fatal only; delay timing is the library's internal ``backoff()``. So
this file tests the retry-vs-give-up decision and the attempt counter,
not delay math. Naming kept as ``test_reconnect_backoff.py`` per
Story 3.1's File List even though delay-math tests are no longer
applicable (see Dev Agent Record → Debug Log).
"""

from __future__ import annotations

import pytest

from pyjmri._transport import WSConnection
from pyjmri.client import ReconnectConfig


def _make_ws(*, max_attempts: int | None = None) -> WSConnection:
    """Construct a bare WSConnection for direct hook testing.

    Does not call ``run()`` — no real network, no real ``websockets.connect()``.
    """
    return WSConnection(
        host="localhost",
        port=12080,
        reconnect_config=ReconnectConfig(max_attempts=max_attempts),
    )


def test_process_exception_returns_none_on_first_failure_when_retry_forever() -> None:
    ws = _make_ws(max_attempts=None)
    result = ws._process_exception(OSError("boom"))
    assert result is None
    assert ws._attempt == 1
    assert ws._give_up_cause is None


def test_process_exception_returns_none_indefinitely_when_max_attempts_none() -> None:
    ws = _make_ws(max_attempts=None)
    for i in range(1, 1001):
        assert ws._process_exception(OSError("boom")) is None
        assert ws._attempt == i
    assert ws._give_up_cause is None


def test_process_exception_increments_attempt_on_each_call() -> None:
    ws = _make_ws(max_attempts=None)
    for expected in range(1, 6):
        ws._process_exception(OSError("transient"))
        assert ws._attempt == expected


def test_process_exception_returns_none_below_max_attempts() -> None:
    ws = _make_ws(max_attempts=3)
    assert ws._process_exception(OSError("1")) is None  # attempt 1
    assert ws._process_exception(OSError("2")) is None  # attempt 2
    assert ws._attempt == 2
    assert ws._give_up_cause is None


def test_process_exception_returns_exception_at_max_attempts() -> None:
    ws = _make_ws(max_attempts=3)
    ws._process_exception(OSError("1"))  # attempt 1, retryable
    ws._process_exception(OSError("2"))  # attempt 2, retryable
    final = OSError("3")
    result = ws._process_exception(final)  # attempt 3, fatal
    assert result is final
    assert ws._attempt == 3
    assert ws._give_up_cause is final


def test_process_exception_records_give_up_cause_for_jmri_reconnect_failed() -> None:
    ws = _make_ws(max_attempts=1)
    cause = ConnectionRefusedError("nope")
    assert ws._process_exception(cause) is cause
    assert ws._give_up_cause is cause


@pytest.mark.parametrize("max_attempts", [1, 2, 5, 10])
def test_process_exception_max_attempts_is_honored_exactly(max_attempts: int) -> None:
    ws = _make_ws(max_attempts=max_attempts)
    for i in range(1, max_attempts):
        assert ws._process_exception(OSError(f"attempt {i}")) is None
    final = OSError(f"attempt {max_attempts}")
    assert ws._process_exception(final) is final
