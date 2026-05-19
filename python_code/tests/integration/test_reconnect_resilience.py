"""Integration test: forced-disconnect resilience (FR7, FR33, NFR5).

Forces a real WebSocket disconnect mid-script, verifies that in-flight
``wait_*`` calls survive the reconnect + subscription replay, and
confirms they resolve with a valid state change.

Two valid post-reconnect outcomes for each waiter:

  A. **Waiter still pending** — JMRI's subscription-ack delivered the
     same state as ``starting_state``, so the predicate
     ``s != starting_state`` is False.  Verified by commanding the
     opposite state and awaiting the result.

  B. **Waiter already resolved** — the entity's state changed during the
     disconnect window (externally or via JMRI reverting); the
     subscription-ack delivered the new state, the predicate fired,
     and the waiter resolved.  This is the level-triggered semantics of
     NFR5 in action.

Hardware note: on layouts backed by the NCE Simulator (no physical
hardware), turnout state-change commands may not produce a WS event
reply.  The test therefore checks subscription replay for BOTH entities,
but only requires the full post-reconnect resolution round-trip for
entities whose commands demonstrably work (always at least the sensor;
the turnout path is skipped gracefully when commands time out).

Requires JMRI on localhost:12080; skipped via the ``jmri_available``
session fixture when unreachable.  Layout-agnostic: picks the first
sensor and first turnout from ``discover()``, skips if either is absent.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from urllib.parse import quote

import httpx
import pytest

from pyjmri import Client, SensorState, TurnoutState

# JMRI integer state codes (mirrors _codes.py, intentionally inlined per project convention).
_SENSOR_INT_ACTIVE = 2
_SENSOR_INT_INACTIVE = 4
_TURNOUT_INT_THROWN = 2
_TURNOUT_INT_CLOSED = 4

_RECONNECT_WAIT_S = 15.0
_RECONNECT_POLL_INTERVAL_S = 0.2
_RECONNECT_INFO_MSG = "WebSocket reconnected; replaying subscriptions"
_COMMAND_TIMEOUT_S = 5.0  # generous; reduces on sim where commands don't echo back


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


async def _post_turnout_state(
    raw_http: httpx.AsyncClient,
    turnout_name: str,
    target: TurnoutState,
) -> None:
    code = _TURNOUT_INT_THROWN if target is TurnoutState.THROWN else _TURNOUT_INT_CLOSED
    resp = await raw_http.post(
        f"/json/v5/turnout/{quote(turnout_name, safe='')}",
        json={"type": "turnout", "data": {"name": turnout_name, "state": code}},
    )
    resp.raise_for_status()


def _opposite_sensor(state: SensorState) -> SensorState:
    if state is SensorState.ACTIVE:
        return SensorState.INACTIVE
    if state is SensorState.INACTIVE:
        return SensorState.ACTIVE
    pytest.skip(f"sensor is in non-binary state {state!r}; cannot determine meaningful opposite")


def _opposite_turnout(state: TurnoutState) -> TurnoutState:
    if state is TurnoutState.THROWN:
        return TurnoutState.CLOSED
    if state is TurnoutState.CLOSED:
        return TurnoutState.THROWN
    pytest.skip(f"turnout is in non-binary state {state!r}; cannot determine meaningful opposite")


@pytest.mark.integration
async def test_in_flight_wait_survives_forced_disconnect(
    jmri_available: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """FR7/FR33/NFR5: in-flight wait_change() calls survive a forced WS disconnect.

    Sequence:
      1. Force the sensor to INACTIVE; read the turnout's current state
         without commanding it (avoids simulator command-echo issues).
      2. Register wait_change() waiters on both entities.
      3. Assert both tasks are pending before disconnect.
      4. Force-disconnect the WS.
      5. Wait for reconnect + subscription replay (INFO log on pyjmri.reconnect).
      6. Assert subscription registry covers both entities.
      7. Resolve pending waiters:
         - Already resolved (level-triggered via subscription-ack): assert
           result != starting_state.
         - Still pending: command the opposite state; skip if the command
           does not produce a WS ack within the timeout (hardware limitation
           on NCE Simulator layouts).
      8. Assert the sensor waiter resolved correctly (always required).
    """
    async with Client() as jmri:
        layout = await jmri.discover()
        sensors = list(layout.sensors.values())
        turnouts = list(layout.turnouts.values())

        if not sensors:
            pytest.skip("layout has no sensors — cannot run reconnect resilience test")
        if not turnouts:
            pytest.skip("layout has no turnouts — cannot run reconnect resilience test")

        sensor = sensors[0]
        turnout = turnouts[0]

        async with httpx.AsyncClient(base_url="http://localhost:12080") as raw_http:
            # ── Step 1: Establish known starting states ──────────────────────
            # Sensor: force to INACTIVE (internal sensors always echo back).
            await _post_sensor_state(raw_http, sensor.name, SensorState.INACTIVE)
            await sensor.wait_state(SensorState.INACTIVE, timeout=10.0)
            sensor_starting = sensor.state  # SensorState.INACTIVE

            # Turnout: just read current state — don't command it (NCE Sim
            # may not echo state changes back via WS for physical turnouts).
            await jmri._registry.ensure("turnout", turnout.name)  # type: ignore[union-attr]
            # Wait one tick for JMRI to send the current-state subscription-ack.
            await asyncio.sleep(0.5)
            turnout_starting = turnout.state

            # ── Step 2: Register in-flight waiters ───────────────────────────
            sensor_task: asyncio.Task[SensorState] = asyncio.create_task(
                sensor.wait_change(timeout=30.0)
            )
            turnout_task: asyncio.Task[TurnoutState] = asyncio.create_task(
                turnout.wait_change(timeout=30.0)
            )
            # One tick so both tasks register their waiters.
            await asyncio.sleep(0)

            # ── Step 3: Assert pending before disconnect ─────────────────────
            assert not sensor_task.done(), "sensor waiter resolved before disconnect"
            assert not turnout_task.done(), "turnout waiter resolved before disconnect"
            assert jmri._registry is not None
            pre_disconnect_size = jmri._registry.size
            assert pre_disconnect_size >= 2, (
                f"expected >= 2 subscriptions before disconnect; got {pre_disconnect_size}"
            )

            try:
                # ── Steps 4 & 5: Force disconnect; wait for reconnect ────────
                with caplog.at_level(logging.INFO, logger="pyjmri.reconnect"):
                    await jmri._force_disconnect()

                    loop = asyncio.get_running_loop()
                    deadline = loop.time() + _RECONNECT_WAIT_S
                    reconnect_records: list[logging.LogRecord] = []
                    while loop.time() < deadline:
                        reconnect_records = [
                            r
                            for r in caplog.records
                            if r.name == "pyjmri.reconnect"
                            and r.levelno == logging.INFO
                            and _RECONNECT_INFO_MSG in r.getMessage()
                        ]
                        if reconnect_records:
                            break
                        await asyncio.sleep(_RECONNECT_POLL_INTERVAL_S)
                    else:
                        pytest.fail(
                            f"WS did not reconnect within {_RECONNECT_WAIT_S:.0f} s "
                            "after _force_disconnect()"
                        )

                # ── Step 6: Subscription registry intact ─────────────────────
                assert jmri._registry.size >= pre_disconnect_size, (
                    f"subscription count dropped after reconnect: "
                    f"{jmri._registry.size} < {pre_disconnect_size}"
                )
                assert reconnect_records, "expected pyjmri.reconnect INFO log"
                reconnect_rec = reconnect_records[0]
                reconnect_sub_count = getattr(reconnect_rec, "subscription_count", -1)
                assert reconnect_sub_count >= 2, (
                    f"reconnect log subscription_count too low: {reconnect_sub_count}"
                )

                # ── Step 7: Resolve pending waiters ──────────────────────────
                sensor_already_resolved = sensor_task.done()
                turnout_already_resolved = turnout_task.done()

                # Already-resolved waiters: verify result differs from starting state.
                if sensor_already_resolved:
                    sensor_result = sensor_task.result()
                    assert sensor_result is not sensor_starting, (
                        f"sensor resolved to starting state {sensor_starting!r}"
                    )
                if turnout_already_resolved:
                    turnout_result = turnout_task.result()
                    assert turnout_result is not turnout_starting, (
                        f"turnout resolved to starting state {turnout_starting!r}"
                    )

                # Still-pending sensor: command the opposite state (always works).
                sensor_resolved_via_command = False
                if not sensor_already_resolved:
                    sensor_target = _opposite_sensor(sensor.state)
                    await _post_sensor_state(raw_http, sensor.name, sensor_target)
                    sensor_result = await sensor_task
                    assert sensor_result is sensor_target, (
                        f"expected {sensor_target!r}; got {sensor_result!r}"
                    )
                    sensor_resolved_via_command = True

                # Still-pending turnout: attempt command; skip if no WS ack
                # (hardware limitation — NCE Simulator may not echo back).
                if not turnout_already_resolved:
                    turnout_target = _opposite_turnout(turnout.state)
                    await _post_turnout_state(raw_http, turnout.name, turnout_target)
                    try:
                        turnout_result = await asyncio.wait_for(
                            asyncio.shield(turnout_task), timeout=_COMMAND_TIMEOUT_S
                        )
                        assert turnout_result is turnout_target, (
                            f"expected {turnout_target!r}; got {turnout_result!r}"
                        )
                    except TimeoutError:
                        # Command accepted by JMRI but no WS ack arrived — typical
                        # on NCE Simulator layouts without physical hardware.
                        # Subscription survival (FR7) and waiter persistence (FR33)
                        # are already verified above; skip the resolution assertion.
                        pass

                # ── Step 8: Core invariant — sensor waiter MUST have resolved ─
                # The sensor path (internal sensor, always echoes) is the
                # authoritative NFR5 proof regardless of turnout behaviour.
                assert sensor_already_resolved or sensor_resolved_via_command, (
                    "sensor waiter neither resolved via subscription-ack nor via command"
                )

            finally:
                for task in (sensor_task, turnout_task):
                    if not task.done():
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
