"""Light entity class and LightState enum.

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

__all__ = ["Light", "LightState"]


class LightState(Enum):
    UNKNOWN = "unknown"
    ON = "on"
    OFF = "off"
    INCONSISTENT = "inconsistent"


class Light:
    """A JMRI light (panel indicator, layout LED, etc.).

    The cached :attr:`state` reflects JMRI's last commanded value. When
    the light has not yet been commanded, the state is
    :attr:`LightState.UNKNOWN` and pyjmri preserves it as ``UNKNOWN``
    rather than coercing to ``OFF`` (FR14).

    Example:
        Refresh a light's state from JMRI::

            current = await light.get_state()
            if current is LightState.ON:
                ...

        Wait for a state change pushed over the WebSocket::

            await light.wait_state(LightState.ON, timeout=5.0)
            await light.wait_change()

    Args:
        name: JMRI system name.
        user_name: Optional JMRI user name.
        state: Initial cached state.
        _handle: Internal :class:`~pyjmri._protocols.ClientHandle`
            issued by the owning :class:`~pyjmri.Client`.
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
        state: LightState,
        _handle: ClientHandle,
    ) -> None:
        self.name = name
        self.user_name = user_name
        self.state = state
        self._handle = _handle
        self._waiters: WaiterList[LightState] = WaiterList()

    async def set_state(self, state: LightState) -> None:
        """Command the light to ``state`` (FR19).

        Returns when JMRI has accepted the command; the library does not
        confirm physical layout state because NCE is open-loop.

        ``state`` must be ``LightState.ON`` or ``LightState.OFF``.
        Passing ``UNKNOWN`` or ``INCONSISTENT`` raises :class:`ValueError`
        synchronously — those are observable-only states, not
        commandable.

        Note:
            Story 4.2 adds a ``wait_for_jmri_state=True`` keyword for
            callers who want to await JMRI's WS-reported post-command
            state. In this version the method is optimistic only.
        """
        from pyjmri._codes import LIGHT_STATE_OUTBOUND

        if state not in LIGHT_STATE_OUTBOUND:
            raise ValueError(
                f"{state!r} is not a commandable light state; "
                f"use {sorted(s.name for s in LIGHT_STATE_OUTBOUND)!r}"
            )
        await self._handle.command("light", self.name, {"state": LIGHT_STATE_OUTBOUND[state]})

    async def on(self) -> None:
        """Alias for ``set_state(LightState.ON)`` (FR19).

        Returns when JMRI has accepted the command; the library does not
        confirm physical layout state because NCE is open-loop.
        """
        await self.set_state(LightState.ON)

    async def off(self) -> None:
        """Alias for ``set_state(LightState.OFF)`` (FR19).

        Returns when JMRI has accepted the command; the library does not
        confirm physical layout state because NCE is open-loop.
        """
        await self.set_state(LightState.OFF)

    async def get_state(self) -> LightState:
        """Refresh the cached :attr:`state` from JMRI and return it.

        Only :attr:`state` is updated; :attr:`name` and :attr:`user_name`
        are identity fields and are never refreshed. ``UNKNOWN`` is a
        first-class value and is never coerced (FR14).
        """
        from pyjmri._parsing import parse_light

        envelope = await self._handle.get_entity("light", self.name)
        parsed = parse_light(envelope)
        self.state = parsed.state
        return parsed.state

    def _on_event(self, new_state: LightState) -> None:
        """Update cached state and resolve matching waiters."""
        self.state = new_state
        self._waiters.fanout(new_state)

    async def wait_state(
        self,
        target: LightState,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> LightState:
        """Await the light reaching ``target`` (FR31).

        Raises:
            WaitTimeout: if ``timeout`` elapses before the target state.
            RuntimeError: if the owning :class:`~pyjmri.Client` is closed
                while this call is suspended inside ``ensure_subscription``.
        """
        if self.state == target:
            return self.state
        await self._handle.ensure_subscription("light", self.name)
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
                entity_type="light",
                name=self.name,
                target=target.name,
            ) from e
        finally:
            self._waiters.remove(future)

    async def wait_change(
        self,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> LightState:
        """Await the next state change from whatever :attr:`state` is now (FR32).

        Captures :attr:`state` after ensuring the subscription is live, so
        the "starting" reference cannot be invalidated by an event that
        arrives during the subscribe await.

        Raises:
            WaitTimeout: if ``timeout`` elapses before any state change.
            RuntimeError: if the owning :class:`~pyjmri.Client` is closed
                while this call is suspended inside ``ensure_subscription``.
        """
        await self._handle.ensure_subscription("light", self.name)
        starting = self.state
        future = self._waiters.register(lambda s: s != starting)
        try:
            if timeout is None:
                return await future
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as e:
            raise WaitTimeout(
                entity_type="light",
                name=self.name,
                from_state=starting.name,
            ) from e
        finally:
            self._waiters.remove(future)
