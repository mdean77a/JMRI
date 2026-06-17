"""Unit tests for ``Client.throttle_for_entry`` resolution (Story 9.3).

``throttle_for_entry`` is a synchronous factory: it resolves a RosterEntry,
name, or address into an *unacquired* :class:`pyjmri.Throttle` whose
``dcc_address`` / ``long`` reflect the matched entry (or the FR55
warn-and-drive fallback). No live JMRI is needed — a non-entered
:class:`pyjmri.Client` constructs the Throttle without touching the network.
Entries are pinned by attribute filter against the live ``roster.json``
fixture; addresses are derived, never hardcoded.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import pytest

from pyjmri import Client, LayoutEntityNotFound, Roster, Throttle
from pyjmri._parsing import parse_roster_entry


def _roster(load_fixture: Callable[[str], list[dict[str, Any]]]) -> Roster:
    return Roster(parse_roster_entry(env) for env in load_fixture("roster"))


def _absent_long_address(roster: Roster) -> int:
    used = {e.dcc_address for e in roster.values()}
    return next(a for a in range(128, 10_000) if a not in used)


def _absent_short_address(roster: Roster) -> int:
    used = {e.dcc_address for e in roster.values()}
    return next(a for a in range(1, 128) if a not in used)


def test_roster_entry_target_reads_addressing_off_the_entry(
    load_fixture: Callable[[str], list[dict[str, Any]]],
) -> None:
    roster = _roster(load_fixture)
    entry = next(e for e in roster.values() if e.long_address)
    client = Client()  # no roster discovered/cached — RosterEntry needs none
    throttle = client.throttle_for_entry(entry)
    assert isinstance(throttle, Throttle)
    assert throttle.dcc_address == entry.dcc_address
    assert throttle.long == entry.long_address


def test_name_resolved_via_cached_roster(
    load_fixture: Callable[[str], list[dict[str, Any]]],
) -> None:
    roster = _roster(load_fixture)
    entry = next(iter(roster.values()))
    client = Client()
    client._roster = roster  # what discover_roster() caches
    throttle = client.throttle_for_entry(entry.name)
    assert throttle.dcc_address == entry.dcc_address
    assert throttle.long == entry.long_address


def test_name_resolved_via_roster_argument(
    load_fixture: Callable[[str], list[dict[str, Any]]],
) -> None:
    roster = _roster(load_fixture)
    entry = next(iter(roster.values()))
    client = Client()  # nothing cached; supplied explicitly
    throttle = client.throttle_for_entry(entry.name, roster=roster)
    assert throttle.dcc_address == entry.dcc_address


def test_name_miss_raises_layout_entity_not_found(
    load_fixture: Callable[[str], list[dict[str, Any]]],
) -> None:
    client = Client()
    client._roster = _roster(load_fixture)
    with pytest.raises(LayoutEntityNotFound):
        client.throttle_for_entry("no such locomotive name")


def test_name_with_no_roster_available_raises() -> None:
    client = Client()  # no roster cached, none passed
    with pytest.raises(LayoutEntityNotFound):
        client.throttle_for_entry("any name")


def test_address_hit_reads_addressing_off_the_entry(
    load_fixture: Callable[[str], list[dict[str, Any]]],
) -> None:
    roster = _roster(load_fixture)
    # First entry overall: guaranteed to be the by_address winner for its own
    # address (the fixture has duplicate addresses resolved first-wins).
    entry = next(iter(roster.values()))
    client = Client()
    client._roster = roster
    throttle = client.throttle_for_entry(entry.dcc_address)
    assert throttle.dcc_address == entry.dcc_address
    assert throttle.long == entry.long_address


def test_address_miss_warns_and_drives_long_convention(
    load_fixture: Callable[[str], list[dict[str, Any]]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    roster = _roster(load_fixture)
    client = Client()
    client._roster = roster
    absent = _absent_long_address(roster)
    with caplog.at_level(logging.WARNING):
        throttle = client.throttle_for_entry(absent)
    assert throttle.dcc_address == absent
    assert throttle.long is True  # address > 127 => long by JMRI convention
    assert any("not in the roster" in r.message for r in caplog.records)


def test_address_miss_short_convention(
    load_fixture: Callable[[str], list[dict[str, Any]]],
) -> None:
    roster = _roster(load_fixture)
    client = Client()
    client._roster = roster
    absent = _absent_short_address(roster)
    throttle = client.throttle_for_entry(absent)
    assert throttle.long is False  # address <= 127 => short


def test_address_miss_with_no_roster_does_not_raise(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = Client()  # no roster at all
    with caplog.at_level(logging.WARNING):
        throttle = client.throttle_for_entry(9001)
    assert throttle.dcc_address == 9001
    assert throttle.long is True
    assert any("not in the roster" in r.message for r in caplog.records)


def test_long_override_on_entry_path(
    load_fixture: Callable[[str], list[dict[str, Any]]],
) -> None:
    roster = _roster(load_fixture)
    entry = next(e for e in roster.values() if e.long_address)
    client = Client()
    throttle = client.throttle_for_entry(entry, long=False)
    assert throttle.long is False  # explicit override beats the entry value


def test_long_override_on_address_miss(
    load_fixture: Callable[[str], list[dict[str, Any]]],
) -> None:
    client = Client()
    # A >127 address would default long; force short via override.
    throttle = client.throttle_for_entry(9001, long=False)
    assert throttle.long is False


def test_bool_target_is_rejected() -> None:
    client = Client()
    with pytest.raises(TypeError):
        client.throttle_for_entry(True)


def test_returns_same_throttle_type_as_raw_factory(
    load_fixture: Callable[[str], list[dict[str, Any]]],
) -> None:
    roster = _roster(load_fixture)
    entry = next(iter(roster.values()))
    client = Client()
    from_entry = client.throttle_for_entry(entry)
    from_raw = client.throttle(entry.dcc_address, long=entry.long_address)
    assert type(from_entry) is type(from_raw) is Throttle


async def test_throttle_for_entry_acquires_through_throttle_acquire(
    load_fixture: Callable[[str], list[dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-15: the returned Throttle acquires through the *same*
    ``throttle_acquire`` path as the raw factory.

    Asserted at the unit level via the existing handle seams (no live JMRI):
    ``throttle_for_entry`` binds the Throttle to the real Client, so we
    monkeypatch the Client's ``throttle_acquire`` / ``spawn_supervised`` /
    ``throttle_release`` to record the acquire call. Entering the context
    must drive the entry's derived address/addressing through that one seam.
    """
    roster = _roster(load_fixture)
    entry = next(iter(roster.values()))
    client = Client()
    client._roster = roster

    acquire_calls: list[tuple[int, bool]] = []

    async def _record_acquire(dcc_address: int, *, long: bool) -> str:
        acquire_calls.append((dcc_address, long))
        return f"pyjmri-{dcc_address}-test"

    async def _noop_release(throttle_id: str) -> None:
        return None

    def _spawn(coro: Coroutine[Any, Any, None], *, name: str | None = None) -> asyncio.Task[None]:
        return asyncio.create_task(coro, name=name)

    monkeypatch.setattr(client, "throttle_acquire", _record_acquire)
    monkeypatch.setattr(client, "throttle_release", _noop_release)
    monkeypatch.setattr(client, "spawn_supervised", _spawn)

    async with client.throttle_for_entry(entry):
        pass

    assert acquire_calls == [(entry.dcc_address, entry.long_address)]
