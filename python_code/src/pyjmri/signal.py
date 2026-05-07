"""Signal head and signal mast state enums.

Story 2.3 will add the SignalHead and SignalMast entity classes.

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

logger = logging.getLogger(__name__)

__all__ = ["SignalHeadAppearance", "SignalMastAspect"]


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
