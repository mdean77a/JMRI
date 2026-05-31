"""Turnout entity class and TurnoutState enum.

Architecture sec. Domain State Modeling.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import TYPE_CHECKING

from pyjmri._wait_helpers import wait_for_change, wait_for_target
from pyjmri._waiters import WaiterList

if TYPE_CHECKING:
    from pyjmri._protocols import ClientHandle

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

    async def set_state(
        self,
        state: TurnoutState,
        *,
        wait_for_jmri_state: bool = False,
    ) -> None:
        """Command the turnout to ``state`` (FR17, FR21).

        With ``wait_for_jmri_state=False`` (the default), returns when
        JMRI has accepted the command via HTTP. With
        ``wait_for_jmri_state=True``, returns only after JMRI has
        reported the post-command state via its WebSocket state-change
        event.

        ``state`` must be ``TurnoutState.CLOSED`` or
        ``TurnoutState.THROWN``. Passing ``UNKNOWN`` or ``INCONSISTENT``
        raises :class:`ValueError` synchronously — those are observable-
        only states, not commandable.

        FR22 honesty: ``wait_for_jmri_state=True`` waits for JMRI's
        *reported* commanded state, **not** physical layout confirmation.
        NCE is open-loop with no feedback path; the library cannot and
        does not promise the physical turnout actually moved. JMRI's WS
        state-change echo for turnouts is verified on this layout (JMRI
        5.14 simulator). On other JMRI versions or layouts where the WS
        echo is not emitted, a ``wait_for_jmri_state=True`` call will
        hang until cancelled — wrap in ``asyncio.timeout()`` if you
        cannot tolerate that.

        Cancellation contract (AC4 of Story 4.2): if a caller cancels
        a ``wait_for_jmri_state=True`` operation (e.g. via
        ``asyncio.timeout``), the wait future is cancelled and removed
        from the entity's waiter list, but the in-flight HTTP command
        is shielded and allowed to complete in the background. Its
        result is silently discarded. Cancelling the command mid-flight
        could leave JMRI in an indeterminate state, so the library
        prefers to let the command finish.

        FR37 discipline: the only exceptions this method ever raises are
        ``JMRIConnectionError``, ``JMRIRequestTimeout``,
        ``JMRIProtocolError``, ``LayoutEntityNotFound``,
        ``LayoutEntityNotControllable``, ``ValueError`` (for invalid
        commandable-state arguments), and — when
        ``wait_for_jmri_state=True`` — whatever the caller's cancellation
        scope propagates (``asyncio.CancelledError`` /
        ``TimeoutError``). The library does not synthesize exceptions
        for failure modes it cannot detect (the physical turnout
        failing to move, JMRI silently dropping the state event, etc.).
        """
        from pyjmri._codes import TURNOUT_STATE_OUTBOUND

        if state not in TURNOUT_STATE_OUTBOUND:
            raise ValueError(
                f"{state!r} is not a commandable turnout state; "
                f"use {sorted(s.name for s in TURNOUT_STATE_OUTBOUND)!r}"
            )

        payload = {"state": TURNOUT_STATE_OUTBOUND[state]}

        if not wait_for_jmri_state:
            await self._handle.command("turnout", self.name, payload)
            return

        # Pre-register-wait pattern (architecture sec. Command / Event
        # Correlation). Order matters: ensure subscription, register
        # waiter, send command, await event. If the waiter were
        # registered AFTER the command went out, a fast post-ack state
        # event could race ahead of registration and be silently dropped.
        await self._handle.ensure_subscription("turnout", self.name)
        future = self._waiters.register(lambda s: s == state)
        try:
            # asyncio.shield: a caller-side cancel must not abort the
            # in-flight HTTP command. JMRI would be left uncertain
            # whether the command was received. The outer await raises
            # CancelledError immediately; the inner task finishes in
            # the background.
            await asyncio.shield(self._handle.command("turnout", self.name, payload))
            await future
        except BaseException:
            self._waiters.remove(future)
            raise

    async def throw(self, *, wait_for_jmri_state: bool = False) -> None:
        """Alias for ``set_state(TurnoutState.THROWN, ...)`` (FR17, FR21).

        See :meth:`set_state` for the ``wait_for_jmri_state`` contract.
        """
        await self.set_state(TurnoutState.THROWN, wait_for_jmri_state=wait_for_jmri_state)

    async def close(self, *, wait_for_jmri_state: bool = False) -> None:
        """Alias for ``set_state(TurnoutState.CLOSED, ...)`` (FR17, FR21).

        See :meth:`set_state` for the ``wait_for_jmri_state`` contract.
        """
        await self.set_state(TurnoutState.CLOSED, wait_for_jmri_state=wait_for_jmri_state)

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
        return await wait_for_target(
            handle=self._handle,
            entity_type="turnout",
            name=self.name,
            waiters=self._waiters,
            read_state=lambda: self.state,
            target=target,
            timeout=timeout,
        )

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
        return await wait_for_change(
            handle=self._handle,
            entity_type="turnout",
            name=self.name,
            waiters=self._waiters,
            read_state=lambda: self.state,
            timeout=timeout,
        )
