"""Unit tests for :class:`pyjmri.Turnout`."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from pyjmri import (
    JMRIProtocolError,
    LayoutEntityNotControllable,
    Turnout,
    TurnoutState,
)
from pyjmri._protocols import ClientHandle


def _envelope(state: int, *, name: str = "NT400", user_name: str | None = "Foo") -> dict[str, Any]:
    return {
        "type": "turnout",
        "data": {"name": name, "userName": user_name, "state": state},
    }


async def test_get_state_round_trips_synthetic_envelope(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    turnout = Turnout(
        name="NT400",
        user_name="Foo",
        state=TurnoutState.UNKNOWN,
        _handle=cast(ClientHandle, handle),
    )

    result = await turnout.get_state()

    assert result is TurnoutState.CLOSED
    assert turnout.state is TurnoutState.CLOSED


async def test_get_state_unknown_is_never_coerced(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(1))
    turnout = Turnout(
        name="NT400",
        user_name=None,
        state=TurnoutState.CLOSED,
        _handle=cast(ClientHandle, handle),
    )

    result = await turnout.get_state()

    assert result is TurnoutState.UNKNOWN
    assert turnout.state is TurnoutState.UNKNOWN


async def test_get_state_zero_state_maps_to_unknown(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(0))
    turnout = Turnout(
        name="NT400",
        user_name=None,
        state=TurnoutState.CLOSED,
        _handle=cast(ClientHandle, handle),
    )

    result = await turnout.get_state()

    assert result is TurnoutState.UNKNOWN


async def test_get_state_thrown_and_inconsistent(make_fake_handle: Any) -> None:
    handle_thrown = make_fake_handle(lambda _t, _n: _envelope(4))
    turnout = Turnout(
        name="NT1",
        user_name=None,
        state=TurnoutState.UNKNOWN,
        _handle=cast(ClientHandle, handle_thrown),
    )
    assert await turnout.get_state() is TurnoutState.THROWN

    handle_inconsistent = make_fake_handle(lambda _t, _n: _envelope(8))
    turnout2 = Turnout(
        name="NT2",
        user_name=None,
        state=TurnoutState.UNKNOWN,
        _handle=cast(ClientHandle, handle_inconsistent),
    )
    assert await turnout2.get_state() is TurnoutState.INCONSISTENT


async def test_get_state_calls_handle_with_correct_args(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    turnout = Turnout(
        name="NT400",
        user_name=None,
        state=TurnoutState.UNKNOWN,
        _handle=cast(ClientHandle, handle),
    )

    await turnout.get_state()

    assert handle.calls == [("turnout", "NT400")]


async def test_get_state_propagates_protocol_error(make_fake_handle: Any) -> None:
    handle = make_fake_handle(
        lambda _t, _n: {"type": "turnout", "data": {"name": "NT1", "userName": None}}
    )
    turnout = Turnout(
        name="NT1",
        user_name=None,
        state=TurnoutState.UNKNOWN,
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(JMRIProtocolError):
        await turnout.get_state()


async def test_construct_turnout_keeps_user_name_immutable(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2, user_name="Different Name From Parser"))
    turnout = Turnout(
        name="NT400",
        user_name="Constructor Name",
        state=TurnoutState.UNKNOWN,
        _handle=cast(ClientHandle, handle),
    )

    await turnout.get_state()

    assert turnout.user_name == "Constructor Name"


# --- Story 4.1: Turnout.set_state / throw / close ---


async def test_throw_sends_thrown_state_code(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    turnout = Turnout(
        name="NT400",
        user_name=None,
        state=TurnoutState.CLOSED,
        _handle=cast(ClientHandle, handle),
    )

    await turnout.throw()

    assert handle.command_calls == [("turnout", "NT400", {"state": 4})]


async def test_close_sends_closed_state_code(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    turnout = Turnout(
        name="NT400",
        user_name=None,
        state=TurnoutState.THROWN,
        _handle=cast(ClientHandle, handle),
    )

    await turnout.close()

    assert handle.command_calls == [("turnout", "NT400", {"state": 2})]


async def test_set_state_thrown(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    turnout = Turnout(
        name="NT400",
        user_name=None,
        state=TurnoutState.CLOSED,
        _handle=cast(ClientHandle, handle),
    )

    await turnout.set_state(TurnoutState.THROWN)

    assert handle.command_calls == [("turnout", "NT400", {"state": 4})]


async def test_set_state_does_not_optimistically_update_cache(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    turnout = Turnout(
        name="NT400",
        user_name=None,
        state=TurnoutState.CLOSED,
        _handle=cast(ClientHandle, handle),
    )

    await turnout.throw()

    # FR22: HTTP ack does not prove the WS state event arrived; the
    # cached state stays as last-observed until _on_event or get_state.
    assert turnout.state is TurnoutState.CLOSED


async def test_set_state_unknown_raises_value_error(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    turnout = Turnout(
        name="NT400",
        user_name=None,
        state=TurnoutState.CLOSED,
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(ValueError):
        await turnout.set_state(TurnoutState.UNKNOWN)
    assert handle.command_calls == []


async def test_set_state_inconsistent_raises_value_error(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    turnout = Turnout(
        name="NT400",
        user_name=None,
        state=TurnoutState.CLOSED,
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(ValueError):
        await turnout.set_state(TurnoutState.INCONSISTENT)
    assert handle.command_calls == []


async def test_throw_propagates_layout_entity_not_controllable(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    handle.command_raises = LayoutEntityNotControllable(
        entity_type="turnout",
        name="NT400",
        jmri_message="locked",
        status=409,
    )
    turnout = Turnout(
        name="NT400",
        user_name=None,
        state=TurnoutState.CLOSED,
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(LayoutEntityNotControllable):
        await turnout.throw()


# --- Story 4.2: wait_for_jmri_state=True ---


def _make_wait_turnout(make_fake_handle: Any) -> tuple[Turnout, Any]:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    turnout = Turnout(
        name="NT400",
        user_name=None,
        state=TurnoutState.CLOSED,
        _handle=cast(ClientHandle, handle),
    )
    return turnout, handle


async def test_throw_wait_default_false_takes_optimistic_path(make_fake_handle: Any) -> None:
    turnout, handle = _make_wait_turnout(make_fake_handle)
    await turnout.throw()
    assert handle.ensure_calls == []
    assert handle.command_calls == [("turnout", "NT400", {"state": 4})]
    assert len(turnout._waiters) == 0


async def test_throw_wait_true_registers_waiter_before_command(make_fake_handle: Any) -> None:
    turnout, handle = _make_wait_turnout(make_fake_handle)
    handle.command_gate = asyncio.Event()

    task = asyncio.create_task(turnout.throw(wait_for_jmri_state=True))
    await asyncio.sleep(0)  # let task reach the gate
    await asyncio.sleep(0)

    # Pre-register-wait ordering: ensure done, waiter registered, command NOT yet sent.
    assert handle.ensure_calls == [("turnout", "NT400")]
    assert len(turnout._waiters) == 1
    assert handle.command_calls == []

    # Release the command and fire the WS event to resolve the waiter.
    handle.command_gate.set()
    await asyncio.sleep(0)
    turnout._on_event(TurnoutState.THROWN)
    await task

    assert handle.command_calls == [("turnout", "NT400", {"state": 4})]
    assert len(turnout._waiters) == 0


async def test_throw_wait_true_resolves_on_ws_event_not_http_response(
    make_fake_handle: Any,
) -> None:
    """The await blocks past the HTTP ack and resolves only on the WS event."""
    turnout, handle = _make_wait_turnout(make_fake_handle)

    task = asyncio.create_task(turnout.throw(wait_for_jmri_state=True))
    # Yield enough for ensure → register → command-record to complete.
    for _ in range(5):
        await asyncio.sleep(0)

    assert handle.command_calls == [("turnout", "NT400", {"state": 4})]
    assert not task.done(), "task must still be pending awaiting the WS event"
    assert len(turnout._waiters) == 1

    turnout._on_event(TurnoutState.THROWN)
    await task
    assert len(turnout._waiters) == 0


async def test_throw_wait_true_event_during_pre_command_window_resolves_correctly(
    make_fake_handle: Any,
) -> None:
    """Race AC6: state event arrives between ensure and command. Waiter resolves."""
    turnout, handle = _make_wait_turnout(make_fake_handle)
    handle.command_gate = asyncio.Event()

    task = asyncio.create_task(turnout.throw(wait_for_jmri_state=True))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # Waiter is registered; command is gated. Fire the event NOW (pre-command window).
    assert len(turnout._waiters) == 1
    assert handle.command_calls == []
    turnout._on_event(TurnoutState.THROWN)
    # Waiter list should be drained by fanout.
    assert len(turnout._waiters) == 0

    # Release the command. The task should complete because the future is already done.
    handle.command_gate.set()
    await task
    assert handle.command_calls == [("turnout", "NT400", {"state": 4})]


async def test_throw_wait_true_cancellation_cleans_up_waiter(make_fake_handle: Any) -> None:
    """AC4: caller-side cancellation removes the waiter, no orphan."""
    turnout, handle = _make_wait_turnout(make_fake_handle)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(turnout.throw(wait_for_jmri_state=True), timeout=0.05)
    await asyncio.sleep(0)  # let asyncio.shield background task complete before asserting

    # Waiter removed, no orphan future.
    assert len(turnout._waiters) == 0
    # The HTTP command was still recorded (shielded — it completed in the background).
    assert handle.command_calls == [("turnout", "NT400", {"state": 4})]


async def test_throw_wait_true_command_error_cleans_up_waiter(make_fake_handle: Any) -> None:
    """A command error propagates AND removes the waiter."""
    turnout, handle = _make_wait_turnout(make_fake_handle)
    handle.command_raises = LayoutEntityNotControllable(
        entity_type="turnout",
        name="NT400",
        jmri_message="locked",
        status=409,
    )

    with pytest.raises(LayoutEntityNotControllable):
        await turnout.throw(wait_for_jmri_state=True)

    assert len(turnout._waiters) == 0
    # ensure_subscription still ran (it's the first step).
    assert handle.ensure_calls == [("turnout", "NT400")]
    # command was sent (recorded before raising).
    assert handle.command_calls == [("turnout", "NT400", {"state": 4})]


async def test_set_state_wait_true_invalid_state_raises_before_subscribe(
    make_fake_handle: Any,
) -> None:
    """Validation happens before any I/O, even in wait-mode."""
    turnout, handle = _make_wait_turnout(make_fake_handle)

    with pytest.raises(ValueError):
        await turnout.set_state(TurnoutState.UNKNOWN, wait_for_jmri_state=True)

    assert handle.ensure_calls == []
    assert handle.command_calls == []
    assert len(turnout._waiters) == 0
