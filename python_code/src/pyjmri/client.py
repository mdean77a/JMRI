"""Client lifecycle and configuration.

See architecture §Client Configuration Shape and §Concurrency Model.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import quote, urlparse

if TYPE_CHECKING:
    from pyjmri.throttle import Throttle

from pyjmri._parsing import (
    parse_block,
    parse_car,
    parse_engine,
    parse_light,
    parse_location,
    parse_memory,
    parse_power,
    parse_route,
    parse_sensor,
    parse_signal_head,
    parse_signal_mast,
    parse_train,
    parse_turnout,
)
from pyjmri._protocols import ClientHandle, Waitable
from pyjmri._subscriptions import SubscriptionRegistry
from pyjmri._transport import HTTPClient, WSConnection
from pyjmri.block import Block
from pyjmri.exceptions import (
    JMRIConnectionError,
    JMRIProtocolError,
    JMRIRequestTimeout,
    JMRIVersionUnsupported,
    ThrottleAcquireFailed,
)
from pyjmri.layout import EntityCollection, Layout
from pyjmri.light import Light
from pyjmri.memory import Memory
from pyjmri.operations import Car, Engine, Location, Operations, Train
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
    throttle_keepalive_interval: float = 15.0
    """Per-throttle keep-alive interval in seconds (matches JMRI WiThrottle
    convention). v1 ships with a no-op keep-alive body — Story 5.1 Task 0
    spike found JMRI's WS-level heartbeat (10 s ping_interval, well under
    JMRI's 13.5 s server-advertised heartbeat) is sufficient to hold
    throttles. Story 5.3 (hardware integration) confirms whether per-throttle
    heartbeat is needed in practice. This knob is for users who want to tune
    the interval if a future hardware finding flips the keep-alive body to
    active; set to a very large number if you want to functionally disable
    it. The v1 no-op body ignores this value.
    """


class Client:
    """Async context manager binding to a JMRI web server.

    Example:
        Connect with default settings::

            async with Client() as jmri:
                ...

    The default URL is ``localhost:12080``. The ``url`` argument accepts
    ``host:port``, ``http://host:port``, or ``ws://host:port/path``.

    A bare ``host:port`` (no scheme) is treated as plaintext ``http://``
    and ``ws://``. JMRI's web server has no authentication and is
    intended for the local network, so HTTP is the right default for a
    basement layout. If you expose JMRI beyond a trusted LAN, pass an
    explicit ``https://host:port`` or ``wss://host:port`` URL so the
    connection is TLS-encrypted; the certificate is verified by the
    underlying ``httpx``/``websockets`` defaults.

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
        # Story 5.1: name-keyed pending throttle acquires (Throttle's WS
        # correlation). Lives across the Client lifetime; cleared in __aexit__.
        self._pending_throttle: dict[str, asyncio.Future[dict[str, Any]]] = {}
        # FIFO queue for un-named JMRI `type:error` correlation (JMRI's error
        # envelope omits the throttle name, so we attribute to the oldest
        # pending acquire). See Story 5.1 AC9.
        self._pending_throttle_error_queue: deque[asyncio.Future[dict[str, Any]]] = deque()

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
                    unwrapped = _unwrap_exception_group(eg, body_exc=exc)
                    if unwrapped is None:
                        # Either only CancelledErrors during clean teardown,
                        # or the lone non-cancellation IS the body exception
                        # already propagating via the context-manager protocol.
                        return
                    if unwrapped is eg:
                        raise
                    raise unwrapped from None
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
            self._pending_throttle = {}
            self._pending_throttle_error_queue.clear()

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
                    unwrapped = _unwrap_exception_group(eg)
                    if unwrapped is eg:
                        raise
                    if unwrapped is not None:
                        raise unwrapped from None
                    # only cancellations — fall through to finally cleanup.
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
        if entity_type == "throttle":
            self._dispatch_throttle_envelope(envelope)
            return None
        if entity_type == "error":
            self._dispatch_error_envelope(envelope)
            return None
        spec = _ENTITY_SPECS.get(entity_type)
        if spec is None or spec.primary_attr is None:
            logger_transport.debug("WS dispatch: drop", extra={"type": entity_type})
            return None
        try:
            parsed = spec.parser(envelope)
            name = parsed.name
            primary = getattr(parsed, spec.primary_attr)
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

    async def command(
        self,
        entity_type: str,
        name: str,
        payload: dict[str, Any],
    ) -> None:
        """Implementation of :class:`pyjmri._protocols.ClientHandle`.

        Dispatches to :meth:`HTTPClient.command`. The optimistic-only
        contract is documented there; this method exists so entity
        classes can issue commands through the Protocol-typed handle
        rather than importing ``_transport`` directly.
        """
        if self._http is None:
            raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
        await self._http.command(entity_type, name, payload)

    def _dispatch_throttle_envelope(self, envelope: dict[str, Any]) -> None:
        """Route an inbound ``type:throttle`` envelope to a pending acquire.

        Per Story 5.1 Task 0 spike, JMRI's throttle API is WS-only.
        Acquire responses (and incidental state-broadcast envelopes for
        held throttles) carry ``data.throttle`` matching the
        client-chosen name. If a pending acquire is waiting on that
        name, resolve its future; otherwise drop silently — release
        echoes and concurrent client-count updates fall through here.
        """
        data = envelope.get("data")
        if not isinstance(data, dict):
            return
        name = data.get("throttle") or data.get("name")
        if not isinstance(name, str):
            return
        future = self._pending_throttle.get(name)
        if future is None or future.done():
            return
        # Acquire success: full state echo (address, speed, F0...). Release
        # echoes (`{"release": null, ...}`) arrive on the same envelope shape
        # but only after the pending future has already been popped during
        # release(), so they hit the `future is None` path above.
        future.set_result(data)

    def _dispatch_error_envelope(self, envelope: dict[str, Any]) -> None:
        """Route an inbound ``type:error`` envelope to the oldest pending throttle op.

        JMRI's error envelopes omit any throttle name, so the only
        correlation possible is FIFO: the next error is assumed to
        belong to the oldest in-flight throttle acquire. Best-effort
        attribution under concurrent acquires (Story 5.1 AC9).

        Limitation: if JMRI sends a ``type:error`` for a non-throttle
        reason (subscription rejection, power command error, etc.) while
        a throttle acquire is pending, the oldest pending future will be
        spuriously attributed that error. JMRI's protocol does not
        include a source field on error envelopes; this is an
        acknowledged limitation of the FIFO design.
        """
        data = envelope.get("data")
        if not isinstance(data, dict):
            return
        while self._pending_throttle_error_queue:
            future = self._pending_throttle_error_queue.popleft()
            if future.done():
                continue
            message = data.get("message")
            code = data.get("code")
            future.set_exception(
                ThrottleAcquireFailed(
                    "JMRI rejected throttle acquire",
                    jmri_message=message if isinstance(message, str) else None,
                    code=code if isinstance(code, int) else None,
                )
            )
            return

    async def throttle_acquire(self, dcc_address: int, *, long: bool) -> str:
        """Implementation of :class:`pyjmri._protocols.ClientHandle`.

        Generates an internal throttle name (``pyjmri-<addr>-<8-hex>``),
        sends a WS acquire envelope, and awaits a name-correlated
        response (resolved by :meth:`_dispatch_throttle_envelope` or
        failed via :meth:`_dispatch_error_envelope`). Returns the
        internal name on success; the caller (Throttle.__aenter__)
        stores it as the throttle id for subsequent release.

        Raises:
            ThrottleAcquireFailed: when JMRI emits a ``type:error``
                envelope while this acquire is pending.
            JMRIConnectionError: when no WS connection is active.
            JMRIRequestTimeout: when the timeout fires before any
                envelope correlates to this acquire.
            RuntimeError: when the Client is not open.
        """
        if self._ws is None:
            raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
        name = f"pyjmri-{dcc_address}-{uuid.uuid4().hex[:8]}"
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending_throttle[name] = future
        self._pending_throttle_error_queue.append(future)
        try:
            await self._ws.send(
                {
                    "type": "throttle",
                    "data": {
                        "throttle": name,
                        "address": dcc_address,
                        "isLongAddress": long,
                    },
                }
            )
            try:
                async with asyncio.timeout(self._config.request_timeout):
                    await future
            except TimeoutError as exc:
                raise JMRIRequestTimeout(
                    "throttle acquire timed out",
                    dcc_address=dcc_address,
                    request_timeout=self._config.request_timeout,
                ) from exc
        finally:
            self._pending_throttle.pop(name, None)
            try:
                self._pending_throttle_error_queue.remove(future)
            except ValueError:
                pass
        return name

    async def throttle_release(self, throttle_id: str) -> None:
        """Implementation of :class:`pyjmri._protocols.ClientHandle`.

        Fire-and-forget WS release envelope (Story 5.1 AC4). The
        release-confirmation envelope (`{"release": null, ...}`) arrives
        on the WS dispatcher but is not awaited — release returns as
        soon as the envelope is written to the socket.
        """
        if self._ws is None:
            raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
        await self._ws.send(
            {
                "type": "throttle",
                "data": {"throttle": throttle_id, "release": None},
            }
        )

    async def throttle_update(
        self,
        throttle_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Implementation of :class:`pyjmri._protocols.ClientHandle`.

        Fire-and-forget WS state-update envelope. Story 5.2 AC1 documents the
        contract: returns as soon as the WS bytes are written; no awaiting
        JMRI's echo. State echoes arrive on the WS dispatcher and fall
        through :meth:`_dispatch_throttle_envelope` to the ``future is None``
        path (silently dropped — no pending acquire matches a held
        throttle's echo).
        """
        if self._ws is None:
            raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
        await self._ws.send(
            {
                "type": "throttle",
                "data": {**payload, "throttle": throttle_id},
            }
        )

    async def throttle_heartbeat(self, throttle_id: str) -> None:
        """Story 5.3 hookpoint — v1 raises :class:`NotImplementedError`.

        Story 5.1 Task 0 spike found JMRI's WS-level heartbeat keeps held
        throttles alive (the WS connection IS the keepalive). The keep-alive
        coroutine body is a no-op stub in v1 and never calls this method.
        If Story 5.3 hardware observation shows JMRI does expire per-throttle
        on hardware-mode, populate this method with a JMRI-specific heartbeat
        envelope and switch the keep-alive body to call it.
        """
        raise NotImplementedError(
            "per-throttle heartbeat is a Story 5.3 hookpoint; v1 keep-alive "
            "body is a no-op per Task 0 spike — JMRI's WS-level heartbeat is "
            "sufficient. Throttle id: " + throttle_id,
        )

    def spawn_supervised(
        self,
        coro: Coroutine[Any, Any, None],
        *,
        name: str | None = None,
    ) -> asyncio.Task[None]:
        """Implementation of :class:`pyjmri._protocols.ClientHandle`.

        Spawns ``coro`` in the Client's supervising TaskGroup (architecture
        sec. Concurrency Model: "the library never uses bare
        ``asyncio.create_task`` outside the supervising TaskGroup").
        """
        if self._tg is None:
            raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
        return self._tg.create_task(coro, name=name)

    @property
    def throttle_keepalive_interval(self) -> float:
        """Return the configured per-throttle keep-alive interval (seconds)."""
        return self._config.throttle_keepalive_interval

    def throttle(self, dcc_address: int, *, long: bool) -> Throttle:
        """Create a :class:`Throttle` bound to this Client.

        Equivalent to ``(await client.discover()).throttle(...)`` when you
        don't need the full Layout. The returned :class:`Throttle` has not
        yet acquired — acquire happens on ``async with`` entry.

        Args:
            dcc_address: DCC decoder address (1..10293 typical; JMRI rejects
                addresses outside its valid range).
            long: ``True`` for long (4-digit) addressing, ``False`` for short.
        """
        # Lazy import to avoid the throttle module pulling in client at
        # module load (Throttle imports ClientHandle via TYPE_CHECKING).
        from pyjmri.throttle import Throttle

        return Throttle(self, dcc_address=dcc_address, long=long)

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
            fetch_tasks = {
                entity_type: tg.create_task(_fetch_collection(http, entity_type))
                for entity_type in _ENTITY_SPECS
            }

        # Walk the registry once to build per-type lists. Each spec.build
        # is a typed lambda that constructs the right domain class from a
        # _Parsed<Kind> dataclass; the dict carries list[Any] because the
        # spec table is heterogeneous, and the per-variable list[...] type
        # annotations below pin the concrete element type back down.
        results: dict[str, list[Any]] = {
            entity_type: [
                spec.build(spec.parser(env), self) for env in fetch_tasks[entity_type].result()
            ]
            for entity_type, spec in _ENTITY_SPECS.items()
        }
        turnouts: list[Turnout] = results["turnout"]
        sensors: list[Sensor] = results["sensor"]
        blocks: list[Block] = results["block"]
        lights: list[Light] = results["light"]
        memories: list[Memory] = results["memory"]
        routes: list[Route] = results["route"]
        signal_heads: list[SignalHead] = results["signalHead"]
        signal_masts: list[SignalMast] = results["signalMast"]

        # Rebuild the WS-dispatch entity index from this discovery. Entity
        # types whose spec.primary_attr is None (memory, route in v1) are
        # skipped — they have no _on_event in v1. Stale Layouts returned by
        # prior discover() calls keep their waiters but those waiters will
        # never resolve via dispatch — see discover() docstring.
        new_index: dict[tuple[str, str], Waitable] = {}
        for entity_type, spec in _ENTITY_SPECS.items():
            if spec.primary_attr is None:
                continue
            for entity in results[entity_type]:
                new_index[(entity_type, entity.name)] = entity
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
            handle=self,
        )

    async def discover_operations(self) -> Operations:
        """Enumerate every Operations entity from JMRI and return an Operations snapshot.

        Issues ``GET /json/v5/{entity_type}`` in parallel via
        :class:`asyncio.TaskGroup` for the four Operations types
        (``location``, ``train``, ``car``, ``engine``), parses each with
        the Story 8.1 parsers, and assembles the results into a read-only
        :class:`~pyjmri.Operations` container.

        This is a **separate entry point** from :meth:`discover` — it
        returns an :class:`~pyjmri.Operations` (its own subsystem),
        **not** a :class:`~pyjmri.Layout`, and does not touch the
        Client's WebSocket-dispatch index. Operations entities are
        read-only point-in-time snapshots, not WebSocket-subscribed; to
        refresh, call this method again.

        On the first discovery against a given Client (whether via
        :meth:`discover` or this method), the JMRI application version is
        fetched from ``/json/v5/networkService`` and rejected if older
        than 5.14 (NFR8). The check is cached for the Client's lifetime
        and shared with :meth:`discover` — subsequent sequential calls to
        either method skip the probe.

        Returns:
            A populated :class:`~pyjmri.Operations`. A JMRI instance with
            no Operations data configured yields a container whose four
            collections are empty — that is a valid result, not an error
            (FR50).

        Raises:
            JMRIVersionUnsupported: when the running JMRI is older than
                5.14 (only if the version check has not already run).
            JMRIProtocolError: when a per-type response is malformed
                (e.g., not a list, missing required fields).
            JMRIConnectionError, JMRIRequestTimeout: surfaced from the
                HTTP transport.
            RuntimeError: when the Client is not open (use
                ``async with Client() as jmri:`` first).

        Note:
            If one of the four parallel per-type fetches fails,
            :class:`asyncio.TaskGroup` cancels the others and propagates
            the underlying error wrapped in an :class:`ExceptionGroup`.
            Catch with ``except* JMRIProtocolError`` (Python 3.11+) or
            ``except ExceptionGroup``.
        """
        if self._http is None:
            raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
        http = self._http

        if not self._version_checked:
            version_payload = await http.get("/json/v5/networkService")
            _check_jmri_version(version_payload)
            self._version_checked = True

        async with asyncio.TaskGroup() as tg:
            fetch_tasks = {
                entity_type: tg.create_task(_fetch_collection(http, entity_type))
                for entity_type in _OPERATIONS_PARSERS
            }

        # Each Operations parser returns the public frozen entity directly
        # (no _Parsed<Kind>/build step — these entities carry no handle).
        # The dict is list[Any] because the parser table is heterogeneous;
        # the per-variable annotations below pin the element type back down.
        results: dict[str, list[Any]] = {
            entity_type: [parser(env) for env in fetch_tasks[entity_type].result()]
            for entity_type, parser in _OPERATIONS_PARSERS.items()
        }
        locations: list[Location] = results["location"]
        trains: list[Train] = results["train"]
        cars: list[Car] = results["car"]
        engines: list[Engine] = results["engine"]

        # Deliberately does NOT rebuild self._entities (the WS-dispatch
        # index): Operations entities are read-only snapshots with no
        # _on_event, and clobbering the index would break in-flight Layout
        # wait_* calls (Epic 8 scope: Epics 1-6 behavior unchanged).
        return Operations(
            locations=EntityCollection(locations, entity_type="location"),
            trains=EntityCollection(trains, entity_type="train"),
            cars=EntityCollection(cars, entity_type="car"),
            engines=EntityCollection(engines, entity_type="engine"),
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


@dataclass(frozen=True, slots=True)
class _EntitySpec:
    """Per-entity-type registry entry for :meth:`Client.discover` and the WS dispatcher.

    ``parser`` consumes one JMRI envelope and returns a ``_Parsed<Kind>``
    dataclass. ``build`` constructs the matching public domain object
    from that dataclass and the owning :class:`ClientHandle`.
    ``primary_attr`` names the field on the parsed dataclass that the
    WS dispatcher passes into ``entity._on_event`` — ``None`` for entity
    types that are not modelled as waitable in v1 (``memory``, ``route``).
    """

    parser: Callable[[dict[str, Any]], Any]
    build: Callable[[Any, ClientHandle], Any]
    primary_attr: str | None


_ENTITY_SPECS: dict[str, _EntitySpec] = {
    "turnout": _EntitySpec(
        parser=parse_turnout,
        build=lambda p, h: Turnout(name=p.name, user_name=p.user_name, state=p.state, _handle=h),
        primary_attr="state",
    ),
    "sensor": _EntitySpec(
        parser=parse_sensor,
        build=lambda p, h: Sensor(name=p.name, user_name=p.user_name, state=p.state, _handle=h),
        primary_attr="state",
    ),
    "block": _EntitySpec(
        parser=parse_block,
        build=lambda p, h: Block(
            name=p.name,
            user_name=p.user_name,
            state=p.state,
            value=p.value,
            _handle=h,
        ),
        primary_attr="state",
    ),
    "light": _EntitySpec(
        parser=parse_light,
        build=lambda p, h: Light(name=p.name, user_name=p.user_name, state=p.state, _handle=h),
        primary_attr="state",
    ),
    "memory": _EntitySpec(
        parser=parse_memory,
        build=lambda p, h: Memory(name=p.name, user_name=p.user_name, value=p.value, _handle=h),
        primary_attr=None,
    ),
    "route": _EntitySpec(
        parser=parse_route,
        build=lambda p, h: Route(name=p.name, user_name=p.user_name, _handle=h),
        primary_attr=None,
    ),
    "signalHead": _EntitySpec(
        parser=parse_signal_head,
        build=lambda p, h: SignalHead(
            name=p.name,
            user_name=p.user_name,
            appearance=p.appearance,
            held=p.held,
            lit=p.lit,
            _handle=h,
        ),
        primary_attr="appearance",
    ),
    "signalMast": _EntitySpec(
        parser=parse_signal_mast,
        build=lambda p, h: SignalMast(
            name=p.name,
            user_name=p.user_name,
            aspect=p.aspect,
            held=p.held,
            lit=p.lit,
            _handle=h,
        ),
        primary_attr="aspect",
    ),
}
"""Single source of truth for every entity type pyjmri knows about.

Driven by :meth:`Client.discover` (uses ``parser`` + ``build``) and by
:meth:`Client._on_ws_message` (uses ``parser`` + ``primary_attr``).
Adding a new entity type is one entry here plus the domain class.
Entries with ``primary_attr=None`` are built and surfaced in the
:class:`~pyjmri.Layout` but excluded from the WS dispatch index — their
state changes are not modelled as waitable events in v1.
"""


_OPERATIONS_PARSERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "location": parse_location,
    "train": parse_train,
    "car": parse_car,
    "engine": parse_engine,
}
"""Single source of truth for the read-only Operations subsystem (FR45-FR48).

Driven by :meth:`Client.discover_operations`. Simpler than
:data:`_ENTITY_SPECS`: each Operations parser returns its public frozen
entity directly, so there is no ``build`` step (no client handle) and no
``primary_attr`` (Operations entities are not WebSocket-waitable).
"""


def _unwrap_exception_group(
    eg: BaseExceptionGroup,
    *,
    body_exc: BaseException | None = None,
) -> BaseException | None:
    """Filter cancellations out of a TaskGroup ExceptionGroup.

    The two call sites — :meth:`Client.__aexit__` and
    :meth:`Client._teardown_on_aenter_failure` — share the same need to
    extract the meaningful exception from a TaskGroup's wrapped result.
    Returns:

    - ``None`` when the group should be suppressed. Two cases: the group
      contained only :class:`asyncio.CancelledError` (clean teardown), or
      the lone non-cancellation IS ``body_exc`` (already propagating via
      the context-manager protocol — used only by ``__aexit__``).
    - A :class:`BaseException` distinct from ``body_exc`` when there is
      exactly one non-cancellation. The caller raises it with
      ``from None`` to keep the traceback focused on the underlying
      cause rather than the TaskGroup wrapping.
    - ``eg`` itself when there is more than one non-cancellation. The
      caller (inside ``except BaseExceptionGroup as eg``) should
      bare-``raise`` to preserve the original group.
    """
    non_cancelled = [e for e in eg.exceptions if not isinstance(e, asyncio.CancelledError)]
    if len(non_cancelled) == 1 and non_cancelled[0] is body_exc:
        return None
    if len(non_cancelled) == 1:
        return non_cancelled[0]
    if non_cancelled:
        return eg
    return None


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

# JMRI's networkService envelope sometimes carries a build-suffixed version
# string like "5.14+Rdea51dcccf"; only the leading dotted-numeric prefix is
# the version we gate on. Anchored at start; the suffix is ignored.
_JMRI_VERSION_PREFIX_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?")


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
    match = _JMRI_VERSION_PREFIX_RE.match(version)
    if match is None:
        raise JMRIProtocolError(
            "networkService response 'jmri' field has no leading numeric version",
            path=_VERSION_PATH,
            field="jmri",
            value=version,
        )
    detected = tuple(int(part) for part in match.groups() if part is not None)
    if detected < _MIN_JMRI_VERSION:
        raise JMRIVersionUnsupported(detected=version, required=_MIN_JMRI_VERSION_STR)
