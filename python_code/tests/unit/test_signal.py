"""Unit tests for :class:`pyjmri.SignalHead` and :class:`pyjmri.SignalMast`."""

from __future__ import annotations

from typing import Any, cast

import pytest

from pyjmri import (
    JMRIProtocolError,
    SignalHead,
    SignalHeadAppearance,
    SignalMast,
    SignalMastAspect,
)
from pyjmri._protocols import ClientHandle


def _head_envelope(
    appearance: int,
    *,
    name: str = "IH1",
    user_name: str | None = None,
    held: bool = False,
    lit: bool = True,
) -> dict[str, Any]:
    return {
        "type": "signalHead",
        "data": {
            "name": name,
            "userName": user_name,
            "appearance": appearance,
            "held": held,
            "lit": lit,
        },
    }


def _mast_envelope(
    aspect: str,
    *,
    name: str = "IF$shsm:basic:one-low($0001)",
    user_name: str | None = None,
    held: bool = False,
    lit: bool = True,
) -> dict[str, Any]:
    return {
        "type": "signalMast",
        "data": {
            "name": name,
            "userName": user_name,
            "aspect": aspect,
            "held": held,
            "lit": lit,
        },
    }


# --- SignalHead ---


async def test_signal_head_get_state_round_trips_red(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _head_envelope(1))
    head = SignalHead(
        name="IH1",
        user_name=None,
        appearance=SignalHeadAppearance.DARK,
        held=False,
        lit=True,
        _handle=cast(ClientHandle, handle),
    )

    result = await head.get_state()

    assert result is SignalHeadAppearance.RED
    assert head.appearance is SignalHeadAppearance.RED


async def test_signal_head_get_state_updates_held_and_lit(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _head_envelope(0, held=True, lit=False))
    head = SignalHead(
        name="IH1",
        user_name=None,
        appearance=SignalHeadAppearance.GREEN,
        held=False,
        lit=True,
        _handle=cast(ClientHandle, handle),
    )

    await head.get_state()

    assert head.held is True
    assert head.lit is False


async def test_signal_head_get_state_calls_handle_with_correct_args(
    make_fake_handle: Any,
) -> None:
    handle = make_fake_handle(lambda _t, _n: _head_envelope(16))
    head = SignalHead(
        name="IH9",
        user_name=None,
        appearance=SignalHeadAppearance.DARK,
        held=False,
        lit=True,
        _handle=cast(ClientHandle, handle),
    )

    await head.get_state()

    assert handle.calls == [("signalHead", "IH9")]


async def test_signal_head_get_state_propagates_protocol_error(
    make_fake_handle: Any,
) -> None:
    handle = make_fake_handle(lambda _t, _n: {"type": "signalHead", "data": {"name": "IH1"}})
    head = SignalHead(
        name="IH1",
        user_name=None,
        appearance=SignalHeadAppearance.DARK,
        held=False,
        lit=True,
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(JMRIProtocolError):
        await head.get_state()


# --- SignalMast ---


async def test_signal_mast_get_state_round_trips_clear(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _mast_envelope("Clear"))
    mast = SignalMast(
        name="IF$shsm:basic:one-low($0001)",
        user_name=None,
        aspect=SignalMastAspect.UNKNOWN,
        held=False,
        lit=True,
        _handle=cast(ClientHandle, handle),
    )

    result = await mast.get_state()

    assert result is SignalMastAspect.CLEAR
    assert mast.aspect is SignalMastAspect.CLEAR


async def test_signal_mast_get_state_updates_held_and_lit(
    make_fake_handle: Any,
) -> None:
    handle = make_fake_handle(lambda _t, _n: _mast_envelope("Stop", held=True, lit=False))
    mast = SignalMast(
        name="IF$shsm:basic:one-low($0001)",
        user_name=None,
        aspect=SignalMastAspect.UNKNOWN,
        held=False,
        lit=True,
        _handle=cast(ClientHandle, handle),
    )

    await mast.get_state()

    assert mast.held is True
    assert mast.lit is False


async def test_signal_mast_non_basic_aspect_raises(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: _mast_envelope("Limited Approach Slow"))
    mast = SignalMast(
        name="IF$shsm:basic:one-low($0001)",
        user_name=None,
        aspect=SignalMastAspect.UNKNOWN,
        held=False,
        lit=True,
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(JMRIProtocolError):
        await mast.get_state()


async def test_signal_mast_get_state_calls_handle_with_correct_args(
    make_fake_handle: Any,
) -> None:
    handle = make_fake_handle(lambda _t, _n: _mast_envelope("Stop"))
    mast = SignalMast(
        name="IF$shsm:basic:one-low($0042)",
        user_name=None,
        aspect=SignalMastAspect.UNKNOWN,
        held=False,
        lit=True,
        _handle=cast(ClientHandle, handle),
    )

    await mast.get_state()

    assert handle.calls == [("signalMast", "IF$shsm:basic:one-low($0042)")]


async def test_signal_mast_get_state_propagates_protocol_error(
    make_fake_handle: Any,
) -> None:
    handle = make_fake_handle(
        lambda _t, _n: {
            "type": "signalMast",
            "data": {"name": "IF$shsm:basic:one-low($0001)", "userName": None, "aspect": "Stop"},
            # missing "held" and "lit"
        }
    )
    mast = SignalMast(
        name="IF$shsm:basic:one-low($0001)",
        user_name=None,
        aspect=SignalMastAspect.UNKNOWN,
        held=False,
        lit=True,
        _handle=cast(ClientHandle, handle),
    )

    with pytest.raises(JMRIProtocolError):
        await mast.get_state()
