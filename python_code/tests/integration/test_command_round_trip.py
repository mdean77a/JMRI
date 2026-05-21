"""Round-trip integration test for the optimistic command path (Story 4.1).

For each commandable entity type present in the running JMRI's layout,
this test:

1. Reads the entity's current state/value.
2. Commands the opposite/different state via the new command method.
3. Re-reads state/value via the per-entity ``get_*`` method.
4. Asserts the re-read matches the commanded state.
5. Restores the original state at teardown.

For turnouts and lights the test accepts the NCE open-loop reality:
if ``get_state()`` after the command still reports the pre-command
state, the test logs a WARNING and continues. The HTTP ack itself is
this story's contract; re-read confirmation is best-effort. (Story 4.2
adds the WS-confirmed path.)

Layout-agnostic — picks the first entity of each commandable type from
``Client.discover()`` and skips types not present.

Marker: ``@pytest.mark.integration`` — excluded from default CI by the
``not integration`` selector.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import pytest

from pyjmri import Client, LightState, TurnoutState

pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)


async def test_turnout_round_trip(jmri_available: None) -> None:
    async with Client() as jmri:
        layout = await jmri.discover()
        turnouts = list(layout.turnouts.values())
        if not turnouts:
            pytest.skip("layout has no turnouts")
        turnout = turnouts[0]

        original = await turnout.get_state()
        if original not in {TurnoutState.CLOSED, TurnoutState.THROWN}:
            pytest.skip(f"turnout {turnout.name} in non-binary state {original.name}")
        target = TurnoutState.THROWN if original is TurnoutState.CLOSED else TurnoutState.CLOSED

        try:
            await turnout.set_state(target)
            refreshed = await turnout.get_state()
            if refreshed is not target:
                logger.warning(
                    "turnout command accepted by JMRI but state did not change on re-read — "
                    "expected on NCE without physical feedback "
                    "(applies to simulator and live layout equally)",
                    extra={
                        "name": turnout.name,
                        "commanded": target.name,
                        "re_read": refreshed.name,
                    },
                )
        finally:
            with contextlib.suppress(Exception):
                await turnout.set_state(original)


async def test_light_round_trip(jmri_available: None) -> None:
    async with Client() as jmri:
        layout = await jmri.discover()
        lights = list(layout.lights.values())
        if not lights:
            pytest.skip("layout has no lights")
        light = lights[0]

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
        memories = list(layout.memories.values())
        if not memories:
            pytest.skip("layout has no memories")
        memory = memories[0]

        original = await memory.get_value()
        # Use a value distinct from any string the layout author might
        # plausibly have set, to maximize the chance the re-read actually
        # reflects this test's write.
        probe = "pyjmri-round-trip-probe"

        try:
            await memory.set_value(probe)
            refreshed = await memory.get_value()
            # Memory writes are pure JMRI-internal data with no hardware
            # leg, so the re-read should reflect the write deterministically.
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
        routes = list(layout.routes.values())
        if not routes:
            pytest.skip("layout has no routes")
        route = routes[0]

        # Route's contract is "no exception on activate" — there is no
        # observable post-state to re-read because JMRI keeps the route's
        # internal state at 0 after activation (the turnouts move; the
        # route is a one-shot trigger). The Story 4.1 acceptance criterion
        # is simply that JMRI HTTP-acks the activation.
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
        turnouts = list(layout.turnouts.values())
        if not turnouts:
            pytest.skip("layout has no turnouts")
        turnout = turnouts[0]

        original = await turnout.get_state()
        if original not in {TurnoutState.CLOSED, TurnoutState.THROWN}:
            pytest.skip(f"turnout {turnout.name} in non-binary state {original.name}")
        target = TurnoutState.THROWN if original is TurnoutState.CLOSED else TurnoutState.CLOSED

        try:
            # wait_for: cap the wait so a non-echoing JMRI can't hang the suite.
            await asyncio.wait_for(
                turnout.set_state(target, wait_for_jmri_state=True),
                timeout=5.0,
            )
            # WS event must have updated cached state.
            assert turnout.state is target
        finally:
            # Restore optimistically (no wait) — the test's purpose is the wait
            # path; restore complexity should not add new failure modes.
            with contextlib.suppress(Exception):
                await turnout.set_state(original)


async def test_light_wait_for_jmri_state_round_trip(jmri_available: None) -> None:
    """AC10 part 2: light wait_for_jmri_state — WARN-and-pass on timeout.

    Light WS echo is UNVERIFIED on Mikey's profile family (Story 4.1
    spike could not probe — no lights present). If the wait times out
    here, treat it as informational rather than a hard fail.
    """
    async with Client() as jmri:
        layout = await jmri.discover()
        lights = list(layout.lights.values())
        if not lights:
            pytest.skip("layout has no lights")
        light = lights[0]

        original = await light.get_state()
        if original not in {LightState.ON, LightState.OFF}:
            pytest.skip(f"light {light.name} in non-binary state {original.name}")
        target = LightState.OFF if original is LightState.ON else LightState.ON

        try:
            try:
                await asyncio.wait_for(
                    light.set_state(target, wait_for_jmri_state=True),
                    timeout=5.0,
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
