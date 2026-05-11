"""Integration smoke test: ``Client.discover()`` against a running JMRI.

Requires JMRI on ``localhost:12080``. Skipped via the ``jmri_available``
session fixture when unreachable. See architecture §Test Harness.
"""

from __future__ import annotations

import time

import pytest

from pyjmri import Client, Layout, TurnoutState


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

    turnout = next(iter(layout.turnouts.values()))
    assert isinstance(turnout.name, str) and turnout.name
    assert turnout.user_name is None or isinstance(turnout.user_name, str)
    assert isinstance(turnout.state, TurnoutState)
