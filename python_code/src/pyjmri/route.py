"""Route entity and ``RouteState`` enum."""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyjmri._protocols import ClientHandle

logger = logging.getLogger(__name__)

__all__ = ["Route", "RouteState"]


class RouteState(Enum):
    """JMRI Route activation state.

    Routes in pyjmri v1 are activation-only — once a route is fired, the
    turnouts have moved and the route returns to "ready to fire again."
    There is no commandable INACTIVE; ``UNKNOWN`` is the FR14-preserved
    default for routes JMRI has never reported a state for.
    """

    UNKNOWN = "unknown"
    ACTIVE = "active"


class Route:
    """A JMRI route — a saved sequence of turnout positions.

    In pyjmri v1 a :class:`Route` exposes metadata (name and user name)
    and an :meth:`activate` method that fires the saved sequence. Routes
    have no readable state in v1 — JMRI reports the route's internal
    state as ``0`` even after activation because the route is a trigger,
    not a state machine.

    Example:
        Activate every route in the layout::

            for route in layout.routes.values():
                await route.activate()

    Args:
        name: JMRI system name.
        user_name: Optional JMRI user name.
        _handle: Internal :class:`~pyjmri._protocols.ClientHandle` issued
            by the owning :class:`~pyjmri.Client`.
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
        _handle: ClientHandle,
    ) -> None:
        self.name = name
        self.user_name = user_name
        self._handle = _handle

    async def activate(self) -> None:
        """Activate the route (FR20).

        Sends ``POST /json/v5/route/<name>`` with the JMRI ACTIVATE state
        code. Returns when JMRI has accepted the activation; the library
        does not confirm the physical turnout outcomes because NCE is
        open-loop.

        ``wait_for_jmri_state=True`` is not available on this method in
        v1 — routes have no observable persistent post-state to wait on
        (JMRI emits ``state=0`` after activation). Story 4.2 introduces
        the keyword on state-bearing command methods only. See README
        §Limitations.
        """
        from pyjmri._codes import ROUTE_STATE_OUTBOUND

        await self._handle.command(
            "route", self.name, {"state": ROUTE_STATE_OUTBOUND[RouteState.ACTIVE]}
        )
