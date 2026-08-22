"""Unit tests for :class:`pyjmri._subscriptions.SubscriptionRegistry`.

These tests use an injected recording send-channel — they do not touch
WebSocket transport, JMRI, or asyncio TaskGroups.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from pyjmri._subscriptions import SubscriptionRegistry


def _make_send_channel() -> tuple[
    Callable[[dict[str, Any]], Awaitable[None]], list[dict[str, Any]]
]:
    """Return ``(send, sent)`` — an async send fn that records into ``sent``."""
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    return send, sent


async def test_ensure_adds_to_set_and_sends_subscribe() -> None:
    send, sent = _make_send_channel()
    registry = SubscriptionRegistry(send=send, ack_timeout=0.01)

    await registry.ensure("turnout", "NT12")

    assert registry.size == 1
    assert sent == [{"type": "turnout", "data": {"name": "NT12"}}]


async def test_ensure_is_idempotent_for_same_pair() -> None:
    send, sent = _make_send_channel()
    registry = SubscriptionRegistry(send=send, ack_timeout=0.01)

    await registry.ensure("turnout", "NT12")
    await registry.ensure("turnout", "NT12")
    await registry.ensure("turnout", "NT12")

    assert registry.size == 1
    assert sent == [{"type": "turnout", "data": {"name": "NT12"}}]


async def test_ensure_distinct_pairs_send_distinct_messages() -> None:
    send, sent = _make_send_channel()
    registry = SubscriptionRegistry(send=send, ack_timeout=0.01)

    await registry.ensure("turnout", "NT12")
    await registry.ensure("sensor", "NS43")
    await registry.ensure("turnout", "NT13")

    assert registry.size == 3
    assert len(sent) == 3
    assert {"type": "turnout", "data": {"name": "NT12"}} in sent
    assert {"type": "sensor", "data": {"name": "NS43"}} in sent
    assert {"type": "turnout", "data": {"name": "NT13"}} in sent


async def test_replay_resends_every_pair_in_registry() -> None:
    send, sent = _make_send_channel()
    registry = SubscriptionRegistry(send=send, ack_timeout=0.01)

    await registry.ensure("turnout", "NT12")
    await registry.ensure("sensor", "NS43")
    await registry.ensure("block", "NB7")

    sent.clear()  # only count messages from replay
    await registry.replay()

    assert len(sent) == 3
    # Use a stable comparison form since set iteration order is unspecified.
    pairs = {(m["type"], m["data"]["name"]) for m in sent}
    assert pairs == {("turnout", "NT12"), ("sensor", "NS43"), ("block", "NB7")}


async def test_replay_on_empty_registry_sends_no_messages(
    caplog: pytest.LogCaptureFixture,
) -> None:
    send, sent = _make_send_channel()
    registry = SubscriptionRegistry(send=send, ack_timeout=0.01)

    with caplog.at_level(logging.DEBUG, logger="pyjmri.subscription"):
        await registry.replay()

    assert sent == []
    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert any(getattr(r, "subscription_count", None) == 0 for r in debug_records), (
        "replay() must emit a DEBUG log with subscription_count even when empty"
    )


async def test_ensure_first_add_emits_info_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    send, _sent = _make_send_channel()
    registry = SubscriptionRegistry(send=send, ack_timeout=0.01)

    with caplog.at_level(logging.INFO, logger="pyjmri.subscription"):
        await registry.ensure("turnout", "NT12")

    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    matching = [
        r
        for r in info_records
        if getattr(r, "entity_type", None) == "turnout"
        and getattr(r, "system_name", None) == "NT12"
    ]
    assert matching, "first ensure() must emit an INFO log with entity_type + system_name"


async def test_ensure_second_call_for_same_pair_emits_no_extra_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    send, _sent = _make_send_channel()
    registry = SubscriptionRegistry(send=send, ack_timeout=0.01)

    await registry.ensure("turnout", "NT12")

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="pyjmri.subscription"):
        await registry.ensure("turnout", "NT12")

    # No new "subscribed" log on repeat ensure.
    assert all(
        getattr(r, "entity_type", None) != "turnout"
        for r in caplog.records
        if r.levelno == logging.INFO
    )


# ---- Subscription-ack behaviour (multi-Client race fix) ----
#
# ensure() must return only after JMRI's subscription ack (the entity
# envelope echoed back on the WS) has been observed via notify_envelope().
# The record-only channels above pass ack_timeout=0.01 to exercise the
# degraded no-ack path quickly; these tests exercise the ack path itself.


async def test_ensure_blocks_until_notify_envelope_releases_it() -> None:
    """ensure() must not return before the ack for its pair arrives."""
    import asyncio

    send, _sent = _make_send_channel()
    registry = SubscriptionRegistry(send=send, ack_timeout=5.0)

    task = asyncio.create_task(registry.ensure("sensor", "IS9"))
    await asyncio.sleep(0)
    assert not task.done(), "ensure() returned before the subscription ack"

    registry.notify_envelope("sensor", "IS9")
    await asyncio.wait_for(task, timeout=1.0)


async def test_ensure_repeat_call_awaits_ack_of_in_flight_subscribe() -> None:
    """A second ensure() for the same pair also waits for the (single) ack."""
    import asyncio

    send, sent = _make_send_channel()
    registry = SubscriptionRegistry(send=send, ack_timeout=5.0)

    first = asyncio.create_task(registry.ensure("sensor", "IS9"))
    await asyncio.sleep(0)
    second = asyncio.create_task(registry.ensure("sensor", "IS9"))
    await asyncio.sleep(0)
    assert not first.done() and not second.done()
    assert len(sent) == 1, "repeat ensure() must not re-send the subscribe"

    registry.notify_envelope("sensor", "IS9")
    await asyncio.wait_for(asyncio.gather(first, second), timeout=1.0)


async def test_ensure_after_ack_returns_immediately() -> None:
    """Once acked, subsequent ensure() calls are synchronous no-ops."""
    send, sent = _make_send_channel()
    registry = SubscriptionRegistry(send=send, ack_timeout=5.0)

    registry.notify_envelope("sensor", "IS9")  # pre-ack is a no-op (unknown pair)
    task_pairs_before = len(sent)

    # Ack arrives while ensure is in flight, then repeat calls are instant.
    import asyncio

    task = asyncio.create_task(registry.ensure("sensor", "IS9"))
    await asyncio.sleep(0)
    registry.notify_envelope("sensor", "IS9")
    await asyncio.wait_for(task, timeout=1.0)

    await registry.ensure("sensor", "IS9")  # must not block or re-send
    assert len(sent) == task_pairs_before + 1


async def test_ensure_ack_timeout_warns_and_proceeds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No ack within ack_timeout: WARNING logged, ensure() still returns."""
    send, _sent = _make_send_channel()
    registry = SubscriptionRegistry(send=send, ack_timeout=0.01)

    with caplog.at_level(logging.WARNING, logger="pyjmri.subscription"):
        await registry.ensure("sensor", "IS9")  # returns despite no ack

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        getattr(r, "entity_type", None) == "sensor" and getattr(r, "system_name", None) == "IS9"
        for r in warnings
    ), "ack timeout must emit a WARNING with entity_type + system_name"


async def test_notify_envelope_for_unknown_pair_is_noop() -> None:
    """Envelopes for pairs never ensured must not raise or register anything."""
    send, _sent = _make_send_channel()
    registry = SubscriptionRegistry(send=send, ack_timeout=0.01)

    registry.notify_envelope("sensor", "IS_NEVER_SUBSCRIBED")

    assert registry.size == 0
