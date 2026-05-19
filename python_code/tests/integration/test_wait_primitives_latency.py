"""Integration test: NFR1 sensor-event latency budget.

Forces sensor state changes via raw ``httpx`` POST to JMRI, measures
how long until the user's ``wait_change()`` resolves, and asserts the
median across 20 trials is under 100 ms (NFR1).

Architecture §Performance: synchronous fanout from the WS receive loop
must keep median sensor-event → ``wait_*`` resolution under 100 ms on
an idle layout with fewer than 100 subscriptions.

The test owns its own raw ``httpx.AsyncClient`` for the sensor-toggle
side. Story 4.1 will ship the proper command path; until then this is
the cleanest way to exercise NFR1 end-to-end.

**Measurement window:** ``t_post`` is snapped BEFORE the HTTP POST so
each sample measures "command issued → ``wait_change`` resolved" —
the practical end-to-end latency NFR1 cares about. This includes the
HTTP POST RTT (typically 5-20 ms on localhost), which is unavoidable
because JMRI emits the WS state event during the HTTP round-trip.
``WARMUP_TRIALS`` discarded iterations absorb cold-start TLS / socket
/ GC overhead before the measured window begins.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from urllib.parse import quote

import httpx
import pytest

from pyjmri import Client, Sensor, SensorState

NUM_TRIALS = 20
WARMUP_TRIALS = 3
NFR1_MEDIAN_BUDGET_MS = 100.0

# JMRI integer state codes for sensors (from _codes.SENSOR_STATE):
_SENSOR_INT_ACTIVE = 2
_SENSOR_INT_INACTIVE = 4


def _int_code_for(target: SensorState) -> int:
    if target is SensorState.ACTIVE:
        return _SENSOR_INT_ACTIVE
    if target is SensorState.INACTIVE:
        return _SENSOR_INT_INACTIVE
    raise ValueError(f"unsupported toggle target: {target!r}")


async def _post_sensor_state(
    raw_http: httpx.AsyncClient,
    sensor_name: str,
    target: SensorState,
) -> None:
    """POST a sensor-state change to JMRI's HTTP API."""
    state_code = _int_code_for(target)
    path = f"/json/v5/sensor/{quote(sensor_name, safe='')}"
    response = await raw_http.post(
        path,
        json={"type": "sensor", "data": {"name": sensor_name, "state": state_code}},
    )
    # JMRI returns 200 with the updated envelope on success.
    response.raise_for_status()


@pytest.mark.integration
async def test_sensor_wait_change_median_latency_under_100ms(
    jmri_available: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with Client() as jmri:
        layout = await jmri.discover()
        sensors = list(layout.sensors.values())
        if not sensors:
            pytest.skip("layout has no sensors — cannot measure NFR1")

        sensor: Sensor = sensors[0]

        # Pick a starting state. UNKNOWN/INCONSISTENT → force INACTIVE first.
        if sensor.state not in (SensorState.ACTIVE, SensorState.INACTIVE):
            async with httpx.AsyncClient(base_url="http://localhost:12080") as raw_http:
                await _post_sensor_state(raw_http, sensor.name, SensorState.INACTIVE)
            # Let the WS event arrive and update the cache.
            try:
                async with asyncio.timeout(3.0):
                    await sensor.wait_state(SensorState.INACTIVE, timeout=2.0)
            except TimeoutError:
                pytest.skip(f"could not force sensor {sensor.name!r} to a known starting state")

        samples_ms: list[float] = []
        async with httpx.AsyncClient(base_url="http://localhost:12080") as raw_http:
            # WARMUP_TRIALS discarded iterations absorb cold-start TLS,
            # socket, and GC pauses so the median asserted below reflects
            # steady-state NFR1 latency. Then NUM_TRIALS measured iterations.
            for trial_idx in range(WARMUP_TRIALS + NUM_TRIALS):
                # Alternate target each trial.
                target = (
                    SensorState.INACTIVE
                    if sensor.state is SensorState.ACTIVE
                    else SensorState.ACTIVE
                )

                waiter: asyncio.Task[SensorState] = asyncio.create_task(
                    sensor.wait_change(timeout=2.0)
                )
                # Give the waiter one event-loop tick to register itself.
                await asyncio.sleep(0)

                # Snap t_post BEFORE the POST so the window captures
                # "command issued → wait_change resolved" (NFR1's budget).
                t_post = time.perf_counter()
                await _post_sensor_state(raw_http, sensor.name, target)
                await waiter
                t_resolved = time.perf_counter()

                if trial_idx >= WARMUP_TRIALS:
                    samples_ms.append((t_resolved - t_post) * 1000.0)

        median_ms = statistics.median(samples_ms)
        if len(samples_ms) >= 20:
            p95_ms = statistics.quantiles(samples_ms, n=20)[-1]
        else:
            p95_ms = max(samples_ms)
        min_ms = min(samples_ms)
        max_ms = max(samples_ms)

        # Print summary so a developer running the test can see the
        # distribution at a glance (pytest captures stdout; -s shows it).
        with capsys.disabled():
            print(
                f"\nNFR1 sensor latency (n={NUM_TRIALS}, sensor={sensor.name!r}): "
                f"median={median_ms:.1f} ms, p95={p95_ms:.1f} ms, "
                f"min={min_ms:.1f} ms, max={max_ms:.1f} ms"
            )

        assert median_ms <= NFR1_MEDIAN_BUDGET_MS, (
            f"NFR1: sensor-event median latency {median_ms:.1f} ms exceeds "
            f"{NFR1_MEDIAN_BUDGET_MS:.0f} ms budget; samples_ms={samples_ms}"
        )

        # Sanity: every wait_change actually resolved (not skipped/cancelled).
        assert len(samples_ms) == NUM_TRIALS
        # And nothing pathological — keep the max under 2 s (the wait_* timeout).
        assert max_ms < 2000.0
