"""Turnout entity class and TurnoutState enum.

Architecture sec. Domain State Modeling.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import TYPE_CHECKING

from pyjmri._waiters import WaiterList
from pyjmri.exceptions import WaitTimeout

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

        Wait for a state change pushed over the WebSocket::

            await turnout.wait_state(TurnoutState.THROWN, timeout=5.0)
            await turnout.wait_change()  # any transition from current

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
        self._waiters: WaiterList[TurnoutState] = WaiterList()

    async def set_state(self, state: TurnoutState) -> None:
        """Command the turnout to ``state`` (FR17).

        Returns when JMRI has accepted the command; the library does not
        confirm physical layout state because NCE is open-loop.

        ``state`` must be ``TurnoutState.CLOSED`` or
        ``TurnoutState.THROWN``. Passing ``UNKNOWN`` or ``INCONSISTENT``
        raises :class:`ValueError` synchronously — those are observable-
        only states, not commandable.

        FR37 discipline: the only exceptions this method ever raises are
        ``JMRIConnectionError``, ``JMRIRequestTimeout``,
        ``JMRIProtocolError``, ``LayoutEntityNotFound``,
        ``LayoutEntityNotControllable``, and ``ValueError`` for invalid
        commandable-state arguments. The library does not synthesize
        exceptions for failure modes it cannot detect — e.g., the
        physical turnout failing to move on the layout. NCE is
        open-loop; pyjmri never claims a state it has not observed.

        Note:
            Story 4.2 adds a ``wait_for_jmri_state=True`` keyword for
            callers who want to await JMRI's WS-reported post-command
            state. In this version the method is optimistic only.
        """
        from pyjmri._codes import TURNOUT_STATE_OUTBOUND

        if state not in TURNOUT_STATE_OUTBOUND:
            raise ValueError(
                f"{state!r} is not a commandable turnout state; "
                f"use {sorted(s.name for s in TURNOUT_STATE_OUTBOUND)!r}"
            )
        await self._handle.command("turnout", self.name, {"state": TURNOUT_STATE_OUTBOUND[state]})

    async def throw(self) -> None:
        """Alias for ``set_state(TurnoutState.THROWN)`` (FR17).

        Returns when JMRI has accepted the command; the library does not
        confirm physical layout state because NCE is open-loop.
        """
        await self.set_state(TurnoutState.THROWN)

    async def close(self) -> None:
        """Alias for ``set_state(TurnoutState.CLOSED)`` (FR17).

        Returns when JMRI has accepted the command; the library does not
        confirm physical layout state because NCE is open-loop.
        """
        await self.set_state(TurnoutState.CLOSED)

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

    def _on_event(self, new_state: TurnoutState) -> None:
        """Update cached state and resolve matching waiters.

        Called from :meth:`pyjmri.Client._on_ws_message` on inbound
        turnout state-change envelopes.
        """
        self.state = new_state
        self._waiters.fanout(new_state)

    async def wait_state(
        self,
        target: TurnoutState,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> TurnoutState:
        """Await the turnout reaching ``target`` (FR31).

        Returns immediately when :attr:`state` already equals ``target``.
        Otherwise auto-subscribes the entity, registers a one-shot
        waiter on :attr:`state` and awaits it.

        Raises:
            WaitTimeout: if ``timeout`` elapses before the target state.
            RuntimeError: if the owning :class:`~pyjmri.Client` is closed
                while this call is suspended inside ``ensure_subscription``.
        """
        if self.state == target:
            return self.state
        await self._handle.ensure_subscription("turnout", self.name)
        if self.state == target:
            return self.state
        future = self._waiters.register(lambda s: s == target)
        try:
            if timeout is None:
                return await future
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as e:
            raise WaitTimeout(
                entity_type="turnout",
                name=self.name,
                target=target.name,
            ) from e
        finally:
            self._waiters.remove(future)

    async def wait_change(
        self,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> TurnoutState:
        """Await the next state change from whatever :attr:`state` is now (FR32).

        Captures :attr:`state` after ensuring the subscription is live, so
        the "starting" reference cannot be invalidated by an event that
        arrives during the subscribe await.

        Raises:
            WaitTimeout: if ``timeout`` elapses before any state change.
            RuntimeError: if the owning :class:`~pyjmri.Client` is closed
                while this call is suspended inside ``ensure_subscription``.
        """
        await self._handle.ensure_subscription("turnout", self.name)
        starting = self.state
        future = self._waiters.register(lambda s: s != starting)
        try:
            if timeout is None:
                return await future
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as e:
            raise WaitTimeout(
                entity_type="turnout",
                name=self.name,
                from_state=starting.name,
            ) from e
        finally:
            self._waiters.remove(future)
