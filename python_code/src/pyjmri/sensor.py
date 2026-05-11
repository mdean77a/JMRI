"""Sensor entity class and SensorState enum.

Architecture sec. Domain State Modeling.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

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

    The cached :attr:`state` reflects JMRI's last reported value. When
    the sensor has not yet reported, the state is
    :attr:`SensorState.UNKNOWN` and pyjmri preserves it as ``UNKNOWN``
    rather than coercing to ``INACTIVE`` (FR14).

    Example:
        Refresh a sensor's state from JMRI::

            current = await sensor.get_state()
            if current is SensorState.ACTIVE:
                ...

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
