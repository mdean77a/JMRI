"""Unit tests for the HTTP transport boundary.

Uses :class:`httpx.MockTransport` to inject failures and responses
without touching the network. Mocks httpx itself, not JMRI.
"""

from __future__ import annotations

import httpx
import pytest

from pyjmri._transport import HTTPClient
from pyjmri.exceptions import (
    JMRIConnectionError,
    JMRIProtocolError,
    JMRIRequestTimeout,
)


def _client(handler: httpx.MockTransport) -> HTTPClient:
    return HTTPClient(
        host="localhost",
        port=12080,
        request_timeout=1.0,
        transport=handler,
    )


async def test_connect_error_wrapped_as_jmri_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    transport = httpx.MockTransport(handler)
    client = _client(transport)
    try:
        with pytest.raises(JMRIConnectionError) as exc_info:
            await client.get("/json/v5")
    finally:
        await client.aclose()

    exc = exc_info.value
    assert exc.host == "localhost"
    assert exc.port == 12080
    assert isinstance(exc.__cause__, httpx.ConnectError)


async def test_timeout_exception_wrapped_as_request_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(JMRIRequestTimeout) as exc_info:
            await client.get("/json/v5")
    finally:
        await client.aclose()

    assert exc_info.value.context["path"] == "/json/v5"
    assert isinstance(exc_info.value.__cause__, httpx.TimeoutException)


async def test_other_transport_error_wrapped_as_jmri_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("connection reset", request=request)

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(JMRIConnectionError) as exc_info:
            await client.get("/json/v5/turnout")
    finally:
        await client.aclose()

    exc = exc_info.value
    assert exc.host == "localhost"
    assert exc.port == 12080
    assert exc.context["error_type"] == "ReadError"
    assert isinstance(exc.__cause__, httpx.ReadError)


async def test_non_200_raises_protocol_error_with_status_in_context() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(JMRIProtocolError) as exc_info:
            await client.get("/json/v5/turnout/UNKNOWN")
    finally:
        await client.aclose()

    assert exc_info.value.context["status"] == 404
    assert exc_info.value.context["path"] == "/json/v5/turnout/UNKNOWN"


async def test_non_json_body_raises_protocol_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="this is not JSON")

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(JMRIProtocolError):
            await client.get("/json/v5")
    finally:
        await client.aclose()


async def test_non_jmri_json_shape_raises_protocol_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(JMRIProtocolError) as exc_info:
            await client.get("/json/v5/turnout")
    finally:
        await client.aclose()

    assert exc_info.value.context["actual_type"] == "list"


async def test_top_level_string_raises_protocol_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json="surprise")

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(JMRIProtocolError) as exc_info:
            await client.get("/json/v5/version")
    finally:
        await client.aclose()

    assert exc_info.value.context["actual_type"] == "str"


async def test_200_with_dict_returns_payload_unchanged() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"type": "version", "data": {"version": "5.14"}},
        )

    client = _client(httpx.MockTransport(handler))
    try:
        payload = await client.get("/json/v5/turnout/NT400")
    finally:
        await client.aclose()

    assert payload == {"type": "version", "data": {"version": "5.14"}}


async def test_200_with_list_of_objects_returns_array_unchanged() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[{"type": "version", "data": {"5.4.0": "v5"}}],
        )

    client = _client(httpx.MockTransport(handler))
    try:
        payload = await client.get("/json/v5/version")
    finally:
        await client.aclose()

    assert payload == [{"type": "version", "data": {"5.4.0": "v5"}}]


async def test_aclose_is_idempotent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = _client(httpx.MockTransport(handler))
    await client.aclose()
    await client.aclose()  # second call must not raise
