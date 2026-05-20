"""Sensor entity class and SensorState enum.

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

__all__ = ["Sensor", "SensorState"]


class SensorState(Enum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    INACTIVE = "inactive"
    INCONSISTENT = "inconsistent"


class Sensor:
    """A JMRI sensor (block detector, button, etc.).

    Read-only in pyjmri v1: there are no command methods on
    :class:`Sensor`; sensors report layout state, they don't drive it.
    See README §Limitations.

    The cached :attr:`state` reflects JMRI's last reported value. When
    the sensor has not yet reported, the state is
    :attr:`SensorState.UNKNOWN` and pyjmri preserves it as ``UNKNOWN``
    rather than coercing to ``INACTIVE`` (FR14).

    Example:
        Refresh a sensor's state from JMRI::

            current = await sensor.get_state()
            if current is SensorState.ACTIVE:
                ...

        Wait for a state change pushed over the WebSocket::

            await sensor.wait_active(timeout=30.0)   # FR30
            await sensor.wait_inactive()             # FR30
            await sensor.wait_change()               # FR32

    Args:
        name: JMRI system name (e.g., ``"NS401"``).
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
        state: SensorState,
        _handle: ClientHandle,
    ) -> None:
        self.name = name
        self.user_name = user_name
        self.state = state
        self._handle = _handle
        self._waiters: WaiterList[SensorState] = WaiterList()

    async def get_state(self) -> SensorState:
        """Refresh the cached :attr:`state` from JMRI and return it.

        Only :attr:`state` is updated; :attr:`name` and :attr:`user_name`
        are identity fields and are never refreshed. ``UNKNOWN`` is a
        first-class value and is never coerced (FR14).
        """
        from pyjmri._parsing import parse_sensor

        envelope = await self._handle.get_entity("sensor", self.name)
        parsed = parse_sensor(envelope)
        self.state = parsed.state
        return parsed.state

    def _on_event(self, new_state: SensorState) -> None:
        """Update cached state and resolve matching waiters."""
        self.state = new_state
        self._waiters.fanout(new_state)

    async def wait_state(
        self,
        target: SensorState,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> SensorState:
        """Await the sensor reaching ``target`` (FR31).

        Raises:
            WaitTimeout: if ``timeout`` elapses before the target state.
            RuntimeError: if the owning :class:`~pyjmri.Client` is closed
                while this call is suspended inside ``ensure_subscription``.
        """
        if self.state == target:
            return self.state
        await self._handle.ensure_subscription("sensor", self.name)
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
                entity_type="sensor",
                name=self.name,
                target=target.name,
            ) from e
        finally:
            self._waiters.remove(future)

    async def wait_change(
        self,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> SensorState:
        """Await the next state change from whatever :attr:`state` is now (FR32).

        Captures :attr:`state` after ensuring the subscription is live, so
        the "starting" reference cannot be invalidated by an event that
        arrives during the subscribe await.

        Raises:
            WaitTimeout: if ``timeout`` elapses before any state change.
            RuntimeError: if the owning :class:`~pyjmri.Client` is closed
                while this call is suspended inside ``ensure_subscription``.
        """
        await self._handle.ensure_subscription("sensor", self.name)
        starting = self.state
        future = self._waiters.register(lambda s: s != starting)
        try:
            if timeout is None:
                return await future
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as e:
            raise WaitTimeout(
                entity_type="sensor",
                name=self.name,
                from_state=starting.name,
            ) from e
        finally:
            self._waiters.remove(future)

    async def wait_active(self, *, timeout: float | None = None) -> SensorState:  # noqa: ASYNC109
        """Convenience wrapper for ``wait_state(SensorState.ACTIVE)`` (FR30)."""
        return await self.wait_state(SensorState.ACTIVE, timeout=timeout)

    async def wait_inactive(self, *, timeout: float | None = None) -> SensorState:  # noqa: ASYNC109
        """Convenience wrapper for ``wait_state(SensorState.INACTIVE)`` (FR30)."""
        return await self.wait_state(SensorState.INACTIVE, timeout=timeout)
