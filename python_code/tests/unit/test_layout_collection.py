"""Unit tests for :class:`pyjmri.EntityCollection` and :class:`pyjmri.Layout`."""

from __future__ import annotations

from typing import Any, cast

import pytest

from pyjmri import (
    Block,
    BlockState,
    EntityCollection,
    Layout,
    LayoutEntityNotFound,
    Light,
    LightState,
    Memory,
    Route,
    Sensor,
    SensorState,
    SignalHead,
    SignalHeadAppearance,
    SignalMast,
    SignalMastAspect,
    Turnout,
    TurnoutState,
)
from pyjmri._protocols import ClientHandle


def _make_turnout(
    make_fake_handle: Any,
    *,
    name: str,
    user_name: str | None,
) -> Turnout:
    handle = make_fake_handle(lambda _t, _n: {})
    return Turnout(
        name=name,
        user_name=user_name,
        state=TurnoutState.UNKNOWN,
        _handle=cast(ClientHandle, handle),
    )


def _make_sensor(make_fake_handle: Any, *, name: str, user_name: str | None) -> Sensor:
    handle = make_fake_handle(lambda _t, _n: {})
    return Sensor(
        name=name,
        user_name=user_name,
        state=SensorState.UNKNOWN,
        _handle=cast(ClientHandle, handle),
    )


def test_getitem_returns_entity_by_user_name(make_fake_handle: Any) -> None:
    t = _make_turnout(make_fake_handle, name="NT1", user_name="Staging West")
    collection: EntityCollection[Turnout] = EntityCollection([t], entity_type="turnout")

    assert collection["Staging West"] is t


def test_getitem_falls_back_to_system_name(make_fake_handle: Any) -> None:
    t = _make_turnout(make_fake_handle, name="NT400", user_name="Staging West")
    collection: EntityCollection[Turnout] = EntityCollection([t], entity_type="turnout")

    assert collection["NT400"] is t


def test_getitem_collision_user_name_wins(make_fake_handle: Any) -> None:
    x = _make_turnout(make_fake_handle, name="NT1", user_name="Foo")
    y = _make_turnout(make_fake_handle, name="Foo", user_name=None)
    collection: EntityCollection[Turnout] = EntityCollection([x, y], entity_type="turnout")

    assert collection["Foo"] is x


def test_by_system_name_returns_other_entity_on_collision(make_fake_handle: Any) -> None:
    x = _make_turnout(make_fake_handle, name="NT1", user_name="Foo")
    y = _make_turnout(make_fake_handle, name="Foo", user_name=None)
    collection: EntityCollection[Turnout] = EntityCollection([x, y], entity_type="turnout")

    assert collection.by_system_name("Foo") is y


def test_getitem_missing_key_raises_layout_entity_not_found(make_fake_handle: Any) -> None:
    collection: EntityCollection[Turnout] = EntityCollection([], entity_type="turnout")

    with pytest.raises(LayoutEntityNotFound):
        collection["NT-missing"]


def test_get_missing_returns_default_now_that_layout_entity_not_found_is_key_error(
    make_fake_handle: Any,
) -> None:
    # AC10 (Story 3.1): LayoutEntityNotFound multi-inherits KeyError so
    # Mapping.get's internal except-KeyError catches it and returns the
    # default rather than surfacing the lookup miss.
    collection: EntityCollection[Turnout] = EntityCollection([], entity_type="turnout")

    assert collection.get("NT-missing") is None
    sentinel = object()
    assert collection.get("NT-missing", sentinel) is sentinel


def test_layout_entity_not_found_carries_entity_type_and_key(make_fake_handle: Any) -> None:
    collection: EntityCollection[Turnout] = EntityCollection([], entity_type="turnout")

    with pytest.raises(LayoutEntityNotFound) as exc_info:
        collection["NT-missing"]

    assert exc_info.value.context["entity_type"] == "turnout"
    assert exc_info.value.context["key"] == "NT-missing"

    rendered = str(exc_info.value)
    assert "turnout" in rendered
    assert "NT-missing" in rendered


def test_by_user_name_missing_raises_layout_entity_not_found(make_fake_handle: Any) -> None:
    t = _make_turnout(make_fake_handle, name="NT1", user_name=None)
    collection: EntityCollection[Turnout] = EntityCollection([t], entity_type="turnout")

    with pytest.raises(LayoutEntityNotFound) as exc_info:
        collection.by_user_name("NT1")

    assert exc_info.value.context["entity_type"] == "turnout"
    assert exc_info.value.context["key"] == "NT1"


def test_by_system_name_missing_raises_layout_entity_not_found(make_fake_handle: Any) -> None:
    collection: EntityCollection[Turnout] = EntityCollection([], entity_type="turnout")

    with pytest.raises(LayoutEntityNotFound) as exc_info:
        collection.by_system_name("NT-missing")

    assert exc_info.value.context["entity_type"] == "turnout"
    assert exc_info.value.context["key"] == "NT-missing"


def test_iter_yields_system_names_in_insertion_order(make_fake_handle: Any) -> None:
    t1 = _make_turnout(make_fake_handle, name="NT3", user_name="Z")
    t2 = _make_turnout(make_fake_handle, name="NT1", user_name="A")
    t3 = _make_turnout(make_fake_handle, name="NT2", user_name="M")
    collection: EntityCollection[Turnout] = EntityCollection([t1, t2, t3], entity_type="turnout")

    assert list(collection) == ["NT3", "NT1", "NT2"]


def test_len_matches_entity_count(make_fake_handle: Any) -> None:
    t1 = _make_turnout(make_fake_handle, name="NT1", user_name=None)
    t2 = _make_turnout(make_fake_handle, name="NT2", user_name="Two")
    t3 = _make_turnout(make_fake_handle, name="NT3", user_name="Three")
    collection: EntityCollection[Turnout] = EntityCollection([t1, t2, t3], entity_type="turnout")

    assert len(collection) == 3


def test_contains_finds_user_name(make_fake_handle: Any) -> None:
    t = _make_turnout(make_fake_handle, name="NT1", user_name="Staging West")
    collection: EntityCollection[Turnout] = EntityCollection([t], entity_type="turnout")

    assert "Staging West" in collection


def test_contains_finds_system_name(make_fake_handle: Any) -> None:
    t = _make_turnout(make_fake_handle, name="NT400", user_name=None)
    collection: EntityCollection[Turnout] = EntityCollection([t], entity_type="turnout")

    assert "NT400" in collection


def test_contains_returns_false_for_unknown_key(make_fake_handle: Any) -> None:
    t = _make_turnout(make_fake_handle, name="NT1", user_name="Foo")
    collection: EntityCollection[Turnout] = EntityCollection([t], entity_type="turnout")

    assert "Unknown" not in collection


def test_values_yields_all_entities(make_fake_handle: Any) -> None:
    t1 = _make_turnout(make_fake_handle, name="NT1", user_name="A")
    t2 = _make_turnout(make_fake_handle, name="NT2", user_name="B")
    collection: EntityCollection[Turnout] = EntityCollection([t1, t2], entity_type="turnout")

    assert list(collection.values()) == [t1, t2]


def test_keys_yields_system_names(make_fake_handle: Any) -> None:
    t1 = _make_turnout(make_fake_handle, name="NT1", user_name="A")
    t2 = _make_turnout(make_fake_handle, name="NT2", user_name="B")
    collection: EntityCollection[Turnout] = EntityCollection([t1, t2], entity_type="turnout")

    assert list(collection.keys()) == ["NT1", "NT2"]


def test_items_yields_system_name_entity_pairs(make_fake_handle: Any) -> None:
    t1 = _make_turnout(make_fake_handle, name="NT1", user_name="A")
    t2 = _make_turnout(make_fake_handle, name="NT2", user_name="B")
    collection: EntityCollection[Turnout] = EntityCollection([t1, t2], entity_type="turnout")

    assert list(collection.items()) == [("NT1", t1), ("NT2", t2)]


def test_entity_with_no_user_name_findable_by_system_name_only(make_fake_handle: Any) -> None:
    t = _make_turnout(make_fake_handle, name="NT1", user_name=None)
    collection: EntityCollection[Turnout] = EntityCollection([t], entity_type="turnout")

    assert collection["NT1"] is t
    assert collection.by_system_name("NT1") is t
    with pytest.raises(LayoutEntityNotFound):
        collection.by_user_name("NT1")


def test_empty_collection_iterates_and_lens_zero() -> None:
    collection: EntityCollection[Turnout] = EntityCollection([], entity_type="turnout")

    assert len(collection) == 0
    assert list(collection) == []
    assert list(collection.values()) == []


def test_collection_is_generic_over_sensor_type(make_fake_handle: Any) -> None:
    s = _make_sensor(make_fake_handle, name="NS1", user_name="Block 1")
    collection: EntityCollection[Sensor] = EntityCollection([s], entity_type="sensor")

    assert collection["Block 1"] is s
    assert collection["NS1"] is s


def test_empty_layout_has_eight_empty_collections() -> None:
    layout = Layout()

    assert len(layout.turnouts) == 0
    assert len(layout.sensors) == 0
    assert len(layout.blocks) == 0
    assert len(layout.lights) == 0
    assert len(layout.memories) == 0
    assert len(layout.routes) == 0
    assert len(layout.signal_heads) == 0
    assert len(layout.signal_masts) == 0


def test_empty_layout_collections_carry_correct_entity_types() -> None:
    layout = Layout()

    expected: list[tuple[EntityCollection[Any], str]] = [
        (layout.turnouts, "turnout"),
        (layout.sensors, "sensor"),
        (layout.blocks, "block"),
        (layout.lights, "light"),
        (layout.memories, "memory"),
        (layout.routes, "route"),
        (layout.signal_heads, "signalHead"),
        (layout.signal_masts, "signalMast"),
    ]
    for collection, entity_type in expected:
        with pytest.raises(LayoutEntityNotFound) as exc_info:
            collection["does-not-exist"]
        assert exc_info.value.context["entity_type"] == entity_type


def test_layout_accepts_pre_populated_collections(make_fake_handle: Any) -> None:
    t = _make_turnout(make_fake_handle, name="NT1", user_name="Staging West")
    s = _make_sensor(make_fake_handle, name="NS1", user_name="Block 1")

    layout = Layout(
        turnouts=EntityCollection([t], entity_type="turnout"),
        sensors=EntityCollection([s], entity_type="sensor"),
    )

    assert layout.turnouts["Staging West"] is t
    assert layout.turnouts["NT1"] is t
    assert layout.sensors["Block 1"] is s
    assert layout.sensors["NS1"] is s
    assert len(layout.blocks) == 0
    assert len(layout.lights) == 0


def test_layout_accepts_all_eight_entity_types(make_fake_handle: Any) -> None:
    """Smoke test exercising the generic constraint for every entity type."""
    h = make_fake_handle(lambda _t, _n: {})
    handle = cast(ClientHandle, h)

    turnout = Turnout(name="T1", user_name=None, state=TurnoutState.UNKNOWN, _handle=handle)
    sensor = Sensor(name="S1", user_name=None, state=SensorState.UNKNOWN, _handle=handle)
    block = Block(
        name="B1",
        user_name=None,
        state=BlockState.UNKNOWN,
        value=None,
        _handle=handle,
    )
    light = Light(name="L1", user_name=None, state=LightState.UNKNOWN, _handle=handle)
    memory = Memory(name="M1", user_name=None, value=None, _handle=handle)
    route = Route(name="R1", user_name=None)
    signal_head = SignalHead(
        name="SH1",
        user_name=None,
        appearance=SignalHeadAppearance.DARK,
        held=False,
        lit=True,
        _handle=handle,
    )
    signal_mast = SignalMast(
        name="SM1",
        user_name=None,
        aspect=SignalMastAspect.UNKNOWN,
        held=False,
        lit=True,
        _handle=handle,
    )

    layout = Layout(
        turnouts=EntityCollection([turnout], entity_type="turnout"),
        sensors=EntityCollection([sensor], entity_type="sensor"),
        blocks=EntityCollection([block], entity_type="block"),
        lights=EntityCollection([light], entity_type="light"),
        memories=EntityCollection([memory], entity_type="memory"),
        routes=EntityCollection([route], entity_type="route"),
        signal_heads=EntityCollection([signal_head], entity_type="signalHead"),
        signal_masts=EntityCollection([signal_mast], entity_type="signalMast"),
    )

    assert layout.turnouts["T1"] is turnout
    assert layout.sensors["S1"] is sensor
    assert layout.blocks["B1"] is block
    assert layout.lights["L1"] is light
    assert layout.memories["M1"] is memory
    assert layout.routes["R1"] is route
    assert layout.signal_heads["SH1"] is signal_head
    assert layout.signal_masts["SM1"] is signal_mast
