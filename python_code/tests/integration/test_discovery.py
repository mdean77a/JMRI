"""Integration smoke test: ``Client.discover()`` against a running JMRI.

Requires JMRI on ``localhost:12080``. Skipped via the ``jmri_available``
session fixture when unreachable. See architecture §Test Harness.
"""

from __future__ import annotations

import time

import pytest

from pyjmri import Client, Layout, LayoutEntityNotFound, TurnoutState

# Read-only probe target (Story 7.1 AC2): pin by system name rather than
# next(iter(...)) positional access. This test only reads NT100's
# attributes — it never commands or waits — so sharing the name with the
# mutating turnout tests is safe; any TurnoutState satisfies the assert.
_TURNOUT_PROBE_NAME = "NT100"


@pytest.mark.integration
async def test_discover_completes_in_under_two_seconds(jmri_available: None) -> None:
    async with Client() as jmri:
        start = time.perf_counter()
        layout = await jmri.discover()
        elapsed = time.perf_counter() - start

    assert isinstance(layout, Layout)
    assert elapsed < 2.0, f"discover() took {elapsed:.3f}s (NFR2 budget: 2.0s)"


@pytest.mark.integration
async def test_discover_layout_has_turnouts_sensors_and_blocks(
    jmri_available: None,
) -> None:
    async with Client() as jmri:
        layout = await jmri.discover()

    assert len(layout.turnouts) > 0, "Basement layout should expose turnouts"
    assert len(layout.sensors) > 0, "Basement layout should expose sensors"
    assert len(layout.blocks) > 0, "Basement layout should expose blocks"

    try:
        turnout = layout.turnouts.by_system_name(_TURNOUT_PROBE_NAME)
    except LayoutEntityNotFound:
        pytest.skip(f"turnout {_TURNOUT_PROBE_NAME!r} not on this layout — cannot probe attributes")
    assert isinstance(turnout.name, str) and turnout.name
    assert turnout.user_name is None or isinstance(turnout.user_name, str)
    assert isinstance(turnout.state, TurnoutState)


@pytest.mark.integration
async def test_discover_roster_populates_within_budget(jmri_available: None) -> None:
    async with Client() as jmri:
        # Warm the shared cached version probe so the timing reflects only the
        # roster fetch (NFR2 roster bound is measured warm, like discover()).
        await jmri.discover_roster()
        start = time.perf_counter()
        roster = await jmri.discover_roster()
        elapsed = time.perf_counter() - start

    assert len(roster) > 0, "Basement layout should expose a roster"
    assert elapsed < 1.0, f"discover_roster() took {elapsed:.3f}s (NFR2 roster budget: 1.0s)"

    # Probe an entry by attribute filter, never positional [0].
    probe = next((e for e in roster.values() if e.function_labels), None)
    if probe is None:
        pytest.skip("no roster entry with function labels on this layout — cannot probe")
    assert isinstance(probe.dcc_address, int)
    assert roster.by_address(probe.dcc_address) is probe


@pytest.mark.integration
async def test_throttle_for_entry_acquires_on_simulator(jmri_available: None) -> None:
    # Plumbing only (Story 9.3): throttle_for_entry acquires and releases a
    # throttle derived from a roster entry. The NCE simulator has no virtual
    # locomotive, so nothing physically moves — set_speed(0.0) just exercises
    # the command path. Physical correctness is hardware-only and manual.
    async with Client() as jmri:
        roster = await jmri.discover_roster()
        entry = next((e for e in roster.values() if e.function_labels), None)
        if entry is None:
            pytest.skip("no roster entry with function labels on this layout — cannot probe")
        async with jmri.throttle_for_entry(entry) as t:
            assert t.dcc_address == entry.dcc_address
            assert t.long == entry.long_address
            await t.set_speed(0.0, forward=True)
