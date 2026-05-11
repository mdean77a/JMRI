"""Signal head and signal mast entity classes and state enums.

``SignalHeadAppearance`` is integer-coded by JMRI (translated through
``_codes.py``). ``SignalMastAspect`` is string-coded by JMRI (translated
via Python's value-based enum lookup; see ``_parsing.parse_signal_mast``).

pyjmri v1 binds to JMRI's "basic" signaling system only. Layouts using
AAR-1946, NORAC, or custom signaling will see ``JMRIProtocolError`` on
signal-mast read. Story 6.2 (README Limitations) must surface this.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyjmri._protocols import ClientHandle

logger = logging.getLogger(__name__)

__all__ = ["SignalHead", "SignalHeadAppearance", "SignalMast", "SignalMastAspect"]


class SignalHeadAppearance(Enum):
    DARK = "dark"
    RED = "red"
    FLASHRED = "flashred"
    YELLOW = "yellow"
    FLASHYELLOW = "flashyellow"
    GREEN = "green"
    FLASHGREEN = "flashgreen"
    LUNAR = "lunar"
    FLASHLUNAR = "flashlunar"


class SignalMastAspect(Enum):
    """JMRI 'basic' signaling-system aspects.

    Member values are the exact JMRI aspect strings — Python's value-based
    enum lookup (``SignalMastAspect("Clear")``) is the translation
    primitive, so the strings MUST match JMRI verbatim.
    """

    CLEAR = "Clear"
    APPROACH = "Approach"
    APPROACH_MEDIUM = "Approach Medium"
    ADVANCE_APPROACH = "Advance Approach"
    APPROACH_SLOW = "Approach Slow"
    SLOW_APPROACH = "Slow Approach"
    MEDIUM_APPROACH = "Medium Approach"
    RESTRICTING = "Restricting"
    PERMISSIVE = "Permissive"
    SLOW = "Slow"
    MEDIUM = "Medium"
    STOP = "Stop"
    DARK = "Dark"
    HELD = "Held"
    UNKNOWN = "Unknown"


class SignalHead:
    """A JMRI signal head with its current appearance.

    Args:
        name: JMRI system name.
        user_name: Optional JMRI user name.
        appearance: Initial cached :class:`SignalHeadAppearance`.
        held: Initial cached "held" flag (when ``True``, JMRI has forced
            the head to its most-restrictive appearance).
        lit: Initial cached "lit" flag (when ``False``, JMRI has blanked
            the head).
        _handle: Internal :class:`~pyjmri._protocols.ClientHandle`.
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
        appearance: SignalHeadAppearance,
        held: bool,
        lit: bool,
        _handle: ClientHandle,
    ) -> None:
        self.name = name
        self.user_name = user_name
        self.appearance = appearance
        self.held = held
        self.lit = lit
        self._handle = _handle

    async def get_state(self) -> SignalHeadAppearance:
        """Refresh and return the cached :class:`SignalHeadAppearance`.

        Updates :attr:`appearance`, :attr:`held`, and :attr:`lit` atomically
        on success. :attr:`name` and :attr:`user_name` are identity fields
        and are never refreshed.
        """
        from pyjmri._parsing import parse_signal_head

        envelope = await self._handle.get_entity("signalHead", self.name)
        parsed = parse_signal_head(envelope)
        self.appearance = parsed.appearance
        self.held = parsed.held
        self.lit = parsed.lit
        return parsed.appearance


class SignalMast:
    """A JMRI signal mast with its current aspect.

    pyjmri v1 binds to the JMRI "basic" signaling system only; aspects
    outside that system raise :class:`~pyjmri.JMRIProtocolError` on read.
    See README Limitations (Story 6.2).

    Args:
        name: JMRI system name.
        user_name: Optional JMRI user name.
        aspect: Initial cached :class:`SignalMastAspect`.
        held: Initial cached "held" flag.
        lit: Initial cached "lit" flag.
        _handle: Internal :class:`~pyjmri._protocols.ClientHandle`.
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
        aspect: SignalMastAspect,
        held: bool,
        lit: bool,
        _handle: ClientHandle,
    ) -> None:
        self.name = name
        self.user_name = user_name
        self.aspect = aspect
        self.held = held
        self.lit = lit
        self._handle = _handle

    async def get_state(self) -> SignalMastAspect:
        """Refresh and return the cached :class:`SignalMastAspect`.

        Updates :attr:`aspect`, :attr:`held`, and :attr:`lit` atomically
        on success. :attr:`name` and :attr:`user_name` are identity fields
        and are never refreshed.
        """
        from pyjmri._parsing import parse_signal_mast

        envelope = await self._handle.get_entity("signalMast", self.name)
        parsed = parse_signal_mast(envelope)
        self.aspect = parsed.aspect
        self.held = parsed.held
        self.lit = parsed.lit
        return parsed.aspect
