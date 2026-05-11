"""Client lifecycle and configuration.

See architecture §Client Configuration Shape and §Concurrency Model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote, urlparse

from pyjmri._parsing import parse_power
from pyjmri._transport import HTTPClient
from pyjmri.exceptions import JMRIProtocolError
from pyjmri.power import PowerState

__all__ = ["Client", "ClientConfig", "ReconnectConfig"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ReconnectConfig:
    """WebSocket reconnect tuning. Consumed by Epic 3.

    Defined here in v1 so the public API surface is fixed before the
    reconnect machinery lands. Constructing a ``ReconnectConfig`` today
    has no effect; the values are read by the WebSocket transport in a
    later story.
    """

    initial_delay: float = 0.5
    max_delay: float = 30.0
    jitter: float = 0.25
    max_attempts: int | None = None


@dataclass(frozen=True, kw_only=True)
class ClientConfig:
    """Client-wide configuration."""

    request_timeout: float = 10.0
    reconnect: ReconnectConfig = field(default_factory=ReconnectConfig)
    subscription_replay_timeout: float = 30.0
    """Seconds to wait for the subscription registry to replay after a
    WebSocket reconnect. Consumed by Epic 3; currently unused in v1."""


class Client:
    """Async context manager binding to a JMRI web server.

    Example:
        Connect with default settings::

            async with Client() as jmri:
                ...

    The default URL is ``localhost:12080``. The ``url`` argument accepts
    ``host:port``, ``http://host:port``, or ``ws://host:port/path``.

    Args:
        url: JMRI URL or host:port string. Defaults to ``localhost:12080``.
        config: Optional :class:`ClientConfig` for tuning.
    """

    def __init__(
        self,
        url: str = "localhost:12080",
        *,
        config: ClientConfig | None = None,
    ) -> None:
        host, port, scheme = _parse_url(url)
        self._host = host
        self._port = port
        self._scheme = scheme
        self._config = config or ClientConfig()
        self._http: HTTPClient | None = None

    async def __aenter__(self) -> Self:
        if self._http is not None:
            raise RuntimeError("Client is already open; cannot re-enter an active context")
        self._http = HTTPClient(
            host=self._host,
            port=self._port,
            scheme=self._scheme,
            request_timeout=self._config.request_timeout,
        )
        # Probe so an unreachable host fails NOW, not on the first user
        # call. The same /json/v5/version endpoint is used by Story 2.5
        # for the JMRI version check; here we discard the body.
        try:
            await self._http.get("/json/v5/version")
        except BaseException:
            await self._http.aclose()
            self._http = None
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def get_entity(self, entity_type: str, name: str) -> dict[str, Any]:
        """Implementation of :class:`pyjmri._protocols.ClientHandle`.

        For internal use by domain entity classes (``Turnout``, ``Sensor``,
        etc.). Issues ``GET /json/v5/{entity_type}/{quoted_name}`` and
        returns the single-entity envelope dict that ``parse_<entity>``
        consumes.

        Raises:
            RuntimeError: when the Client is not open.
            JMRIProtocolError: when JMRI returns an empty list (entity
                not found) or a non-dict payload for a per-name endpoint.
            JMRIConnectionError, JMRIRequestTimeout: surfaced from the
                HTTP transport.
        """
        if self._http is None:
            raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
        path = f"/json/v5/{entity_type}/{quote(name, safe='')}"
        payload = await self._http.get(path)
        if isinstance(payload, list) and not payload:
            raise JMRIProtocolError(
                "entity not found: per-name endpoint returned empty list",
                entity_type=entity_type,
                name=name,
                path=path,
            )
        if not isinstance(payload, dict):
            raise JMRIProtocolError(
                "expected single entity envelope, got list",
                entity_type=entity_type,
                name=name,
                path=path,
            )
        return payload

    async def power_state(self) -> PowerState:
        """Return the current JMRI track-power state.

        Issues ``GET /json/v5/power`` and returns the parsed
        :class:`~pyjmri.PowerState`. Read-only by design — the booster's
        physical power switch is the source of truth on NCE hardware
        (PRD FR16, sec. "Power control" note).

        Raises:
            RuntimeError: when the Client is not open.
            JMRIProtocolError: when the JMRI response is empty or
                malformed.
            JMRIConnectionError, JMRIRequestTimeout: surfaced from the
                HTTP transport.
        """
        if self._http is None:
            raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
        payload = await self._http.get("/json/v5/power")
        if isinstance(payload, list):
            if not payload:
                raise JMRIProtocolError(
                    "empty power response",
                    path="/json/v5/power",
                )
            envelope = payload[0]
            if not isinstance(envelope, dict):
                raise JMRIProtocolError(
                    "unexpected power response type",
                    path="/json/v5/power",
                )
        elif isinstance(payload, dict):
            envelope = payload
        else:
            raise JMRIProtocolError(
                "unexpected power response type",
                path="/json/v5/power",
            )
        parsed = parse_power(envelope)
        return parsed.state


def _parse_url(url: str) -> tuple[str, int, str]:
    """Return ``(host, port, scheme)`` for the supported URL forms.

    Accepts:
        - ``"host:port"``
        - ``"http://host:port"`` / ``"https://host:port"``
        - ``"ws://host:port/path"`` / ``"wss://host:port/path"``

    The ``ws``/``wss`` schemes are accepted for forward-compat with
    Epic 3 and are normalized to ``http``/``https`` for HTTP transport.

    Raises:
        ValueError: when the URL is missing host or port, or uses an
            unsupported scheme.
    """
    if not url:
        raise ValueError("URL must be a non-empty string")
    if "://" not in url:
        url = f"http://{url}"
    parsed = urlparse(url)
    if not parsed.hostname or parsed.port is None:
        raise ValueError(f"URL must include host and port: {url!r}")
    scheme_map = {
        "http": "http",
        "https": "https",
        "ws": "http",
        "wss": "https",
    }
    if parsed.scheme not in scheme_map:
        raise ValueError(f"unsupported URL scheme {parsed.scheme!r}; use http, https, ws, or wss")
    return parsed.hostname, parsed.port, scheme_map[parsed.scheme]
