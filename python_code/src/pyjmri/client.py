"""Client lifecycle and configuration.

See architecture §Client Configuration Shape and §Concurrency Model.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
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
from pyjmri._protocols import Waitable
from pyjmri._subscriptions import SubscriptionRegistry
from pyjmri._transport import HTTPClient, WSConnection
from pyjmri.block import Block
from pyjmri.exceptions import (
    JMRIConnectionError,
    JMRIProtocolError,
    JMRIVersionUnsupported,
)
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
logger_reconnect = logging.getLogger("pyjmri.reconnect")
logger_transport = logging.getLogger("pyjmri.transport")


@dataclass(frozen=True, kw_only=True)
class ReconnectConfig:
    """WebSocket reconnect tuning.

    Only ``max_attempts`` is configurable. Delay timing is delegated to
    the ``websockets`` library's built-in backoff (random initial 0-5 s,
    growing by factor 1.618, capped at 90 s) — the v16 API exposes no
    per-``connect()`` parameter for delay tuning, so ``pyjmri`` ships
    with the library defaults and avoids process-wide env-var hacks.

    Args:
        max_attempts: Maximum consecutive reconnect attempts before the
            Client gives up and raises :class:`JMRIReconnectFailed`.
            ``None`` (default) retries forever.
    """

    max_attempts: int | None = None


@dataclass(frozen=True, kw_only=True)
class ClientConfig:
    """Client-wide configuration."""

    request_timeout: float = 10.0
    reconnect: ReconnectConfig = field(default_factory=ReconnectConfig)
    subscription_replay_timeout: float = 30.0
    """Maximum seconds to wait for the first WebSocket connection in
    :meth:`Client.__aenter__`. Story 3.2 may also use this for
    subscription-replay or ``wait_*`` deadlines tied to reconnect.
    """


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
        self._tg: asyncio.TaskGroup | None = None
        self._ws: WSConnection | None = None
        self._registry: SubscriptionRegistry | None = None
        self._ws_connected: asyncio.Event | None = None
        self._supervisor_task: asyncio.Task[None] | None = None
        self._entities: dict[tuple[str, str], Waitable] = {}

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

        # Open the Client-level TaskGroup that supervises every
        # long-running coroutine the library owns (architecture sec.
        # Concurrency Model). Currently supervises the WS receive loop;
        # Story 5.1 will add per-throttle keep-alive tasks here.
        self._tg = asyncio.TaskGroup()
        await self._tg.__aenter__()
        self._ws_connected = asyncio.Event()
        self._ws = WSConnection(
            host=self._host,
            port=self._port,
            reconnect_config=self._config.reconnect,
            secure=self._scheme == "https",
            on_reconnect=self._on_ws_reconnect,
            connected_event=self._ws_connected,
        )
        self._registry = SubscriptionRegistry(send=self._ws.send)
        self._supervisor_task = self._tg.create_task(self._ws.run(on_message=self._on_ws_message))

        # Wait for the first WS connection to come up. If it doesn't
        # within subscription_replay_timeout, tear down cleanly so the
        # user doesn't get a half-open Client. If the supervisor task
        # raises during this wait, the TaskGroup cancels this parent
        # task; we catch CancelledError and unwrap the supervisor's
        # exception from the TaskGroup's __aexit__ ExceptionGroup
        # (Open Design Decision #2: unwrap single-exception groups at
        # the API boundary).
        try:
            async with asyncio.timeout(self._config.subscription_replay_timeout):
                await self._ws_connected.wait()
        except BaseException as first_connect_exc:
            await self._teardown_on_aenter_failure(first_connect_exc)
            if isinstance(first_connect_exc, asyncio.CancelledError):
                # CancelledError was almost certainly the TaskGroup
                # cancelling us because the supervisor raised. The
                # supervisor's exception was already unwrapped and
                # raised by _teardown_on_aenter_failure; if we get
                # here, fall back to a generic ConnectionError.
                raise JMRIConnectionError(host=self._host, port=self._port) from first_connect_exc
            if isinstance(first_connect_exc, TimeoutError):
                raise JMRIConnectionError(host=self._host, port=self._port) from first_connect_exc
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if self._supervisor_task is not None and not self._supervisor_task.done():
                self._supervisor_task.cancel()
            if self._tg is not None:
                try:
                    await self._tg.__aexit__(exc_type, exc, tb)
                except BaseExceptionGroup as eg:
                    non_cancelled = [
                        e for e in eg.exceptions if not isinstance(e, asyncio.CancelledError)
                    ]
                    if len(non_cancelled) == 1 and non_cancelled[0] is exc:
                        # The TaskGroup re-wrapped the body exception in a
                        # group with no other failures. Let the original
                        # body exception propagate (it's already on its
                        # way out via Python's context-manager protocol).
                        return
                    if len(non_cancelled) == 1:
                        raise non_cancelled[0] from None
                    if non_cancelled:
                        raise
                    # ExceptionGroup carried only CancelledErrors —
                    # expected during clean teardown; swallow.
        finally:
            self._tg = None
            if self._http is not None:
                await self._http.aclose()
                self._http = None
            self._ws = None
            self._registry = None
            self._ws_connected = None
            self._supervisor_task = None
            self._entities = {}
            self._version_checked = False

    async def _teardown_on_aenter_failure(self, first_exc: BaseException) -> None:
        """Tear down the half-open Client when first-connect fails.

        Cancels the supervisor task (if still running), drives the
        TaskGroup through its ``__aexit__``, unwraps any single non-
        cancellation exception, and closes the HTTP transport. Always
        leaves the Client in a fully-closed state before re-raising the
        original ``first_exc`` (which the caller is responsible for).
        """
        if self._supervisor_task is not None and not self._supervisor_task.done():
            self._supervisor_task.cancel()
        try:
            if self._tg is not None:
                try:
                    await self._tg.__aexit__(type(first_exc), first_exc, first_exc.__traceback__)
                except BaseExceptionGroup as eg:
                    non_cancelled = [
                        e for e in eg.exceptions if not isinstance(e, asyncio.CancelledError)
                    ]
                    if len(non_cancelled) == 1:
                        raise non_cancelled[0] from None
                    if non_cancelled:
                        raise
        finally:
            self._tg = None
            if self._http is not None:
                await self._http.aclose()
                self._http = None
            self._ws = None
            self._registry = None
            self._ws_connected = None
            self._supervisor_task = None
            self._entities = {}

    async def _on_ws_message(self, envelope: dict[str, Any]) -> None:
        """Dispatch one inbound WS envelope to the matching entity.

        Parses ``envelope["type"]`` against the six waitable entity-type
        strings, calls the matching parser, looks up the entity in
        :attr:`_entities`, and invokes ``entity._on_event(primary_state)``.

        Non-fatal paths (drop + log at DEBUG):

        - JMRI ``hello`` envelopes and any unrecognized ``type``
        - ``memory`` and ``route`` envelopes (no waitable model in v1)
        - Known type whose ``(entity_type, name)`` is not in this
          Client's discovered Layout

        Non-fatal error paths (drop + log at WARNING):

        - Parser raises :class:`JMRIProtocolError`, or raises any other
          :class:`Exception` during parse/extract (bad frame handling)
        - ``entity._on_event`` raises any :class:`Exception` (treated
          adversarially so a buggy waiter cannot kill the supervisor)
        """
        entity_type = envelope.get("type")
        if not isinstance(entity_type, str):
            logger_transport.debug("WS dispatch: drop", extra={"reason": "no type field"})
            return None
        parser_entry = _DISPATCH_PARSERS.get(entity_type)
        if parser_entry is None:
            logger_transport.debug("WS dispatch: drop", extra={"type": entity_type})
            return None
        parser, primary_attr = parser_entry
        try:
            parsed = parser(envelope)
            name = parsed.name
            primary = getattr(parsed, primary_attr)
        except Exception as e:
            logger_transport.warning(
                "WS dispatch: parse failed",
                extra={"entity_type": entity_type, "error_type": type(e).__name__},
                exc_info=True,
            )
            return None
        entity = self._entities.get((entity_type, name))
        if entity is None:
            logger_transport.debug(
                "WS dispatch: entity not in current Layout",
                extra={"entity_type": entity_type, "system_name": name},
            )
            return None
        try:
            entity._on_event(primary)
        except Exception as e:
            logger_transport.warning(
                "WS dispatch: entity _on_event raised",
                extra={
                    "entity_type": entity_type,
                    "system_name": name,
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
        return None

    async def _force_disconnect(self) -> None:
        """Test-only hook: force a WebSocket disconnect to exercise reconnect resilience.

        Delegates to :meth:`pyjmri._transport.WSConnection._force_disconnect`.
        After this call returns, the ``websockets`` library schedules a
        reconnect (initial backoff 0-5 s); :meth:`_on_ws_reconnect` fires on
        the fresh connection and replays all subscriptions. Never call from
        production code.

        Raises:
            RuntimeError: when the Client is not open.
        """
        if self._ws is None:
            raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
        await self._ws._force_disconnect()

    async def ensure_subscription(self, entity_type: str, name: str) -> None:
        """Implementation of :class:`pyjmri._protocols.ClientHandle`.

        Idempotently registers a WS subscription for ``(entity_type,
        name)``. Called by entity ``wait_*`` methods before they
        register a waiter (FR29).

        Raises:
            RuntimeError: when the Client is not open.
        """
        if self._registry is None:
            raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
        await self._registry.ensure(entity_type, name)

    async def _on_ws_reconnect(self) -> None:
        """Called by ``WSConnection`` after each successful reconnect (not the first).

        Replays every known subscription so in-flight ``wait_*`` calls
        survive the disconnect (FR7, NFR5). Story 3.2 wires the
        waiter side; Story 3.1 just stands up the replay plumbing.
        """
        if self._registry is not None:
            logger_reconnect.info(
                "WebSocket reconnected; replaying subscriptions",
                extra={"host": self._host, "subscription_count": self._registry.size},
            )
            await self._registry.replay()

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

        Note:
            Calling ``discover()`` more than once rebuilds the
            Client's internal WS-dispatch index from the freshly
            discovered entities. In-flight ``wait_*`` calls on
            entities from a *previous* Layout will silently never
            resolve because their entity instances are no longer in
            the dispatch index — cancel them or restructure your
            script to call ``discover()`` once.
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

        # Rebuild the WS-dispatch entity index from this discovery.
        # Memory and Route entities are skipped (no _on_event in v1).
        # Stale Layouts returned by prior discover() calls keep their
        # waiters but those waiters will never resolve via dispatch —
        # see discover() docstring.
        new_index: dict[tuple[str, str], Waitable] = {}
        for t in turnouts:
            new_index[("turnout", t.name)] = t
        for s in sensors:
            new_index[("sensor", s.name)] = s
        for b in blocks:
            new_index[("block", b.name)] = b
        for la in lights:
            new_index[("light", la.name)] = la
        for sh in signal_heads:
            new_index[("signalHead", sh.name)] = sh
        for sm in signal_masts:
            new_index[("signalMast", sm.name)] = sm
        self._entities = new_index

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


_DISPATCH_PARSERS: dict[
    str,
    tuple[Callable[[dict[str, Any]], Any], str],
] = {
    "turnout": (parse_turnout, "state"),
    "sensor": (parse_sensor, "state"),
    "block": (parse_block, "state"),
    "light": (parse_light, "state"),
    "signalHead": (parse_signal_head, "appearance"),
    "signalMast": (parse_signal_mast, "aspect"),
}
"""Per-entity-type ``(parser_fn, primary_attr)`` table.

The six entries are the waitable entity types. ``memory`` and ``route``
are intentionally absent — their envelopes drop at the dispatch layer.
Adding a seventh waitable entity is one line here plus the entity's
own ``_on_event``/``_waiters`` plumbing.
"""


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
