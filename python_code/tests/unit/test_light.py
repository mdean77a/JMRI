"""Unit tests for :class:`pyjmri.Light`."""

from __future__ import annotations

from typing import Any, cast

import pytest

from pyjmri import JMRIProtocolError, Light, LightState
from pyjmri._protocols import ClientHandle


def _envelope(state: int, *, name: str = "IL1", user_name: str | None = None) -> dict[str, Any]:
    return {
        "type": "light",
        "data": {"name": name, "userName": user_name, "state": state},
    }


async def test_get_state_round_trips_on(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    light = Light(
        name="IL1",
        user_name=None,
        state=LightState.UNKNOWN,
        _handle=cast(ClientHandle, handle),
    )

    result = await light.get_state()

    assert result is LightState.ON
    assert light.state is LightState.ON


async def test_get_state_unknown_is_never_coerced(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(1))
    light = Light(
        name="IL1",
        user_name=None,
        state=LightState.ON,
        _handle=cast(ClientHandle, handle),
    )
    assert await light.get_state() is LightState.UNKNOWN


async def test_get_state_zero_state_maps_to_unknown(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(0))
    light = Light(
        name="IL1",
        user_name=None,
        state=LightState.ON,
        _handle=cast(ClientHandle, handle),
    )
    assert await light.get_state() is LightState.UNKNOWN


async def test_get_state_off_and_inconsistent(make_fake_handle: Any) -> None:
    handle_off = make_fake_handle(lambda _t, _n: _envelope(4))
    light = Light(
        name="IL1",
        user_name=None,
        state=LightState.UNKNOWN,
        _handle=cast(ClientHandle, handle_off),
    )
    assert await light.get_state() is LightState.OFF

    handle_inc = make_fake_handle(lambda _t, _n: _envelope(8))
    light2 = Light(
        name="IL2",
        user_name=None,
        state=LightState.UNKNOWN,
        _handle=cast(ClientHandle, handle_inc),
    )
    assert await light2.get_state() is LightState.INCONSISTENT


async def test_get_state_calls_handle_with_correct_args(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    light = Light(
        name="IL42",
        user_name=None,
        state=LightState.UNKNOWN,
        _handle=cast(ClientHandle, handle),
    )

    await light.get_state()

    assert handle.calls == [("light", "IL42")]


async def test_get_state_propagates_protocol_error(make_fake_handle: Any) -> None:
    handle = make_fake_handle(
        lambda _t, _n: {"type": "light", "data": {"name": "IL1", "userName": None}}
    )
    light = Light(
        name="IL1",
        user_name=None,
        state=LightState.UNKNOWN,
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(JMRIProtocolError):
        await light.get_state()
