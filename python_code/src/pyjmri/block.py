"""Block entity class and BlockState enum.

Architecture sec. Domain State Modeling.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyjmri._protocols import ClientHandle

logger = logging.getLogger(__name__)

__all__ = ["Block", "BlockState"]


class BlockState(Enum):
    UNKNOWN = "unknown"
    OCCUPIED = "occupied"
    UNOCCUPIED = "unoccupied"
    UNDETECTED = "undetected"
    INCONSISTENT = "inconsistent"


class Block:
    """A JMRI block.

    Blocks model occupancy regions on the layout and may carry an
    optional :attr:`value` (for example, the train ID currently in the
    block). :attr:`BlockState.UNDETECTED` (JMRI ``state=0``) means the
    block has no occupancy detector wired — a real and distinct value
    from :attr:`BlockState.UNKNOWN` (no command observed yet); pyjmri
    never coerces ``UNKNOWN`` to any other value (FR14).

    Example:
        Refresh a block's state and value from JMRI::

            await block.get_state()
            print(block.state, block.value)

    Args:
        name: JMRI system name.
        user_name: Optional JMRI user name.
        state: Initial cached state.
        value: Initial cached value (optional string payload).
        _handle: Internal :class:`~pyjmri._protocols.ClientHandle`
            issued by the owning :class:`~pyjmri.Client`.
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
        state: BlockState,
        value: str | None,
        _handle: ClientHandle,
    ) -> None:
        self.name = name
        self.user_name = user_name
        self.state = state
        self.value = value
        self._handle = _handle

    async def get_state(self) -> BlockState:
        """Refresh both cached :attr:`state` and :attr:`value`; return state.

        Only :attr:`state` and :attr:`value` are updated; :attr:`name`
        and :attr:`user_name` are identity fields and are never refreshed.
        ``UNKNOWN`` is a first-class value and is never coerced (FR14).
        """
        from pyjmri._parsing import parse_block

        envelope = await self._handle.get_entity("block", self.name)
        parsed = parse_block(envelope)
        self.state = parsed.state
        self.value = parsed.value
        return parsed.state
