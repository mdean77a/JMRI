"""Unit tests: the Roster subsystem exposes no mutating/command surface (FR56).

Story 9.4 boundary test. Story 9.1's frozen-dataclass tests
(``test_roster_parsing.py`` / ``test_roster_capability.py``) assert attribute
*immutability*; this file asserts the complementary axis — that no Roster type
defines an edit/program/set_*/command/wait method. Mirrors the
absence-of-method pattern in ``test_operations_boundary.py`` (Story 8.3).

The read-only boundary is structural: FR56 is "enforced by the class surface."
Editing a locomotive — its address, function labels, or decoder CVs — stays in
DecoderPro; ``pyjmri`` only reads the roster.
"""

from __future__ import annotations

import pytest

from pyjmri import FunctionLabel, Roster, RosterEntry

# Every mutating/command verb a future decoder-programming increment would add,
# plus the layout-entity command/observe surface (set_state/get_state/wait_*).
# No Roster type may expose any of these in the read-only v1.2.
_FORBIDDEN_METHODS = (
    # Standard MutableMapping mutators — Roster is a read-only Mapping, NOT a
    # MutableMapping. These are absent today; forbidding them explicitly guards
    # against a future base-class switch silently making `roster[k] = v`,
    # `roster.pop(...)`, or `roster.clear()` real (the FR56 "enforced by the
    # class surface" boundary must catch that regression).
    "__setitem__",
    "__delitem__",
    "pop",
    "popitem",
    "clear",
    "setdefault",
    # Roster/decoder-domain mutations (deferred to a future command increment)
    "edit",
    "save",
    "delete",
    "create",
    "update",
    "program",
    "write_cv",
    "read_cv",
    "set_cv",
    "set_address",
    "set_function_label",
    "set_decoder",
    # Layout-entity command/observe surface (must not leak onto data records)
    "set_state",
    "set_value",
    "set_speed",
    "set_function",
    "activate",
    "throttle",
    "command",
    "get_state",
    "get_value",
    "wait",
    "wait_for_state",
    "wait_active",
    "wait_inactive",
)

# One representative instance of every public Roster type, built directly —
# method absence is a class-level property, so this needs no live JMRI or
# fixtures. RosterEntry.user_name is always None (the roster ID is the label).
_INSTANCES = [
    pytest.param(FunctionLabel(num=0, label=None, lockable=False), id="FunctionLabel"),
    pytest.param(
        RosterEntry(
            name="X",
            user_name=None,
            dcc_address=3,
            long_address=False,
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
            function_labels=(),
        ),
        id="RosterEntry",
    ),
    pytest.param(Roster([]), id="Roster"),
]


@pytest.mark.parametrize("entity", _INSTANCES)
@pytest.mark.parametrize("method_name", _FORBIDDEN_METHODS)
def test_roster_type_exposes_no_mutating_method(entity: object, method_name: str) -> None:
    """No Roster type defines any edit/program/set_*/command method (FR56)."""
    assert hasattr(entity, method_name) is False, (
        f"{type(entity).__name__} unexpectedly exposes '{method_name}' — "
        "the Roster is read-only in v1.2 (FR56); editing stays in DecoderPro."
    )


def test_roster_exposes_only_read_only_collection_surface() -> None:
    """Roster's only roster-specific method is the get()-style ``by_address`` find (FR56).

    The container inherits ``EntityCollection``'s read-only Mapping surface
    (iteration, ``values``, ``__len__``, name lookup); it must add no mutator.
    """
    roster = Roster([])
    # The address index is a find, not a mutation, and it is the only
    # roster-specific public method.
    assert callable(roster.by_address)
    # None of the forbidden mutators leak from the base collection.
    for method_name in _FORBIDDEN_METHODS:
        assert hasattr(roster, method_name) is False, (
            f"Roster unexpectedly exposes '{method_name}' — it must stay read-only (FR56)."
        )
    # Sanity: the read-only Mapping surface is present.
    assert len(roster) == 0
    assert list(roster.values()) == []
