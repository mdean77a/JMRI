"""Memory entity (a typed read-only memory variable in JMRI)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyjmri._protocols import ClientHandle

logger = logging.getLogger(__name__)

__all__ = ["Memory"]


class Memory:
    """A JMRI memory variable.

    Memories are typed string-or-null containers JMRI uses for layout
    metadata (current train ID per block, temperature, etc.). pyjmri v1
    exposes them as read-only via :meth:`get_value`; the cached
    :attr:`value` is updated as a side effect (FR15).

    Example:
        Refresh and read a memory::

            current = await memory.get_value()

    Args:
        name: JMRI system name.
        user_name: Optional JMRI user name.
        value: Initial cached value (or ``None`` if unset).
        _handle: Internal :class:`~pyjmri._protocols.ClientHandle`.
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
        value: str | None,
        _handle: ClientHandle,
    ) -> None:
        self.name = name
        self.user_name = user_name
        self.value = value
        self._handle = _handle

    async def set_value(self, value: str) -> None:
        """Set the memory's value to ``value`` (FR18).

        Returns when JMRI has accepted the assignment. The cached
        :attr:`value` is **not** updated optimistically — call
        :meth:`get_value` afterward to refresh it. FR22 discipline: the
        library does not confirm a state it has not observed, and a
        successful HTTP ack does not yet mean a WS state-change event
        has propagated.

        ``wait_for_jmri_state=True`` is not available on this method in
        v1 — memory entities have no ``_on_event`` plumbing (no parser
        entry, no waiter list). If you need confirmed memory writes,
        call ``set_value`` followed by ``get_value`` and compare. See
        README §Limitations.
        """
        await self._handle.command("memory", self.name, {"value": value})

    async def get_value(self) -> str | None:
        """Refresh the cached :attr:`value` from JMRI and return it.

        Returns:
            The memory's current value, or ``None`` if unset (FR15).
        """
        from pyjmri._parsing import parse_memory

        envelope = await self._handle.get_entity("memory", self.name)
        parsed = parse_memory(envelope)
        self.value = parsed.value
        return parsed.value
