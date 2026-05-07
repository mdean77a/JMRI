"""Light state enum. Story 2.3 will add the Light entity class."""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)

__all__ = ["LightState"]


class LightState(Enum):
    UNKNOWN = "unknown"
    ON = "on"
    OFF = "off"
    INCONSISTENT = "inconsistent"
