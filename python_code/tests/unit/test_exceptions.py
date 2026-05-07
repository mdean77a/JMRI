"""Unit tests for the JMRIError hierarchy."""

from __future__ import annotations

import pytest

from pyjmri.exceptions import (
    JMRIConnectionError,
    JMRIError,
    JMRIProtocolError,
    JMRIReconnectFailed,
    JMRIRequestTimeout,
    JMRIVersionUnsupported,
    LayoutEntityNotControllable,
    LayoutEntityNotFound,
    ThrottleAcquireFailed,
    ThrottleError,
    ThrottleReleased,
    WaitTimeout,
)

ALL_SUBCLASSES = [
    JMRIRequestTimeout,
    JMRIProtocolError,
    JMRIVersionUnsupported,
    LayoutEntityNotFound,
    LayoutEntityNotControllable,
    ThrottleError,
    ThrottleAcquireFailed,
    ThrottleReleased,
    WaitTimeout,
]


def test_jmri_connection_error_str_matches_fr35() -> None:
    exc = JMRIConnectionError(host="localhost", port=12080)
    assert str(exc) == (
        "could not connect to localhost:12080 — is JMRI running with the web server enabled?"
    )


def test_jmri_connection_error_str_ignores_message_arg() -> None:
    # __str__ always returns the FR35 actionable string regardless of message.
    exc = JMRIConnectionError("custom message", host="localhost", port=12080)
    assert str(exc) == (
        "could not connect to localhost:12080 — is JMRI running with the web server enabled?"
    )


def test_jmri_connection_error_exposes_host_and_port_attrs() -> None:
    exc = JMRIConnectionError(host="example.com", port=8080)
    assert exc.host == "example.com"
    assert exc.port == 8080
    assert exc.context == {"host": "example.com", "port": 8080}


def test_jmri_reconnect_failed_inherits_connection_error() -> None:
    exc = JMRIReconnectFailed(host="localhost", port=12080, attempts=10)
    assert isinstance(exc, JMRIConnectionError)
    assert exc.context["attempts"] == 10


def test_jmri_version_unsupported_inherits_protocol_error() -> None:
    exc = JMRIVersionUnsupported(detected="5.10", required="5.14")
    assert isinstance(exc, JMRIProtocolError)
    assert exc.context == {"detected": "5.10", "required": "5.14"}


def test_throttle_acquire_failed_inherits_throttle_error() -> None:
    exc = ThrottleAcquireFailed(address=12)
    assert isinstance(exc, ThrottleError)


def test_throttle_released_inherits_throttle_error() -> None:
    exc = ThrottleReleased()
    assert isinstance(exc, ThrottleError)


def test_wait_timeout_caught_as_timeout_error() -> None:
    with pytest.raises(TimeoutError):
        raise WaitTimeout("timed out", entity="sensor:1")


def test_wait_timeout_caught_as_jmri_error() -> None:
    with pytest.raises(JMRIError):
        raise WaitTimeout("timed out", entity="sensor:1")


def test_base_jmri_error_str_with_context_and_message() -> None:
    exc = JMRIError("bad shape", endpoint="/json/turnout")
    assert str(exc) == "bad shape [endpoint='/json/turnout']"


def test_base_jmri_error_str_with_only_context() -> None:
    exc = JMRIError(endpoint="/json/turnout", status=500)
    assert str(exc) == "[endpoint='/json/turnout', status=500]"


def test_base_jmri_error_str_with_no_context() -> None:
    exc = JMRIError("naked message")
    assert str(exc) == "naked message"


@pytest.mark.parametrize("cls", ALL_SUBCLASSES)
def test_subclasses_caught_by_jmri_error(cls: type[JMRIError]) -> None:
    with pytest.raises(JMRIError):
        if cls is WaitTimeout:
            raise cls("t")
        elif cls is JMRIVersionUnsupported:
            raise cls()
        else:
            raise cls()


def test_cause_chaining_preserved() -> None:
    original = ConnectionRefusedError("boom")
    try:
        try:
            raise original
        except ConnectionRefusedError as e:
            raise JMRIConnectionError(host="localhost", port=12080) from e
    except JMRIConnectionError as wrapped:
        assert wrapped.__cause__ is original


def test_context_accepts_arbitrary_keyword_diagnostics() -> None:
    exc = JMRIProtocolError(
        "missing field",
        endpoint="/json/turnout/NT400",
        missing_keys=["userName"],
        status=200,
    )
    assert exc.context["endpoint"] == "/json/turnout/NT400"
    assert exc.context["missing_keys"] == ["userName"]
    assert exc.context["status"] == 200
