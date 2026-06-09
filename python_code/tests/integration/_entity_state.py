"""Shared raw-``httpx`` entity force-state helpers for integration tests.

Story 7.1 discipline: integration tests pin their target entity by
**system name** (never by positional ``collection[0]`` indexing) and
force a **known starting state** via a raw ``httpx`` POST before they
measure anything — instead of trusting whatever state a previously-run
test happened to leave behind. This is the root-cause fix for the
inter-test interference observed during the v1.0.0 release runs (two
flakes, both on a shared first-entity under suite load).

These force-state helpers are shared by three or more tests
(``test_command_round_trip``, ``test_command_wait_reconnect``,
``test_command_latency``, ``test_reconnect_resilience``), so per the
story's "extract only when 3+ tests share it" rule they live here rather
than being copy-pasted inline.

The integer state codes mirror ``pyjmri._codes`` and are intentionally
inlined per the project convention for integration tests (tests assert
against the wire contract independently of the library's own mapping).
"""

from __future__ import annotations

from urllib.parse import quote

import httpx

from pyjmri import SensorState, TurnoutState

JMRI_BASE_URL = "http://localhost:12080"

# JMRI integer state codes (mirror pyjmri._codes; inlined by convention).
# Turnout: JMRI Turnout.CLOSED == 2, Turnout.THROWN == 4 (see
# pyjmri._codes.TURNOUT_STATE_OUTBOUND). Note these are the OPPOSITE of the
# sensor pair below; an inverted copy in the old reconnect test went
# unnoticed because its turnout path always skipped on the simulator.
_SENSOR_INT_ACTIVE = 2
_SENSOR_INT_INACTIVE = 4
_TURNOUT_INT_CLOSED = 2
_TURNOUT_INT_THROWN = 4


async def force_sensor_state(raw_http: httpx.AsyncClient, name: str, target: SensorState) -> None:
    """POST ``name`` to ``target`` (ACTIVE/INACTIVE); raise on non-2xx.

    ``raw_http`` must be an ``httpx.AsyncClient`` whose ``base_url`` is the
    JMRI web server (``JMRI_BASE_URL``).
    """
    if target is SensorState.ACTIVE:
        code = _SENSOR_INT_ACTIVE
    elif target is SensorState.INACTIVE:
        code = _SENSOR_INT_INACTIVE
    else:
        raise ValueError(f"unsupported SensorState for force: {target!r}")
    resp = await raw_http.post(
        f"/json/v5/sensor/{quote(name, safe='')}",
        json={"type": "sensor", "data": {"name": name, "state": code}},
    )
    resp.raise_for_status()


async def force_turnout_state(raw_http: httpx.AsyncClient, name: str, target: TurnoutState) -> None:
    """POST ``name`` to ``target`` (THROWN/CLOSED); raise on non-2xx.

    ``raw_http`` must be an ``httpx.AsyncClient`` whose ``base_url`` is the
    JMRI web server (``JMRI_BASE_URL``).
    """
    if target is TurnoutState.THROWN:
        code = _TURNOUT_INT_THROWN
    elif target is TurnoutState.CLOSED:
        code = _TURNOUT_INT_CLOSED
    else:
        raise ValueError(f"unsupported TurnoutState for force: {target!r}")
    resp = await raw_http.post(
        f"/json/v5/turnout/{quote(name, safe='')}",
        json={"type": "turnout", "data": {"name": name, "state": code}},
    )
    resp.raise_for_status()
