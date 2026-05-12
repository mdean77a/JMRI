"""Subscription registry — authoritative set of WS subscriptions.

See architecture sec. Subscription Registry & Event Fanout. The registry
is decoupled from any particular :class:`~pyjmri._transport.WSConnection`:
it holds an injected ``send`` callable, which lets unit tests substitute
a recording fake without standing up real transport.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("pyjmri.subscription")

__all__ = ["SubscriptionRegistry"]


class SubscriptionRegistry:
    """Authoritative set of ``(entity_type, name)`` WS subscriptions.

    Args:
        send: Async callable that delivers an outbound envelope on the
            current WebSocket. In production this is
            :meth:`pyjmri._transport.WSConnection.send`; tests pass a
            recording fake.
    """

    def __init__(self, send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._send = send
        self._subscriptions: set[tuple[str, str]] = set()

    @property
    def size(self) -> int:
        """Number of distinct ``(entity_type, name)`` subscriptions."""
        return len(self._subscriptions)

    async def ensure(self, entity_type: str, name: str) -> None:
        """Idempotently subscribe to state-change events for ``(entity_type, name)``.

        First call for a given pair adds it to the authoritative set and
        sends a subscribe envelope. Subsequent calls for the same pair
        are no-ops (no duplicate add, no duplicate envelope).
        """
        key = (entity_type, name)
        if key in self._subscriptions:
            return
        self._subscriptions.add(key)
        logger.info(
            "subscribed",
            extra={"entity_type": entity_type, "system_name": name},
        )
        await self._send(_format_subscribe(entity_type, name))

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
