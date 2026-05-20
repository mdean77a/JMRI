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
