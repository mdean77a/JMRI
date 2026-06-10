"""Integration test: ``Client.discover_operations()`` against a running JMRI.

Requires JMRI on ``localhost:12080`` with Operations data loaded (the
basement simulator profile has it: 3 locations / 4 engines / 3 cars /
1 train). Skipped via the ``jmri_available`` session fixture when JMRI is
unreachable. The FR50 empty-collection path is covered hermetically in
``tests/unit/test_discover_operations.py`` (the live basement profile now
has Operations data and can no longer produce empty collections). See
architecture §Operations Subsystem (Read-Only).
"""

from __future__ import annotations

import time

import pytest

from pyjmri import Client, Operations


@pytest.mark.integration
async def test_discover_operations_returns_populated_container(
    jmri_available: None,
) -> None:
    async with Client() as jmri:
        ops = await jmri.discover_operations()

    assert isinstance(ops, Operations)
    assert len(ops.locations) > 0, "basement profile should expose Operations locations"
    assert len(ops.trains) > 0, "basement profile should expose Operations trains"
    assert len(ops.cars) > 0, "basement profile should expose Operations cars"
    assert len(ops.engines) > 0, "basement profile should expose Operations engines"


@pytest.mark.integration
async def test_discover_operations_resolves_by_system_and_user_name(
    jmri_available: None,
) -> None:
    async with Client() as jmri:
        ops = await jmri.discover_operations()

    # Locations/trains carry both names: a named location resolves by user
    # AND system name to the same object. Pin by attribute, not position
    # (Story 7.1 lesson) — find the first location that has a user name.
    named_location = next(
        (loc for loc in ops.locations.values() if loc.user_name is not None),
        None,
    )
    if named_location is None:
        pytest.skip("no location with a user name on this layout — cannot probe dual-name")
    assert ops.locations[named_location.user_name] is named_location
    assert ops.locations[named_location.name] is named_location

    # Cars have no user name and are keyed by road+number (system name).
    car = next(iter(ops.cars.values()), None)
    if car is None:
        pytest.skip("no cars configured on this layout — cannot probe car identity")
    assert car.user_name is None
    assert ops.cars[car.name] is car


@pytest.mark.integration
async def test_discover_operations_completes_within_nfr2_bound(
    jmri_available: None,
) -> None:
    async with Client() as jmri:
        # Warm the version check via discover() so the timed call below
        # maps to NFR2's "additional 1 second" Operations budget.
        await jmri.discover()
        start = time.perf_counter()
        ops = await jmri.discover_operations()
        elapsed = time.perf_counter() - start

    assert isinstance(ops, Operations)
    assert elapsed < 1.0, f"discover_operations() took {elapsed:.3f}s (NFR2 budget: 1.0s)"
