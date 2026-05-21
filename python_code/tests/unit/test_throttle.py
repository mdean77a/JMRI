"""Unit tests for :class:`pyjmri.Throttle` lifecycle (Story 5.1)."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from pyjmri import (
    JMRIConnectionError,
    Layout,
    Throttle,
    ThrottleAcquireFailed,
    ThrottleReleased,
)
from pyjmri._protocols import ClientHandle


def _make_throttle(handle: Any, *, dcc_address: int = 5327, long: bool = True) -> Throttle:
    return Throttle(cast(ClientHandle, handle), dcc_address=dcc_address, long=long)


# AC9 + AC12 #1
async def test_aenter_acquires_then_spawns_keepalive(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        assert handle.throttle_acquire_calls == [(5327, True)]
        assert len(handle.spawned_coros) == 1
        assert t is throttle
        assert t._throttle_id == "pyjmri-5327-fake"


# AC2 + AC12 #2
async def test_aenter_raises_throttle_acquire_failed_when_jmri_rejects(
    make_fake_handle: Any,
) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    handle.throttle_acquire_raises = ThrottleAcquireFailed(
        "JMRI rejected", jmri_message="The address 99,999 is invalid.", code=400
    )
    throttle = _make_throttle(handle, dcc_address=99999)
    with pytest.raises(ThrottleAcquireFailed):
        async with throttle:
            pass  # pragma: no cover — acquire raises before body
    # No keep-alive spawned, no release attempted.
    assert handle.spawned_coros == []
    assert handle.throttle_release_calls == []


# AC4 + AC12 #3
async def test_release_cancels_keepalive_and_sends_release(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        keepalive_task = handle.spawned_coros[0]
        await t.release()
        # Yield so the cancelled task can settle.
        await asyncio.sleep(0)
        assert keepalive_task.done()
        assert handle.throttle_release_calls == ["pyjmri-5327-fake"]
        assert t._released is True


# AC4 + AC12 #4
async def test_aexit_releases_on_clean_exit(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle:
        keepalive_task = handle.spawned_coros[0]
    await asyncio.sleep(0)
    assert handle.throttle_release_calls == ["pyjmri-5327-fake"]
    assert keepalive_task.done()
    assert throttle._released is True


# AC6 + AC12 #5
async def test_aexit_releases_on_exception_in_body(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})

    class _Boom(Exception):
        pass

    throttle = _make_throttle(handle)
    with pytest.raises(_Boom):
        async with throttle:
            keepalive_task = handle.spawned_coros[0]
            raise _Boom("body raised")
    await asyncio.sleep(0)
    assert keepalive_task.done()
    assert handle.throttle_release_calls == ["pyjmri-5327-fake"]
    assert throttle._released is True


# AC6 + AC12 #6
async def test_aexit_swallows_release_failure_when_body_raised(
    make_fake_handle: Any, caplog: pytest.LogCaptureFixture
) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    handle.throttle_release_raises = JMRIConnectionError(host="localhost", port=12080)

    class _Boom(Exception):
        pass

    throttle = _make_throttle(handle)
    caplog.set_level("WARNING", logger="pyjmri.throttle")
    with pytest.raises(_Boom):
        async with throttle:
            raise _Boom("body raised")
    # Release was attempted, but the failure was swallowed in favor of _Boom.
    assert handle.throttle_release_calls == ["pyjmri-5327-fake"]
    assert throttle._released is True
    assert any("release failed" in rec.message for rec in caplog.records)


# AC5 + AC12 #7
async def test_post_release_reacquire_raises_throttle_released(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        await t.release()
    pre_acquire_count = len(handle.throttle_acquire_calls)
    with pytest.raises(ThrottleReleased):
        async with throttle:
            pass  # pragma: no cover
    # No additional acquire was attempted.
    assert len(handle.throttle_acquire_calls) == pre_acquire_count


# AC4 + AC12 #8
async def test_release_is_idempotent(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        await t.release()
        # Second release: should be a no-op, no error.
        await t.release()
    # Only one WS release went out.
    assert handle.throttle_release_calls == ["pyjmri-5327-fake"]


# AC3 + AC12 #9 — v1 keep-alive body is a no-op stub
async def test_keepalive_body_is_no_op_and_does_not_call_heartbeat(
    make_fake_handle: Any,
) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle:
        keepalive_task = handle.spawned_coros[0]
        # Give the loop time to settle and any (hypothetical) heartbeat
        # iterations a chance to fire. Interval is 0.01 s in the fake;
        # this would be 5 iterations if the body were active.
        await asyncio.sleep(0.05)
        assert handle.throttle_heartbeat_calls == []
        # Task is still alive (waiting on the inner asyncio.Event).
        assert not keepalive_task.done()


# AC3 + AC12 #10 — keep-alive cancels cleanly on release
async def test_keepalive_task_cancels_cleanly_on_release(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        keepalive_task = handle.spawned_coros[0]
        await t.release()
        await asyncio.sleep(0)
        # Cancelled cleanly; either .cancelled() or .done() with no exception.
        assert keepalive_task.done()
        # No exception leaked out — the no-op body absorbs CancelledError.
        if keepalive_task.cancelled():
            return
        # If it returned normally (after asyncio.CancelledError caught), no exc.
        assert keepalive_task.exception() is None


# AC12 #11 — short addressing
async def test_aenter_with_short_addressing(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle, dcc_address=42, long=False)
    async with throttle:
        assert handle.throttle_acquire_calls == [(42, False)]


# AC10 + AC12 #12
async def test_layout_throttle_factory_passes_handle(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    layout = Layout(handle=cast(ClientHandle, handle))
    throttle = layout.throttle(5327, long=True)
    assert throttle._handle is handle
    assert throttle.dcc_address == 5327
    assert throttle.long is True


# AC10 + AC12 #13
async def test_layout_throttle_factory_raises_when_no_handle() -> None:
    layout = Layout()
    with pytest.raises(RuntimeError, match=r"client\.throttle"):
        layout.throttle(5327, long=True)
