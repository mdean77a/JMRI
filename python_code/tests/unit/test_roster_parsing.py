"""Unit tests for roster wire-format parsing (``parse_roster_entry``).

Covers the capability-aware read-only ``RosterEntry``: full metadata,
decoder identifiers, per-function labels (including F29+), null/empty-label
handling, frozen immutability, and per-entry strict validation. The
``roster`` fixture is a live 44-entry capture from the basement layout.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

import pytest

from pyjmri import FunctionLabel, JMRIProtocolError, RosterEntry
from pyjmri._parsing import parse_roster_entry

LoadFixture = Callable[[str], list[dict[str, Any]]]


def _entry_named(load_fixture: LoadFixture, name: str) -> RosterEntry:
    for env in load_fixture("roster"):
        entry = parse_roster_entry(env)
        if entry.name == name:
            return entry
    raise AssertionError(f"fixture has no roster entry named {name!r}")


# ---- Happy path: every live envelope round-trips ----


def test_round_trips_every_live_envelope(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("roster")
    assert envelopes, "roster fixture should not be empty"
    for env in envelopes:
        entry = parse_roster_entry(env)
        assert isinstance(entry, RosterEntry)
        assert entry.name
        assert isinstance(entry.dcc_address, int)
        assert isinstance(entry.long_address, bool)
        assert isinstance(entry.function_labels, tuple)


def test_user_name_is_always_none(load_fixture: LoadFixture) -> None:
    for env in load_fixture("roster"):
        assert parse_roster_entry(env).user_name is None


def test_full_metadata_populated(load_fixture: LoadFixture) -> None:
    entry = _entry_named(load_fixture, "1029 NW2 Switcher")
    assert entry.dcc_address == 1029
    assert entry.long_address is True
    assert entry.road_name == "Union Pacific"
    assert entry.road_number == "1029"
    assert entry.model == "176-4374"
    assert entry.mfg == "Kato"
    assert entry.owner == "Mike Dean"
    assert entry.comment == "$92 plus decoder"
    assert entry.max_speed_pct == 100
    assert entry.decoder_family == "Series 3 with FX3, silent, readback"
    assert entry.decoder_model == "DN123K3"
    assert entry.image_path is None


# ---- Function labels ----


def test_motor_only_entry_has_present_but_null_labels(load_fixture: LoadFixture) -> None:
    # "1029 NW2 Switcher" has functionKeys with all-null labels: the keys are
    # PRESENT (not dropped), each carrying label=None.
    entry = _entry_named(load_fixture, "1029 NW2 Switcher")
    assert entry.function_labels, "keys should be present even when all labels are null"
    assert all(fl.label is None for fl in entry.function_labels)
    f0 = next(fl for fl in entry.function_labels if fl.num == 0)
    assert f0.lockable is True


def test_some_entry_carries_real_sound_labels(load_fixture: LoadFixture) -> None:
    labels = {
        fl.label
        for env in load_fixture("roster")
        for fl in parse_roster_entry(env).function_labels
        if fl.label
    }
    assert labels, "fixture should contain at least one labelled function"
    # The basement fleet has sound-equipped locos with these labels.
    assert any(lbl == "Bell" or "Horn" in lbl for lbl in labels)


def test_function_numbers_parse_past_f28(load_fixture: LoadFixture) -> None:
    high = [
        fl
        for env in load_fixture("roster")
        for fl in parse_roster_entry(env).function_labels
        if fl.num >= 29
    ]
    assert high, "fixture should include F29+ keys (roster data is not capped at F28)"
    assert all(isinstance(fl.num, int) for fl in high)


def test_empty_function_keys_yields_empty_tuple() -> None:
    env = {
        "type": "rosterEntry",
        "data": {"name": "X", "address": "100", "isLongAddress": False, "functionKeys": []},
    }
    assert parse_roster_entry(env).function_labels == ()


def test_absent_function_keys_yields_empty_tuple() -> None:
    env = {
        "type": "rosterEntry",
        "data": {"name": "X", "address": "100", "isLongAddress": False},
    }
    assert parse_roster_entry(env).function_labels == ()


def test_function_key_missing_label_and_lockable_defaults() -> None:
    env = {
        "type": "rosterEntry",
        "data": {
            "name": "X",
            "address": "100",
            "isLongAddress": False,
            "functionKeys": [{"name": "F0"}],
        },
    }
    (label,) = parse_roster_entry(env).function_labels
    assert label == FunctionLabel(num=0, label=None, lockable=False)


def test_empty_string_label_becomes_none() -> None:
    env = {
        "type": "rosterEntry",
        "data": {
            "name": "X",
            "address": "100",
            "isLongAddress": False,
            "functionKeys": [{"name": "F5", "label": "", "lockable": False}],
        },
    }
    (label,) = parse_roster_entry(env).function_labels
    assert label.num == 5
    assert label.label is None


# ---- Metadata + addressing (migrated from test_parsing.py) ----


def test_short_address_and_null_optionals() -> None:
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
    entry = parse_roster_entry(env)
    assert entry.dcc_address == 7
    assert entry.long_address is False
    assert entry.road_name is None
    assert entry.road_number is None
    assert entry.model is None
    assert entry.comment is None
    assert entry.max_speed_pct is None
    assert entry.function_labels == ()


def test_surfaces_decoder_and_owner_fields() -> None:
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
            "maxSpeedPct": 100,
            "image": None,
        },
    }
    entry = parse_roster_entry(env)
    assert entry.mfg == "Kato"
    assert entry.decoder_model == "DN123"
    assert entry.decoder_family == "Series 3"
    assert entry.owner == "Mike"
    assert entry.max_speed_pct == 100
    assert entry.image_path is None


def test_non_null_image_path_is_surfaced() -> None:
    env = {
        "type": "rosterEntry",
        "data": {
            "name": "X",
            "address": "100",
            "isLongAddress": False,
            "image": "/path/to/loco.png",
        },
    }
    assert parse_roster_entry(env).image_path == "/path/to/loco.png"


# ---- Per-entry strict validation (the FR58 collection-level wrap is Story 9.2) ----


def test_raises_on_non_digit_address() -> None:
    env = {
        "type": "rosterEntry",
        "data": {"name": "Bad Loco", "address": "1A2B", "isLongAddress": False},
    }
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_roster_entry(env)
    assert exc_info.value.context["field"] == "address"
    assert exc_info.value.context["address"] == "1A2B"


def test_raises_on_unicode_decimal_address() -> None:
    # U+FF11..FF13 fullwidth digits: isdecimal()=True but isascii()=False
    unicode_addr = chr(0xFF11) + chr(0xFF12) + chr(0xFF13)
    env = {
        "type": "rosterEntry",
        "data": {"name": "X", "address": unicode_addr, "isLongAddress": False},
    }
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_roster_entry(env)
    assert exc_info.value.context["field"] == "address"


def test_raises_on_missing_is_long_address() -> None:
    env = {"type": "rosterEntry", "data": {"name": "X", "address": "100"}}
    with pytest.raises(JMRIProtocolError) as exc_info:
        parse_roster_entry(env)
    assert exc_info.value.context["field"] == "isLongAddress"


def test_raises_on_missing_data() -> None:
    with pytest.raises(JMRIProtocolError):
        parse_roster_entry({})


def test_raises_on_non_dict_envelope() -> None:
    # A non-dict list element must raise JMRIProtocolError (not AttributeError),
    # so discover_roster's per-entry skip-and-continue can catch it (FR58).
    with pytest.raises(JMRIProtocolError):
        parse_roster_entry("not an object")  # type: ignore[arg-type]


# ---- Read-only (frozen) — supports FR56; full no-mutation surface test is Story 9.4 ----


def test_roster_entry_is_frozen() -> None:
    env = {"type": "rosterEntry", "data": {"name": "X", "address": "100", "isLongAddress": False}}
    entry = parse_roster_entry(env)
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.dcc_address = 1  # type: ignore[misc]


def test_function_label_is_frozen() -> None:
    label = FunctionLabel(num=0, label=None, lockable=True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        label.num = 1  # type: ignore[misc]
