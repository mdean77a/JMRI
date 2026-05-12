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
    registry = SubscriptionRegistry(send=send)

    await registry.ensure("turnout", "NT12")

    assert registry.size == 1
    assert sent == [{"type": "turnout", "data": {"name": "NT12"}}]


async def test_ensure_is_idempotent_for_same_pair() -> None:
    send, sent = _make_send_channel()
    registry = SubscriptionRegistry(send=send)

    await registry.ensure("turnout", "NT12")
    await registry.ensure("turnout", "NT12")
    await registry.ensure("turnout", "NT12")

    assert registry.size == 1
    assert sent == [{"type": "turnout", "data": {"name": "NT12"}}]


async def test_ensure_distinct_pairs_send_distinct_messages() -> None:
    send, sent = _make_send_channel()
    registry = SubscriptionRegistry(send=send)

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
    registry = SubscriptionRegistry(send=send)

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
    registry = SubscriptionRegistry(send=send)

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
    registry = SubscriptionRegistry(send=send)

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
    registry = SubscriptionRegistry(send=send)

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
