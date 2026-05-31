"""JMRI integer code <-> Enum tables.

Single source of truth for wire-format state-code translation. Each
table is keyed by the integer JMRI emits in the JSON ``state`` (or
``appearance``) field; the value is the matching Enum member from the
public per-entity module.

Architecture sec. Domain State Modeling and JSON <-> Python Translation.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from pyjmri.block import BlockState
from pyjmri.light import LightState
from pyjmri.power import PowerState
from pyjmri.route import RouteState
from pyjmri.sensor import SensorState
from pyjmri.signal import SignalHeadAppearance
from pyjmri.turnout import TurnoutState

# JMRI Turnout: UNKNOWN=1, CLOSED=2, THROWN=4, INCONSISTENT=8.
# Live observation: idle/never-commanded turnouts emit state=0 -> UNKNOWN.
TURNOUT_STATE: Mapping[int, TurnoutState] = MappingProxyType(
    {
        0: TurnoutState.UNKNOWN,
        1: TurnoutState.UNKNOWN,
        2: TurnoutState.CLOSED,
        4: TurnoutState.THROWN,
        8: TurnoutState.INCONSISTENT,
    }
)

# JMRI Sensor: UNKNOWN=1, ACTIVE=2, INACTIVE=4, INCONSISTENT=8.
# Live observation: state=0 also seen on never-commanded sensors -> UNKNOWN.
SENSOR_STATE: Mapping[int, SensorState] = MappingProxyType(
    {
        0: SensorState.UNKNOWN,
        1: SensorState.UNKNOWN,
        2: SensorState.ACTIVE,
        4: SensorState.INACTIVE,
        8: SensorState.INCONSISTENT,
    }
)

# JMRI Block: UNDETECTED=0, UNKNOWN=1, OCCUPIED=2, UNOCCUPIED=4, INCONSISTENT=8.
# UNDETECTED is preserved as a distinct enum member.
BLOCK_STATE: Mapping[int, BlockState] = MappingProxyType(
    {
        0: BlockState.UNDETECTED,
        1: BlockState.UNKNOWN,
        2: BlockState.OCCUPIED,
        4: BlockState.UNOCCUPIED,
        8: BlockState.INCONSISTENT,
    }
)

# JMRI Light: UNKNOWN=1, ON=2, OFF=4, INCONSISTENT=8.
# Live observation: state=0 may appear on never-commanded lights -> UNKNOWN.
LIGHT_STATE: Mapping[int, LightState] = MappingProxyType(
    {
        0: LightState.UNKNOWN,
        1: LightState.UNKNOWN,
        2: LightState.ON,
        4: LightState.OFF,
        8: LightState.INCONSISTENT,
    }
)

# JMRI Power: UNKNOWN=0, ON=2, OFF=4. (Power has no INCONSISTENT.)
# NamedBean's UNKNOWN=1 is also accepted for forward-compat.
POWER_STATE: Mapping[int, PowerState] = MappingProxyType(
    {
        0: PowerState.UNKNOWN,
        1: PowerState.UNKNOWN,
        2: PowerState.ON,
        4: PowerState.OFF,
    }
)

# Outbound (Enum -> int) maps for commandable entities. Verified against
# JMRI 5.14.0 by the Story 4.1 live-spike (2026-05-20). The integer codes
# JMRI accepts on POST match the codes it emits on GET, so the outbound
# maps are the canonical (non-zero) inverse of the inbound tables above.
# Memory does not need an outbound code map — its payload is
# ``{"value": str}``, not ``{"state": int}``.

TURNOUT_STATE_OUTBOUND: Mapping[TurnoutState, int] = MappingProxyType(
    {
        TurnoutState.CLOSED: 2,
        TurnoutState.THROWN: 4,
    }
)

LIGHT_STATE_OUTBOUND: Mapping[LightState, int] = MappingProxyType(
    {
        LightState.ON: 2,
        LightState.OFF: 4,
    }
)

# Route activation: JMRI's ``jmri.Route.ACTIVATE`` is state=2. The live-
# spike confirmed JMRI accepts state=2 with HTTP 200; state=8 (TOGGLE) is
# also accepted but state=2 is the documented canonical value.
ROUTE_STATE_OUTBOUND: Mapping[RouteState, int] = MappingProxyType(
    {
        RouteState.ACTIVE: 2,
    }
)


# JMRI SignalHead appearances:
# DARK=0, RED=1, FLASHRED=2, YELLOW=4, FLASHYELLOW=8,
# GREEN=16, FLASHGREEN=32, LUNAR=64, FLASHLUNAR=128.
# HELD=256 is exposed via the separate ``held`` boolean field, NOT via
# ``appearance``, so it does not appear in this table.
SIGNAL_HEAD_APPEARANCE: Mapping[int, SignalHeadAppearance] = MappingProxyType(
    {
        0: SignalHeadAppearance.DARK,
        1: SignalHeadAppearance.RED,
        2: SignalHeadAppearance.FLASHRED,
        4: SignalHeadAppearance.YELLOW,
        8: SignalHeadAppearance.FLASHYELLOW,
        16: SignalHeadAppearance.GREEN,
        32: SignalHeadAppearance.FLASHGREEN,
        64: SignalHeadAppearance.LUNAR,
        128: SignalHeadAppearance.FLASHLUNAR,
    }
)
