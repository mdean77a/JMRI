"""Unit tests for ``pyjmri._codes`` integer-to-Enum tables.

Covers:
- Total integer-key coverage matches JMRI's published constants.
- ``UNKNOWN`` is reachable from every state-bearing table.
- Live-layout robustness: state=0 maps to a sane member.
- Enums are NOT subclasses of ``int`` (no IntEnum leakage).
"""

from __future__ import annotations

from pyjmri import (
    BlockState,
    LightState,
    PowerState,
    SensorState,
    SignalHeadAppearance,
    TurnoutState,
)
from pyjmri._codes import (
    BLOCK_STATE,
    LIGHT_STATE,
    POWER_STATE,
    SENSOR_STATE,
    SIGNAL_HEAD_APPEARANCE,
    TURNOUT_STATE,
)

# ---- Total integer-key coverage per JMRI's published constants ----


def test_turnout_codes_cover_all_documented_integers() -> None:
    # JMRI Turnout: 1=UNKNOWN, 2=CLOSED, 4=THROWN, 8=INCONSISTENT
    # Plus runtime-emitted 0 for never-commanded turnouts.
    assert set(TURNOUT_STATE.keys()) == {0, 1, 2, 4, 8}
    assert TURNOUT_STATE[1] is TurnoutState.UNKNOWN
    assert TURNOUT_STATE[2] is TurnoutState.CLOSED
    assert TURNOUT_STATE[4] is TurnoutState.THROWN
    assert TURNOUT_STATE[8] is TurnoutState.INCONSISTENT


def test_sensor_codes_cover_all_documented_integers() -> None:
    # JMRI Sensor: 1=UNKNOWN, 2=ACTIVE, 4=INACTIVE, 8=INCONSISTENT
    # Plus runtime-emitted 0 for never-commanded sensors.
    assert set(SENSOR_STATE.keys()) == {0, 1, 2, 4, 8}
    assert SENSOR_STATE[1] is SensorState.UNKNOWN
    assert SENSOR_STATE[2] is SensorState.ACTIVE
    assert SENSOR_STATE[4] is SensorState.INACTIVE
    assert SENSOR_STATE[8] is SensorState.INCONSISTENT


def test_block_codes_cover_all_documented_integers() -> None:
    # JMRI Block: 0=UNDETECTED, 1=UNKNOWN, 2=OCCUPIED, 4=UNOCCUPIED, 8=INCONSISTENT.
    assert set(BLOCK_STATE.keys()) == {0, 1, 2, 4, 8}
    assert BLOCK_STATE[0] is BlockState.UNDETECTED
    assert BLOCK_STATE[1] is BlockState.UNKNOWN
    assert BLOCK_STATE[2] is BlockState.OCCUPIED
    assert BLOCK_STATE[4] is BlockState.UNOCCUPIED
    assert BLOCK_STATE[8] is BlockState.INCONSISTENT


def test_light_codes_cover_all_documented_integers() -> None:
    # JMRI Light: 1=UNKNOWN, 2=ON, 4=OFF, 8=INCONSISTENT
    # Plus runtime-emitted 0 for never-commanded lights.
    assert set(LIGHT_STATE.keys()) == {0, 1, 2, 4, 8}
    assert LIGHT_STATE[1] is LightState.UNKNOWN
    assert LIGHT_STATE[2] is LightState.ON
    assert LIGHT_STATE[4] is LightState.OFF
    assert LIGHT_STATE[8] is LightState.INCONSISTENT


def test_power_codes_cover_all_documented_integers() -> None:
    # JMRI Power: 0=UNKNOWN, 2=ON, 4=OFF. (Power has no INCONSISTENT.)
    # NamedBean's UNKNOWN=1 is also mapped for forward-compat.
    assert set(POWER_STATE.keys()) == {0, 1, 2, 4}
    assert POWER_STATE[0] is PowerState.UNKNOWN
    assert POWER_STATE[2] is PowerState.ON
    assert POWER_STATE[4] is PowerState.OFF


def test_signal_head_codes_cover_all_documented_integers() -> None:
    # DARK=0, RED=1, FLASHRED=2, YELLOW=4, FLASHYELLOW=8,
    # GREEN=16, FLASHGREEN=32, LUNAR=64, FLASHLUNAR=128.
    # HELD=256 is NOT in this table — exposed via separate ``held`` boolean.
    assert set(SIGNAL_HEAD_APPEARANCE.keys()) == {0, 1, 2, 4, 8, 16, 32, 64, 128}
    assert SIGNAL_HEAD_APPEARANCE[0] is SignalHeadAppearance.DARK
    assert SIGNAL_HEAD_APPEARANCE[1] is SignalHeadAppearance.RED
    assert SIGNAL_HEAD_APPEARANCE[2] is SignalHeadAppearance.FLASHRED
    assert SIGNAL_HEAD_APPEARANCE[4] is SignalHeadAppearance.YELLOW
    assert SIGNAL_HEAD_APPEARANCE[8] is SignalHeadAppearance.FLASHYELLOW
    assert SIGNAL_HEAD_APPEARANCE[16] is SignalHeadAppearance.GREEN
    assert SIGNAL_HEAD_APPEARANCE[32] is SignalHeadAppearance.FLASHGREEN
    assert SIGNAL_HEAD_APPEARANCE[64] is SignalHeadAppearance.LUNAR
    assert SIGNAL_HEAD_APPEARANCE[128] is SignalHeadAppearance.FLASHLUNAR


# ---- UNKNOWN reachable per state-bearing table ----


def test_turnout_codes_include_unknown() -> None:
    assert TurnoutState.UNKNOWN in TURNOUT_STATE.values()


def test_sensor_codes_include_unknown() -> None:
    assert SensorState.UNKNOWN in SENSOR_STATE.values()


def test_block_codes_include_unknown() -> None:
    assert BlockState.UNKNOWN in BLOCK_STATE.values()


def test_light_codes_include_unknown() -> None:
    assert LightState.UNKNOWN in LIGHT_STATE.values()


def test_power_codes_include_unknown() -> None:
    assert PowerState.UNKNOWN in POWER_STATE.values()


# ---- Live-layout robustness: state=0 ----


def test_turnout_codes_map_zero_to_unknown() -> None:
    assert TURNOUT_STATE[0] is TurnoutState.UNKNOWN


def test_sensor_codes_map_zero_to_unknown() -> None:
    assert SENSOR_STATE[0] is SensorState.UNKNOWN


def test_block_codes_map_zero_to_undetected() -> None:
    # Distinct from UNKNOWN: state=0 means "block has no occupancy detector."
    assert BLOCK_STATE[0] is BlockState.UNDETECTED


def test_light_codes_map_zero_to_unknown() -> None:
    assert LIGHT_STATE[0] is LightState.UNKNOWN


def test_power_codes_map_zero_to_unknown() -> None:
    assert POWER_STATE[0] is PowerState.UNKNOWN


# ---- No int leakage: state enums must NOT subclass int ----


def test_turnout_state_is_not_int_enum() -> None:
    assert not issubclass(TurnoutState, int)


def test_sensor_state_is_not_int_enum() -> None:
    assert not issubclass(SensorState, int)


def test_block_state_is_not_int_enum() -> None:
    assert not issubclass(BlockState, int)


def test_light_state_is_not_int_enum() -> None:
    assert not issubclass(LightState, int)


def test_power_state_is_not_int_enum() -> None:
    assert not issubclass(PowerState, int)


def test_signal_head_appearance_is_not_int_enum() -> None:
    assert not issubclass(SignalHeadAppearance, int)


# ---- No str leakage either: state enums must NOT subclass str ----


def test_turnout_state_is_not_str_enum() -> None:
    assert not issubclass(TurnoutState, str)


def test_sensor_state_is_not_str_enum() -> None:
    assert not issubclass(SensorState, str)


def test_block_state_is_not_str_enum() -> None:
    assert not issubclass(BlockState, str)


def test_light_state_is_not_str_enum() -> None:
    assert not issubclass(LightState, str)


def test_power_state_is_not_str_enum() -> None:
    assert not issubclass(PowerState, str)


def test_signal_head_appearance_is_not_str_enum() -> None:
    assert not issubclass(SignalHeadAppearance, str)


# ---- Tables are immutable (MappingProxyType behavior) ----


def test_turnout_state_table_is_immutable() -> None:
    import pytest

    with pytest.raises(TypeError):
        TURNOUT_STATE[99] = TurnoutState.UNKNOWN  # type: ignore[index]


def test_block_state_table_is_immutable() -> None:
    import pytest

    with pytest.raises(TypeError):
        BLOCK_STATE[99] = BlockState.UNKNOWN  # type: ignore[index]
