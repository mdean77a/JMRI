"""Integration tests for Throttle acquire/release lifecycle (Story 5.1).

These tests exercise library / JMRI plumbing only. The NCE simulator
accepts throttle acquire and release envelopes and emits the standard
JSON v5 responses, but has no virtual decoder — no physical locomotive
behavior is exercised here. Story 5.3 covers multi-throttle plumbing +
hardware-mode physical verification per the CONTRIBUTING.md release
checklist.

Per Story 5.1 Task 0 spike (2026-05-21): JMRI's throttle API is
WebSocket-only — all HTTP verbs on ``/json/v5/throttle*`` return 405.
The library uses ``WSConnection`` for acquire/release; this file
exercises that path end-to-end against the running JMRI.
"""

from __future__ import annotations

import asyncio

import pytest

from pyjmri import Client, ThrottleAcquireFailed

pytestmark = pytest.mark.integration


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
