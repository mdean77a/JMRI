"""Unit tests for :class:`pyjmri.Memory`."""

from __future__ import annotations

from typing import Any, cast

import pytest

from pyjmri import JMRIProtocolError, Memory
from pyjmri._protocols import ClientHandle
from pyjmri.exceptions import LayoutEntityNotControllable


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


# --- Story 4.1: Memory.set_value ---


async def test_set_value_sends_value_payload(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope("stored"))
    memory = Memory(
        name="IM42",
        user_name=None,
        value="old",
        _handle=cast(ClientHandle, handle),
    )

    await memory.set_value("hello")

    assert handle.command_calls == [("memory", "IM42", {"value": "hello"})]


async def test_set_value_does_not_optimistically_update_cache(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope("stored"))
    memory = Memory(
        name="IM42",
        user_name=None,
        value="old",
        _handle=cast(ClientHandle, handle),
    )

    await memory.set_value("hello")

    # FR22: cached value remains last-observed until get_value() refreshes
    assert memory.value == "old"


async def test_set_value_accepts_empty_string(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope(""))
    memory = Memory(
        name="IM42",
        user_name=None,
        value="old",
        _handle=cast(ClientHandle, handle),
    )

    await memory.set_value("")

    assert handle.command_calls == [("memory", "IM42", {"value": ""})]


@pytest.mark.anyio
async def test_set_value_propagates_layout_entity_not_controllable(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _envelope("stored"))
    handle.command_raises = LayoutEntityNotControllable(
        entity_type="memory",
        name="IM42",
        jmri_message="locked",
        status=409,
    )
    memory = Memory(
        name="IM42",
        user_name=None,
        value="old",
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(LayoutEntityNotControllable):
        await memory.set_value("new")


async def test_set_value_does_not_accept_wait_for_jmri_state_kwarg(
    make_fake_handle: Any,
) -> None:
    """Story 4.2 AC3: Memory has no _on_event plumbing, so the kwarg is not in v1."""
    handle = make_fake_handle(lambda _t, _n: _envelope("stored"))
    memory = Memory(
        name="IM42",
        user_name=None,
        value="old",
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(TypeError):
        # Bypass mypy --strict at call site so we exercise the runtime signature guard.
        await memory.set_value("new", wait_for_jmri_state=True)  # type: ignore[call-arg]
