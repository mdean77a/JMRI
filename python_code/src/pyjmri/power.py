"""Power state enum. Story 2.3 will add the Power entity class."""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)

__all__ = ["PowerState"]


class PowerState(Enum):
    UNKNOWN = "unknown"
    ON = "on"
    OFF = "off"
