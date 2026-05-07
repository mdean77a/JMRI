"""HTTP transport boundary.

The only module allowed to import or catch ``httpx`` exceptions. See
architecture §Transport Layer and §Architectural Boundaries.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from pyjmri.exceptions import (
    JMRIConnectionError,
    JMRIProtocolError,
    JMRIRequestTimeout,
)

__all__ = ["HTTPClient"]

logger = logging.getLogger("pyjmri.transport")


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
        except httpx.ConnectError as e:
            raise JMRIConnectionError(host=self._host, port=self._port) from e
        except httpx.TimeoutException as e:
            raise JMRIRequestTimeout(
                "HTTP request exceeded request_timeout",
                host=self._host,
                port=self._port,
                path=path,
            ) from e
        except httpx.TransportError as e:
            # Covers ReadError, WriteError, CloseError, ProxyError,
            # ProtocolError, DecodingError, TooManyRedirects, etc.
            raise JMRIConnectionError(
                host=self._host,
                port=self._port,
                error_type=type(e).__name__,
            ) from e

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

        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
            return payload

        raise JMRIProtocolError(
            "response JSON was not a JMRI v5 entity (object or array of objects)",
            path=path,
            actual_type=type(payload).__name__,
        )

    async def aclose(self) -> None:
        """Close the underlying httpx client. Idempotent."""
        await self._http.aclose()
