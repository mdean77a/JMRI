"""Power state enum. Story 2.3 will add the Power entity class."""

from __future__ import annotations

from enum import Enum

__all__ = ["PowerState"]


class PowerState(Enum):
    UNKNOWN = "unknown"
    ON = "on"
    OFF = "off"
