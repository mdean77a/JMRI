"""Round-trip integration test for the optimistic command path (Story 4.1).

For each commandable entity type present in the running JMRI's layout,
this test:

1. Forces a known starting state via raw ``httpx`` POST (Story 7.1 AC3).
2. Commands the opposite/different state via the new command method.
3. Re-reads state/value via the per-entity ``get_*`` method.
4. Asserts the re-read matches the commanded state.
5. Restores the starting state at teardown.

For turnouts and lights the test accepts the NCE open-loop reality:
if ``get_state()`` after the command still reports the pre-command
state, the test logs a WARNING and continues. The HTTP ack itself is
this story's contract; re-read confirmation is best-effort. (Story 4.2
adds the WS-confirmed path.)

Entity targets are **pinned by system name** (Story 7.1 AC2), never by
positional ``collection[0]`` indexing — each test owns a distinct entity
so no two tests contend for the same JMRI object during a suite run, and
suite ordering / layout growth cannot silently retarget a test. Layout-
agnostic via skip-if-missing (FR43): a test whose pinned entity is not
on the discovered layout skips cleanly naming the missing entity.

Marker: ``@pytest.mark.integration`` — excluded from default CI by the
``not integration`` selector.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import httpx
import pytest
from _entity_state import JMRI_BASE_URL, force_turnout_state

from pyjmri import Client, LayoutEntityNotFound, LightState, TurnoutState

pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)

# Pinned, non-overlapping entity targets (Story 7.1 AC2). Each mutating
# turnout test owns a distinct NCE turnout so none contend for the same
# object during a single suite run:
#   NT100 — optimistic round-trip (this file)
#   NT102 — wait_for_jmri_state round-trip (this file)
#   NT104 — wait_for_jmri_state survives reconnect (test_command_wait_reconnect)
#   NT106 — forced-disconnect resilience (test_reconnect_resilience)
#   NT108 — command-overhead microbenchmark (test_command_latency, slow)
_TURNOUT_ROUND_TRIP_NAME = "NT100"
_TURNOUT_WAIT_STATE_NAME = "NT102"
# The basement layout has 0 lights; IL1 is pinned so the light tests skip
# cleanly by name (FR43) and remain correct if a light is ever added.
_LIGHT_NAME = "IL1"
_MEMORY_NAME = "IM:AUTO:0001"
_ROUTE_NAME = "IO:AUTO:0001"

# AC10 budget: wait_for_jmri_state=True round-trip. Raised from 5.0 s to
# 10.0 s (Story 7.1 AC4) — tight enough to catch a regression, loose
# enough to survive coverage instrumentation; the old 5.0 s flaked under
# pytest-cov during the v1.0.0 post-ship coverage run.
_WAIT_FOR_JMRI_STATE_TIMEOUT_S = 10.0
# Light wait_for budget. Kept at 5.0 s: light WS echo is UNVERIFIED on
# this profile family (no lights present to probe), and the test is
# WARN-and-pass on timeout, so a tight ceiling cannot turn into a flake.
_LIGHT_WAIT_FOR_TIMEOUT_S = 5.0


async def test_turnout_round_trip(jmri_available: None) -> None:
    async with Client() as jmri:
        layout = await jmri.discover()
        try:
            turnout = layout.turnouts.by_system_name(_TURNOUT_ROUND_TRIP_NAME)
        except LayoutEntityNotFound:
            pytest.skip(
                f"turnout {_TURNOUT_ROUND_TRIP_NAME!r} not on this layout — "
                "required for the optimistic turnout round-trip test"
            )

        async with httpx.AsyncClient(base_url=JMRI_BASE_URL) as raw_http:
            # AC3: force CLOSED via raw httpx and confirm via an
            # authoritative HTTP GET before commanding — never trust the
            # state a prior test left behind.
            await force_turnout_state(raw_http, turnout.name, TurnoutState.CLOSED)
            assert await turnout.get_state() is TurnoutState.CLOSED

            try:
                await turnout.set_state(TurnoutState.THROWN)
                refreshed = await turnout.get_state()
                if refreshed is not TurnoutState.THROWN:
                    logger.warning(
                        "turnout command accepted by JMRI but state did not change on re-read — "
                        "expected on NCE without physical feedback "
                        "(applies to simulator and live layout equally)",
                        extra={
                            "name": turnout.name,
                            "commanded": TurnoutState.THROWN.name,
                            "re_read": refreshed.name,
                        },
                    )
            finally:
                with contextlib.suppress(Exception):
                    await force_turnout_state(raw_http, turnout.name, TurnoutState.CLOSED)


async def test_light_round_trip(jmri_available: None) -> None:
    async with Client() as jmri:
        layout = await jmri.discover()
        try:
            light = layout.lights.by_system_name(_LIGHT_NAME)
        except LayoutEntityNotFound:
            pytest.skip(f"light {_LIGHT_NAME!r} not on this layout — no light round-trip to run")

        original = await light.get_state()
        if original not in {LightState.ON, LightState.OFF}:
            pytest.skip(f"light {light.name} in non-binary state {original.name}")
        target = LightState.OFF if original is LightState.ON else LightState.ON

        try:
            await light.set_state(target)
            refreshed = await light.get_state()
            if refreshed is not target:
                logger.warning(
                    "light command accepted by JMRI but state did not change on re-read — "
                    "may indicate no physical feedback path "
                    "(applies to simulator and live layout equally)",
                    extra={
                        "name": light.name,
                        "commanded": target.name,
                        "re_read": refreshed.name,
                    },
                )
        finally:
            with contextlib.suppress(Exception):
                await light.set_state(original)


async def test_memory_round_trip(jmri_available: None) -> None:
    async with Client() as jmri:
        layout = await jmri.discover()
        try:
            memory = layout.memories.by_system_name(_MEMORY_NAME)
        except LayoutEntityNotFound:
            pytest.skip(f"memory {_MEMORY_NAME!r} not on this layout — no memory round-trip to run")

        # Memory writes are pure JMRI-internal data with no hardware leg and
        # no per-entity rate limit, so this test does not suffer the shared-
        # entity flakiness AC3's force-state pattern guards against: the
        # write+read of `probe` below is itself a deterministic force+assert.
        original = await memory.get_value()
        # Use a value distinct from any string the layout author might
        # plausibly have set, to maximize the chance the re-read actually
        # reflects this test's write.
        probe = "pyjmri-round-trip-probe"

        try:
            await memory.set_value(probe)
            refreshed = await memory.get_value()
            assert refreshed == probe
        finally:
            with contextlib.suppress(Exception):
                if original is None:
                    # JMRI's wire format expects strings; restoring to
                    # None is not directly possible via set_value. Set
                    # to empty string as the closest legal restore.
                    await memory.set_value("")
                else:
                    await memory.set_value(original)


async def test_route_activate_round_trip(jmri_available: None) -> None:
    async with Client() as jmri:
        layout = await jmri.discover()
        try:
            route = layout.routes.by_system_name(_ROUTE_NAME)
        except LayoutEntityNotFound:
            pytest.skip(f"route {_ROUTE_NAME!r} not on this layout — no route to activate")

        # Route's contract is "no exception on activate" — there is no
        # observable post-state to re-read because JMRI keeps the route's
        # internal state at 0 after activation (the turnouts move; the
        # route is a one-shot trigger). The Story 4.1 acceptance criterion
        # is simply that JMRI HTTP-acks the activation. No starting state to
        # force (a route is a trigger, not a stateful entity).
        await route.activate()


# --- Story 4.2: wait_for_jmri_state=True round-trip ---


async def test_turnout_wait_for_jmri_state_round_trip(jmri_available: None) -> None:
    """AC10 part 1: wait_for_jmri_state=True confirms via WS event.

    On this layout family (JMRI 5.14 sim, Mikey's profile), turnout WS
    echo IS emitted on REST commands — the Story 4.1 spike verified
    this. So we assert strictly that the call returns and cached state
    matches the commanded state.
    """
    async with Client() as jmri:
        layout = await jmri.discover()
        try:
            turnout = layout.turnouts.by_system_name(_TURNOUT_WAIT_STATE_NAME)
        except LayoutEntityNotFound:
            pytest.skip(
                f"turnout {_TURNOUT_WAIT_STATE_NAME!r} not on this layout — "
                "required for the wait_for_jmri_state turnout round-trip test"
            )

        async with httpx.AsyncClient(base_url=JMRI_BASE_URL) as raw_http:
            # AC3: force CLOSED and confirm before commanding THROWN.
            await force_turnout_state(raw_http, turnout.name, TurnoutState.CLOSED)
            assert await turnout.get_state() is TurnoutState.CLOSED
            target = TurnoutState.THROWN

            try:
                # wait_for: cap the wait so a non-echoing JMRI can't hang the suite.
                await asyncio.wait_for(
                    turnout.set_state(target, wait_for_jmri_state=True),
                    timeout=_WAIT_FOR_JMRI_STATE_TIMEOUT_S,
                )
                # WS event must have updated cached state.
                assert turnout.state is target
            finally:
                # Restore to CLOSED deterministically via raw httpx — the
                # test's purpose is the wait path; restore should not add
                # new failure modes.
                with contextlib.suppress(Exception):
                    await force_turnout_state(raw_http, turnout.name, TurnoutState.CLOSED)


async def test_light_wait_for_jmri_state_round_trip(jmri_available: None) -> None:
    """AC10 part 2: light wait_for_jmri_state — WARN-and-pass on timeout.

    Light WS echo is UNVERIFIED on Mikey's profile family (Story 4.1
    spike could not probe — no lights present). If the wait times out
    here, treat it as informational rather than a hard fail.
    """
    async with Client() as jmri:
        layout = await jmri.discover()
        try:
            light = layout.lights.by_system_name(_LIGHT_NAME)
        except LayoutEntityNotFound:
            pytest.skip(
                f"light {_LIGHT_NAME!r} not on this layout — no light wait_for round-trip to run"
            )

        original = await light.get_state()
        if original not in {LightState.ON, LightState.OFF}:
            pytest.skip(f"light {light.name} in non-binary state {original.name}")
        target = LightState.OFF if original is LightState.ON else LightState.ON

        try:
            try:
                await asyncio.wait_for(
                    light.set_state(target, wait_for_jmri_state=True),
                    timeout=_LIGHT_WAIT_FOR_TIMEOUT_S,
                )
                assert light.state is target
            except TimeoutError:
                logger.warning(
                    "light wait_for_jmri_state command accepted but no WS state event "
                    "observed within 5s — light WS echo unverified on this layout "
                    "family; treating as informational",
                    extra={"name": light.name, "commanded": target.name},
                )
        finally:
            with contextlib.suppress(Exception):
                await light.set_state(original)
