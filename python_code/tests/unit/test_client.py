"""Unit tests for ``Client`` URL parsing and async-lifecycle behavior."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pyjmri import Client, ClientConfig, JMRIConnectionError, ReconnectConfig
from pyjmri._transport import WSConnection
from pyjmri.client import _parse_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("localhost:12080", ("localhost", 12080, "http")),
        ("http://localhost:12080", ("localhost", 12080, "http")),
        ("https://example.com:12080", ("example.com", 12080, "https")),
        ("ws://localhost:12080/json", ("localhost", 12080, "http")),
        ("wss://secure.example.com:443/json", ("secure.example.com", 443, "https")),
        ("127.0.0.1:8080", ("127.0.0.1", 8080, "http")),
    ],
)
def test_parse_url_happy_paths(url: str, expected: tuple[str, int, str]) -> None:
    assert _parse_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "localhost",
        "http://",
        "http://localhost",
        "://localhost:12080",
    ],
)
def test_parse_url_rejects_invalid_input(url: str) -> None:
    with pytest.raises(ValueError):
        _parse_url(url)


def test_parse_url_rejects_unsupported_scheme() -> None:
    with pytest.raises(ValueError) as exc_info:
        _parse_url("ftp://localhost:12080")
    assert "unsupported URL scheme" in str(exc_info.value)


def test_ws_connection_url_uses_wss_when_secure() -> None:
    ws = WSConnection(
        host="secure.example.com",
        port=443,
        reconnect_config=ReconnectConfig(),
        secure=True,
    )
    assert ws.url == "wss://secure.example.com:443/json/"


def test_ws_connection_url_uses_ws_by_default() -> None:
    ws = WSConnection(
        host="localhost",
        port=12080,
        reconnect_config=ReconnectConfig(),
    )
    assert ws.url == "ws://localhost:12080/json/"


def test_client_default_url_is_localhost_12080() -> None:
    client = Client()
    assert client._host == "localhost"
    assert client._port == 12080
    assert client._scheme == "http"


def test_client_default_config_has_expected_defaults() -> None:
    client = Client()
    assert client._config.request_timeout == 10.0
    assert isinstance(client._config.reconnect, ReconnectConfig)
    assert client._config.subscription_replay_timeout == 30.0


def test_client_accepts_custom_config() -> None:
    cfg = ClientConfig(
        request_timeout=2.5,
        reconnect=ReconnectConfig(max_attempts=5),
    )
    client = Client("localhost:12080", config=cfg)
    assert client._config.request_timeout == 2.5
    assert client._config.reconnect.max_attempts == 5


@pytest.mark.parametrize(
    "url",
    [
        "localhost:12080",
        "http://localhost:12080",
        "ws://localhost:12080/json",
    ],
)
def test_client_accepts_documented_url_forms(url: str) -> None:
    client = Client(url)
    assert client._host == "localhost"
    assert client._port == 12080


async def test_aenter_probes_version_and_aexit_closes(
    patch_http_factory: list[Any],
) -> None:
    async with Client() as jmri:
        assert jmri is not None

    fake = patch_http_factory[0]
    assert fake.probed == ["/json/v5/version"]
    assert fake.close_count == 1


async def test_aenter_failure_wraps_to_jmri_connection_error(
    patch_http_factory: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pyjmri import client as client_module

    class FailingHTTPClient:
        def __init__(self, **kwargs: Any) -> None:
            self.host = kwargs["host"]
            self.port = kwargs["port"]
            self.close_count = 0

        async def get(self, path: str) -> dict[str, Any]:
            err = JMRIConnectionError(host=self.host, port=self.port)
            err.__cause__ = httpx.ConnectError("refused")
            raise err

        async def aclose(self) -> None:
            self.close_count += 1

    constructed: list[FailingHTTPClient] = []
    original_init = FailingHTTPClient.__init__

    def capture_init(self: FailingHTTPClient, **kwargs: Any) -> None:
        original_init(self, **kwargs)
        constructed.append(self)

    monkeypatch.setattr(FailingHTTPClient, "__init__", capture_init)
    monkeypatch.setattr(client_module, "HTTPClient", FailingHTTPClient)

    with pytest.raises(JMRIConnectionError) as exc_info:
        async with Client() as _:
            pass  # pragma: no cover — should not reach

    exc = exc_info.value
    assert exc.host == "localhost"
    assert exc.port == 12080
    assert isinstance(exc.__cause__, httpx.ConnectError)
    # Failed __aenter__ must still close the partially-opened transport.
    assert constructed[0].close_count == 1


async def test_aexit_closes_transport_even_on_user_exception(
    patch_http_factory: list[Any],
) -> None:
    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        async with Client():
            raise Boom

    fake = patch_http_factory[0]
    assert fake.close_count == 1


async def test_request_timeout_is_passed_through_to_http_client(
    patch_http_factory: list[Any],
) -> None:
    async with Client(config=ClientConfig(request_timeout=4.2)):
        pass

    fake = patch_http_factory[0]
    assert fake.kwargs["request_timeout"] == 4.2


async def test_aenter_reentrant_raises_runtime_error(
    patch_http_factory: list[Any],
) -> None:
    client = Client()
    async with client:
        with pytest.raises(RuntimeError, match="already open"):
            await client.__aenter__()


async def test_aenter_https_passes_secure_to_ws_connection(
    patch_http_factory: list[Any],
) -> None:
    client = Client("https://localhost:12080")
    async with client:
        assert client._ws is not None
        assert client._ws.kwargs.get("secure") is True


async def test_aenter_establishes_websocket_alongside_http(
    patch_http_factory: list[Any],
) -> None:
    # AC2: Client.__aenter__ establishes both HTTP and WS.
    client = Client()
    async with client:
        assert client._http is not None
        assert client._ws is not None
        assert client._registry is not None
        # FakeWSConnection records that "first connect" succeeded.
        assert client._ws_connected is not None and client._ws_connected.is_set()


async def test_aenter_supervises_ws_run_inside_taskgroup(
    patch_http_factory: list[Any],
) -> None:
    # AC7: a single asyncio.TaskGroup supervises the WS receive loop.
    client = Client()
    async with client:
        assert client._tg is not None
        assert client._supervisor_task is not None
        assert not client._supervisor_task.done()  # still running
    # Exit cleanly: TaskGroup must have been closed.
    assert client._tg is None
    assert client._supervisor_task is None


async def test_aexit_cancels_supervisor_task_cleanly(
    patch_http_factory: list[Any],
) -> None:
    # AC7: __aexit__ cancels the supervisor; clean shutdown leaves no
    # uncancelled task behind.
    import asyncio

    client = Client()
    async with client:
        captured_task = client._supervisor_task
    assert captured_task is not None
    assert captured_task.done()
    # The fake supervisor swallows CancelledError and returns cleanly,
    # so done() is True without an exception.
    assert captured_task.cancelled() or captured_task.exception() is None
    # Sanity: no uncancelled tasks left after the Client closes.
    remaining = [t for t in asyncio.all_tasks() if not t.done()]
    # Filter out the currently-running test task itself.
    remaining = [t for t in remaining if t is not asyncio.current_task()]
    assert remaining == []


async def test_on_ws_message_is_a_stub_for_story_3_1(
    patch_http_factory: list[Any],
) -> None:
    # AC11: 3.1 ships a stub message handler. Story 3.2 wires real dispatch.
    client = Client()
    async with client:
        result = await client._on_ws_message(
            {"type": "turnout", "data": {"name": "NT1", "state": 2}}
        )
    assert result is None
