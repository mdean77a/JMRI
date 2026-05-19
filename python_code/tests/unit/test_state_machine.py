"""Unit tests for per-entity waiter mechanics and ``Client._on_ws_message`` dispatch.

Covers Story 3.2 acceptance criteria 1, 2, 3, 4, 6, 8, 9.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

import pytest

from pyjmri import (
    Block,
    BlockState,
    Client,
    Light,
    LightState,
    Sensor,
    SensorState,
    SignalHead,
    SignalHeadAppearance,
    SignalMast,
    SignalMastAspect,
    Turnout,
    TurnoutState,
    WaitTimeout,
)
from pyjmri._protocols import ClientHandle

# ---- Helpers ----


def _make_turnout(handle: Any, *, state: TurnoutState = TurnoutState.UNKNOWN) -> Turnout:
    return Turnout(
        name="NT1",
        user_name=None,
        state=state,
        _handle=cast(ClientHandle, handle),
    )


def _make_sensor(handle: Any, *, state: SensorState = SensorState.UNKNOWN) -> Sensor:
    return Sensor(
        name="NS1",
        user_name=None,
        state=state,
        _handle=cast(ClientHandle, handle),
    )


def _envelope_sensor(state: int, *, name: str = "NS1") -> dict[str, Any]:
    return {"type": "sensor", "data": {"name": name, "userName": None, "state": state}}


def _envelope_turnout(state: int, *, name: str = "NT1") -> dict[str, Any]:
    return {"type": "turnout", "data": {"name": name, "userName": None, "state": state}}


# ---- Per-entity waiter mechanics (AC1, AC2, AC3, AC8) ----


async def test_on_event_updates_state_and_resolves_matching_waiter(
    make_fake_handle: Any,
) -> None:
    """AC1: ``_on_event`` updates cached state and resolves matching waiters."""
    handle = make_fake_handle(lambda _t, _n: _envelope_turnout(2))
    turnout = _make_turnout(handle, state=TurnoutState.CLOSED)

    task = asyncio.create_task(turnout.wait_state(TurnoutState.THROWN))
    await asyncio.sleep(0)
    assert len(turnout._waiters) == 1

    turnout._on_event(TurnoutState.THROWN)

    result = await task
    assert result is TurnoutState.THROWN
    assert turnout.state is TurnoutState.THROWN
    # Waiter removed after the future resolved + finally cleanup.
    assert len(turnout._waiters) == 0


async def test_fanout_resolves_multiple_matching_waiters(make_fake_handle: Any) -> None:
    """AC1: synchronous fanout resolves every matching waiter."""
    handle = make_fake_handle(lambda _t, _n: _envelope_turnout(2))
    turnout = _make_turnout(handle, state=TurnoutState.CLOSED)

    t1 = asyncio.create_task(turnout.wait_state(TurnoutState.THROWN))
    t2 = asyncio.create_task(turnout.wait_state(TurnoutState.THROWN))
    await asyncio.sleep(0)
    assert len(turnout._waiters) == 2

    turnout._on_event(TurnoutState.THROWN)

    r1, r2 = await asyncio.gather(t1, t2)
    assert r1 is TurnoutState.THROWN
    assert r2 is TurnoutState.THROWN


async def test_predicate_mismatch_retains_waiter(make_fake_handle: Any) -> None:
    """AC1: a waiter whose predicate does NOT match stays in the list."""
    handle = make_fake_handle(lambda _t, _n: _envelope_turnout(2))
    turnout = _make_turnout(handle, state=TurnoutState.CLOSED)

    task = asyncio.create_task(turnout.wait_state(TurnoutState.THROWN))
    await asyncio.sleep(0)
    assert len(turnout._waiters) == 1

    # An off-target event should NOT resolve a wait_state(THROWN) waiter.
    turnout._on_event(TurnoutState.UNKNOWN)
    assert not task.done()
    assert len(turnout._waiters) == 1

    # Now the matching event resolves it.
    turnout._on_event(TurnoutState.THROWN)
    assert await task is TurnoutState.THROWN


async def test_wait_state_early_returns_when_already_at_target(
    make_fake_handle: Any,
) -> None:
    """AC2 early-return: no subscription, no waiter, immediate return."""
    handle = make_fake_handle(lambda _t, _n: _envelope_turnout(4))
    turnout = _make_turnout(handle, state=TurnoutState.THROWN)

    result = await turnout.wait_state(TurnoutState.THROWN)
    assert result is TurnoutState.THROWN
    # No subscription was requested.
    assert handle.ensure_calls == []
    # No waiter was registered.
    assert len(turnout._waiters) == 0


async def test_wait_state_auto_subscribes_first_call(make_fake_handle: Any) -> None:
    """AC2 / FR29: first wait_* call invokes ensure_subscription."""
    handle = make_fake_handle(lambda _t, _n: _envelope_turnout(2))
    turnout = _make_turnout(handle, state=TurnoutState.CLOSED)

    task = asyncio.create_task(turnout.wait_state(TurnoutState.THROWN))
    await asyncio.sleep(0)
    turnout._on_event(TurnoutState.THROWN)
    await task

    assert handle.ensure_calls == [("turnout", "NT1")]


async def test_wait_state_repeated_calls_each_invoke_ensure_subscription(
    make_fake_handle: Any,
) -> None:
    """AC2: ``ensure_subscription`` idempotency lives in the registry, not the entity.

    The entity always calls it; the registry de-duplicates.
    """
    handle = make_fake_handle(lambda _t, _n: _envelope_turnout(2))
    turnout = _make_turnout(handle, state=TurnoutState.CLOSED)

    task1 = asyncio.create_task(turnout.wait_state(TurnoutState.THROWN))
    await asyncio.sleep(0)
    turnout._on_event(TurnoutState.THROWN)
    await task1

    task2 = asyncio.create_task(turnout.wait_state(TurnoutState.CLOSED))
    await asyncio.sleep(0)
    turnout._on_event(TurnoutState.CLOSED)
    await task2

    assert handle.ensure_calls == [("turnout", "NT1"), ("turnout", "NT1")]


async def test_wait_state_timeout_raises_wait_timeout_and_cleans_up(
    make_fake_handle: Any,
) -> None:
    """AC2 / AC8: WaitTimeout on timeout; _waiters left empty."""
    handle = make_fake_handle(lambda _t, _n: _envelope_turnout(2))
    turnout = _make_turnout(handle, state=TurnoutState.CLOSED)

    with pytest.raises(WaitTimeout) as excinfo:
        await turnout.wait_state(TurnoutState.THROWN, timeout=0.05)

    assert excinfo.value.context["entity_type"] == "turnout"
    assert excinfo.value.context["name"] == "NT1"
    assert excinfo.value.context["target"] == "THROWN"
    assert len(turnout._waiters) == 0


async def test_wait_state_cancellation_cleans_up_waiter(make_fake_handle: Any) -> None:
    """AC8: caller-cancellation propagates and removes the waiter."""
    handle = make_fake_handle(lambda _t, _n: _envelope_turnout(2))
    turnout = _make_turnout(handle, state=TurnoutState.CLOSED)

    task = asyncio.create_task(turnout.wait_state(TurnoutState.THROWN))
    await asyncio.sleep(0)
    assert len(turnout._waiters) == 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(turnout._waiters) == 0


async def test_wait_change_cancellation_cleans_up_waiter(make_fake_handle: Any) -> None:
    """AC8: caller-cancellation on wait_change propagates and removes the waiter."""
    handle = make_fake_handle(lambda _t, _n: _envelope_turnout(2))
    turnout = _make_turnout(handle, state=TurnoutState.CLOSED)

    task = asyncio.create_task(turnout.wait_change())
    await asyncio.sleep(0)
    assert len(turnout._waiters) == 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(turnout._waiters) == 0


async def test_wait_change_captures_starting_state(make_fake_handle: Any) -> None:
    """AC3: ``wait_change`` captures the starting state at call time.

    An ``_on_event`` with the SAME state must NOT resolve it; a different
    state MUST resolve it.
    """
    handle = make_fake_handle(lambda _t, _n: _envelope_turnout(2))
    turnout = _make_turnout(handle, state=TurnoutState.CLOSED)

    task = asyncio.create_task(turnout.wait_change())
    await asyncio.sleep(0)
    assert len(turnout._waiters) == 1

    # Same as starting → no resolution.
    turnout._on_event(TurnoutState.CLOSED)
    assert not task.done()

    # Different → resolves.
    turnout._on_event(TurnoutState.THROWN)
    result = await task
    assert result is TurnoutState.THROWN


async def test_wait_change_timeout_context_carries_from_state(
    make_fake_handle: Any,
) -> None:
    """AC3 + Open Design Decision #4: wait_change WaitTimeout carries ``from_state``."""
    handle = make_fake_handle(lambda _t, _n: _envelope_turnout(2))
    turnout = _make_turnout(handle, state=TurnoutState.CLOSED)

    with pytest.raises(WaitTimeout) as excinfo:
        await turnout.wait_change(timeout=0.05)

    assert excinfo.value.context["entity_type"] == "turnout"
    assert excinfo.value.context["name"] == "NT1"
    assert excinfo.value.context["from_state"] == "CLOSED"
    # target should NOT be in the context for wait_change.
    assert "target" not in excinfo.value.context


# ---- Sensor convenience wrappers (AC4) ----


async def test_sensor_wait_active_resolves_on_active_event(make_fake_handle: Any) -> None:
    """AC4: ``Sensor.wait_active()`` resolves on SensorState.ACTIVE."""
    handle = make_fake_handle(lambda _t, _n: _envelope_sensor(2))
    sensor = _make_sensor(handle, state=SensorState.INACTIVE)

    task = asyncio.create_task(sensor.wait_active())
    await asyncio.sleep(0)
    sensor._on_event(SensorState.ACTIVE)

    result = await task
    assert result is SensorState.ACTIVE


async def test_sensor_wait_inactive_resolves_on_inactive_event(
    make_fake_handle: Any,
) -> None:
    """AC4: ``Sensor.wait_inactive()`` resolves on SensorState.INACTIVE."""
    handle = make_fake_handle(lambda _t, _n: _envelope_sensor(4))
    sensor = _make_sensor(handle, state=SensorState.ACTIVE)

    task = asyncio.create_task(sensor.wait_inactive())
    await asyncio.sleep(0)
    sensor._on_event(SensorState.INACTIVE)

    result = await task
    assert result is SensorState.INACTIVE


async def test_sensor_wait_active_early_returns_when_already_active(
    make_fake_handle: Any,
) -> None:
    """AC4: convenience wrapper inherits ``wait_state``'s early-return."""
    handle = make_fake_handle(lambda _t, _n: _envelope_sensor(2))
    sensor = _make_sensor(handle, state=SensorState.ACTIVE)

    result = await sensor.wait_active()
    assert result is SensorState.ACTIVE
    assert handle.ensure_calls == []
    assert len(sensor._waiters) == 0


async def test_sensor_wait_active_does_not_resolve_on_inactive_event(
    make_fake_handle: Any,
) -> None:
    """AC9: wait_active predicate is s == ACTIVE; an INACTIVE event must NOT resolve it."""
    handle = make_fake_handle(lambda _t, _n: _envelope_sensor(2))
    sensor = _make_sensor(handle, state=SensorState.UNKNOWN)

    task = asyncio.create_task(sensor.wait_active())
    await asyncio.sleep(0)
    assert len(sensor._waiters) == 1

    # Non-matching event — waiter must stay registered.
    sensor._on_event(SensorState.INACTIVE)
    assert not task.done(), "INACTIVE event must not resolve wait_active()"
    assert len(sensor._waiters) == 1

    # Matching event — waiter must resolve.
    sensor._on_event(SensorState.ACTIVE)
    result = await task
    assert result is SensorState.ACTIVE
    assert len(sensor._waiters) == 0


# ---- Done-future pruning (AC1) ----


async def test_fanout_prunes_done_futures(make_fake_handle: Any) -> None:
    """AC1: futures resolved out-of-band get pruned during the next fanout."""
    handle = make_fake_handle(lambda _t, _n: _envelope_turnout(2))
    turnout = _make_turnout(handle, state=TurnoutState.CLOSED)

    # Register two waiters; resolve the first one externally.
    f1 = turnout._waiters.register(lambda s: s == TurnoutState.THROWN)
    f2 = turnout._waiters.register(lambda s: s == TurnoutState.UNKNOWN)
    assert len(turnout._waiters) == 2

    f1.set_result(TurnoutState.THROWN)  # done before fanout
    # Trigger fanout with a state that matches NEITHER predicate so we
    # can observe pruning of the done future without resolving the other.
    turnout._on_event(TurnoutState.INCONSISTENT)

    # f1 was done → pruned; f2 did not match → retained.
    assert len(turnout._waiters) == 1

    # Clean up f2.
    f2.cancel()


# ---- Cross-entity smoke (AC1, AC2, AC3 across all six waitable entities) ----


async def test_block_wait_state(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {"type": "block", "data": {}})
    block = Block(
        name="IB1",
        user_name=None,
        state=BlockState.UNOCCUPIED,
        value=None,
        _handle=cast(ClientHandle, handle),
    )
    task = asyncio.create_task(block.wait_state(BlockState.OCCUPIED))
    await asyncio.sleep(0)
    block._on_event(BlockState.OCCUPIED)
    assert await task is BlockState.OCCUPIED


async def test_light_wait_change(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {"type": "light", "data": {}})
    light = Light(
        name="IL1",
        user_name=None,
        state=LightState.OFF,
        _handle=cast(ClientHandle, handle),
    )
    task = asyncio.create_task(light.wait_change())
    await asyncio.sleep(0)
    light._on_event(LightState.ON)
    assert await task is LightState.ON


async def test_signal_head_wait_state_on_appearance(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {"type": "signalHead", "data": {}})
    head = SignalHead(
        name="IH1",
        user_name=None,
        appearance=SignalHeadAppearance.RED,
        held=False,
        lit=True,
        _handle=cast(ClientHandle, handle),
    )
    task = asyncio.create_task(head.wait_state(SignalHeadAppearance.GREEN))
    await asyncio.sleep(0)
    head._on_event(SignalHeadAppearance.GREEN)
    assert await task is SignalHeadAppearance.GREEN
    assert head.appearance is SignalHeadAppearance.GREEN


async def test_signal_mast_wait_state_on_aspect(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {"type": "signalMast", "data": {}})
    mast = SignalMast(
        name="IM1",
        user_name=None,
        aspect=SignalMastAspect.STOP,
        held=False,
        lit=True,
        _handle=cast(ClientHandle, handle),
    )
    task = asyncio.create_task(mast.wait_state(SignalMastAspect.CLEAR))
    await asyncio.sleep(0)
    mast._on_event(SignalMastAspect.CLEAR)
    assert await task is SignalMastAspect.CLEAR
    assert mast.aspect is SignalMastAspect.CLEAR


# ---- Client dispatch (AC6, AC7) ----


async def test_client_on_ws_message_dispatches_to_entity(
    patch_http_factory: list[Any],
) -> None:
    """AC6: a synthesized envelope routes through real ``_on_ws_message``
    and lands on the right entity's ``_on_event``."""
    client = Client()
    async with client:
        # Hand-build a Turnout and register it directly in the index
        # (skip discover()).
        turnout = Turnout(
            name="NT1",
            user_name=None,
            state=TurnoutState.CLOSED,
            _handle=cast(ClientHandle, client),
        )
        client._entities[("turnout", "NT1")] = turnout

        task = asyncio.create_task(turnout.wait_state(TurnoutState.THROWN))
        await asyncio.sleep(0)
        await client._on_ws_message(_envelope_turnout(4))  # 4 = THROWN
        result = await task
        assert result is TurnoutState.THROWN
        assert turnout.state is TurnoutState.THROWN


async def test_client_on_ws_message_drops_hello_envelope(
    patch_http_factory: list[Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC6: JMRI ``hello`` envelope drops cleanly (DEBUG log on pyjmri.transport; no raise)."""
    client = Client()
    async with client:
        with caplog.at_level(logging.DEBUG, logger="pyjmri.transport"):
            await client._on_ws_message({"type": "hello", "data": {"JMRI": "5.14"}})
    # Locks the documented "drop + DEBUG log" behavior: a future refactor
    # that silently swallows hello envelopes must update this assertion.
    drops = [
        r
        for r in caplog.records
        if r.levelno == logging.DEBUG and "WS dispatch: drop" in r.getMessage()
    ]
    assert drops, "expected DEBUG 'WS dispatch: drop' log for hello envelope"
    assert any(getattr(r, "type", None) == "hello" for r in drops)


async def test_client_on_ws_message_drops_unknown_type(
    patch_http_factory: list[Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC6: unrecognized types (memory, route, etc.) drop with DEBUG log and no raise."""
    client = Client()
    async with client:
        with caplog.at_level(logging.DEBUG, logger="pyjmri.transport"):
            await client._on_ws_message({"type": "memory", "data": {"name": "IM1"}})
            await client._on_ws_message({"type": "route", "data": {"name": "IR1"}})
            await client._on_ws_message({"type": "somethingelse", "data": {}})
            await client._on_ws_message({"data": {"name": "x"}})  # no type field
    drop_records = [
        r
        for r in caplog.records
        if r.levelno == logging.DEBUG and "WS dispatch: drop" in r.getMessage()
    ]
    dropped_types = {getattr(r, "type", None) for r in drop_records}
    assert "memory" in dropped_types, "expected DEBUG drop log for memory envelope"
    assert "route" in dropped_types, "expected DEBUG drop log for route envelope"


async def test_client_on_ws_message_drops_entity_not_in_index(
    patch_http_factory: list[Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC6: known type whose entity is not in this Client's Layout drops."""
    client = Client()
    async with client:
        # _entities is empty; an envelope for an unknown turnout must drop.
        with caplog.at_level(logging.DEBUG, logger="pyjmri.transport"):
            await client._on_ws_message(_envelope_turnout(2, name="NT-NOT-IN-LAYOUT"))
    debug_records = [
        r
        for r in caplog.records
        if r.levelno == logging.DEBUG
        and "WS dispatch: entity not in current Layout" in r.getMessage()
    ]
    assert debug_records, (
        "expected DEBUG 'WS dispatch: entity not in current Layout' log for unknown turnout"
    )
    assert any(
        getattr(r, "entity_type", None) == "turnout"
        and getattr(r, "system_name", None) == "NT-NOT-IN-LAYOUT"
        for r in debug_records
    )


async def test_client_on_ws_message_swallows_parser_protocol_error(
    patch_http_factory: list[Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC6: malformed JMRI frame logs WARNING on pyjmri.transport and drops; does not raise."""
    client = Client()
    async with client:
        with caplog.at_level(logging.WARNING, logger="pyjmri.transport"):
            # Missing 'state' field → parse_turnout raises JMRIProtocolError.
            await client._on_ws_message({"type": "turnout", "data": {"name": "NT1"}})
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("parse failed" in r.getMessage() for r in warnings)


async def test_client_on_ws_message_swallows_on_event_exception(
    patch_http_factory: list[Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC6: a buggy ``_on_event`` cannot kill the dispatch path."""

    class _BrokenTurnout:
        name = "NT1"

        def _on_event(self, _new_state: Any) -> None:
            raise RuntimeError("boom")

    client = Client()
    async with client:
        client._entities[("turnout", "NT1")] = cast(Any, _BrokenTurnout())
        with caplog.at_level(logging.WARNING, logger="pyjmri.transport"):
            await client._on_ws_message(_envelope_turnout(4))
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("_on_event raised" in r.getMessage() for r in warnings)


async def test_client_ensure_subscription_delegates_to_registry(
    patch_http_factory: list[Any],
) -> None:
    """AC5: ``Client.ensure_subscription`` forwards to ``SubscriptionRegistry.ensure``."""
    client = Client()
    async with client:
        await client.ensure_subscription("turnout", "NT1")
        await client.ensure_subscription("turnout", "NT1")  # idempotent
        await client.ensure_subscription("sensor", "NS1")
        assert client._registry is not None
        # The registry's internal set has both distinct pairs.
        assert client._registry.size == 2


async def test_client_ensure_subscription_raises_when_closed() -> None:
    """AC5: ``Client.ensure_subscription`` raises RuntimeError when not open."""
    client = Client()
    with pytest.raises(RuntimeError, match="Client is not open"):
        await client.ensure_subscription("turnout", "NT1")


# ---- Discover populates _entities (AC7) ----


async def test_discover_populates_entities_index(
    patch_http_factory: list[Any],
) -> None:
    """AC7: after discover(), _entities contains one entry per waitable entity."""
    client = Client()
    async with client:
        # Set up the fake HTTP transport's per-path responses.
        fake_http = patch_http_factory[0]
        responses: dict[str, list[dict[str, Any]] | dict[str, Any]] = {
            "/json/v5/version": {},
            "/json/v5/networkService": [
                {"type": "networkService", "data": {"jmri": "5.14.0"}},
            ],
            "/json/v5/turnout": [_envelope_turnout(2, name="NT1")],
            "/json/v5/sensor": [_envelope_sensor(4, name="NS1")],
            "/json/v5/block": [
                {
                    "type": "block",
                    "data": {"name": "IB1", "userName": None, "state": 2, "value": None},
                }
            ],
            "/json/v5/light": [
                {"type": "light", "data": {"name": "IL1", "userName": None, "state": 2}}
            ],
            "/json/v5/memory": [
                {"type": "memory", "data": {"name": "IM1", "userName": None, "value": None}}
            ],
            "/json/v5/route": [{"type": "route", "data": {"name": "IR1", "userName": None}}],
            "/json/v5/signalHead": [],
            "/json/v5/signalMast": [],
        }

        def _resolve(path: str) -> list[dict[str, Any]] | dict[str, Any]:
            return responses[path]

        fake_http.next_response = _resolve
        layout = await client.discover()

        # Six waitable entity types contribute: turnout, sensor, block, light;
        # signalHead/signalMast are empty in this fixture; memory/route are excluded.
        assert ("turnout", "NT1") in client._entities
        assert ("sensor", "NS1") in client._entities
        assert ("block", "IB1") in client._entities
        assert ("light", "IL1") in client._entities
        # Memory and Route entities are deliberately NOT in the index.
        assert ("memory", "IM1") not in client._entities
        assert ("route", "IR1") not in client._entities

        # The same instance is in the Layout and in _entities.
        assert client._entities[("turnout", "NT1")] is layout.turnouts["NT1"]


async def test_aexit_clears_entities_index(patch_http_factory: list[Any]) -> None:
    """AC7: __aexit__ resets _entities to {}."""
    client = Client()
    async with client:
        client._entities[("turnout", "NT1")] = cast(
            Any,
            Turnout(
                name="NT1",
                user_name=None,
                state=TurnoutState.UNKNOWN,
                _handle=cast(ClientHandle, client),
            ),
        )
        assert client._entities
    assert client._entities == {}
