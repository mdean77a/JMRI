"""Client lifecycle and configuration.

See architecture §Client Configuration Shape and §Concurrency Model.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote, urlparse

from pyjmri._parsing import (
    parse_block,
    parse_light,
    parse_memory,
    parse_power,
    parse_route,
    parse_sensor,
    parse_signal_head,
    parse_signal_mast,
    parse_turnout,
)
from pyjmri._transport import HTTPClient
from pyjmri.block import Block
from pyjmri.exceptions import JMRIProtocolError, JMRIVersionUnsupported
from pyjmri.layout import EntityCollection, Layout
from pyjmri.light import Light
from pyjmri.memory import Memory
from pyjmri.power import PowerState
from pyjmri.route import Route
from pyjmri.sensor import Sensor
from pyjmri.signal import SignalHead, SignalMast
from pyjmri.turnout import Turnout

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
        self._version_checked: bool = False

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
        # call. /json/v5/version is the cheapest endpoint that proves the
        # JSON API is alive; its response (the JSON API version) is
        # discarded. discover() performs the JMRI application version
        # gate against /json/v5/networkService — see _check_jmri_version.
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
        self._version_checked = False

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

    async def discover(self) -> Layout:
        """Enumerate every supported entity type from JMRI and return a Layout.

        Issues ``GET /json/v5/{entity_type}`` in parallel via
        :class:`asyncio.TaskGroup` for the eight supported types
        (``turnout``, ``sensor``, ``block``, ``light``, ``memory``,
        ``route``, ``signalHead``, ``signalMast``) and assembles the
        results into a :class:`~pyjmri.Layout`.

        On the first call against a given Client, ``discover()`` first
        fetches ``/json/v5/networkService`` and refuses to proceed if
        the running JMRI is older than 5.14 (NFR8). The JMRI
        application version lives in each network-service envelope's
        ``data.jmri`` field; ``/json/v5/version`` only carries the JSON
        API version. The version check is cached for the Client's
        lifetime — subsequent ``discover()`` calls skip the version
        probe.

        Returns:
            A fully populated :class:`~pyjmri.Layout`. Empty per-type
            responses produce empty :class:`~pyjmri.EntityCollection`
            instances — they are valid, not errors.

        Raises:
            JMRIVersionUnsupported: when the running JMRI is older than
                5.14.
            JMRIProtocolError: when a per-type response is malformed
                (e.g., not a list, missing required fields).
            JMRIConnectionError, JMRIRequestTimeout: surfaced from the
                HTTP transport.
            RuntimeError: when the Client is not open (use
                ``async with Client() as jmri:`` first).

        Note:
            If one of the eight parallel per-type fetches fails,
            :class:`asyncio.TaskGroup` cancels the other tasks and
            propagates the underlying error wrapped in an
            :class:`ExceptionGroup`. Catch with ``except*
            JMRIProtocolError`` (Python 3.11+) or ``except
            ExceptionGroup``.
        """
        if self._http is None:
            raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
        http = self._http

        if not self._version_checked:
            version_payload = await http.get("/json/v5/networkService")
            _check_jmri_version(version_payload)
            self._version_checked = True

        async with asyncio.TaskGroup() as tg:
            t_turnout = tg.create_task(_fetch_collection(http, "turnout"))
            t_sensor = tg.create_task(_fetch_collection(http, "sensor"))
            t_block = tg.create_task(_fetch_collection(http, "block"))
            t_light = tg.create_task(_fetch_collection(http, "light"))
            t_memory = tg.create_task(_fetch_collection(http, "memory"))
            t_route = tg.create_task(_fetch_collection(http, "route"))
            t_sighead = tg.create_task(_fetch_collection(http, "signalHead"))
            t_sigmast = tg.create_task(_fetch_collection(http, "signalMast"))

        turnouts: list[Turnout] = []
        for envelope in t_turnout.result():
            parsed_t = parse_turnout(envelope)
            turnouts.append(
                Turnout(
                    name=parsed_t.name,
                    user_name=parsed_t.user_name,
                    state=parsed_t.state,
                    _handle=self,
                )
            )

        sensors: list[Sensor] = []
        for envelope in t_sensor.result():
            parsed_s = parse_sensor(envelope)
            sensors.append(
                Sensor(
                    name=parsed_s.name,
                    user_name=parsed_s.user_name,
                    state=parsed_s.state,
                    _handle=self,
                )
            )

        blocks: list[Block] = []
        for envelope in t_block.result():
            parsed_b = parse_block(envelope)
            blocks.append(
                Block(
                    name=parsed_b.name,
                    user_name=parsed_b.user_name,
                    state=parsed_b.state,
                    value=parsed_b.value,
                    _handle=self,
                )
            )

        lights: list[Light] = []
        for envelope in t_light.result():
            parsed_l = parse_light(envelope)
            lights.append(
                Light(
                    name=parsed_l.name,
                    user_name=parsed_l.user_name,
                    state=parsed_l.state,
                    _handle=self,
                )
            )

        memories: list[Memory] = []
        for envelope in t_memory.result():
            parsed_m = parse_memory(envelope)
            memories.append(
                Memory(
                    name=parsed_m.name,
                    user_name=parsed_m.user_name,
                    value=parsed_m.value,
                    _handle=self,
                )
            )

        routes: list[Route] = []
        for envelope in t_route.result():
            parsed_r = parse_route(envelope)
            routes.append(Route(name=parsed_r.name, user_name=parsed_r.user_name))

        signal_heads: list[SignalHead] = []
        for envelope in t_sighead.result():
            parsed_sh = parse_signal_head(envelope)
            signal_heads.append(
                SignalHead(
                    name=parsed_sh.name,
                    user_name=parsed_sh.user_name,
                    appearance=parsed_sh.appearance,
                    held=parsed_sh.held,
                    lit=parsed_sh.lit,
                    _handle=self,
                )
            )

        signal_masts: list[SignalMast] = []
        for envelope in t_sigmast.result():
            parsed_sm = parse_signal_mast(envelope)
            signal_masts.append(
                SignalMast(
                    name=parsed_sm.name,
                    user_name=parsed_sm.user_name,
                    aspect=parsed_sm.aspect,
                    held=parsed_sm.held,
                    lit=parsed_sm.lit,
                    _handle=self,
                )
            )

        return Layout(
            turnouts=EntityCollection(turnouts, entity_type="turnout"),
            sensors=EntityCollection(sensors, entity_type="sensor"),
            blocks=EntityCollection(blocks, entity_type="block"),
            lights=EntityCollection(lights, entity_type="light"),
            memories=EntityCollection(memories, entity_type="memory"),
            routes=EntityCollection(routes, entity_type="route"),
            signal_heads=EntityCollection(signal_heads, entity_type="signalHead"),
            signal_masts=EntityCollection(signal_masts, entity_type="signalMast"),
        )

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


_MIN_JMRI_VERSION: tuple[int, int] = (5, 14)
_MIN_JMRI_VERSION_STR: str = "5.14"


async def _fetch_collection(http: HTTPClient, entity_type: str) -> list[dict[str, Any]]:
    """Fetch a collection endpoint and validate that the response is a list.

    Used by :meth:`Client.discover` for each of the eight supported
    entity types. JMRI's collection endpoints return a JSON array of
    envelopes; a non-list response indicates a protocol violation.
    """
    path = f"/json/v5/{entity_type}"
    payload = await http.get(path)
    if not isinstance(payload, list):
        raise JMRIProtocolError(
            "expected list from collection endpoint",
            entity_type=entity_type,
            path=path,
        )
    return payload


_VERSION_PATH: str = "/json/v5/networkService"


def _check_jmri_version(payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    """Validate the running JMRI is >= 5.14, else raise.

    JMRI's ``/json/v5/networkService`` endpoint returns a list of
    advertised services; each envelope's ``data.jmri`` field carries
    the JMRI application version (e.g., ``"5.14.0"``). A single-dict
    payload is also accepted for robustness. The ``/json/v5/version``
    endpoint is **not** used here — it returns only the JSON API
    version, not JMRI itself.
    """
    if isinstance(payload, list):
        if not payload:
            raise JMRIProtocolError("empty networkService response", path=_VERSION_PATH)
        envelope = payload[0]
    else:
        envelope = payload
    if not isinstance(envelope, dict):
        raise JMRIProtocolError("networkService response is not a dict", path=_VERSION_PATH)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise JMRIProtocolError("networkService response missing 'data' object", path=_VERSION_PATH)
    version = data.get("jmri")
    if not isinstance(version, str):
        raise JMRIProtocolError(
            "networkService response missing 'jmri' field",
            path=_VERSION_PATH,
            field="jmri",
        )
    try:
        detected = tuple(int(part) for part in version.split("."))
    except ValueError as exc:
        raise JMRIProtocolError(
            "networkService response 'jmri' field is not dot-separated integers",
            path=_VERSION_PATH,
            field="jmri",
            value=version,
        ) from exc
    if detected < _MIN_JMRI_VERSION:
        raise JMRIVersionUnsupported(detected=version, required=_MIN_JMRI_VERSION_STR)
