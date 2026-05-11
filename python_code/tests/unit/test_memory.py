"""Unit tests for :class:`pyjmri.Memory`."""

from __future__ import annotations

from typing import Any, cast

import pytest

from pyjmri import JMRIProtocolError, Memory
from pyjmri._protocols import ClientHandle


def _envelope(value: str | None, *, name: str = "IM1") -> dict[str, Any]:
    return {
        "type": "memory",
        "data": {"name": name, "userName": None, "value": value},
    }


async def test_get_value_returns_string(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope("hello"))
    memory = Memory(
        name="IM1",
        user_name=None,
        value=None,
        _handle=cast(ClientHandle, handle),
    )

    result = await memory.get_value()

    assert result == "hello"
    assert memory.value == "hello"


async def test_get_value_returns_none(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(None))
    memory = Memory(
        name="IM1",
        user_name=None,
        value="stale",
        _handle=cast(ClientHandle, handle),
    )

    result = await memory.get_value()

    assert result is None
    assert memory.value is None


async def test_get_value_handles_missing_key(make_fake_handle: Any) -> None:
    handle = make_fake_handle(
        lambda _t, _n: {"type": "memory", "data": {"name": "IM1", "userName": None}}
    )
    memory = Memory(
        name="IM1",
        user_name=None,
        value="stale",
        _handle=cast(ClientHandle, handle),
    )

    result = await memory.get_value()

    assert result is None
    assert memory.value is None


async def test_get_value_propagates_protocol_error(make_fake_handle: Any) -> None:
    handle = make_fake_handle(
        lambda _t, _n: {"type": "memory", "data": {"userName": None}}  # missing "name"
    )
    memory = Memory(
        name="IM1",
        user_name=None,
        value=None,
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(JMRIProtocolError):
        await memory.get_value()


async def test_get_value_calls_handle_with_correct_args(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope("x"))
    memory = Memory(
        name="IM42",
        user_name=None,
        value=None,
        _handle=cast(ClientHandle, handle),
    )

    await memory.get_value()

    assert handle.calls == [("memory", "IM42")]
