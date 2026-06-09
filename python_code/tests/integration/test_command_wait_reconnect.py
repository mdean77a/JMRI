"""Integration test: a ``wait_for_jmri_state=True`` operation survives a WS reconnect.

Sequence (AC8 / AC11 of Story 4.2):

  1. Discover; pick the first turnout (skip if none / non-binary state).
  2. Start ``turnout.set_state(target, wait_for_jmri_state=True)`` as a Task,
     wrapped in ``asyncio.wait_for(..., timeout=15.0)`` so a non-echoing
     JMRI cannot hang the suite.
  3. Brief sleep so ensure_subscription + HTTP command + waiter registration
     have all started before the disconnect lands.
  4. Force-disconnect the WS via ``jmri._force_disconnect()`` (the same
     primitive ``test_reconnect_resilience.py`` uses).
  5. Poll for the reconnect INFO log (``pyjmri.reconnect``).
  6. Wait for the task to complete. The post-reconnect ``replay()`` re-
     subscribes the turnout, JMRI emits the current (commanded) state on
     subscribe, ``_on_event`` → ``_waiters.fanout(...)`` resolves the
     pending future. Caller resumes (NFR5 level-triggered semantics).
  7. Assert cached state matches the commanded target.

Story 3.4 carry-forward: the ``sensor.state`` stale-cache concern
(deferred-work.md, "Deferred from: code review of 3-4") does NOT apply
here — ``original`` is read before the disconnect; we don't re-read
mid-test.

Marker: ``integration`` only (NOT ``slow``). Skips cleanly if no turnouts.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import httpx
import pytest
from _entity_state import JMRI_BASE_URL, force_turnout_state

from pyjmri import Client, LayoutEntityNotFound, TurnoutState

pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)

# Pinned target (Story 7.1 AC2): NT104 — distinct from the turnouts used
# by the other turnout tests so no two contend for one object in a run.
_TURNOUT_NAME = "NT104"

_RECONNECT_WAIT_S = 15.0
_RECONNECT_POLL_INTERVAL_S = 0.2
_RECONNECT_INFO_MSG = "WebSocket reconnected; replaying subscriptions"
_PRE_DISCONNECT_SLEEP_S = 0.2  # let ensure → command → register complete
# 15.0 s ≥ 10 s (Story 7.1 AC4): must comfortably exceed reconnect +
# subscription-replay latency, which itself can take several seconds.
_WAIT_TIMEOUT_S = 15.0


async def test_wait_for_jmri_state_resolves_after_ws_reconnect(
    jmri_available: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with Client() as jmri:
        layout = await jmri.discover()
        try:
            turnout = layout.turnouts.by_system_name(_TURNOUT_NAME)
        except LayoutEntityNotFound:
            pytest.skip(
                f"turnout {_TURNOUT_NAME!r} not on this layout — "
                "required for the wait-survives-reconnect test"
            )

        # AC3: force CLOSED via raw httpx and confirm via authoritative
        # HTTP GET, then command THROWN — never trust leaked state.
        # async with ensures aclose() on all exit paths (including setup errors).
        async with httpx.AsyncClient(base_url=JMRI_BASE_URL) as raw_http:
            await force_turnout_state(raw_http, turnout.name, TurnoutState.CLOSED)
            assert await turnout.get_state() is TurnoutState.CLOSED
            target = TurnoutState.THROWN

            try:
                task = asyncio.create_task(
                    asyncio.wait_for(
                        turnout.set_state(target, wait_for_jmri_state=True),
                        timeout=_WAIT_TIMEOUT_S,
                    )
                )
                try:
                    # Let ensure_subscription + HTTP command + waiter registration
                    # complete before forcing the disconnect.
                    await asyncio.sleep(_PRE_DISCONNECT_SLEEP_S)

                    with caplog.at_level(logging.INFO, logger="pyjmri.reconnect"):
                        await jmri._force_disconnect()

                        loop = asyncio.get_running_loop()
                        deadline = loop.time() + _RECONNECT_WAIT_S
                        reconnect_records: list[logging.LogRecord] = []
                        while loop.time() < deadline and not reconnect_records:
                            reconnect_records = [
                                r
                                for r in caplog.records
                                if r.name == "pyjmri.reconnect"
                                and r.levelno == logging.INFO
                                and _RECONNECT_INFO_MSG in r.getMessage()
                            ]
                            if not reconnect_records:
                                await asyncio.sleep(_RECONNECT_POLL_INTERVAL_S)
                        if not reconnect_records:
                            pytest.fail(
                                f"WS did not reconnect within {_RECONNECT_WAIT_S:.0f} s "
                                "after _force_disconnect()"
                            )

                    # The wait must complete after the post-reconnect subscription
                    # replay surfaces the current state and fanout resolves the
                    # pending future.
                    await task

                    # Cached state reflects the commanded target.
                    assert turnout.state is target, (
                        f"expected cached state {target.name}; got {turnout.state.name}"
                    )
                except TimeoutError:
                    pytest.fail(
                        f"wait_for_jmri_state=True did not resolve within {_WAIT_TIMEOUT_S:.0f} s "
                        "after reconnect; subscription replay may not be surfacing current state"
                    )
            finally:
                # Restore to CLOSED deterministically via raw httpx — restoration
                # shouldn't add new failure modes to a test whose purpose is the
                # wait path.
                with contextlib.suppress(Exception):
                    await force_turnout_state(raw_http, turnout.name, TurnoutState.CLOSED)
