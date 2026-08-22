"""Integration test bootstrap. See architecture §Test Harness."""

from __future__ import annotations

import contextlib
import re
import socket
from collections.abc import AsyncIterator
from urllib.parse import quote

import httpx
import pytest
from _entity_state import JMRI_BASE_URL, force_sensor_state

from pyjmri import SensorState


def _jmri_listening(host: str = "localhost", port: int = 12080) -> bool:
    """Return True iff a TCP connection to the given address completes."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def jmri_available() -> None:
    """Skip integration tests unless JMRI is reachable on localhost:12080."""
    if not _jmri_listening():
        pytest.skip(
            "JMRI is not reachable on localhost:12080 — "
            "start JMRI with the web server enabled to run integration tests."
        )


@pytest.fixture
async def provisioned_internal_sensor(
    jmri_available: None,
    request: pytest.FixtureRequest,
) -> AsyncIterator[str]:
    """Provision a dedicated internal sensor for one test; yield its system name.

    A latency / round-trip test needs an internal sensor it fully owns.
    On a real panel every *discovered* internal sensor is a meaningful
    layout sensor (occupancy, staging, routes) that drives signals and
    LogixNG, so toggling one is both invasive and flake-prone — the
    watching logic can move the sensor out from under the measurement.
    Hard-pinning a name like ``IS1`` also breaks on any layout that does
    not happen to define it.

    JMRI provisions an internal sensor on first ``PUT`` with no panel
    edit; it lives only in memory and is gone on the next JMRI restart
    (this fixture never saves the panel). The name is derived from the
    test's node id, so every test gets a unique, collision-proof target —
    the Story 7.1 non-overlap discipline, made installation-agnostic.
    """
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", request.node.name).strip("_").upper()
    name = f"IS:PYJMRI_TEST_{suffix}"
    async with httpx.AsyncClient(base_url=JMRI_BASE_URL) as raw_http:
        resp = await raw_http.put(
            f"/json/v5/sensor/{quote(name, safe='')}",
            json={"type": "sensor", "data": {"name": name}},
        )
        resp.raise_for_status()
        # Known starting state so the first measured transition is real.
        await force_sensor_state(raw_http, name, SensorState.INACTIVE)
    yield name
    # Best-effort teardown: return it to INACTIVE. JMRI's JSON API has no
    # sensor-delete; the in-memory internal sensor simply vanishes on the
    # next JMRI restart, and is never written to the panel XML by this test.
    with contextlib.suppress(Exception):
        async with httpx.AsyncClient(base_url=JMRI_BASE_URL) as raw_http:
            await force_sensor_state(raw_http, name, SensorState.INACTIVE)
