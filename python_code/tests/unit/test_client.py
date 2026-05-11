"""Unit tests for ``Client`` URL parsing and async-lifecycle behavior."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pyjmri import Client, ClientConfig, JMRIConnectionError, ReconnectConfig
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
        reconnect=ReconnectConfig(initial_delay=1.0, max_attempts=5),
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
