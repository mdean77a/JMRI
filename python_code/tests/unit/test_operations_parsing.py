"""Unit tests for ``pyjmri._parsing`` Operations parsers (FR45-FR48).

Covers:
- Happy-path round-trip from each captured fixture -> typed entity.
- Dual-name vs road+number identity (locations/trains carry userName;
  cars/engines do not).
- Absence path: null trainName/destination -> None (FR48).
- Assignment path: nested location -> track and destination -> track.
- Train consist: nested engines[]/cars[] (bare data objects) and ordered
  route stops.
- Engine is a distinct type from Car (FR48 type model).
- Frozen/read-only entities (supports FR49) and malformed-envelope errors.

Fixtures under ``tests/unit/fixtures/operations/`` are captured from a
live JMRI instance with Operations data loaded; no live JMRI is required
to run these tests.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

import pytest

from pyjmri import (
    Car,
    Engine,
    JMRIProtocolError,
    Location,
    Placement,
    RouteStop,
    Track,
    Train,
)
from pyjmri._parsing import (
    parse_car,
    parse_engine,
    parse_location,
    parse_train,
)

LoadFixture = Callable[[str], list[dict[str, Any]]]


# ---- Happy-path: every fixture envelope parses to its typed entity ----


def test_parse_location_round_trips_every_envelope(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("operations/locations")
    assert envelopes, "locations fixture should not be empty"
    for env in envelopes:
        parsed = parse_location(env)
        assert isinstance(parsed, Location)
        assert parsed.name
        assert isinstance(parsed.length, int)
        assert isinstance(parsed.tracks, tuple)
        for track in parsed.tracks:
            assert isinstance(track, Track)


def test_parse_car_round_trips_every_envelope(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("operations/cars")
    assert envelopes, "cars fixture should not be empty"
    for env in envelopes:
        parsed = parse_car(env)
        assert isinstance(parsed, Car)
        assert parsed.name == f"{parsed.road}{parsed.number}"


def test_parse_engine_round_trips_every_envelope(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("operations/engines")
    assert envelopes, "engines fixture should not be empty"
    for env in envelopes:
        parsed = parse_engine(env)
        assert isinstance(parsed, Engine)
        assert parsed.name == f"{parsed.road}{parsed.number}"


def test_parse_train_round_trips_every_envelope(load_fixture: LoadFixture) -> None:
    envelopes = load_fixture("operations/trains")
    assert envelopes, "trains fixture should not be empty"
    for env in envelopes:
        parsed = parse_train(env)
        assert isinstance(parsed, Train)
        assert parsed.name


# ---- Identity / dual-name rules ----


def test_locations_carry_both_names(load_fixture: LoadFixture) -> None:
    """Locations have a system name AND a user name (dual-name lookup)."""
    locations = [parse_location(e) for e in load_fixture("operations/locations")]
    by_user = {loc.user_name: loc for loc in locations}
    assert "NW_Staging_Yard" in by_user
    yard = by_user["NW_Staging_Yard"]
    assert yard.name == "2"  # system id distinct from user name
    assert yard.length == 4000
    assert yard.tracks  # staging yard has tracks


def test_trains_carry_both_names(load_fixture: LoadFixture) -> None:
    trains = [parse_train(e) for e in load_fixture("operations/trains")]
    by_user = {t.user_name: t for t in trains}
    assert "TestTrainOne" in by_user
    assert by_user["TestTrainOne"].name == "1"


def test_cars_have_no_user_name_keyed_by_road_number(load_fixture: LoadFixture) -> None:
    cars = {c.name: c for c in (parse_car(e) for e in load_fixture("operations/cars"))}
    assert "AA123" in cars
    car = cars["AA123"]
    assert car.user_name is None
    assert car.road == "AA"
    assert car.number == "123"


def test_engines_have_no_user_name(load_fixture: LoadFixture) -> None:
    engines = [parse_engine(e) for e in load_fixture("operations/engines")]
    assert engines
    assert all(eng.user_name is None for eng in engines)


# ---- Absence path (FR48): null operational state -> None ----


def test_unassigned_engine_parses_with_none_state(load_fixture: LoadFixture) -> None:
    """An engine not on a train: trainName/destination null -> None, no crash."""
    engines = {e.name: e for e in (parse_engine(env) for env in load_fixture("operations/engines"))}
    up2570 = engines["UP2570"]
    assert up2570.train is None
    assert up2570.destination is None
    # It is still placed on a track even though unassigned.
    assert up2570.location is not None
    assert isinstance(up2570.location, Placement)
    assert up2570.location.track is not None
    assert up2570.location.track.user_name == "NW_Track_6"
    assert up2570.model == "ES44AC"
    assert up2570.engine_type == "Diesel"


# ---- Assignment path: nested location -> track, destination -> track ----


def test_assigned_car_parses_full_placement(load_fixture: LoadFixture) -> None:
    cars = {c.name: c for c in (parse_car(e) for e in load_fixture("operations/cars"))}
    car = cars["AA123"]
    assert car.train == "TestTrainOne"
    assert car.car_type == "Boxcar"
    assert car.location is not None
    assert car.location.user_name == "NW_Staging_Yard"
    assert car.location.track is not None
    assert car.location.track.user_name == "NW_Track_1"
    assert car.destination is not None
    assert car.destination.user_name == "South Interchange"
    assert car.destination.track is not None
    assert car.destination.track.user_name == "Arrival_Departure"


# ---- Train consist + route ----


def test_train_consist_and_route(load_fixture: LoadFixture) -> None:
    train = next(
        t
        for t in (parse_train(e) for e in load_fixture("operations/trains"))
        if t.user_name == "TestTrainOne"
    )
    assert train.route == "Test_Route"
    assert train.current_location == "NW_Staging_Yard"
    assert train.status == "Partial 3/27 cars"
    assert train.status_code == 20
    assert train.lead_engine == "UP 8997"
    # Consist: full nested Car/Engine objects parsed from bare data objects.
    assert train.cars, "consist should include cars"
    assert all(isinstance(c, Car) for c in train.cars)
    assert train.engines, "consist should include engines"
    assert all(isinstance(eng, Engine) for eng in train.engines)
    # Route stops are ordered by sequence_id.
    seqs = [s.sequence_id for s in train.route_stops]
    assert seqs == sorted(seqs)
    assert all(isinstance(s, RouteStop) for s in train.route_stops)
    assert [s.user_name for s in train.route_stops] == ["NW_Staging_Yard", "South Interchange"]


def test_route_stops_sorted_regardless_of_jmri_order() -> None:
    """Parser must sort route_stops by sequence_id, not rely on JMRI's JSON order."""
    # Construct a synthetic train with stops deliberately out of sequence order.
    payload: dict[str, Any] = {
        "type": "train",
        "data": {
            "name": "99",
            "userName": "SortTest",
            "route": "R1",
            "location": "StopB",
            "status": "Ready",
            "statusCode": 0,
            "leadEngine": None,
            "locations": [
                {
                    "name": "99r3",
                    "userName": "StopC",
                    "sequenceId": 3,
                    "trainDirection": "East",
                },
                {
                    "name": "99r1",
                    "userName": "StopA",
                    "sequenceId": 1,
                    "trainDirection": "East",
                },
                {
                    "name": "99r2",
                    "userName": "StopB",
                    "sequenceId": 2,
                    "trainDirection": "West",
                },
            ],
            "engines": [],
            "cars": [],
        },
    }
    train = parse_train(payload)
    seqs = [s.sequence_id for s in train.route_stops]
    assert seqs == [1, 2, 3], "parser must sort route_stops by sequence_id"
    assert [s.user_name for s in train.route_stops] == ["StopA", "StopB", "StopC"]


# ---- Type model (FR48): Engine is distinct from Car ----


def test_engine_is_distinct_type_from_car(load_fixture: LoadFixture) -> None:
    engine = parse_engine(load_fixture("operations/engines")[0])
    car = parse_car(load_fixture("operations/cars")[0])
    assert isinstance(engine, Engine)
    assert not isinstance(engine, Car)
    assert isinstance(car, Car)
    assert not isinstance(car, Engine)
    assert Engine is not Car


# ---- Read-only enforcement (supports FR49) ----


def test_entities_are_frozen(load_fixture: LoadFixture) -> None:
    car = parse_car(load_fixture("operations/cars")[0])
    with pytest.raises(dataclasses.FrozenInstanceError):
        car.train = "X"  # type: ignore[misc]


def test_nested_value_objects_are_frozen(load_fixture: LoadFixture) -> None:
    car = parse_car(load_fixture("operations/cars")[0])
    assert car.location is not None and car.location.track is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        car.location.track.name = "X"  # type: ignore[misc]


# ---- Malformed envelopes ----


@pytest.mark.parametrize(
    "parser",
    [parse_location, parse_car, parse_engine, parse_train],
)
def test_missing_data_object_raises(parser: Callable[[dict[str, Any]], Any]) -> None:
    with pytest.raises(JMRIProtocolError):
        parser({})


def test_missing_required_field_raises() -> None:
    # A car envelope missing the required integer 'length' field.
    with pytest.raises(JMRIProtocolError):
        parse_car(
            {"type": "car", "data": {"name": "ZZ1", "road": "ZZ", "number": "1", "type": "Boxcar"}}
        )
