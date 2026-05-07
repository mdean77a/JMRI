"""Sensor state enum. Story 2.3 will add the Sensor entity class."""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)

__all__ = ["SensorState"]


class SensorState(Enum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    INACTIVE = "inactive"
    INCONSISTENT = "inconsistent"
