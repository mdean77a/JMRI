"""Unit tests for :class:`pyjmri.Block`."""

from __future__ import annotations

from typing import Any, cast

import pytest

from pyjmri import Block, BlockState, JMRIProtocolError
from pyjmri._protocols import ClientHandle


def _envelope(
    state: int,
    *,
    name: str = "IB:1",
    user_name: str | None = "Block 1",
    value: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "block",
        "data": {
            "name": name,
            "userName": user_name,
            "state": state,
            "value": value,
        },
    }


async def test_get_state_round_trips_occupied(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2, value="Train 99"))
    block = Block(
        name="IB:1",
        user_name="Block 1",
        state=BlockState.UNKNOWN,
        value=None,
        _handle=cast(ClientHandle, handle),
    )

    result = await block.get_state()

    assert result is BlockState.OCCUPIED
    assert block.state is BlockState.OCCUPIED
    assert block.value == "Train 99"


async def test_get_state_unknown_is_never_coerced(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(1))
    block = Block(
        name="IB:1",
        user_name=None,
        state=BlockState.OCCUPIED,
        value=None,
        _handle=cast(ClientHandle, handle),
    )

    assert await block.get_state() is BlockState.UNKNOWN


async def test_get_state_undetected_is_distinct(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(0))
    block = Block(
        name="IB:1",
        user_name=None,
        state=BlockState.UNKNOWN,
        value=None,
        _handle=cast(ClientHandle, handle),
    )

    result = await block.get_state()

    assert result is BlockState.UNDETECTED
    assert result is not BlockState.UNKNOWN


async def test_get_state_unoccupied_and_inconsistent(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(4))
    block = Block(
        name="IB:1",
        user_name=None,
        state=BlockState.UNKNOWN,
        value=None,
        _handle=cast(ClientHandle, handle),
    )
    assert await block.get_state() is BlockState.UNOCCUPIED

    handle_inc = make_fake_handle(lambda _t, _n: _envelope(8))
    block2 = Block(
        name="IB:2",
        user_name=None,
        state=BlockState.UNKNOWN,
        value=None,
        _handle=cast(ClientHandle, handle_inc),
    )
    assert await block2.get_state() is BlockState.INCONSISTENT


async def test_get_state_value_may_be_none(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(4, value=None))
    block = Block(
        name="IB:1",
        user_name=None,
        state=BlockState.UNKNOWN,
        value="stale",
        _handle=cast(ClientHandle, handle),
    )

    await block.get_state()

    assert block.value is None


async def test_get_state_calls_handle_with_correct_args(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(2))
    block = Block(
        name="IB:99",
        user_name=None,
        state=BlockState.UNKNOWN,
        value=None,
        _handle=cast(ClientHandle, handle),
    )

    await block.get_state()

    assert handle.calls == [("block", "IB:99")]


async def test_get_state_propagates_protocol_error(make_fake_handle: Any) -> None:
    handle = make_fake_handle(
        lambda _t, _n: {"type": "block", "data": {"name": "IB:1", "userName": None}}
    )
    block = Block(
        name="IB:1",
        user_name=None,
        state=BlockState.UNKNOWN,
        value=None,
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(JMRIProtocolError):
        await block.get_state()
