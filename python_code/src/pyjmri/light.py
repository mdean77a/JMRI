"""Light entity class and LightState enum.

Architecture sec. Domain State Modeling.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

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
