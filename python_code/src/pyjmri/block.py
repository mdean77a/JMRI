"""Block state enum. Story 2.3 will add the Block entity class."""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)

__all__ = ["BlockState"]


class BlockState(Enum):
    UNKNOWN = "unknown"
    OCCUPIED = "occupied"
    UNOCCUPIED = "unoccupied"
    UNDETECTED = "undetected"
    INCONSISTENT = "inconsistent"
