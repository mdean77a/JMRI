"""Per-entity waiter list: ``(predicate, future)`` pairs.

Architecture sec. Subscription Registry & Event Fanout. Single
event loop ⇒ no lock needed; fanout is synchronous. The list is
internal to each state-bearing entity; the WS receive loop drives
it via ``entity._on_event(new_state)``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

StateT = TypeVar("StateT")

__all__ = ["WaiterList"]


class WaiterList(Generic[StateT]):
    """List of ``(predicate, future)`` pairs awaiting matching state events.

    Each entity owns one instance. ``wait_*`` methods on the entity
    call :meth:`register` to enroll a future, then ``await`` it. The
    WS receive loop calls :meth:`fanout` from
    ``entity._on_event(new_state)``; matching futures resolve, done
    futures get pruned, non-matching futures stay registered.
    """

    def __init__(self) -> None:
        self._entries: list[tuple[Callable[[StateT], bool], asyncio.Future[StateT]]] = []

    def __len__(self) -> int:
        return len(self._entries)

    def register(self, predicate: Callable[[StateT], bool]) -> asyncio.Future[StateT]:
        """Create a fresh future, register ``(predicate, future)``, return the future.

        Must be called from within an active asyncio event loop.
        """
        future: asyncio.Future[StateT] = asyncio.get_running_loop().create_future()
        self._entries.append((predicate, future))
        return future

    def remove(self, future: asyncio.Future[StateT]) -> None:
        """Drop the entry whose future matches; cancel the future if it was registered.

        Idempotent: removing a future that's no longer in the list (e.g.,
        because :meth:`fanout` already resolved and pruned it) is a no-op
        and does NOT cancel the future. The cancel side effect fires only
        when an entry was actually removed by this call — never on a
        foreign future the caller passes in by mistake.
        """
        before = len(self._entries)
        self._entries = [(p, f) for (p, f) in self._entries if f is not future]
        removed = before != len(self._entries)
        if removed and not future.done():
            future.cancel()

    def fanout(self, new_state: StateT) -> None:
        """Resolve every matching, not-done future; prune done futures.

        Per-entry guard: if a single predicate raises, log + drop that
        entry and continue iterating the rest of the list. One bad
        predicate cannot poison the fanout for every other waiter on
        the entity.
        """
        kept: list[tuple[Callable[[StateT], bool], asyncio.Future[StateT]]] = []
        try:
            for predicate, future in self._entries:
                if future.done():
                    continue
                try:
                    if predicate(new_state):
                        future.set_result(new_state)
                    else:
                        kept.append((predicate, future))
                except Exception as e:
                    logger.warning(
                        "WaiterList: predicate raised; dropping entry",
                        extra={"error_type": type(e).__name__},
                        exc_info=True,
                    )
                    if not future.done():
                        future.cancel()
        finally:
            self._entries = kept
