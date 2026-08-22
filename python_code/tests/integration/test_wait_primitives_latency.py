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

import httpx
import pytest
from _entity_state import JMRI_BASE_URL, force_sensor_state

from pyjmri import Client, Sensor, SensorState

NUM_TRIALS = 20
WARMUP_TRIALS = 3
NFR1_MEDIAN_BUDGET_MS = 100.0

# Per-trial wait_change budget. Raised from 2.0 s to 5.0 s (Story 7.1
# AC4). The NFR1 median assertion below stays pinned at 100 ms — we do
# NOT relax the spec — but this per-trial ceiling absorbs suite-load and
# coverage-instrumentation variance so a single slow trial is not misread
# as a regression. The old 2.0 s ceiling flaked during the v1.0.0
# coverage run; 5.0 s survives that while still tripping on a real hang.
_WAIT_CHANGE_TIMEOUT_S = 5.0

# Target: a dedicated internal sensor provisioned by the
# ``provisioned_internal_sensor`` fixture (see tests/integration/conftest.py).
# We do NOT hard-pin a name like ``IS1`` — on a real panel that name is a
# meaningful layout sensor (e.g. an occupancy/staging sensor) whose watching
# logic can move it mid-measurement, and it may not exist at all on another
# installation. A freshly provisioned internal sensor is fully owned by this
# test, always echoes state changes back over WS, and cannot collide with a
# real entity (Story 7.1 non-overlap discipline, made installation-agnostic).

# Budget for forcing + confirming the known starting state before the
# measured window. Outer context-manager 5.0 s, inner wait_state 4.5 s
# (Story 7.1 AC4; inner < outer so the inner fires first as a clean
# TimeoutError and the outer acts as a hard-cancel backstop).
_STARTING_STATE_TIMEOUT_S = 5.0
_STARTING_STATE_INNER_TIMEOUT_S = 4.5


@pytest.mark.integration
async def test_sensor_wait_change_median_latency_under_100ms(
    provisioned_internal_sensor: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with Client() as jmri:
        layout = await jmri.discover()
        # The fixture provisioned this internal sensor before discover(), so
        # it is guaranteed present; a missing lookup here is a real bug, not
        # a layout gap, and should fail rather than skip.
        sensor: Sensor = layout.sensors.by_system_name(provisioned_internal_sensor)

        # Prime the WS subscription BEFORE the measured loop. ensure_subscription
        # returns only after JMRI acks the subscribe (echoes the entity
        # envelope), so every trial below runs against a confirmed-attached
        # listener. Without this, trial 0 races first-subscription arming
        # against the HTTP POST — the POST can land before JMRI attaches the
        # listener, and the toggle is either missed or consumed by arming.
        await jmri.ensure_subscription("sensor", sensor.name)

        # AC3: always force a known starting state (INACTIVE) via raw httpx
        # POST — never trust whatever state a prior step left on the sensor —
        # and confirm the WS-cached state reaches it before the measured window.
        async with httpx.AsyncClient(base_url=JMRI_BASE_URL) as raw_http:
            await force_sensor_state(raw_http, sensor.name, SensorState.INACTIVE)
        try:
            async with asyncio.timeout(_STARTING_STATE_TIMEOUT_S):
                await sensor.wait_state(
                    SensorState.INACTIVE, timeout=_STARTING_STATE_INNER_TIMEOUT_S
                )
        except TimeoutError:
            pytest.skip(f"could not force sensor {sensor.name!r} to a known starting state")

        samples_ms: list[float] = []
        async with httpx.AsyncClient(base_url=JMRI_BASE_URL) as raw_http:
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
                    sensor.wait_change(timeout=_WAIT_CHANGE_TIMEOUT_S)
                )
                # Give the waiter one event-loop tick to register itself.
                await asyncio.sleep(0)

                # Snap t_post BEFORE the POST so the window captures
                # "command issued → wait_change resolved" (NFR1's budget).
                t_post = time.perf_counter()
                await force_sensor_state(raw_http, sensor.name, target)
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
        # And nothing pathological — keep the max under the per-trial
        # wait_change ceiling (Story 7.1 AC4 raised it to 5.0 s).
        assert max_ms < _WAIT_CHANGE_TIMEOUT_S * 1000.0
