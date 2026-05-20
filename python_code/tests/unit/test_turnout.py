"""Unit tests for :class:`pyjmri.Turnout`."""

from __future__ import annotations

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
