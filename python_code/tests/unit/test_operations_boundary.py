"""Unit tests: the Operations subsystem exposes no mutating/command surface (FR49).

Story 8.3 boundary test. Story 8.1's frozen-dataclass tests
(``test_operations_parsing.py``) assert attribute *immutability*; this file
asserts the complementary axis — that no Operations type defines a
build/move/assign/manifest/set_*/command/wait method. Mirrors the
absence-of-method pattern in ``test_route.py::test_route_has_no_get_state``.

The read-only boundary is structural: FR49 is "enforced by the class
surface." The mutating surface (build train, move/assign car, generate
manifest) is deliberately deferred to the Vision command increment.
"""

from __future__ import annotations

import pytest

from pyjmri import (
    Car,
    Engine,
    Location,
    Operations,
    Placement,
    RouteStop,
    Track,
    Train,
)

# Every mutating/command verb the Vision command increment would add, plus the
# layout-entity command/observe surface (set_state/get_state/activate/wait_*).
# No Operations type may expose any of these in the read-only v1.1.
_FORBIDDEN_METHODS = (
    # Operations-domain mutations (deferred to Vision)
    "build",
    "move",
    "assign",
    "reset",
    "manifest",
    "generate_manifest",
    "set_location",
    "set_train",
    "set_destination",
    # Layout-entity command/observe surface (must not leak onto data records)
    "set_state",
    "set_value",
    "set_speed",
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

# One representative instance of every public Operations type, built directly —
# method absence is a class-level property, so this needs no live JMRI or
# fixtures. Construction also documents the full read-only attribute surface.
_INSTANCES = [
    pytest.param(Track(name="1s1", user_name=None), id="Track"),
    pytest.param(Placement(name="1", user_name=None, track=None), id="Placement"),
    pytest.param(
        RouteStop(name="1", user_name=None, sequence_id=1, train_direction="North"),
        id="RouteStop",
    ),
    pytest.param(
        Location(name="1", user_name=None, length=0, comment=None),
        id="Location",
    ),
    pytest.param(
        Car(
            name="AA1",
            road="AA",
            number="1",
            car_type="Boxcar",
            length=40,
            location=None,
            train=None,
            destination=None,
        ),
        id="Car",
    ),
    pytest.param(
        Engine(
            name="UP1",
            road="UP",
            number="1",
            model=None,
            engine_type="Diesel",
            length=50,
            location=None,
            train=None,
            destination=None,
        ),
        id="Engine",
    ),
    pytest.param(
        Train(
            name="1",
            user_name=None,
            route=None,
            current_location=None,
            status="",
            status_code=0,
            lead_engine=None,
        ),
        id="Train",
    ),
    pytest.param(Operations(), id="Operations"),
]


@pytest.mark.parametrize("entity", _INSTANCES)
@pytest.mark.parametrize("method_name", _FORBIDDEN_METHODS)
def test_operations_type_exposes_no_mutating_method(entity: object, method_name: str) -> None:
    """No Operations type defines any build/move/assign/manifest/set_*/command method (FR49)."""
    assert hasattr(entity, method_name) is False, (
        f"{type(entity).__name__} unexpectedly exposes '{method_name}' — "
        "Operations is read-only in v1.1 (FR49); the mutating surface is Vision."
    )


def test_operations_container_exposes_only_collection_attributes() -> None:
    """Operations surfaces only the four read-only collections — no handle, no methods (FR49)."""
    ops = Operations()
    public_attrs = {name for name in dir(ops) if not name.startswith("_")}
    assert public_attrs == {"locations", "trains", "cars", "engines"}
