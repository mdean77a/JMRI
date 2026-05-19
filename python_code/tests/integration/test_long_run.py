"""Parameterized unattended stability test (FR7, FR33, NFR4, NFR5).

Default 5-minute run for normal dev use; invoke with ``--duration=3600`` (or
``PYJMRI_LONG_RUN_DURATION=3600``) for the pre-release one-hour stability
gate. The test exercises the reconnect machinery across multiple forced
WS disconnects and verifies that:

* In-flight ``wait_change()`` waiters survive each disconnect (FR33).
* Subscriptions are replayed on every reconnect (FR7).
* The process does not leak memory, file descriptors, or asyncio tasks
  across the run (NFR4) — thresholds scale linearly between the 5-minute
  and 60-minute marks.
* Disconnect cadence yields at least 5/hour for runs ≥ 1 hour (NFR5
  floor).

Cadence formula: ``num_disconnects = max(1, ceil(duration_s / 720))``
yields 1 at 300 s, 3 at 1800 s, 5 at 3600 s. Disconnects are spaced
evenly at ``duration * (i+1) / (N+1)`` for ``i ∈ {0..N-1}`` — never at
the start, never at the end.

Layout-agnostic: picks the first sensor from ``discover()``; skips with a
clear message if the layout has no sensors. Sensor round-trip is the
authoritative NFR4 / NFR5 proof on NCE-Simulator layouts where turnout
state-change commands do not echo back via WS.

Excluded from the default CI invocation (``pytest -m "not integration"``)
by the ``integration`` marker; also gated by the ``slow`` marker so it
can be excluded with ``pytest -m "not slow"`` even when integration tests
are enabled.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import os
from urllib.parse import quote

import httpx
import pytest

try:
    import psutil  # type: ignore[import-untyped]
except ImportError:
    pytest.skip("psutil required for leak-metric capture", allow_module_level=True)

from pyjmri import Client, SensorState

# ── Constants ──────────────────────────────────────────────────────────────
_DEFAULT_DURATION_S = 300
_DISCONNECT_PERIOD_S = 720  # 1 disconnect / 720s → 5/hour at 3600s (NFR5 floor)
_RECONNECT_WAIT_S = 15.0
_RECONNECT_POLL_INTERVAL_S = 0.2
_RECONNECT_INFO_MSG = "WebSocket reconnected; replaying subscriptions"
_RECONNECT_LOGGER = "pyjmri.reconnect"
_PER_CYCLE_WAIT_TIMEOUT_S = 30.0
_POST_RECONNECT_COMMAND_TIMEOUT_S = 10.0
_INITIAL_STATE_TIMEOUT_S = 10.0

_FD_DELTA_MAX = 5
_TASK_DELTA_MAX = 2
_RSS_DELTA_FLOOR_MB = 10
_RSS_DELTA_CEIL_MB = 50

_SENSOR_INT_ACTIVE = 2
_SENSOR_INT_INACTIVE = 4

_BYTES_PER_MB = 1024 * 1024


# ── Helpers (intentionally self-contained per repo convention) ──────────────


async def _post_sensor_state(
    raw_http: httpx.AsyncClient,
    sensor_name: str,
    target: SensorState,
) -> None:
    code = _SENSOR_INT_ACTIVE if target is SensorState.ACTIVE else _SENSOR_INT_INACTIVE
    resp = await raw_http.post(
        f"/json/v5/sensor/{quote(sensor_name, safe='')}",
        json={"type": "sensor", "data": {"name": sensor_name, "state": code}},
    )
    resp.raise_for_status()


def _opposite_sensor(state: SensorState) -> SensorState:
    if state is SensorState.ACTIVE:
        return SensorState.INACTIVE
    if state is SensorState.INACTIVE:
        return SensorState.ACTIVE
    pytest.skip(f"sensor is in non-binary state {state!r}; cannot determine meaningful opposite")


def _resolve_duration(request: pytest.FixtureRequest) -> int:
    raw = request.config.getoption("--duration", default=None)
    if raw is None:
        raw = os.environ.get("PYJMRI_LONG_RUN_DURATION")
    if raw is None:
        return _DEFAULT_DURATION_S
    try:
        value = int(raw)
    except (TypeError, ValueError) as e:
        raise pytest.UsageError(
            f"invalid --duration / PYJMRI_LONG_RUN_DURATION value: {raw!r}"
        ) from e
    if value <= 0:
        raise pytest.UsageError(f"--duration must be positive; got {value}")
    if value < 30:
        raise pytest.UsageError(f"--duration must be at least 30 seconds; got {value}")
    return value


def _max_rss_delta_mb(duration_s: int) -> float:
    if duration_s <= 300:
        return float(_RSS_DELTA_FLOOR_MB)
    if duration_s >= 3600:
        return float(_RSS_DELTA_CEIL_MB)
    span_factor = (duration_s - 300) / (3600 - 300)
    return _RSS_DELTA_FLOOR_MB + (_RSS_DELTA_CEIL_MB - _RSS_DELTA_FLOOR_MB) * span_factor


def _num_fds_or_skip(process: psutil.Process) -> int:
    # ``num_fds()`` is Unix-only; Windows is best-effort per NFR9.
    if not hasattr(process, "num_fds"):
        pytest.skip(
            "psutil.Process.num_fds() unavailable on this platform (Windows is not a v1 target)"
        )
    return int(process.num_fds())


def _metric_snapshot(process: psutil.Process) -> dict[str, int | float]:
    current = asyncio.current_task()
    other_tasks = [t for t in asyncio.all_tasks() if t is not current]
    return {
        "rss_bytes": process.memory_info().rss,
        "fds": _num_fds_or_skip(process),
        "tasks": len(other_tasks),
    }


async def _await_reconnect_log(
    caplog: pytest.LogCaptureFixture,
    since_index: int,
    cycle_idx: int,
) -> int:
    """Poll ``caplog.records`` for a ``pyjmri.reconnect`` INFO record after ``since_index``.

    Returns the new index (one past the matching record) so the caller can
    advance its marker for the next cycle. Calls :func:`pytest.fail` on
    timeout — index-tracking is critical when multiple reconnects happen
    in one test run, since otherwise the first match would short-circuit
    every later cycle.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _RECONNECT_WAIT_S
    while loop.time() < deadline:
        for idx in range(since_index, len(caplog.records)):
            rec = caplog.records[idx]
            if (
                rec.name == _RECONNECT_LOGGER
                and rec.levelno == logging.INFO
                and _RECONNECT_INFO_MSG in rec.getMessage()
            ):
                return idx + 1
        await asyncio.sleep(_RECONNECT_POLL_INTERVAL_S)
    pytest.fail(
        f"cycle {cycle_idx}: WS did not reconnect within {_RECONNECT_WAIT_S:.0f} s "
        f"after _force_disconnect()"
    )


# ── The test ────────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.slow
async def test_long_run_stability(
    jmri_available: None,
    request: pytest.FixtureRequest,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """NFR4/NFR5: unattended stability across multiple forced WS disconnects."""
    duration_s = _resolve_duration(request)
    num_disconnects = max(1, math.ceil(duration_s / _DISCONNECT_PERIOD_S))
    max_rss_delta_mb = _max_rss_delta_mb(duration_s)
    process = psutil.Process()

    async with Client() as jmri:
        layout = await jmri.discover()
        sensors = list(layout.sensors.values())
        if not sensors:
            pytest.skip("layout has no sensors — cannot run long-run stability test")
        sensor = sensors[0]

        async with httpx.AsyncClient(base_url="http://localhost:12080") as raw_http:
            # Force a known starting state so the cache is correct and we
            # have a deterministic "opposite" target for each cycle.
            await _post_sensor_state(raw_http, sensor.name, SensorState.INACTIVE)
            await sensor.wait_state(SensorState.INACTIVE, timeout=_INITIAL_STATE_TIMEOUT_S)
            starting_state = sensor.state

            with caplog.at_level(logging.INFO, logger=_RECONNECT_LOGGER):
                # Baseline snapshot AFTER the Client + first discover settle.
                baseline = _metric_snapshot(process)
                caplog_marker = len(caplog.records)

                # Even disconnect schedule, never at t=0 or t=duration.
                schedule = [
                    duration_s * (i + 1) / (num_disconnects + 1) for i in range(num_disconnects)
                ]

                loop = asyncio.get_running_loop()
                start_t = loop.time()
                disconnects_done = 0
                reconnects_done = 0

                for cycle_idx, scheduled_t in enumerate(schedule, start=1):
                    # Wait until the scheduled disconnect time.
                    while True:
                        elapsed = loop.time() - start_t
                        delay = scheduled_t - elapsed
                        if delay <= 0:
                            break
                        await asyncio.sleep(min(delay, 1.0))

                    pre_cycle_state = sensor.state
                    wait_task: asyncio.Task[SensorState] = asyncio.create_task(
                        sensor.wait_change(timeout=_PER_CYCLE_WAIT_TIMEOUT_S)
                    )
                    await asyncio.sleep(0)  # let the waiter register

                    try:
                        await jmri._force_disconnect()
                        disconnects_done += 1
                        caplog_marker = await _await_reconnect_log(caplog, caplog_marker, cycle_idx)
                        reconnects_done += 1

                        if wait_task.done():
                            resolved = wait_task.result()
                            assert resolved is not pre_cycle_state, (
                                f"cycle {cycle_idx}: waiter resolved to starting state "
                                f"{pre_cycle_state!r}"
                            )
                        else:
                            target = _opposite_sensor(sensor.state)
                            await _post_sensor_state(raw_http, sensor.name, target)
                            resolved = await asyncio.wait_for(
                                asyncio.shield(wait_task),
                                timeout=_POST_RECONNECT_COMMAND_TIMEOUT_S,
                            )
                            assert resolved is target, (
                                f"cycle {cycle_idx}: expected {target!r}; got {resolved!r}"
                            )
                            # Restore the original starting state for the next cycle.
                            if sensor.state is not starting_state:
                                await _post_sensor_state(raw_http, sensor.name, starting_state)
                                await sensor.wait_state(
                                    starting_state, timeout=_INITIAL_STATE_TIMEOUT_S
                                )
                    finally:
                        if not wait_task.done():
                            wait_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await wait_task

                # Idle for the remainder of the duration so the test wall-clock
                # actually matches the requested span — NFR4 is a duration claim.
                while True:
                    elapsed = loop.time() - start_t
                    remaining = duration_s - elapsed
                    if remaining <= 0:
                        break
                    await asyncio.sleep(min(remaining, 1.0))

                # Final snapshot — still inside the Client context so deltas
                # measure library-internal growth, not teardown cleanup.
                final = _metric_snapshot(process)

    # ── Threshold assertions (deltas) ────────────────────────────────────
    rss_baseline_bytes = int(baseline["rss_bytes"])
    rss_final_bytes = int(final["rss_bytes"])
    rss_delta_mb = (rss_final_bytes - rss_baseline_bytes) / _BYTES_PER_MB

    fd_baseline = int(baseline["fds"])
    fd_final = int(final["fds"])
    fd_delta = fd_final - fd_baseline

    task_baseline = int(baseline["tasks"])
    task_final = int(final["tasks"])
    task_delta = task_final - task_baseline

    assert rss_delta_mb <= max_rss_delta_mb, (
        f"RSS delta {rss_delta_mb:.2f} MB exceeds threshold {max_rss_delta_mb:.2f} MB "
        f"at duration={duration_s}s (baseline={rss_baseline_bytes} bytes, "
        f"final={rss_final_bytes} bytes)"
    )
    assert fd_delta <= _FD_DELTA_MAX, (
        f"FD delta {fd_delta} exceeds threshold {_FD_DELTA_MAX} "
        f"(baseline={fd_baseline}, final={fd_final})"
    )
    assert task_delta <= _TASK_DELTA_MAX, (
        f"asyncio task delta {task_delta} exceeds threshold {_TASK_DELTA_MAX} "
        f"(baseline={task_baseline}, final={task_final})"
    )
    assert reconnects_done == disconnects_done == num_disconnects, (
        f"disconnect/reconnect count mismatch: "
        f"planned={num_disconnects}, disconnects={disconnects_done}, "
        f"reconnects={reconnects_done}"
    )

    # Release-prep evidence line; visible under ``pytest -s``.
    print(
        f"pyjmri long-run: duration={duration_s}s "
        f"disconnects={disconnects_done} reconnects={reconnects_done} "
        f"rss_delta={rss_delta_mb:.1f}MB fd_delta={fd_delta} "
        f"task_delta={task_delta} status=PASS"
    )
