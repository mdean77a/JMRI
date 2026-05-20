"""Unit tests for :class:`pyjmri.Light`."""

from __future__ import annotations

from typing import Any, cast

import pytest

from pyjmri import JMRIProtocolError, Light, LightState
from pyjmri._protocols import ClientHandle
from pyjmri.exceptions import LayoutEntityNotControllable


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


# --- Story 4.1: Light.set_state / on / off ---


async def test_on_sends_on_state_code(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    light = Light(
        name="IL1",
        user_name=None,
        state=LightState.OFF,
        _handle=cast(ClientHandle, handle),
    )

    await light.on()

    assert handle.command_calls == [("light", "IL1", {"state": 2})]


async def test_off_sends_off_state_code(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    light = Light(
        name="IL1",
        user_name=None,
        state=LightState.ON,
        _handle=cast(ClientHandle, handle),
    )

    await light.off()

    assert handle.command_calls == [("light", "IL1", {"state": 4})]


async def test_set_state_does_not_optimistically_update_cache(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    light = Light(
        name="IL1",
        user_name=None,
        state=LightState.OFF,
        _handle=cast(ClientHandle, handle),
    )

    await light.on()

    assert light.state is LightState.OFF


async def test_set_state_unknown_raises_value_error(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    light = Light(
        name="IL1",
        user_name=None,
        state=LightState.OFF,
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(ValueError):
        await light.set_state(LightState.UNKNOWN)
    assert handle.command_calls == []


async def test_set_state_inconsistent_raises_value_error(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    light = Light(
        name="IL1",
        user_name=None,
        state=LightState.OFF,
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(ValueError):
        await light.set_state(LightState.INCONSISTENT)
    assert handle.command_calls == []


@pytest.mark.anyio
async def test_on_propagates_layout_entity_not_controllable(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(4))
    handle.command_raises = LayoutEntityNotControllable(
        entity_type="light",
        name="IL1",
        jmri_message="locked",
        status=409,
    )
    light = Light(
        name="IL1",
        user_name=None,
        state=LightState.OFF,
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(LayoutEntityNotControllable):
        await light.on()
