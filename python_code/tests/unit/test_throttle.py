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


# ============================================================================
# Story 5.2: set_speed / set_function control surface
# ============================================================================


# Story 5.2 AC1 + AC9 #1
async def test_set_speed_sends_single_envelope_with_speed_and_forward(
    make_fake_handle: Any,
) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        await t.set_speed(0.4, forward=True)
    assert handle.throttle_update_calls == [("pyjmri-5327-fake", {"speed": 0.4, "forward": True})]


# Story 5.2 AC1 + AC9 #2
async def test_set_speed_with_reverse_direction(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        await t.set_speed(0.25, forward=False)
    assert handle.throttle_update_calls == [("pyjmri-5327-fake", {"speed": 0.25, "forward": False})]


# Story 5.2 AC1 + AC9 #3 — closed-range lower bound (emergency stop)
async def test_set_speed_zero_is_valid(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        await t.set_speed(0.0, forward=True)
    assert handle.throttle_update_calls == [("pyjmri-5327-fake", {"speed": 0.0, "forward": True})]


# Story 5.2 AC1 + AC9 #4 — closed-range upper bound
async def test_set_speed_one_is_valid(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        await t.set_speed(1.0, forward=True)
    assert handle.throttle_update_calls == [("pyjmri-5327-fake", {"speed": 1.0, "forward": True})]


# Story 5.2 AC1 + AC9 #5 — validation runs before transport
async def test_set_speed_rejects_negative(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            await t.set_speed(-0.1, forward=True)
    assert handle.throttle_update_calls == []


# Story 5.2 AC1 + AC9 #6
async def test_set_speed_rejects_above_one(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            await t.set_speed(1.1, forward=True)
    assert handle.throttle_update_calls == []


# Story 5.2 AC1 + AC9 #7 — NaN propagates as out-of-range (0.0 <= NaN is False)
async def test_set_speed_rejects_nan(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            await t.set_speed(float("nan"), forward=True)
    assert handle.throttle_update_calls == []


# Story 5.2 AC2 + AC9 #8
async def test_set_function_sends_F_indexed_envelope(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        await t.set_function(2, True)
    assert handle.throttle_update_calls == [("pyjmri-5327-fake", {"F2": True})]


# Story 5.2 AC2 + AC9 #9 — closed-range bounds
async def test_set_function_zero_and_twentyeight_are_valid(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        await t.set_function(0, True)
        await t.set_function(28, False)
    assert handle.throttle_update_calls == [
        ("pyjmri-5327-fake", {"F0": True}),
        ("pyjmri-5327-fake", {"F28": False}),
    ]


# Story 5.2 AC2 + AC9 #10
async def test_set_function_rejects_negative(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        with pytest.raises(ValueError, match=r"\[0, 28\]"):
            await t.set_function(-1, True)
    assert handle.throttle_update_calls == []


# Story 5.2 AC2 + AC9 #11
async def test_set_function_rejects_above_twentyeight(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        with pytest.raises(ValueError, match=r"\[0, 28\]"):
            await t.set_function(29, True)
    assert handle.throttle_update_calls == []


# Story 5.2 AC3 + AC9 #12
async def test_set_speed_after_release_raises_throttle_released(
    make_fake_handle: Any,
) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        await t.release()
        with pytest.raises(ThrottleReleased) as excinfo:
            await t.set_speed(0.4, forward=True)
        assert excinfo.value.context["dcc_address"] == 5327
    assert handle.throttle_update_calls == []


# Story 5.2 AC3 + AC9 #13
async def test_set_function_after_release_raises_throttle_released(
    make_fake_handle: Any,
) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        await t.release()
        with pytest.raises(ThrottleReleased) as excinfo:
            await t.set_function(2, True)
        assert excinfo.value.context["dcc_address"] == 5327
    assert handle.throttle_update_calls == []


# Story 5.2 AC4 + AC9 #14
async def test_set_speed_on_never_acquired_throttle_raises_runtime_error(
    make_fake_handle: Any,
) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    with pytest.raises(RuntimeError, match=r"not acquired"):
        await throttle.set_speed(0.4, forward=True)
    assert handle.throttle_update_calls == []


# Story 5.2 AC3 + AC9 #15 — released check beats arg validation
async def test_set_speed_with_invalid_value_on_released_throttle_raises_throttle_released(
    make_fake_handle: Any,
) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        await t.release()
        with pytest.raises(ThrottleReleased) as excinfo:
            await t.set_speed(-0.1, forward=True)
        assert excinfo.value.context["dcc_address"] == 5327
    assert handle.throttle_update_calls == []


# ============================================================================
# Review fixes (code review 2026-05-21)
# ============================================================================


# P1 — bool is a subtype of int; `set_function(True, True)` must be rejected
async def test_set_function_rejects_bool_as_n(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        with pytest.raises(ValueError, match=r"must be an int"):
            await t.set_function(True, True)
    assert handle.throttle_update_calls == []


# P1 — float passes range guard but produces a malformed key like "F2.5"
async def test_set_function_rejects_float_as_n(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    async with throttle as t:
        with pytest.raises(ValueError, match=r"must be an int"):
            await t.set_function(2.5, True)  # type: ignore[arg-type]
    assert handle.throttle_update_calls == []


# P3 — AC4 covers "set_speed or set_function"; only set_speed had test #14
async def test_set_function_on_never_acquired_throttle_raises_runtime_error(
    make_fake_handle: Any,
) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    with pytest.raises(RuntimeError, match=r"not acquired"):
        await throttle.set_function(2, True)
    assert handle.throttle_update_calls == []


# P5 — AC1: INFO log carries correct extra fields for set_speed
async def test_set_speed_logs_info_with_extra_fields(
    make_fake_handle: Any, caplog: pytest.LogCaptureFixture
) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    caplog.set_level("INFO", logger="pyjmri.throttle")
    async with throttle as t:
        await t.set_speed(0.4, forward=True)
    speed_logs = [r for r in caplog.records if "speed updated" in r.message]
    assert len(speed_logs) == 1
    rec = speed_logs[0]
    assert rec.dcc_address == 5327  # type: ignore[attr-defined]
    assert rec.throttle_id == "pyjmri-5327-fake"  # type: ignore[attr-defined]
    assert rec.speed == pytest.approx(0.4)  # type: ignore[attr-defined]
    assert rec.forward is True  # type: ignore[attr-defined]


# P5 — AC2: INFO log carries correct extra fields for set_function
async def test_set_function_logs_info_with_extra_fields(
    make_fake_handle: Any, caplog: pytest.LogCaptureFixture
) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    throttle = _make_throttle(handle)
    caplog.set_level("INFO", logger="pyjmri.throttle")
    async with throttle as t:
        await t.set_function(2, True)
    fn_logs = [r for r in caplog.records if "function updated" in r.message]
    assert len(fn_logs) == 1
    rec = fn_logs[0]
    assert rec.dcc_address == 5327  # type: ignore[attr-defined]
    assert rec.throttle_id == "pyjmri-5327-fake"  # type: ignore[attr-defined]
    assert rec.function == 2  # type: ignore[attr-defined]
    assert rec.on is True  # type: ignore[attr-defined]


# P7 — throttle_update_raises knob: transport error propagates from set_speed
async def test_set_speed_propagates_transport_error(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    handle.throttle_update_raises = JMRIConnectionError(host="localhost", port=12080)
    throttle = _make_throttle(handle)
    with pytest.raises(JMRIConnectionError):
        async with throttle as t:
            await t.set_speed(0.4, forward=True)
