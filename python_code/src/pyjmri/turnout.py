"""Turnout entity class and TurnoutState enum.

Architecture sec. Domain State Modeling.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyjmri._protocols import ClientHandle

logger = logging.getLogger(__name__)

__all__ = ["Turnout", "TurnoutState"]


class TurnoutState(Enum):
    UNKNOWN = "unknown"
    CLOSED = "closed"
    THROWN = "thrown"
    INCONSISTENT = "inconsistent"


class Turnout:
    """A JMRI turnout discovered on the layout.

    The cached :attr:`state` reflects JMRI's last commanded position,
    not the physical state of the turnout on the layout — JMRI knows
    only what it has been told (NCE is open-loop). When the position
    has never been commanded since JMRI started, the state is
    :attr:`TurnoutState.UNKNOWN` and pyjmri preserves it as ``UNKNOWN``
    rather than coercing to ``CLOSED`` (FR14).

    Example:
        Refresh a turnout's state from JMRI::

            current = await turnout.get_state()
            if current is TurnoutState.THROWN:
                ...

    Args:
        name: JMRI system name (e.g., ``"NT400"``).
        user_name: Optional JMRI user name.
        state: Initial cached state (typically captured by
            :meth:`pyjmri.Client.discover` in Story 2.5).
        _handle: Internal :class:`~pyjmri._protocols.ClientHandle`
            issued by the owning :class:`~pyjmri.Client`.
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
        state: TurnoutState,
        _handle: ClientHandle,
    ) -> None:
        self.name = name
        self.user_name = user_name
        self.state = state
        self._handle = _handle

    async def get_state(self) -> TurnoutState:
        """Refresh the cached :attr:`state` from JMRI and return it.

        Only :attr:`state` is updated; :attr:`name` and :attr:`user_name`
        are identity fields and are never refreshed.

        Returns:
            The newly read :class:`TurnoutState`. ``UNKNOWN`` is a real,
            first-class value — the library never coerces it to
            ``CLOSED`` (FR14).

        Raises:
            JMRIProtocolError, JMRIConnectionError, JMRIRequestTimeout:
                surfaced from :class:`~pyjmri.Client`.
        """
        from pyjmri._parsing import parse_turnout

        envelope = await self._handle.get_entity("turnout", self.name)
        parsed = parse_turnout(envelope)
        self.state = parsed.state
        return parsed.state
