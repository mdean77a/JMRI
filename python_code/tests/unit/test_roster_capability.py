"""Unit tests for capability classification (Story 9.3).

``classify_capability`` and ``firable_startup_functions`` are pure functions
over a :class:`pyjmri.RosterEntry` — no live JMRI required. Tests drive the
live ``roster.json`` fixture (entries pinned by attribute filter, never
positional ``[0]``) plus a few synthetic entries for the edge cases the
fixture cannot guarantee.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from pyjmri import (
    Capability,
    FunctionLabel,
    RosterEntry,
    classify_capability,
    firable_startup_functions,
)
from pyjmri._parsing import parse_roster_entry


def _entries(load_fixture: Callable[[str], list[dict[str, Any]]]) -> list[RosterEntry]:
    return [parse_roster_entry(env) for env in load_fixture("roster")]


def _make_entry(*, dcc_address: int = 3, function_labels: tuple[FunctionLabel, ...]) -> RosterEntry:
    """Build a synthetic RosterEntry with only the fields the classifier reads."""
    return RosterEntry(
        name=f"synthetic-{dcc_address}",
        user_name=None,
        dcc_address=dcc_address,
        long_address=dcc_address > 127,
        road_name=None,
        road_number=None,
        model=None,
        mfg=None,
        owner=None,
        comment=None,
        image_path=None,
        max_speed_pct=None,
        decoder_family=None,
        decoder_model=None,
        function_labels=function_labels,
    )


def test_sound_labeled_entry_is_sound_capable(
    load_fixture: Callable[[str], list[dict[str, Any]]],
) -> None:
    entries = _entries(load_fixture)
    sound = next(
        e
        for e in entries
        if any(fl.label is not None and "horn" in fl.label.lower() for fl in e.function_labels)
    )
    capability = classify_capability(sound)
    assert capability.sound is True
    assert capability.motor_only is False
    assert len(capability.sound_functions) > 0
    # Every reported sound function genuinely carries a label.
    assert all(fl.label is not None for fl in capability.sound_functions)


def test_motor_only_entry_when_all_labels_blank(
    load_fixture: Callable[[str], list[dict[str, Any]]],
) -> None:
    entries = _entries(load_fixture)
    motor_only = next(
        e
        for e in entries
        if e.function_labels and all(fl.label is None for fl in e.function_labels)
    )
    capability = classify_capability(motor_only)
    assert capability.sound is False
    assert capability.motor_only is True
    assert capability.sound_functions == ()


def test_mixed_labels_keeps_only_matching_functions() -> None:
    entry = _make_entry(
        function_labels=(
            FunctionLabel(num=0, label="Headlight", lockable=True),  # not a sound keyword
            FunctionLabel(num=1, label="Bell", lockable=False),  # sound
            FunctionLabel(num=2, label=None, lockable=True),  # blank
            FunctionLabel(num=3, label="Horn 1", lockable=False),  # sound
        ),
    )
    capability = classify_capability(entry)
    assert capability.sound is True
    assert tuple(fl.num for fl in capability.sound_functions) == (1, 3)


def test_classification_ignores_decoder_family_strings() -> None:
    # decoder_family literally contains "Sound" ("ESU LokSound 5"), but the
    # classifier must read labels only — all-None labels => motor-only.
    entry = RosterEntry(
        name="LokSound but no labels",
        user_name=None,
        dcc_address=55,
        long_address=False,
        road_name=None,
        road_number=None,
        model=None,
        mfg=None,
        owner=None,
        comment=None,
        image_path=None,
        max_speed_pct=None,
        decoder_family="ESU LokSound 5",
        decoder_model="LokSound 5 DCC",
        function_labels=(FunctionLabel(num=0, label=None, lockable=True),),
    )
    capability = classify_capability(entry)
    assert capability.motor_only is True
    assert capability.sound_functions == ()


def test_empty_function_labels_is_motor_only() -> None:
    capability = classify_capability(_make_entry(function_labels=()))
    assert capability.motor_only is True
    assert capability.sound_functions == ()


def test_firable_startup_functions_excludes_above_f28() -> None:
    capability = Capability(
        sound=True,
        sound_functions=(
            FunctionLabel(num=2, label="Bell", lockable=False),
            FunctionLabel(num=8, label="Startup", lockable=True),
            FunctionLabel(num=30, label="Sound mute", lockable=True),  # F29+ not commandable
        ),
    )
    assert firable_startup_functions(capability) == (2, 8)


def test_firable_startup_functions_dedupes_and_preserves_order() -> None:
    capability = Capability(
        sound=True,
        sound_functions=(
            FunctionLabel(num=5, label="Horn", lockable=False),
            FunctionLabel(num=2, label="Bell", lockable=False),
            FunctionLabel(num=5, label="Horn alt", lockable=False),  # duplicate num
        ),
    )
    assert firable_startup_functions(capability) == (5, 2)


def test_firable_startup_functions_empty_for_motor_only() -> None:
    assert firable_startup_functions(Capability(sound=False, sound_functions=())) == ()


def test_capability_is_frozen() -> None:
    capability = Capability(sound=False, sound_functions=())
    with pytest.raises(AttributeError):
        capability.sound = True  # type: ignore[misc]
