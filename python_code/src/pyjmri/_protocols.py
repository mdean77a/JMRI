"""Slim Client surface that domain entities depend on.

Defining these Protocols keeps ``_transport.py`` and ``_subscriptions.py``
out of ``turnout.py``, ``sensor.py``, etc. Entity modules import only
:class:`ClientHandle`. The concrete implementation lives on
:class:`pyjmri.Client`; the indirection lets unit tests construct
entities with a fake handle.

Architecture sec. Internal Layering: domain entities hold a
Protocol-typed handle to the Client for issuing commands and for
auto-subscription. They do not import ``_transport`` or
``_subscriptions`` directly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, Protocol


class ClientHandle(Protocol):
    """Internal Protocol for entity → Client calls.

    The :class:`pyjmri.Client` implements this Protocol implicitly via
    duck typing: it has matching ``get_entity`` and
    ``ensure_subscription`` methods.

    This Protocol is not part of the public API; users of pyjmri never
    interact with it. It exists to satisfy mypy strict mode in entity
    modules without importing ``_transport`` or ``_subscriptions``
    (transport/domain boundary preservation).
    """

    async def get_entity(self, entity_type: str, name: str) -> dict[str, Any]: ...

    async def ensure_subscription(self, entity_type: str, name: str) -> None:
        """Idempotently subscribe to WS state-change events.

        Entity ``wait_*`` methods call this to enroll the entity for
        push events before registering a waiter (FR29 — no manual
        subscription bookkeeping).
        """
        ...

    async def command(
        self,
        entity_type: str,
        name: str,
        payload: dict[str, Any],
    ) -> None:
        """Issue an HTTP command to JMRI and return when JMRI acks.

        Story 4.1 implements the optimistic path (HTTP 2xx is the
        contract; no WS-event confirmation). Story 4.2 layers
        ``wait_for_jmri_state=True`` over per-entity command methods.
        See architecture sec. Command / Event Correlation.
        """
        ...

    async def throttle_acquire(self, dcc_address: int, *, long: bool) -> str:
        """Acquire a JMRI throttle for ``dcc_address``; return the internal name.

        Per Story 5.1 Task 0 spike, JMRI's throttle API is WS-only. The
        implementation generates an internal correlation name
        (``pyjmri-<addr>-<8-hex>``), sends a WS acquire envelope, and
        awaits a name-keyed response future. Raises
        :class:`ThrottleAcquireFailed` if JMRI emits a ``type:error``
        envelope while this acquire is pending (FIFO correlation queue).
        The returned string is the internal name; users never see it.
        """
        ...

    async def throttle_release(self, throttle_id: str) -> None:
        """Release a throttle by its internal name (fire-and-forget WS).

        Sends ``{"type":"throttle","data":{"throttle":<id>,"release":null}}``
        and returns immediately. The release-echo envelope is consumed by
        the WS dispatcher but not awaited (Story 5.1 AC4).
        """
        ...

    async def throttle_heartbeat(self, throttle_id: str) -> None:
        """Per-throttle heartbeat hookpoint — Story 5.3.

        v1 implementation raises :class:`NotImplementedError`. JMRI's WS-level
        heartbeat (Story 3.1 transport, ``ping_interval=10 s``) keeps the
        connection — and therefore all held throttles — alive; no per-throttle
        application heartbeat is needed in v1 (Story 5.1 AC3, Task 0 spike).
        """
        ...

    async def throttle_update(
        self,
        throttle_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Send a fire-and-forget WS state-update envelope for ``throttle_id``.

        Wraps ``payload`` in ``{"type":"throttle","data":{"throttle":<id>,
        **payload}}`` and writes it to the WS connection. Returns as soon as
        the bytes are written; does NOT await JMRI's state-echo (Story 5.2
        AC1 — symmetric with :meth:`throttle_release`'s fire-and-forget
        design). State-echo envelopes arrive on the WS dispatcher and fall
        through the ``future is None`` path in
        :meth:`pyjmri.Client._dispatch_throttle_envelope` (silently dropped).
        """
        ...

    def spawn_supervised(
        self,
        coro: Coroutine[Any, Any, None],
        *,
        name: str | None = None,
    ) -> asyncio.Task[None]:
        """Spawn ``coro`` in the Client's supervising TaskGroup.

        Raises :class:`RuntimeError` if the Client is not in an active
        ``async with`` context (architecture sec. Concurrency Model — no
        bare ``asyncio.create_task`` outside the supervising TaskGroup).
        """
        ...

    @property
    def throttle_keepalive_interval(self) -> float:
        """The configured keep-alive interval in seconds.

        Story 5.1 ships with a no-op keep-alive body, so this value is
        currently unused by the loop itself. Reserved for Story 5.3 if
        hardware observation finds a heartbeat is needed.
        """
        ...


class Waitable(Protocol):
    """Internal Protocol describing a state-bearing entity.

    The :class:`pyjmri.Client` keeps a ``dict[(entity_type, name),
    Waitable]`` index built at ``discover()`` time so the WS receive
    loop can dispatch envelopes by ``(type, name)`` to the right
    entity's ``_on_event`` method without caring about the concrete
    primary-state type. ``_on_event`` accepts ``object`` here because
    dispatch is dynamic; each concrete entity narrows its argument to
    the right state enum at call time via its parsed payload.
    """

    name: str

    def _on_event(self, new_state: Any) -> None: ...
