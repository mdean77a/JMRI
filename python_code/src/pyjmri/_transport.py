"""HTTP + WebSocket transport boundary.

The only module allowed to import or catch ``httpx`` or ``websockets``
exceptions. See architecture §Transport Layer and §Architectural
Boundaries.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx
import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import WebSocketException

from pyjmri.exceptions import (
    JMRIConnectionError,
    JMRIProtocolError,
    JMRIReconnectFailed,
    JMRIRequestTimeout,
    LayoutEntityNotControllable,
    LayoutEntityNotFound,
)

if TYPE_CHECKING:
    from pyjmri.client import ReconnectConfig

__all__ = ["HTTPClient", "WSConnection"]

logger = logging.getLogger("pyjmri.transport")
logger_reconnect = logging.getLogger("pyjmri.reconnect")

WS_PATH = "/json/"
"""JMRI's WebSocket endpoint path. The trailing slash matters — JMRI
302-redirects ``/json`` to ``/json/``, and the ``websockets`` library
cannot follow that redirect (the target uses ``http://`` scheme)."""

_PING_INTERVAL_SEC = 10.0
"""Keepalive ping interval. JMRI's ``hello`` envelope advertises a 13.5 s
heartbeat; staying below that with WS-protocol pings keeps the
connection alive without a JMRI-specific heartbeat envelope."""


class HTTPClient:
    """Async HTTP client wrapper around :class:`httpx.AsyncClient`.

    Catches ``httpx.*`` exceptions and re-raises them as
    :class:`~pyjmri.exceptions.JMRIError` subclasses with ``from e``. No
    other module in the package is allowed to do this.

    Args:
        host: JMRI host (e.g. ``"localhost"``).
        port: JMRI web-server port (e.g. ``12080``).
        scheme: Either ``"http"`` or ``"https"``. Defaults to ``"http"``.
        request_timeout: Per-request timeout in seconds.
        transport: Optional custom :class:`httpx.AsyncBaseTransport` for
            tests. Production callers leave this as ``None``.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        scheme: str = "http",
        request_timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._base_url = f"{scheme}://{host}:{port}"
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=request_timeout,
            transport=transport,
        )

    async def get(self, path: str) -> dict[str, Any] | list[dict[str, Any]]:
        """GET ``path`` and return the parsed JSON body.

        JMRI JSON v5 endpoints return either a single object
        (``GET /json/v5/<type>/<name>``) or an array of objects
        (``GET /json/v5/<type>``). Both shapes are returned as-is for
        the parsing layer (Story 2.2) to narrow.

        Raises:
            JMRIConnectionError: when the underlying socket cannot connect,
                or any other transport-level failure occurs (network errors,
                proxy errors, protocol errors at the transport layer).
            JMRIRequestTimeout: when the request exceeds ``request_timeout``.
            JMRIProtocolError: when the response is non-200, not JSON, or
                does not match the JMRI shape (object or array of objects).
        """
        try:
            response = await self._http.get(path)
        except httpx.TransportError as e:
            raise self._translate_httpx_error(e, path=path) from e

        if response.status_code != 200:
            raise JMRIProtocolError(
                "unexpected HTTP status",
                status=response.status_code,
                path=path,
            )

        try:
            payload = response.json()
        except ValueError as e:
            raise JMRIProtocolError(
                "response body was not valid JSON",
                path=path,
            ) from e

        if isinstance(payload, dict) or (
            isinstance(payload, list) and all(isinstance(item, dict) for item in payload)
        ):
            logger.debug(
                "HTTP GET %s -> %d",
                path,
                response.status_code,
                extra={"method": "GET", "path": path, "status": response.status_code},
            )
            return payload

        raise JMRIProtocolError(
            "response JSON was not a JMRI v5 entity (object or array of objects)",
            path=path,
            actual_type=type(payload).__name__,
        )

    async def command(
        self,
        entity_type: str,
        name: str,
        payload: dict[str, Any],
    ) -> None:
        """POST a state/value command to JMRI and return when JMRI acks.

        FR22 / FR37 discipline: JMRI's HTTP 2xx response means JMRI
        accepted the command into its model. It does NOT mean the
        physical layout has reached the commanded state — NCE is
        open-loop and the library never claims a state it did not
        observe. Story 4.2 layers a ``wait_for_jmri_state=True`` opt-in
        over this method for callers who want to await the WS echo.

        Args:
            entity_type: JMRI entity-type string (``"turnout"``,
                ``"light"``, ``"memory"``, ``"route"``).
            name: Entity system name; URL-encoded into the path.
            payload: Per-type body fragment merged into
                ``{"type", "data": {"name", **payload}}``. For state-
                bearing types pass ``{"state": <int>}``; for memory pass
                ``{"value": <str>}``.

        Raises:
            JMRIConnectionError: socket-level failure (transport error).
            JMRIRequestTimeout: request exceeded ``request_timeout``.
            JMRIProtocolError: JMRI returned a non-2xx with a non-error-
                envelope body, or a 2xx with a malformed body.
            LayoutEntityNotControllable: JMRI returned an error envelope
                indicating the entity is locked, refuses the command, or
                is otherwise not controllable.
            LayoutEntityNotFound: JMRI returned an error envelope
                indicating the entity name does not exist on JMRI's
                side.
        """
        path = f"/json/v5/{entity_type}/{quote(name, safe='')}"
        body = {"type": entity_type, "data": {"name": name, **payload}}
        try:
            response = await self._http.post(path, json=body)
        except httpx.TransportError as e:
            raise self._translate_httpx_error(e, path=path) from e

        status = response.status_code
        if 200 <= status < 300:
            logger.debug(
                "HTTP POST %s -> %d",
                path,
                status,
                extra={"method": "POST", "path": path, "status": status},
            )
            return None

        # Non-2xx — try to translate JMRI's error envelope.
        jmri_message = _extract_jmri_error_message(response)
        if jmri_message is None:
            raise JMRIProtocolError(
                "unexpected HTTP status from command",
                status=status,
                path=path,
            )
        if status == 404:
            raise LayoutEntityNotFound(
                entity_type=entity_type,
                name=name,
                jmri_message=jmri_message,
                status=status,
            )
        if status in (400, 403, 409):
            raise LayoutEntityNotControllable(
                entity_type=entity_type,
                name=name,
                jmri_message=jmri_message,
                status=status,
            )
        raise JMRIProtocolError(
            "unexpected HTTP status from command",
            status=status,
            path=path,
            jmri_message=jmri_message,
        )

    async def aclose(self) -> None:
        """Close the underlying httpx client. Idempotent."""
        await self._http.aclose()

    def _translate_httpx_error(
        self,
        e: httpx.TransportError,
        *,
        path: str,
    ) -> JMRIConnectionError | JMRIRequestTimeout:
        """Translate an :class:`httpx.TransportError` into the matching JMRIError subclass.

        Three branches, ordered to honor the httpx class hierarchy
        (``ConnectError`` and ``TimeoutException`` are both
        ``TransportError`` subclasses):

        - :class:`httpx.ConnectError` → :class:`JMRIConnectionError` (plain).
        - :class:`httpx.TimeoutException` → :class:`JMRIRequestTimeout` with ``path``.
        - Any other ``TransportError`` subclass (``ReadError``, ``WriteError``,
          ``ProxyError``, ``ProtocolError``, ``DecodingError``, ``TooManyRedirects``,
          ...) → :class:`JMRIConnectionError` with ``error_type`` captured in context.

        Callers must preserve cause chaining:
        ``raise self._translate_httpx_error(e, path=path) from e``.
        """
        if isinstance(e, httpx.ConnectError):
            return JMRIConnectionError(host=self._host, port=self._port)
        if isinstance(e, httpx.TimeoutException):
            return JMRIRequestTimeout(
                "HTTP request exceeded request_timeout",
                host=self._host,
                port=self._port,
                path=path,
            )
        return JMRIConnectionError(
            host=self._host,
            port=self._port,
            error_type=type(e).__name__,
        )


class WSConnection:
    """WebSocket connection wrapper consuming ``websockets.connect()`` as an async iterator.

    Architecture sec. Transport Layer + sec. Reconnect & Restoration
    Mechanism. Only this module imports ``websockets``.

    The library's built-in ``async for ... in connect(...)`` iterator drives
    reconnection. pyjmri does not write its own retry loop. The
    ``process_exception`` hook returns the original exception once
    ``ReconnectConfig.max_attempts`` consecutive failures occur, causing
    the iterator to raise; :meth:`run` then re-raises as
    :class:`~pyjmri.exceptions.JMRIReconnectFailed`. With
    ``max_attempts=None`` (the default), the hook returns ``None``
    forever and retries continue indefinitely.

    Note: in ``websockets`` v16+, returning ``None`` from ``process_exception``
    means retryable (inverted from earlier library versions where ``None``
    meant give up). Full hook contract: :meth:`_process_exception`.

    Args:
        host: JMRI host (e.g. ``"localhost"``).
        port: JMRI web-server port (e.g. ``12080``).
        reconnect_config: Reconnect tuning. Currently only
            ``max_attempts`` is honored — delay timing is delegated to
            the ``websockets`` library's built-in ``backoff()``.
        secure: When ``True``, use ``wss://`` (TLS). :class:`~pyjmri.client.Client`
            sets this from its HTTP scheme (``https`` / ``wss`` URLs → secure).
        on_reconnect: Optional coroutine invoked after each successful
            reconnect (not the very first connect). The Client passes
            ``SubscriptionRegistry.replay`` here.
        connected_event: Optional :class:`asyncio.Event` set once on the
            very first successful connect. The Client awaits this in
            ``__aenter__`` so users see a fully-open Client.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        reconnect_config: ReconnectConfig,
        secure: bool = False,
        on_reconnect: Callable[[], Awaitable[None]] | None = None,
        connected_event: Any = None,  # asyncio.Event, typed Any to avoid eager import
    ) -> None:
        self._host = host
        self._port = port
        self._secure = secure
        self._config = reconnect_config
        self._on_reconnect = on_reconnect
        self._connected = connected_event
        self._connection: ClientConnection | None = None
        self._attempt: int = 0
        self._give_up_cause: BaseException | None = None

    @property
    def url(self) -> str:
        proto = "wss" if self._secure else "ws"
        return f"{proto}://{self._host}:{self._port}{WS_PATH}"

    async def run(self, on_message: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """Long-running coroutine: connect, receive, reconnect indefinitely.

        Supervised by the Client's :class:`asyncio.TaskGroup`. Cancellation
        propagates from the TaskGroup's ``__aexit__`` and exits this
        coroutine cleanly. The ``finally`` closes the active connection on
        the way out — without it, cancellation leaves the socket to be
        reaped by GC at some arbitrary later time, and JMRI's delayed
        server-side cleanup of that stale connection can interfere with
        the next Client opened in the same process (observed as a missed
        first subscription event).
        """
        try:
            async for connection in websockets.connect(
                self.url,
                process_exception=self._process_exception,
                ping_interval=_PING_INTERVAL_SEC,
            ):
                self._connection = connection
                first_connect = self._connected is not None and not self._connected.is_set()
                self._attempt = 0  # reset on each successful connect
                if first_connect:
                    self._connected.set()
                else:
                    if self._on_reconnect is not None:
                        try:
                            await self._on_reconnect()
                        except Exception as cb_exc:
                            logger_reconnect.warning(
                                "on_reconnect callback raised; continuing receive loop",
                                extra={
                                    "host": self._host,
                                    "error_type": type(cb_exc).__name__,
                                },
                            )
                try:
                    async for raw in connection:
                        try:
                            envelope = _decode_ws_frame(raw)
                            logger.debug(
                                "WS inbound",
                                extra={
                                    "direction": "inbound",
                                    "type": envelope.get("type"),
                                },
                            )
                            await on_message(envelope)
                        except Exception as msg_exc:
                            logger.warning(
                                "WS message handling error; skipping frame",
                                extra={"error_type": type(msg_exc).__name__},
                            )
                except WebSocketException:
                    self._connection = None
                    continue
        except WebSocketException as e:
            self._connection = None
            if self._give_up_cause is not None:
                raise JMRIReconnectFailed(
                    host=self._host,
                    port=self._port,
                    attempts=self._attempt,
                    cause=type(self._give_up_cause).__name__,
                ) from self._give_up_cause
            raise JMRIConnectionError(host=self._host, port=self._port) from e
        finally:
            active, self._connection = self._connection, None
            if active is not None:
                # websockets' close() is cancellation-safe: if the close
                # handshake is interrupted, it aborts the connection — an
                # abrupt TCP close is still deterministic teardown, which
                # is all we need here. Suppress everything: teardown must
                # never mask the exception already propagating.
                try:
                    await active.close()
                except BaseException:
                    pass

    def _process_exception(self, exc: Exception) -> Exception | None:
        """``websockets`` v16 retry hook.

        Returns ``None`` to mark the exception retryable (library schedules
        the next reconnect via its built-in ``backoff()``). Returns the
        exception itself to mark it fatal (library raises it and exits the
        async iterator).
        """
        self._attempt += 1
        if self._config.max_attempts is not None and self._attempt >= self._config.max_attempts:
            self._give_up_cause = exc
            logger_reconnect.warning(
                "WebSocket reconnect attempts exhausted",
                extra={
                    "host": self._host,
                    "attempt": self._attempt,
                    "max_attempts": self._config.max_attempts,
                    "error_type": type(exc).__name__,
                },
            )
            return exc
        logger_reconnect.warning(
            "WebSocket disconnected; will retry",
            extra={
                "host": self._host,
                "attempt": self._attempt,
                "error_type": type(exc).__name__,
            },
        )
        return None

    async def _force_disconnect(self) -> None:
        """Test-only hook: close the active WS connection to trigger the reconnect loop.

        Closing ``self._connection`` causes the ``async for raw in connection``
        inner loop to exit, which the outer ``async for connection in
        websockets.connect(...)`` iterator handles by scheduling a reconnect.
        Safe to call when no connection is active (no-op). Never call from
        production code — use this hook only in integration tests.
        """
        if self._connection is not None:
            await self._connection.close()

    async def send(self, message: dict[str, Any]) -> None:
        """JSON-encode ``message`` and send it on the current connection.

        Raises :class:`JMRIConnectionError` if no connection is active
        (e.g., a send arrives between disconnect and reconnect, or after
        the supervisor task has been cancelled).
        """
        connection = self._connection
        if connection is None:
            raise JMRIConnectionError(host=self._host, port=self._port)
        try:
            await connection.send(json.dumps(message))
        except WebSocketException as e:
            raise JMRIConnectionError(host=self._host, port=self._port) from e
        logger.debug(
            "WS outbound",
            extra={"direction": "outbound", "type": message.get("type")},
        )


def _extract_jmri_error_message(response: httpx.Response) -> str | None:
    """Return JMRI's error message if the body matches the error envelope.

    JMRI 5.14+ returns ``{"type":"error","data":{"code":<int>,
    "message":"<text>"}}`` for command-path failures. Returns ``None``
    when the body cannot be parsed as JSON or does not match this shape;
    the caller then raises :class:`JMRIProtocolError` instead.
    """
    try:
        body = response.json()
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    if body.get("type") != "error":
        return None
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    message = data.get("message")
    if not isinstance(message, str):
        return None
    return message


def _decode_ws_frame(raw: Any) -> dict[str, Any]:
    """Decode a WebSocket text or binary frame into a JMRI envelope dict.

    Raises:
        JMRIProtocolError: when the frame is not valid JSON or is not a
            JSON object.
    """
    if isinstance(raw, (bytes, bytearray)):
        raw_text = raw.decode("utf-8")
    elif isinstance(raw, str):
        raw_text = raw
    else:
        raise JMRIProtocolError(
            "unexpected WebSocket frame type",
            frame_type=type(raw).__name__,
        )
    try:
        envelope = json.loads(raw_text)
    except ValueError as e:
        raise JMRIProtocolError("WebSocket frame was not valid JSON") from e
    if not isinstance(envelope, dict):
        raise JMRIProtocolError(
            "WebSocket envelope was not a JSON object",
            actual_type=type(envelope).__name__,
        )
    return envelope
