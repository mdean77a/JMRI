"""Integration tests for Throttle acquire/release lifecycle (Stories 5.1, 5.2, 5.3).

All tests in this module exercise library / JMRI plumbing only. The NCE
simulator accepts throttle acquire, release, and update envelopes and
emits the standard JSON v5 responses, but has no virtual decoder — no
physical locomotive behavior is observable on the simulator. The
single-throttle tests from Story 5.1 (acquire / release / __aexit__ /
acquire-failure) and the speed + function plumbing test from Story 5.2
share this constraint; Story 5.3 adds multi-throttle tests under the
same rule.

NCE open-loop also applies on real hardware: JMRI reports "last
commanded" throttle state, not observed motion. Even when the test
suite runs against a layout with real DCC decoders, asserting on
``Client``-side state would add no information beyond "no exception was
raised." For that reason, none of these tests attempt JMRI-state-read
verification of throttle commands.

Physical correctness of throttle commands (does the locomotive actually
move?) is owned by the hardware-mode validation protocol in
``CONTRIBUTING.md``'s release checklist (Story 6.5, currently backlog).
A reviewer reading these tests must NOT mistake "tests pass against the
simulator" for "throttles drive real locomotives." That claim requires
the hardware-mode procedure documented in ``CONTRIBUTING.md``.

Per Story 5.1 Task 0 spike (2026-05-21): JMRI's throttle API is
WebSocket-only — all HTTP verbs on ``/json/v5/throttle*`` return 405.
The library uses ``WSConnection`` for acquire / release / update; these
tests exercise that path end-to-end against the running JMRI.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack

import httpx
import pytest

from pyjmri import Client, ThrottleAcquireFailed, ThrottleReleased

pytestmark = pytest.mark.integration


async def _fetch_test_dcc_addresses(count: int = 2) -> list[tuple[int, bool]]:
    """Fetch ``count`` DCC ``(address, long)`` tuples from JMRI's live roster.

    Calls ``pytest.skip`` if the roster has fewer than ``count`` entries —
    layout-agnostic per Epic 5 AC9. Uses raw ``httpx`` (same pattern as
    ``test_reconnect_resilience.py`` etc.) because pyjmri has no public
    ``Layout.roster`` API in v1 — that surface is Growth-deferred.

    Returns:
        First ``count`` entries from JMRI's ``/json/v5/roster`` response,
        as ``[(dcc_address, is_long_address), ...]``.
    """
    async with httpx.AsyncClient(base_url="http://localhost:12080") as raw_http:
        resp = await raw_http.get("/json/v5/roster")
        resp.raise_for_status()
        envelopes = resp.json()
    entries: list[tuple[int, bool]] = []
    for envelope in envelopes:
        data = envelope["data"]
        entries.append((int(data["address"]), bool(data["isLongAddress"])))
    if len(entries) < count:
        pytest.skip(f"roster has {len(entries)} entries; multi-throttle test requires >= {count}")
    return entries[:count]


async def test_throttle_acquire_release_roundtrip(jmri_available: None) -> None:
    """Acquire DCC 3 (a conventional safe test address), confirm the
    keep-alive task is alive in the Client's TaskGroup, then release
    explicitly. Re-acquire should succeed (no JMRI-side lock from us)."""
    async with Client() as jmri:
        throttle = jmri.throttle(3, long=False)
        async with throttle:
            assert throttle._throttle_id is not None
            keepalive_task = throttle._keepalive_task
            assert keepalive_task is not None
            # The keep-alive task should be alive (the no-op stub is
            # awaiting an asyncio.Event that's never set).
            assert not keepalive_task.done()
            await throttle.release()
            await asyncio.sleep(0)
            assert keepalive_task.done()
            assert throttle._released is True

        # Re-acquire on the same Client should succeed.
        throttle2 = jmri.throttle(3, long=False)
        async with throttle2:
            assert throttle2._throttle_id is not None
            assert throttle2._throttle_id != throttle._throttle_id


async def test_throttle_aexit_releases_cleanly(jmri_available: None) -> None:
    """Exit via __aexit__ (no explicit release) cancels the keep-alive
    and sends the release envelope. After exit, _released is True."""
    async with Client() as jmri:
        throttle = jmri.throttle(3, long=False)
        keepalive_task: asyncio.Task[None] | None = None
        async with throttle:
            keepalive_task = throttle._keepalive_task
            assert keepalive_task is not None
            assert not keepalive_task.done()
        # Outside the `async with`: keep-alive cancelled, release sent.
        await asyncio.sleep(0)
        assert keepalive_task is not None
        assert keepalive_task.done()
        assert throttle._released is True


async def test_throttle_acquire_failure_raises_throttle_acquire_failed(
    jmri_available: None,
) -> None:
    """JMRI rejects address 99,999 with a `type:error` envelope (Task 0
    spike confirmed). The library surfaces this as
    :class:`ThrottleAcquireFailed`."""
    async with Client() as jmri:
        throttle = jmri.throttle(99999, long=True)
        with pytest.raises(ThrottleAcquireFailed) as excinfo:
            async with throttle:
                pass  # pragma: no cover — acquire raises
        # JMRI's error envelope is surfaced in .context.
        assert excinfo.value.context.get("code") == 400
        assert "invalid" in str(excinfo.value.context.get("jmri_message", "")).lower()


async def test_set_speed_and_set_function_plumbing(jmri_available: None) -> None:
    """Story 5.2 plumbing test: send set_speed / set_function updates over
    WS without raising. JMRI accepts the envelopes; the simulator has no
    virtual decoder, so no physical loco motion is asserted. Story 5.3
    covers physical correctness on hardware."""
    async with Client() as jmri:
        throttle = jmri.throttle(3, long=False)
        async with throttle as t:
            # Drive forward, headlight on, then stop, headlight off. Each
            # call writes a single WS envelope; JMRI's per-field delta echoes
            # are silently consumed by the dispatcher.
            await t.set_speed(0.1, forward=True)
            await t.set_function(0, True)
            await t.set_speed(0.0, forward=True)
            await t.set_function(0, False)


async def test_multi_throttle_parallel_acquire_drive_release(
    jmri_available: None,
) -> None:
    """Acquire 2 throttles in parallel via AsyncExitStack; drive speed +
    function on each; verify clean parallel release and post-release
    ``ThrottleReleased`` invariant on every throttle."""
    addrs = await _fetch_test_dcc_addresses(2)
    async with Client() as jmri:
        throttle_objs = [jmri.throttle(addr, long=long_flag) for addr, long_flag in addrs]
        async with AsyncExitStack() as stack:
            throttles = await asyncio.gather(
                *[stack.enter_async_context(t) for t in throttle_objs],
            )
            # Sequential drive per throttle: the parallel invariant under
            # test is the acquire, not the drive phase. Sequential drive
            # keeps assertions readable.
            for t in throttles:
                await t.set_speed(0.1, forward=True)
                await t.set_function(0, True)
                await t.set_speed(0.0, forward=True)
                await t.set_function(0, False)
        # AsyncExitStack has unwound: every throttle is released LIFO.
        await asyncio.sleep(0)
        for t in throttle_objs:
            assert t._released is True
            with pytest.raises(ThrottleReleased) as excinfo:
                await t.set_speed(0.1, forward=True)
            assert excinfo.value.context["dcc_address"] == t.dcc_address
            with pytest.raises(ThrottleReleased) as excinfo:
                await t.set_function(0, True)
            assert excinfo.value.context["dcc_address"] == t.dcc_address


async def test_multi_throttle_keepalive_tasks_cancel_on_release(
    jmri_available: None,
) -> None:
    """Two parallel-acquired throttles each spawn a supervised keep-alive
    task; on stack exit, both tasks are cancelled and removed from the
    running event loop."""
    addrs = await _fetch_test_dcc_addresses(2)
    async with Client() as jmri:
        throttle_objs = [jmri.throttle(addr, long=long_flag) for addr, long_flag in addrs]
        # Save keep-alive task refs before release — _release_impl sets
        # the throttle's _keepalive_task attribute back to None.
        keepalive_refs: list[asyncio.Task[None]] = []
        async with AsyncExitStack() as stack:
            throttles = await asyncio.gather(
                *[stack.enter_async_context(t) for t in throttle_objs],
            )
            for t in throttles:
                keepalive = t._keepalive_task
                assert keepalive is not None
                assert not keepalive.done()
                assert keepalive.get_name() == (f"pyjmri-throttle-keepalive-{t.dcc_address}")
                keepalive_refs.append(keepalive)
            keepalive_tasks_inside = [
                task
                for task in asyncio.all_tasks()
                if task.get_name().startswith("pyjmri-throttle-keepalive-")
            ]
            assert len(keepalive_tasks_inside) == 2
        # Outside the stack: cancelled tasks finalize on the next loop tick.
        await asyncio.sleep(0)
        for keepalive in keepalive_refs:
            assert keepalive.done()
        keepalive_tasks_after = [
            task
            for task in asyncio.all_tasks()
            if task.get_name().startswith("pyjmri-throttle-keepalive-")
        ]
        assert keepalive_tasks_after == []


async def test_multi_throttle_partial_acquire_failure_releases_siblings(
    jmri_available: None,
) -> None:
    """Partial-acquire failure: AsyncExitStack must release whatever
    entered before the failure landed; never-acquired siblings are not
    released (and cannot be — they hold no JMRI session)."""
    valid_addrs = await _fetch_test_dcc_addresses(2)
    async with Client() as jmri:
        throttle_valid_1 = jmri.throttle(valid_addrs[0][0], long=valid_addrs[0][1])
        throttle_valid_2 = jmri.throttle(valid_addrs[1][0], long=valid_addrs[1][1])
        throttle_invalid = jmri.throttle(99999, long=True)
        valid_throttles = [throttle_valid_1, throttle_valid_2]

        with pytest.raises((ThrottleAcquireFailed, ExceptionGroup)):
            async with AsyncExitStack() as stack:
                await asyncio.gather(
                    stack.enter_async_context(throttle_valid_1),
                    stack.enter_async_context(throttle_valid_2),
                    stack.enter_async_context(throttle_invalid),
                )
        # Let any in-flight enter_async_context tasks settle before
        # inspecting state — asyncio.gather propagates the first
        # exception without cancelling siblings, so a sibling acquire
        # may finalize after the stack has already closed.
        await asyncio.sleep(0)
        # No leaks: every valid throttle that actually acquired a JMRI
        # session must have been released by the stack's LIFO unwind.
        # Throttles that never entered (acquire was still in-flight when
        # the stack closed) hold no session, so their ``_released`` flag
        # staying False is acceptable.
        for t in valid_throttles:
            if t._throttle_id is not None:
                assert t._released is True
        # The invalid throttle's __aenter__ raised before assigning
        # _throttle_id; release was never called.
        assert throttle_invalid._throttle_id is None
        assert throttle_invalid._released is False
