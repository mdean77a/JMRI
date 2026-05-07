"""Unit tests for ``pyjmri._parsing`` JMRI JSON v5 -> typed Python translation.

Covers:
- Happy-path round-trip from each fixture file -> typed dataclass.
- Inline-constructed envelopes for documented-but-unobserved enum members.
- Translation rules: camelCase -> snake_case, null -> None, unknown keys ignored,
  missing required keys raise ``JMRIProtocolError``.
- Per-entity peculiarities: state=0 mappings, signal-mast aspect translation,
  roster DCC-address parsing, power singleton.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from pyjmri import (
    BlockState,
    JMRIProtocolError,
    LightState,
    PowerState,
    SensorState,
    SignalHeadAppearance,
    SignalMastAspect,
    TurnoutState,
)
from pyjmri._parsing import (
    _ParsedBlock,
    _ParsedMemory,
    _ParsedPower,
    _ParsedRoute,
    _ParsedSensor,
    _ParsedSignalHead,
    _ParsedSignalMast,
    _ParsedTurnout,
    parse_block,
    parse_light,
    parse_memory,
    parse_power,
    parse_roster_entry,
    parse_route,
    parse_sensor,
    parse_signal_head,
    parse_signal_mast,
    parse_turnout,
)

LoadFixture = Callable[[str], list[dict[str, Any]]]


# ---- Happy-path: every fixture envelope parses to its typed dataclass ----


def test_parse_turnout_round_trips_every_live_envelope(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("turnouts")
    assert envelopes, "turnouts fixture should not be empty"
    for env in envelopes:
        parsed = parse_turnout(env)
        assert isinstance(parsed, _ParsedTurnout)
        assert parsed.name
        assert isinstance(parsed.state, TurnoutState)


def test_parse_sensor_round_trips_every_live_envelope(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("sensors")
    assert envelopes, "sensors fixture should not be empty"
    for env in envelopes:
        parsed = parse_sensor(env)
        assert isinstance(parsed, _ParsedSensor)
        assert parsed.name
        assert isinstance(parsed.state, SensorState)


def test_parse_block_round_trips_every_live_envelope(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("blocks")
    assert envelopes, "blocks fixture should not be empty"
    for env in envelopes:
        parsed = parse_block(env)
        assert isinstance(parsed, _ParsedBlock)
        assert parsed.name
        assert isinstance(parsed.state, BlockState)


def test_parse_memory_round_trips_every_live_envelope(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("memories")
    assert envelopes, "memories fixture should not be empty"
    for env in envelopes:
        parsed = parse_memory(env)
        assert isinstance(parsed, _ParsedMemory)
        assert parsed.name


def test_parse_route_round_trips_every_live_envelope(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("routes")
    assert envelopes, "routes fixture should not be empty"
    for env in envelopes:
        parsed = parse_route(env)
        assert isinstance(parsed, _ParsedRoute)
        assert parsed.name


def test_parse_signal_head_round_trips_every_live_envelope(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("signal_heads")
    assert envelopes, "signal_heads fixture should not be empty"
    for env in envelopes:
        parsed = parse_signal_head(env)
        assert isinstance(parsed, _ParsedSignalHead)
        assert parsed.name
        assert isinstance(parsed.appearance, SignalHeadAppearance)
        assert isinstance(parsed.held, bool)
        assert isinstance(parsed.lit, bool)


def test_parse_signal_mast_round_trips_every_live_envelope(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("signal_masts")
    assert envelopes, "signal_masts fixture should not be empty"
    for env in envelopes:
        parsed = parse_signal_mast(env)
        assert isinstance(parsed, _ParsedSignalMast)
        assert parsed.name
        assert isinstance(parsed.aspect, SignalMastAspect)
        assert isinstance(parsed.held, bool)
        assert isinstance(parsed.lit, bool)


def test_parse_roster_round_trips_every_live_envelope(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("roster")
    assert envelopes, "roster fixture should not be empty"
    for env in envelopes:
        parsed = parse_roster_entry(env)
        assert parsed.name
        assert isinstance(parsed.dcc_address, int)
        assert isinstance(parsed.long_address, bool)


def test_parse_power_round_trips_singleton_envelope(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("power")
    assert len(envelopes) == 1
    parsed = parse_power(envelopes[0])
    assert isinstance(parsed, _ParsedPower)
    assert parsed.name
    assert isinstance(parsed.state, PowerState)
    assert isinstance(parsed.default, bool)


def test_lights_fixture_is_empty(load_fixture: LoadFixture) -> None:
    """Live layout has zero lights — fixture committed for shape consistency."""
    envelopes = load_fixture("lights")
    assert envelopes == []


# ---- Inline-constructed envelopes for documented-but-unobserved values ----


def test_parse_turnout_unknown_state_inline() -> None:
    env = {"type": "turnout", "data": {"name": "NT9001", "userName": None, "state": 1}}
    assert parse_turnout(env).state is TurnoutState.UNKNOWN


def test_parse_turnout_inconsistent_state_inline() -> None:
    env = {"type": "turnout", "data": {"name": "NT9001", "userName": None, "state": 8}}
    assert parse_turnout(env).state is TurnoutState.INCONSISTENT


def test_parse_turnout_zero_state_maps_to_unknown_inline() -> None:
    env = {"type": "turnout", "data": {"name": "NT9001", "userName": None, "state": 0}}
    assert parse_turnout(env).state is TurnoutState.UNKNOWN


def test_parse_sensor_unknown_state_inline() -> None:
    env = {"type": "sensor", "data": {"name": "NS9001", "userName": None, "state": 1}}
    assert parse_sensor(env).state is SensorState.UNKNOWN


def test_parse_sensor_zero_state_inline() -> None:
    env = {"type": "sensor", "data": {"name": "NS9001", "userName": None, "state": 0}}
    assert parse_sensor(env).state is SensorState.UNKNOWN


def test_parse_sensor_inconsistent_state_inline() -> None:
    env = {"type": "sensor", "data": {"name": "NS9001", "userName": None, "state": 8}}
    assert parse_sensor(env).state is SensorState.INCONSISTENT


def test_parse_block_unknown_state_inline() -> None:
    env = {
        "type": "block",
        "data": {"name": "IB9001", "userName": None, "state": 1, "value": None},
    }
    assert parse_block(env).state is BlockState.UNKNOWN


def test_parse_block_occupied_state_inline() -> None:
    env = {
        "type": "block",
        "data": {"name": "IB9001", "userName": None, "state": 2, "value": None},
    }
    assert parse_block(env).state is BlockState.OCCUPIED


def test_parse_block_inconsistent_state_inline() -> None:
    env = {
        "type": "block",
        "data": {"name": "IB9001", "userName": None, "state": 8, "value": None},
    }
    assert parse_block(env).state is BlockState.INCONSISTENT


def test_parse_block_zero_state_maps_to_undetected() -> None:
    """Live-layout case: blocks without occupancy detectors emit state=0."""
    env = {
        "type": "block",
        "data": {"name": "IB9001", "userName": None, "state": 0, "value": None},
    }
    assert parse_block(env).state is BlockState.UNDETECTED


def test_parse_light_on_state_inline() -> None:
    env = {"type": "light", "data": {"name": "IL9001", "userName": None, "state": 2}}
    assert parse_light(env).state is LightState.ON


def test_parse_light_off_state_inline() -> None:
    env = {"type": "light", "data": {"name": "IL9001", "userName": None, "state": 4}}
    assert parse_light(env).state is LightState.OFF


def test_parse_light_unknown_state_inline() -> None:
    env = {"type": "light", "data": {"name": "IL9001", "userName": None, "state": 1}}
    assert parse_light(env).state is LightState.UNKNOWN


def test_parse_light_inconsistent_state_inline() -> None:
    env = {"type": "light", "data": {"name": "IL9001", "userName": None, "state": 8}}
    assert parse_light(env).state is LightState.INCONSISTENT


def test_parse_power_on_inline() -> None:
    env = {"type": "power", "data": {"name": "NCE", "state": 2, "default": True}}
    assert parse_power(env).state is PowerState.ON


def test_parse_power_off_inline() -> None:
    env = {"type": "power", "data": {"name": "NCE", "state": 4, "default": True}}
    assert parse_power(env).state is PowerState.OFF


def test_parse_power_unknown_inline() -> None:
    env = {"type": "power", "data": {"name": "NCE", "state": 0, "default": True}}
    assert parse_power(env).state is PowerState.UNKNOWN


@pytest.mark.parametrize(
    ("appearance_int", "expected"),
    [
        (0, SignalHeadAppearance.DARK),
        (1, SignalHeadAppearance.RED),
        (2, SignalHeadAppearance.FLASHRED),
        (4, SignalHeadAppearance.YELLOW),
        (8, SignalHeadAppearance.FLASHYELLOW),
        (16, SignalHeadAppearance.GREEN),
        (32, SignalHeadAppearance.FLASHGREEN),
        (64, SignalHeadAppearance.LUNAR),
        (128, SignalHeadAppearance.FLASHLUNAR),
    ],
)
def test_parse_signal_head_each_documented_appearance_inline(
    appearance_int: int, expected: SignalHeadAppearance
) -> None:
    env = {
        "type": "signalHead",
        "data": {
            "name": "NH9001",
            "userName": None,
            "appearance": appearance_int,
            "held": False,
            "lit": True,
        },
    }
    assert parse_signal_head(env).appearance is expected


# ---- Translation rules: camelCase -> snake_case, null handling, unknown keys ----


def test_parser_translates_user_name_camel_to_snake() -> None:
    env = {"type": "turnout", "data": {"name": "X", "userName": "Foo", "state": 2}}
    assert parse_turnout(env).user_name == "Foo"


def test_parser_treats_user_name_null_as_none() -> None:
    env = {"type": "turnout", "data": {"name": "X", "userName": None, "state": 2}}
    assert parse_turnout(env).user_name is None


def test_parser_treats_missing_user_name_as_none() -> None:
    env = {"type": "turnout", "data": {"name": "X", "state": 2}}
    assert parse_turnout(env).user_name is None


def test_parser_user_name_null_is_not_string_literal() -> None:
    """Regression guard: ``userName: null`` must not surface as the string ``"null"``."""
    env = {"type": "turnout", "data": {"name": "X", "userName": None, "state": 2}}
    parsed = parse_turnout(env)
    assert parsed.user_name is None
    assert parsed.user_name != "null"


def test_parser_ignores_unknown_keys() -> None:
    env = {
        "type": "turnout",
        "data": {
            "name": "X",
            "userName": "Foo",
            "state": 2,
            "futureField": 42,
            "alsoIgnored": [1, 2, 3],
        },
    }
    parsed = parse_turnout(env)
    assert parsed.name == "X"
    assert parsed.user_name == "Foo"
    assert parsed.state is TurnoutState.CLOSED


def test_parser_returns_frozen_dataclass() -> None:
    env = {"type": "turnout", "data": {"name": "X", "userName": None, "state": 2}}
    parsed = parse_turnout(env)
    with pytest.raises((AttributeError, Exception)):  # frozen dataclass raises FrozenInstanceError
        parsed.name = "Y"  # type: ignore[misc]


# ---- Error path: missing required keys ----


def test_parser_raises_on_missing_data_key() -> None:
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_turnout({"type": "turnout"})
    assert exc_info.value.context["entity_type"] == "turnout"
    assert exc_info.value.context["field"] == "data"


def test_parser_raises_on_non_dict_data() -> None:
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_turnout({"type": "turnout", "data": "not-a-dict"})
    assert exc_info.value.context["field"] == "data"


def test_parser_raises_on_missing_name() -> None:
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_turnout({"type": "turnout", "data": {"state": 2, "userName": None}})
    assert exc_info.value.context["entity_type"] == "turnout"
    assert exc_info.value.context["field"] == "name"


def test_parser_raises_on_missing_state_for_state_bearing_entity() -> None:
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_turnout({"type": "turnout", "data": {"name": "X", "userName": None}})
    assert exc_info.value.context["entity_type"] == "turnout"
    assert exc_info.value.context["field"] == "state"
    assert exc_info.value.context["name"] == "X"


def test_parser_raises_on_unknown_state_code() -> None:
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_turnout({"type": "turnout", "data": {"name": "X", "userName": None, "state": 99}})
    assert exc_info.value.context["entity_type"] == "turnout"
    assert exc_info.value.context["field"] == "state"
    assert exc_info.value.context["state_code"] == 99
    assert exc_info.value.context["name"] == "X"


def test_parser_raises_on_non_integer_state() -> None:
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_turnout({"type": "turnout", "data": {"name": "X", "userName": None, "state": "two"}})
    assert exc_info.value.context["field"] == "state"


def test_parse_signal_head_raises_on_missing_appearance() -> None:
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_signal_head(
            {
                "type": "signalHead",
                "data": {"name": "NH1", "userName": None, "held": False, "lit": True},
            }
        )
    assert exc_info.value.context["entity_type"] == "signalHead"
    assert exc_info.value.context["field"] == "appearance"


def test_parse_signal_head_raises_on_unknown_appearance() -> None:
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_signal_head(
            {
                "type": "signalHead",
                "data": {
                    "name": "NH1",
                    "userName": None,
                    "appearance": 999,
                    "held": False,
                    "lit": True,
                },
            }
        )
    assert exc_info.value.context["field"] == "appearance"
    assert exc_info.value.context["state_code"] == 999


def test_parse_signal_head_raises_on_missing_held() -> None:
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_signal_head(
            {
                "type": "signalHead",
                "data": {"name": "NH1", "userName": None, "appearance": 16, "lit": True},
            }
        )
    assert exc_info.value.context["field"] == "held"


# ---- SignalMast: aspect string translation ----


def test_parse_signal_mast_translates_basic_clear_aspect() -> None:
    env = {
        "type": "signalMast",
        "data": {
            "name": "IF$shsm:basic:one-searchlight(X)",
            "userName": "X",
            "aspect": "Clear",
            "held": False,
            "lit": True,
        },
    }
    assert parse_signal_mast(env).aspect is SignalMastAspect.CLEAR


@pytest.mark.parametrize(
    ("aspect_str", "expected"),
    [
        ("Clear", SignalMastAspect.CLEAR),
        ("Approach", SignalMastAspect.APPROACH),
        ("Approach Medium", SignalMastAspect.APPROACH_MEDIUM),
        ("Advance Approach", SignalMastAspect.ADVANCE_APPROACH),
        ("Approach Slow", SignalMastAspect.APPROACH_SLOW),
        ("Slow Approach", SignalMastAspect.SLOW_APPROACH),
        ("Medium Approach", SignalMastAspect.MEDIUM_APPROACH),
        ("Restricting", SignalMastAspect.RESTRICTING),
        ("Permissive", SignalMastAspect.PERMISSIVE),
        ("Slow", SignalMastAspect.SLOW),
        ("Medium", SignalMastAspect.MEDIUM),
        ("Stop", SignalMastAspect.STOP),
        ("Dark", SignalMastAspect.DARK),
        ("Held", SignalMastAspect.HELD),
        ("Unknown", SignalMastAspect.UNKNOWN),
    ],
)
def test_parse_signal_mast_basic_aspects_inline(
    aspect_str: str, expected: SignalMastAspect
) -> None:
    env = {
        "type": "signalMast",
        "data": {
            "name": "MX",
            "userName": None,
            "aspect": aspect_str,
            "held": False,
            "lit": True,
        },
    }
    assert parse_signal_mast(env).aspect is expected


def test_parse_signal_mast_unknown_aspect_raises() -> None:
    """Aspect outside the basic-system enum -> JMRIProtocolError."""
    env = {
        "type": "signalMast",
        "data": {
            "name": "MX",
            "userName": None,
            "aspect": "Manchester Cab Signal",
            "held": False,
            "lit": True,
        },
    }
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_signal_mast(env)
    assert exc_info.value.context["entity_type"] == "signalMast"
    assert exc_info.value.context["field"] == "aspect"
    assert exc_info.value.context["aspect"] == "Manchester Cab Signal"
    assert exc_info.value.context["name"] == "MX"
    assert exc_info.value.context["signaling_system_hint"] == "basic"


def test_parse_signal_mast_unknown_aspect_message_mentions_basic_system() -> None:
    env = {
        "type": "signalMast",
        "data": {
            "name": "MX",
            "userName": None,
            "aspect": "Custom Aspect Foo",
            "held": False,
            "lit": True,
        },
    }
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_signal_mast(env)
    assert "basic" in str(exc_info.value).lower()


def test_parse_signal_mast_raises_on_missing_aspect() -> None:
    env = {
        "type": "signalMast",
        "data": {"name": "MX", "userName": None, "held": False, "lit": True},
    }
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_signal_mast(env)
    assert exc_info.value.context["field"] == "aspect"


def test_parse_signal_mast_chained_from_value_error() -> None:
    env = {
        "type": "signalMast",
        "data": {
            "name": "MX",
            "userName": None,
            "aspect": "Bogus",
            "held": False,
            "lit": True,
        },
    }
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_signal_mast(env)
    assert isinstance(exc_info.value.__cause__, ValueError)


# ---- Roster: DCC address parsing ----


def test_parse_roster_entry_extracts_dcc_address() -> None:
    env = {
        "type": "rosterEntry",
        "data": {
            "name": "1029 NW2 Switcher",
            "address": "1029",
            "isLongAddress": True,
            "road": "Union Pacific",
            "number": "1029",
            "model": "176-4374",
            "comment": "$92 plus decoder",
        },
    }
    parsed = parse_roster_entry(env)
    assert parsed.dcc_address == 1029
    assert parsed.long_address is True
    assert parsed.road_name == "Union Pacific"
    assert parsed.road_number == "1029"
    assert parsed.model == "176-4374"
    assert parsed.comment == "$92 plus decoder"


def test_parse_roster_entry_short_address_is_long_address_false() -> None:
    env = {
        "type": "rosterEntry",
        "data": {
            "name": "Switcher 7",
            "address": "7",
            "isLongAddress": False,
            "road": None,
            "number": None,
            "model": None,
            "comment": None,
        },
    }
    parsed = parse_roster_entry(env)
    assert parsed.dcc_address == 7
    assert parsed.long_address is False
    assert parsed.road_name is None
    assert parsed.road_number is None
    assert parsed.model is None
    assert parsed.comment is None


def test_parse_roster_entry_raises_on_non_digit_address() -> None:
    env = {
        "type": "rosterEntry",
        "data": {
            "name": "Bad Loco",
            "address": "1A2B",
            "isLongAddress": False,
        },
    }
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_roster_entry(env)
    assert exc_info.value.context["field"] == "address"
    assert exc_info.value.context["address"] == "1A2B"


def test_parse_roster_entry_raises_on_missing_is_long_address() -> None:
    env = {
        "type": "rosterEntry",
        "data": {"name": "X", "address": "100"},
    }
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_roster_entry(env)
    assert exc_info.value.context["field"] == "isLongAddress"


def test_parse_roster_entry_ignores_extra_jmri_fields() -> None:
    """Roster envelopes carry many fields pyjmri doesn't surface; they are ignored."""
    env = {
        "type": "rosterEntry",
        "data": {
            "name": "X",
            "address": "100",
            "isLongAddress": False,
            "mfg": "Kato",
            "decoderModel": "DN123",
            "decoderFamily": "Series 3",
            "owner": "Mike",
            "dateModified": "2015-08-15T14:58:45.000+00:00",
            "functionKeys": [{"name": "F0"}],
            "image": None,
            "icon": None,
            "maxSpeedPct": 100,
            "shuntingFunction": "",
        },
    }
    parsed = parse_roster_entry(env)
    assert parsed.dcc_address == 100


# ---- Memory peculiarities ----


def test_parse_memory_value_can_be_string(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("memories")
    string_valued = [env for env in envelopes if isinstance(env["data"].get("value"), str)]
    assert string_valued, "fixture should contain at least one string-valued memory"
    parsed = parse_memory(string_valued[0])
    assert isinstance(parsed.value, str)


def test_parse_memory_value_null_returns_none(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("memories")
    null_valued = [env for env in envelopes if env["data"].get("value") is None]
    if not null_valued:
        pytest.skip("no null-valued memory in fixture")
    parsed = parse_memory(null_valued[0])
    assert parsed.value is None


def test_parse_memory_value_inline_string() -> None:
    env = {
        "type": "memory",
        "data": {"name": "IM:AUTO:0001", "userName": "Foo", "value": "hello"},
    }
    assert parse_memory(env).value == "hello"


def test_parse_memory_value_inline_null() -> None:
    env = {
        "type": "memory",
        "data": {"name": "IM:AUTO:0001", "userName": None, "value": None},
    }
    assert parse_memory(env).value is None


# ---- Power ----


def test_parse_power_envelope_inline() -> None:
    env = {"type": "power", "data": {"name": "NCE", "state": 0, "default": True}}
    parsed = parse_power(env)
    assert parsed.name == "NCE"
    assert parsed.state is PowerState.UNKNOWN
    assert parsed.default is True


def test_parse_power_raises_on_missing_default() -> None:
    env = {"type": "power", "data": {"name": "NCE", "state": 0}}
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_power(env)
    assert exc_info.value.context["field"] == "default"


# ---- Signal head: held/lit booleans round-trip ----


def test_parse_signal_head_held_true_inline() -> None:
    env = {
        "type": "signalHead",
        "data": {
            "name": "NH1",
            "userName": None,
            "appearance": 16,
            "held": True,
            "lit": True,
        },
    }
    parsed = parse_signal_head(env)
    assert parsed.held is True
    assert parsed.lit is True


def test_parse_signal_head_lit_false_inline() -> None:
    env = {
        "type": "signalHead",
        "data": {
            "name": "NH1",
            "userName": None,
            "appearance": 0,
            "held": False,
            "lit": False,
        },
    }
    parsed = parse_signal_head(env)
    assert parsed.appearance is SignalHeadAppearance.DARK
    assert parsed.lit is False
