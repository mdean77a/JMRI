"""Subscription registry — authoritative set of WS subscriptions.

See architecture sec. Subscription Registry & Event Fanout. The registry
is decoupled from any particular :class:`~pyjmri._transport.WSConnection`:
it holds an injected ``send`` callable, which lets unit tests substitute
a recording fake without standing up real transport.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("pyjmri.subscription")

__all__ = ["SubscriptionRegistry"]

# How long ensure() waits for JMRI's subscription ack (the current-entity
# envelope JMRI echoes back on the WS when it processes a subscribe frame)
# before proceeding without it. Generous versus the observed ack latency
# (single-digit ms on localhost) while still bounding a broken path.
_ACK_TIMEOUT_S = 2.0


class SubscriptionRegistry:
    """Authoritative set of ``(entity_type, name)`` WS subscriptions.

    Args:
        send: Async callable that delivers an outbound envelope on the
            current WebSocket. In production this is
            :meth:`pyjmri._transport.WSConnection.send`; tests pass a
            recording fake.
        ack_timeout: Seconds :meth:`ensure` waits for JMRI's subscription
            ack before proceeding without it. Tests exercising the
            no-ack path pass a small value to stay fast.
    """

    def __init__(
        self,
        send: Callable[[dict[str, Any]], Awaitable[None]],
        *,
        ack_timeout: float = _ACK_TIMEOUT_S,
    ) -> None:
        self._send = send
        self._ack_timeout = ack_timeout
        self._subscriptions: set[tuple[str, str]] = set()
        self._acks: dict[tuple[str, str], asyncio.Event] = {}

    @property
    def size(self) -> int:
        """Number of distinct ``(entity_type, name)`` subscriptions."""
        return len(self._subscriptions)

    async def ensure(self, entity_type: str, name: str) -> None:
        """Subscribe to state-change events for ``(entity_type, name)`` and
        wait until JMRI has confirmed the enrollment.

        First call for a given pair adds it to the authoritative set and
        sends a subscribe envelope; subsequent calls send nothing. Every
        call then waits (bounded by ``ack_timeout``) until JMRI's ack —
        the current-entity envelope it echoes back on the WS — has been
        observed via :meth:`notify_envelope`. Returning only after the
        ack is what makes the wait-primitives race-free: JMRI attaches
        its event listener when it processes the subscribe frame, so an
        unacked subscription can silently miss a state change commanded
        immediately after ``ensure()`` returns (observed as a ~50%
        first-``wait_change`` failure when a previous Client's teardown
        delayed the server's frame processing).

        On ack timeout, logs a WARNING and returns anyway — degrading to
        the historical fire-and-forget behavior rather than failing the
        caller's wait outright; the reconnect replay path re-sends every
        subscription, so a lost frame heals on the next reconnect.
        """
        key = (entity_type, name)
        if key not in self._subscriptions:
            self._subscriptions.add(key)
            self._acks[key] = asyncio.Event()
            logger.info(
                "subscribed",
                extra={"entity_type": entity_type, "system_name": name},
            )
            await self._send(_format_subscribe(entity_type, name))
        ack = self._acks.get(key)
        if ack is None or ack.is_set():
            return
        try:
            async with asyncio.timeout(self._ack_timeout):
                await ack.wait()
        except TimeoutError:
            logger.warning(
                "subscription ack not received; proceeding without it",
                extra={
                    "entity_type": entity_type,
                    "system_name": name,
                    "ack_timeout_s": self._ack_timeout,
                },
            )

    def notify_envelope(self, entity_type: str, name: str) -> None:
        """Record that an inbound WS envelope arrived for ``(entity_type, name)``.

        Called by the Client's WS dispatch for every inbound entity
        envelope. Any envelope for a subscribed pair proves JMRI has the
        listener attached (it only emits envelopes for enrolled pairs or
        as the subscribe ack itself), so it releases waiters blocked in
        :meth:`ensure`. Cheap no-op for unsubscribed pairs.
        """
        ack = self._acks.get((entity_type, name))
        if ack is not None and not ack.is_set():
            ack.set()

    async def replay(self) -> None:
        """Re-send every known subscription. Called by the WS supervisor on reconnect."""
        logger.debug(
            "replaying subscriptions",
            extra={"subscription_count": len(self._subscriptions)},
        )
        for entity_type, name in self._subscriptions:
            await self._send(_format_subscribe(entity_type, name))


def _format_subscribe(entity_type: str, name: str) -> dict[str, Any]:
    """Build the outbound subscribe envelope JMRI expects.

    Validated 2026-05-12 against live JMRI 5.14+Rdea51dcccf: sending
    ``{"type": "<entity_type>", "data": {"name": "<system_name>"}}`` on
    ``ws://host:port/json/`` returns the current entity envelope and
    enrolls the connection for future state-change events.
    """
    return {"type": entity_type, "data": {"name": name}}
