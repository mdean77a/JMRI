"""Block entity class and BlockState enum.

Architecture sec. Domain State Modeling.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pyjmri._wait_helpers import wait_for_change, wait_for_target
from pyjmri._waiters import WaiterList

if TYPE_CHECKING:
    from pyjmri._protocols import ClientHandle

__all__ = ["Block", "BlockState"]


class BlockState(Enum):
    UNKNOWN = "unknown"
    OCCUPIED = "occupied"
    UNOCCUPIED = "unoccupied"
    UNDETECTED = "undetected"
    INCONSISTENT = "inconsistent"


class Block:
    """A JMRI block.

    Read-only in pyjmri v1: there are no command methods on
    :class:`Block`; block occupancy is driven by hardware detectors, not
    by API writes. See README §Limitations.

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

        Wait for a state change pushed over the WebSocket::

            await block.wait_state(BlockState.OCCUPIED, timeout=60.0)
            await block.wait_change()

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
        self._waiters: WaiterList[BlockState] = WaiterList()

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

    def _on_event(self, new_state: BlockState) -> None:
        """Update cached state and resolve matching waiters.

        The block's :attr:`value` is not updated by ``_on_event`` —
        block-value pushes are not modeled as waitable events in v1.
        Call :meth:`get_state` to refresh both fields explicitly.
        """
        self.state = new_state
        self._waiters.fanout(new_state)

    async def wait_state(
        self,
        target: BlockState,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> BlockState:
        """Await the block reaching ``target`` (FR31).

        Raises:
            WaitTimeout: if ``timeout`` elapses before the target state.
            RuntimeError: if the owning :class:`~pyjmri.Client` is closed
                while this call is suspended inside ``ensure_subscription``.
        """
        return await wait_for_target(
            handle=self._handle,
            entity_type="block",
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
    ) -> BlockState:
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
            entity_type="block",
            name=self.name,
            waiters=self._waiters,
            read_state=lambda: self.state,
            timeout=timeout,
        )
