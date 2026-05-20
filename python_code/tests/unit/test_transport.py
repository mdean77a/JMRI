"""Unit tests for the HTTP transport boundary.

Uses :class:`httpx.MockTransport` to inject failures and responses
without touching the network. Mocks httpx itself, not JMRI.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from pyjmri._transport import HTTPClient
from pyjmri.exceptions import (
    JMRIConnectionError,
    JMRIProtocolError,
    JMRIRequestTimeout,
    LayoutEntityNotControllable,
    LayoutEntityNotFound,
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


# --- HTTPClient.command() (Story 4.1) ---


async def test_command_200_returns_none() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        captured["content_type"] = request.headers.get("content-type")
        return httpx.Response(
            200,
            json={"type": "turnout", "data": {"name": "NT9", "state": 4}},
        )

    client = _client(httpx.MockTransport(handler))
    try:
        result = await client.command("turnout", "NT9", {"state": 4})
    finally:
        await client.aclose()

    assert result is None
    assert captured["method"] == "POST"
    assert captured["url"] == "http://localhost:12080/json/v5/turnout/NT9"
    assert captured["body"] == {
        "type": "turnout",
        "data": {"name": "NT9", "state": 4},
    }
    assert captured["content_type"] is not None
    assert captured["content_type"].startswith("application/json")


async def test_command_204_also_treated_as_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = _client(httpx.MockTransport(handler))
    try:
        result = await client.command("turnout", "NT9", {"state": 2})
    finally:
        await client.aclose()
    assert result is None


async def test_command_url_quotes_special_characters_in_name() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"type": "memory", "data": {"name": "IM:AUTO:0001"}})

    client = _client(httpx.MockTransport(handler))
    try:
        await client.command("memory", "IM:AUTO:0001", {"value": "hello"})
    finally:
        await client.aclose()

    # Colons in the name must be %-encoded in the URL path
    assert "IM%3AAUTO%3A0001" in captured["url"]
    # But the body's "name" field carries the raw, unencoded name
    assert captured["body"]["data"]["name"] == "IM:AUTO:0001"
    assert captured["body"]["data"]["value"] == "hello"


async def test_command_connect_error_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(JMRIConnectionError) as exc_info:
            await client.command("turnout", "NT9", {"state": 4})
    finally:
        await client.aclose()
    assert isinstance(exc_info.value.__cause__, httpx.ConnectError)


async def test_command_timeout_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(JMRIRequestTimeout) as exc_info:
            await client.command("turnout", "NT9", {"state": 4})
    finally:
        await client.aclose()
    assert exc_info.value.context["path"] == "/json/v5/turnout/NT9"
    assert isinstance(exc_info.value.__cause__, httpx.TimeoutException)


async def test_command_other_transport_error_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("connection reset", request=request)

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(JMRIConnectionError) as exc_info:
            await client.command("turnout", "NT9", {"state": 4})
    finally:
        await client.aclose()
    assert exc_info.value.context["error_type"] == "ReadError"


async def test_command_404_with_jmri_error_envelope_raises_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "type": "error",
                "data": {"code": 404, "message": 'Object type turnout named "NT9" not found.'},
            },
        )

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(LayoutEntityNotFound) as exc_info:
            await client.command("turnout", "NT9", {"state": 4})
    finally:
        await client.aclose()
    ctx = exc_info.value.context
    assert ctx["entity_type"] == "turnout"
    assert ctx["name"] == "NT9"
    assert "not found" in ctx["jmri_message"]
    assert ctx["status"] == 404


async def test_command_400_with_jmri_error_envelope_raises_not_controllable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "type": "error",
                "data": {
                    "code": 400,
                    "message": "Attempting to set object type turnout to unknown state 99.",
                },
            },
        )

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(LayoutEntityNotControllable) as exc_info:
            await client.command("turnout", "NT9", {"state": 99})
    finally:
        await client.aclose()
    ctx = exc_info.value.context
    assert ctx["entity_type"] == "turnout"
    assert ctx["name"] == "NT9"
    assert ctx["status"] == 400


async def test_command_409_with_jmri_error_envelope_raises_not_controllable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "type": "error",
                "data": {"code": 409, "message": "Entity locked by Dispatcher section."},
            },
        )

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(LayoutEntityNotControllable):
            await client.command("turnout", "NT9", {"state": 4})
    finally:
        await client.aclose()


async def test_command_non_2xx_without_envelope_raises_protocol_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(JMRIProtocolError) as exc_info:
            await client.command("turnout", "NT9", {"state": 4})
    finally:
        await client.aclose()
    assert exc_info.value.context["status"] == 500


async def test_command_502_with_envelope_still_protocol_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={"type": "error", "data": {"code": 502, "message": "upstream"}},
        )

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(JMRIProtocolError) as exc_info:
            await client.command("turnout", "NT9", {"state": 4})
    finally:
        await client.aclose()
    assert exc_info.value.context["status"] == 502
    assert exc_info.value.context["jmri_message"] == "upstream"
