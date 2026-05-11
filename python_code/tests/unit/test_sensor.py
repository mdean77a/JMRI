"""Unit tests for :class:`pyjmri.Sensor`."""

from __future__ import annotations

from typing import Any, cast

import pytest

from pyjmri import JMRIProtocolError, Sensor, SensorState
from pyjmri._protocols import ClientHandle


def _envelope(state: int, *, name: str = "NS401", user_name: str | None = None) -> dict[str, Any]:
    return {
        "type": "sensor",
        "data": {"name": name, "userName": user_name, "state": state},
    }


async def test_get_state_round_trips_active(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    sensor = Sensor(
        name="NS401",
        user_name=None,
        state=SensorState.UNKNOWN,
        _handle=cast(ClientHandle, handle),
    )

    result = await sensor.get_state()

    assert result is SensorState.ACTIVE
    assert sensor.state is SensorState.ACTIVE


async def test_get_state_unknown_is_never_coerced(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(1))
    sensor = Sensor(
        name="NS1",
        user_name=None,
        state=SensorState.ACTIVE,
        _handle=cast(ClientHandle, handle),
    )
    assert await sensor.get_state() is SensorState.UNKNOWN


async def test_get_state_zero_state_maps_to_unknown(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(0))
    sensor = Sensor(
        name="NS1",
        user_name=None,
        state=SensorState.ACTIVE,
        _handle=cast(ClientHandle, handle),
    )
    assert await sensor.get_state() is SensorState.UNKNOWN


async def test_get_state_inactive_and_inconsistent(make_fake_handle: Any) -> None:
    handle_inactive = make_fake_handle(lambda _t, _n: _envelope(4))
    sensor = Sensor(
        name="NS1",
        user_name=None,
        state=SensorState.UNKNOWN,
        _handle=cast(ClientHandle, handle_inactive),
    )
    assert await sensor.get_state() is SensorState.INACTIVE

    handle_inc = make_fake_handle(lambda _t, _n: _envelope(8))
    sensor2 = Sensor(
        name="NS2",
        user_name=None,
        state=SensorState.UNKNOWN,
        _handle=cast(ClientHandle, handle_inc),
    )
    assert await sensor2.get_state() is SensorState.INCONSISTENT


async def test_get_state_calls_handle_with_correct_args(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    sensor = Sensor(
        name="NS401",
        user_name=None,
        state=SensorState.UNKNOWN,
        _handle=cast(ClientHandle, handle),
    )

    await sensor.get_state()

    assert handle.calls == [("sensor", "NS401")]


async def test_get_state_propagates_protocol_error(make_fake_handle: Any) -> None:
    handle = make_fake_handle(
        lambda _t, _n: {"type": "sensor", "data": {"name": "NS1", "userName": None}}
    )
    sensor = Sensor(
        name="NS1",
        user_name=None,
        state=SensorState.UNKNOWN,
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(JMRIProtocolError):
        await sensor.get_state()
