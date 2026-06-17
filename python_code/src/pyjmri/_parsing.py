"""JMRI JSON v5 -> typed Python value translation.

Layout entity parsers (``parse_turnout``, ``parse_sensor``, etc.) receive
the JMRI envelope shape (``{"type": "...", "data": {...}}``) and return
a frozen ``_Parsed<Kind>`` intermediate dataclass; the public domain
object is assembled later by ``Client.discover`` using the ``_ENTITY_SPECS``
registry (which injects the ``ClientHandle``).

Operations entity parsers (``parse_location``, ``parse_train``,
``parse_car``, ``parse_engine``) and the roster parser
(``parse_roster_entry``) are handle-free snapshots, so they return the
public frozen entity classes from :mod:`pyjmri.operations` /
:mod:`pyjmri.roster` directly with no ``_Parsed*`` intermediate.

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
from pyjmri.operations import Car, Engine, Location, Placement, RouteStop, Track, Train
from pyjmri.power import PowerState
from pyjmri.roster import FunctionLabel, RosterEntry
from pyjmri.sensor import SensorState
from pyjmri.signal import SignalHeadAppearance, SignalMastAspect
from pyjmri.turnout import TurnoutState

logger = logging.getLogger("pyjmri.parsing")

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
class _ParsedPower:
    name: str
    state: PowerState
    default: bool


# ---- Helpers ----


def _data(payload: dict[str, Any], entity_type: str) -> dict[str, Any]:
    """Return ``payload['data']`` or raise :class:`JMRIProtocolError`."""
    if not isinstance(payload, dict):
        raise JMRIProtocolError(
            "envelope is not a JSON object",
            entity_type=entity_type,
        )
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


def _as_int(value: Any) -> int | None:
    # bool is an int subclass; JMRI never sends a bool here, so reject it.
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return value


def _optional_int(data: dict[str, Any], key: str) -> int | None:
    return _as_int(data.get(key))


def _optional_bool(data: dict[str, Any], key: str, *, default: bool = False) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        return default
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


def _required_int(data: dict[str, Any], key: str, *, entity_type: str) -> int:
    value = _as_int(data.get(key))
    if value is None:
        raise JMRIProtocolError(
            f"missing or non-integer field {key!r}",
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


def _parse_function_labels(data: dict[str, Any]) -> tuple[FunctionLabel, ...]:
    """Build the per-function label tuple from a roster entry's ``functionKeys``.

    Each element is one F-key object (``{"name": "F0", "label": ..., "lockable":
    ...}``). The function number is parsed from the ``"Fnn"`` name; ``label`` is
    ``None`` when JMRI reports ``null`` or an empty string; ``lockable`` defaults
    to ``False`` when absent. All keys JMRI sends are parsed, including F29+ — the
    F0..F28 limit is a throttle-command constraint, not a roster-data one. An
    absent or non-list ``functionKeys`` yields an empty tuple.
    """
    raw = data.get("functionKeys")
    if not isinstance(raw, list):
        return ()
    labels: list[FunctionLabel] = []
    for element in raw:
        if not isinstance(element, dict):
            logger.debug("skipping non-dict functionKeys element: %r", element)
            continue
        fname = element.get("name")
        # Require an ASCII-decimal suffix, mirroring the address guard above: a
        # name whose digits are non-ASCII (e.g. a fullwidth-digit "Fn") still
        # satisfies str.isdecimal(), and int() would silently coerce it, so
        # reject it rather than fabricate a bogus function number.
        if (
            not isinstance(fname, str)
            or not fname.startswith("F")
            or not fname[1:].isascii()
            or not fname[1:].isdecimal()
        ):
            logger.debug("skipping functionKeys element with unparsable name: %r", fname)
            continue
        labels.append(
            FunctionLabel(
                num=int(fname[1:]),
                label=_optional_str(element, "label") or None,
                lockable=_optional_bool(element, "lockable"),
            )
        )
    return tuple(labels)


def parse_roster_entry(payload: dict[str, Any]) -> RosterEntry:
    """Parse a ``rosterEntry`` envelope into a read-only :class:`RosterEntry`.

    The collection URL is ``/json/v5/roster`` but each envelope's
    ``type`` field is ``"rosterEntry"`` (not ``"roster"``).
    """
    data = _data(payload, "rosterEntry")
    name = _required_str(data, "name", entity_type="rosterEntry")
    address_str = _required_str(data, "address", entity_type="rosterEntry")
    if not address_str.isascii() or not address_str.isdecimal():
        raise JMRIProtocolError(
            "DCC address is not an integer string",
            entity_type="rosterEntry",
            field="address",
            address=address_str,
            name=name,
        )
    long_address = _required_bool(data, "isLongAddress", entity_type="rosterEntry")
    return RosterEntry(
        name=name,
        user_name=None,
        dcc_address=int(address_str),
        long_address=long_address,
        road_name=_optional_str(data, "road"),
        road_number=_optional_str(data, "number"),
        model=_optional_str(data, "model"),
        mfg=_optional_str(data, "mfg"),
        owner=_optional_str(data, "owner"),
        comment=_optional_str(data, "comment"),
        image_path=_optional_str(data, "image"),
        max_speed_pct=_optional_int(data, "maxSpeedPct"),
        decoder_family=_optional_str(data, "decoderFamily"),
        decoder_model=_optional_str(data, "decoderModel"),
        function_labels=_parse_function_labels(data),
    )


def parse_power(payload: dict[str, Any]) -> _ParsedPower:
    data = _data(payload, "power")
    return _ParsedPower(
        name=_required_str(data, "name", entity_type="power"),
        state=_required_state(data, _codes.POWER_STATE, entity_type="power"),
        default=_required_bool(data, "default", entity_type="power"),
    )


# ---- Operations parsers (read-only; return public frozen entities directly) ----
#
# Operations entities carry no mutable handle, so — unlike the Layout entities
# above — the parser fully constructs the public ``operations`` object; there is
# no ``_Parsed*`` intermediate. ``train.engines[]`` / ``train.cars[]`` consist
# elements are bare data objects (the inner ``data`` dict, no ``{type, data}``
# envelope), so the ``_*_from_data`` helpers are shared between the top-level
# collection parsers and the train-consist path. Absence (JSON ``null`` or an
# empty reference string) maps to ``None`` rather than raising (FR48).


def _parse_track(value: Any) -> Track | None:
    """Build a :class:`Track` from a nested ``track`` object, or ``None``."""
    if not isinstance(value, dict) or not value:
        return None
    return Track(
        name=_required_str(value, "name", entity_type="track"),
        user_name=_optional_str(value, "userName"),
    )


def _parse_placement(value: Any) -> Placement | None:
    """Build a :class:`Placement` from a ``location``/``destination`` object.

    Returns ``None`` when JMRI reports the reference as ``null`` or an
    empty object — an unplaced/unassigned car or engine (FR48).
    """
    if not isinstance(value, dict) or not value:
        return None
    return Placement(
        name=_required_str(value, "name", entity_type="placement"),
        user_name=_optional_str(value, "userName"),
        track=_parse_track(value.get("track")),
    )


def _parse_route_stop(value: dict[str, Any]) -> RouteStop:
    """Build a :class:`RouteStop` from one ``train.locations[]`` element."""
    return RouteStop(
        name=_required_str(value, "name", entity_type="routeStop"),
        user_name=_optional_str(value, "userName"),
        sequence_id=_required_int(value, "sequenceId", entity_type="routeStop"),
        train_direction=_required_str(value, "trainDirection", entity_type="routeStop"),
    )


def _car_from_data(data: dict[str, Any]) -> Car:
    """Build a :class:`Car` from a car ``data`` object (envelope or consist)."""
    return Car(
        name=_required_str(data, "name", entity_type="car"),
        road=_required_str(data, "road", entity_type="car"),
        number=_required_str(data, "number", entity_type="car"),
        car_type=_required_str(data, "type", entity_type="car"),
        length=_required_int(data, "length", entity_type="car"),
        location=_parse_placement(data.get("location")),
        train=_optional_str(data, "trainName") or None,
        destination=_parse_placement(data.get("destination")),
    )


def _engine_from_data(data: dict[str, Any]) -> Engine:
    """Build an :class:`Engine` from an engine ``data`` object (envelope or consist)."""
    return Engine(
        name=_required_str(data, "name", entity_type="engine"),
        road=_required_str(data, "road", entity_type="engine"),
        number=_required_str(data, "number", entity_type="engine"),
        engine_type=_required_str(data, "type", entity_type="engine"),
        model=_optional_str(data, "model") or None,
        length=_required_int(data, "length", entity_type="engine"),
        location=_parse_placement(data.get("location")),
        train=_optional_str(data, "trainName") or None,
        destination=_parse_placement(data.get("destination")),
    )


def parse_location(payload: dict[str, Any]) -> Location:
    data = _data(payload, "location")
    raw_tracks = data.get("track")
    tracks = (
        tuple(t for t in (_parse_track(rt) for rt in raw_tracks) if t is not None)
        if isinstance(raw_tracks, list)
        else ()
    )
    return Location(
        name=_required_str(data, "name", entity_type="location"),
        user_name=_optional_str(data, "userName"),
        length=_required_int(data, "length", entity_type="location"),
        comment=_optional_str(data, "comment") or None,
        tracks=tracks,
    )


def parse_car(payload: dict[str, Any]) -> Car:
    return _car_from_data(_data(payload, "car"))


def parse_engine(payload: dict[str, Any]) -> Engine:
    return _engine_from_data(_data(payload, "engine"))


def parse_train(payload: dict[str, Any]) -> Train:
    data = _data(payload, "train")
    raw_stops = data.get("locations")
    route_stops = (
        tuple(
            sorted(
                (_parse_route_stop(s) for s in raw_stops if isinstance(s, dict)),
                key=lambda s: s.sequence_id,
            )
        )
        if isinstance(raw_stops, list)
        else ()
    )
    raw_engines = data.get("engines")
    engines = (
        tuple(_engine_from_data(e) for e in raw_engines if isinstance(e, dict))
        if isinstance(raw_engines, list)
        else ()
    )
    raw_cars = data.get("cars")
    cars = (
        tuple(_car_from_data(c) for c in raw_cars if isinstance(c, dict))
        if isinstance(raw_cars, list)
        else ()
    )
    return Train(
        name=_required_str(data, "name", entity_type="train"),
        user_name=_optional_str(data, "userName"),
        route=_optional_str(data, "route") or None,
        current_location=_optional_str(data, "location") or None,
        status=_required_str(data, "status", entity_type="train"),
        status_code=_required_int(data, "statusCode", entity_type="train"),
        lead_engine=_optional_str(data, "leadEngine") or None,
        route_stops=route_stops,
        engines=engines,
        cars=cars,
    )
