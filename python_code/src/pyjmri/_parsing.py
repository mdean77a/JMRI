"""JMRI JSON v5 -> typed Python value translation.

Each parser receives the JMRI envelope shape (``{"type": "...",
"data": {...}}``) and returns a frozen ``_Parsed<Kind>`` dataclass.
Architecture sec. JSON <-> Python Translation: integer codes are
translated through ``_codes.py`` only; unknown JSON keys are silently
ignored; missing required keys raise ``JMRIProtocolError``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

from pyjmri import _codes
from pyjmri.block import BlockState
from pyjmri.exceptions import JMRIProtocolError
from pyjmri.light import LightState
from pyjmri.power import PowerState
from pyjmri.sensor import SensorState
from pyjmri.signal import SignalHeadAppearance, SignalMastAspect
from pyjmri.turnout import TurnoutState

logger = logging.getLogger(__name__)

EnumT = TypeVar("EnumT", bound=Enum)


# ---- Frozen parsed-shape dataclasses ----


@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedTurnout:
    name: str
    user_name: str | None
    state: TurnoutState


@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedSensor:
    name: str
    user_name: str | None
    state: SensorState


@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedBlock:
    name: str
    user_name: str | None
    state: BlockState
    value: str | None


@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedLight:
    name: str
    user_name: str | None
    state: LightState


@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedMemory:
    name: str
    user_name: str | None
    value: str | None


@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedRoute:
    name: str
    user_name: str | None


@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedSignalHead:
    name: str
    user_name: str | None
    appearance: SignalHeadAppearance
    held: bool
    lit: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedSignalMast:
    name: str
    user_name: str | None
    aspect: SignalMastAspect
    held: bool
    lit: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedRosterEntry:
    name: str
    dcc_address: int
    long_address: bool
    road_name: str | None
    road_number: str | None
    model: str | None
    comment: str | None


@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedPower:
    name: str
    state: PowerState
    default: bool


# ---- Helpers ----


def _data(payload: dict[str, Any], entity_type: str) -> dict[str, Any]:
    """Return ``payload['data']`` or raise :class:`JMRIProtocolError`."""
    data = payload.get("data")
    if not isinstance(data, dict):
        raise JMRIProtocolError(
            "envelope is missing 'data' object",
            entity_type=entity_type,
            field="data",
        )
    return data


def _required_str(data: dict[str, Any], key: str, *, entity_type: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise JMRIProtocolError(
            f"missing or non-string field {key!r}",
            entity_type=entity_type,
            field=key,
            name=data.get("name"),
        )
    return value


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    return value


def _required_state(
    data: dict[str, Any],
    table: Mapping[int, EnumT],
    *,
    entity_type: str,
    field: str = "state",
) -> EnumT:
    code = data.get(field)
    if not isinstance(code, int) or isinstance(code, bool):
        raise JMRIProtocolError(
            f"missing or non-integer {field!r} field",
            entity_type=entity_type,
            field=field,
            name=data.get("name"),
        )
    member = table.get(code)
    if member is None:
        raise JMRIProtocolError(
            f"unknown {field} code",
            entity_type=entity_type,
            field=field,
            state_code=code,
            name=data.get("name"),
        )
    return member


def _required_bool(data: dict[str, Any], key: str, *, entity_type: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise JMRIProtocolError(
            f"missing or non-boolean field {key!r}",
            entity_type=entity_type,
            field=key,
            name=data.get("name"),
        )
    return value


# ---- Parsers ----


def parse_turnout(payload: dict[str, Any]) -> _ParsedTurnout:
    data = _data(payload, "turnout")
    return _ParsedTurnout(
        name=_required_str(data, "name", entity_type="turnout"),
        user_name=_optional_str(data, "userName"),
        state=_required_state(data, _codes.TURNOUT_STATE, entity_type="turnout"),
    )


def parse_sensor(payload: dict[str, Any]) -> _ParsedSensor:
    data = _data(payload, "sensor")
    return _ParsedSensor(
        name=_required_str(data, "name", entity_type="sensor"),
        user_name=_optional_str(data, "userName"),
        state=_required_state(data, _codes.SENSOR_STATE, entity_type="sensor"),
    )


def parse_block(payload: dict[str, Any]) -> _ParsedBlock:
    data = _data(payload, "block")
    return _ParsedBlock(
        name=_required_str(data, "name", entity_type="block"),
        user_name=_optional_str(data, "userName"),
        state=_required_state(data, _codes.BLOCK_STATE, entity_type="block"),
        value=_optional_str(data, "value"),
    )


def parse_light(payload: dict[str, Any]) -> _ParsedLight:
    data = _data(payload, "light")
    return _ParsedLight(
        name=_required_str(data, "name", entity_type="light"),
        user_name=_optional_str(data, "userName"),
        state=_required_state(data, _codes.LIGHT_STATE, entity_type="light"),
    )


def parse_memory(payload: dict[str, Any]) -> _ParsedMemory:
    data = _data(payload, "memory")
    return _ParsedMemory(
        name=_required_str(data, "name", entity_type="memory"),
        user_name=_optional_str(data, "userName"),
        value=_optional_str(data, "value"),
    )


def parse_route(payload: dict[str, Any]) -> _ParsedRoute:
    data = _data(payload, "route")
    return _ParsedRoute(
        name=_required_str(data, "name", entity_type="route"),
        user_name=_optional_str(data, "userName"),
    )


def parse_signal_head(payload: dict[str, Any]) -> _ParsedSignalHead:
    data = _data(payload, "signalHead")
    return _ParsedSignalHead(
        name=_required_str(data, "name", entity_type="signalHead"),
        user_name=_optional_str(data, "userName"),
        appearance=_required_state(
            data,
            _codes.SIGNAL_HEAD_APPEARANCE,
            entity_type="signalHead",
            field="appearance",
        ),
        held=_required_bool(data, "held", entity_type="signalHead"),
        lit=_required_bool(data, "lit", entity_type="signalHead"),
    )


def parse_signal_mast(payload: dict[str, Any]) -> _ParsedSignalMast:
    """Parse a ``signalMast`` envelope.

    JMRI emits ``aspect`` as a string drawn from the layout's loaded
    signaling system. pyjmri v1 supports the JMRI "basic" system only;
    aspects outside that enum raise ``JMRIProtocolError``.
    """
    data = _data(payload, "signalMast")
    name = _required_str(data, "name", entity_type="signalMast")
    aspect_str = _required_str(data, "aspect", entity_type="signalMast")
    try:
        aspect = SignalMastAspect(aspect_str)
    except ValueError as e:
        raise JMRIProtocolError(
            "unknown signal-mast aspect "
            "(pyjmri v1 supports the JMRI 'basic' signaling system only)",
            entity_type="signalMast",
            field="aspect",
            aspect=aspect_str,
            name=name,
            signaling_system_hint="basic",
        ) from e
    return _ParsedSignalMast(
        name=name,
        user_name=_optional_str(data, "userName"),
        aspect=aspect,
        held=_required_bool(data, "held", entity_type="signalMast"),
        lit=_required_bool(data, "lit", entity_type="signalMast"),
    )


def parse_roster_entry(payload: dict[str, Any]) -> _ParsedRosterEntry:
    """Parse a ``rosterEntry`` envelope.

    The collection URL is ``/json/v5/roster`` but each envelope's
    ``type`` field is ``"rosterEntry"`` (not ``"roster"``).
    """
    data = _data(payload, "rosterEntry")
    name = _required_str(data, "name", entity_type="rosterEntry")
    address_str = _required_str(data, "address", entity_type="rosterEntry")
    if not address_str.isdecimal():
        raise JMRIProtocolError(
            "DCC address is not an integer string",
            entity_type="rosterEntry",
            field="address",
            address=address_str,
            name=name,
        )
    long_address = data.get("isLongAddress")
    if not isinstance(long_address, bool):
        raise JMRIProtocolError(
            "missing or non-boolean field 'isLongAddress'",
            entity_type="rosterEntry",
            field="isLongAddress",
            name=name,
        )
    return _ParsedRosterEntry(
        name=name,
        dcc_address=int(address_str),
        long_address=long_address,
        road_name=_optional_str(data, "road"),
        road_number=_optional_str(data, "number"),
        model=_optional_str(data, "model"),
        comment=_optional_str(data, "comment"),
    )


def parse_power(payload: dict[str, Any]) -> _ParsedPower:
    data = _data(payload, "power")
    return _ParsedPower(
        name=_required_str(data, "name", entity_type="power"),
        state=_required_state(data, _codes.POWER_STATE, entity_type="power"),
        default=_required_bool(data, "default", entity_type="power"),
    )
