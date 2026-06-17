"""Unit tests for roster discovery — the standalone ``Client.discover_roster()``.

Mirrors ``test_discover_operations.py``: drives the ``patch_http_factory``
fake HTTP transport so no live JMRI is required. Covers the populated path
(against the Story 9.1 captured ``roster.json`` fixture), the version-probe
gate shared with ``discover()``, ``by_address`` hit/miss, name lookup, the
FR57 graceful-degrade guarantee (a fetch failure returns an empty ``Roster``
rather than raising — and cannot affect a separate ``discover()`` call), the
empty and malformed-entry paths (FR58), the first-wins address-collision
rule, and the invariant that roster discovery does NOT touch the WS-dispatch
index.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest

from pyjmri import Client, LayoutEntityNotFound, Roster, RosterEntry

LoadFixture = Callable[[str], list[dict[str, Any]]]

_VERSION_PATH = "/json/v5/networkService"
_ROSTER_PATH = "/json/v5/roster"


def _version_payload(version: str = "5.14.0") -> list[dict[str, Any]]:
    """Return the JMRI ``/json/v5/networkService`` envelope shape."""
    return [
        {
            "type": "networkService",
            "data": {
                "name": "_http._tcp.local.",
                "port": 12080,
                "type": "_http._tcp.local.",
                "version": f"{version}+Rtest",
                "json": "5.4.0",
                "jmri": version,
                "node": "test-node",
                "path": "/",
            },
        }
    ]


Responder = Callable[[str], dict[str, Any] | list[dict[str, Any]]]


def _roster_responder(roster_payload: list[dict[str, Any]]) -> Responder:
    """Version payload for the version path, ``roster_payload`` for the roster, [] else."""

    def _respond(path: str) -> dict[str, Any] | list[dict[str, Any]]:
        if path == _VERSION_PATH:
            return _version_payload()
        if path == _ROSTER_PATH:
            return roster_payload
        return []

    return _respond


def _mk_entry(name: str, dcc_address: int) -> RosterEntry:
    """Minimal RosterEntry for direct container construction (collision tests)."""
    return RosterEntry(
        name=name,
        user_name=None,
        dcc_address=dcc_address,
        long_address=dcc_address > 127,
        road_name=None,
        road_number=None,
        model=None,
        mfg=None,
        owner=None,
        comment=None,
        image_path=None,
        max_speed_pct=None,
        decoder_family=None,
        decoder_model=None,
        function_labels=(),
    )


# ---- Populated path against the Story 9.1 captured fixture (AC-1, AC-10) ----


async def test_discover_roster_populates(
    patch_http_factory: list[Any],
    load_fixture: LoadFixture,
) -> None:
    roster_fixture = load_fixture("roster")
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _roster_responder(roster_fixture)
        roster = await jmri.discover_roster()

    assert isinstance(roster, Roster)
    # Count derived from the fixture, never hardcoded (AC-10).
    assert len(roster) == len(roster_fixture)
    assert _ROSTER_PATH in fake.probed


async def test_version_probe_shared_across_discover_and_discover_roster(
    patch_http_factory: list[Any],
    load_fixture: LoadFixture,
) -> None:
    # The cached >= 5.14 gate is shared: discover() then discover_roster()
    # on the same Client probes the version endpoint exactly once (AC-2).
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _roster_responder(load_fixture("roster"))
        await jmri.discover()
        await jmri.discover_roster()

    assert fake.probed.count(_VERSION_PATH) == 1


# ---- by_address: get()-style find (AC-6) ----


async def test_by_address_hit(
    patch_http_factory: list[Any],
    load_fixture: LoadFixture,
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _roster_responder(load_fixture("roster"))
        roster = await jmri.discover_roster()

    # Pin a probe entry by attribute, never positional [0] (AC-10).
    probe = next(e for e in roster.values() if e.function_labels)
    assert roster.by_address(probe.dcc_address) is probe


async def test_by_address_miss_returns_none_and_warns(
    patch_http_factory: list[Any],
    load_fixture: LoadFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _roster_responder(load_fixture("roster"))
        roster = await jmri.discover_roster()

    # An address guaranteed absent: one past the current max (layout-agnostic).
    absent = max(e.dcc_address for e in roster.values()) + 1
    with caplog.at_level(logging.WARNING, logger="pyjmri.roster"):
        result = roster.by_address(absent)

    assert result is None
    assert any(str(absent) in rec.message for rec in caplog.records)


# ---- Name lookup is Mapping-style and raises on a miss (AC-5) ----


async def test_name_lookup_hit_and_miss(
    patch_http_factory: list[Any],
    load_fixture: LoadFixture,
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _roster_responder(load_fixture("roster"))
        roster = await jmri.discover_roster()

    probe = next(e for e in roster.values() if e.function_labels)
    assert roster[probe.name] is probe
    with pytest.raises(LayoutEntityNotFound):
        roster["no-such-roster-id"]


# ---- FR57: graceful-degrade — the headline guarantee (AC-4) ----


async def test_roster_fetch_failure_returns_empty_roster(
    patch_http_factory: list[Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    def respond(path: str) -> dict[str, Any] | list[dict[str, Any]]:
        if path == _VERSION_PATH:
            return _version_payload()
        if path == _ROSTER_PATH:
            raise ConnectionError("roster endpoint exploded")
        return []

    with caplog.at_level(logging.WARNING, logger="pyjmri.client"):
        async with Client() as jmri:
            fake = patch_http_factory[0]
            fake.next_response = respond
            # Must NOT raise — degrades to an empty Roster.
            roster = await jmri.discover_roster()

    assert isinstance(roster, Roster)
    assert len(roster) == 0
    assert any("roster discovery failed" in rec.message for rec in caplog.records)


async def test_roster_failure_does_not_affect_discover(
    patch_http_factory: list[Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Because discover_roster() is a separate call, a roster-endpoint failure
    # leaves a sibling discover() fully populated (FR8-FR12 unaffected).
    turnout_env = {"type": "turnout", "data": {"name": "NT400", "userName": None, "state": 0}}

    def respond(path: str) -> dict[str, Any] | list[dict[str, Any]]:
        if path == _VERSION_PATH:
            return _version_payload()
        if path == "/json/v5/turnout":
            return [turnout_env]
        if path == _ROSTER_PATH:
            raise ConnectionError("roster endpoint exploded")
        return []

    with caplog.at_level(logging.WARNING, logger="pyjmri.client"):
        async with Client() as jmri:
            fake = patch_http_factory[0]
            fake.next_response = respond
            layout = await jmri.discover()
            roster = await jmri.discover_roster()

    assert len(layout.turnouts) == 1
    assert layout.turnouts["NT400"].name == "NT400"
    assert len(roster) == 0
    assert any("roster discovery failed" in rec.message for rec in caplog.records)


# ---- FR58: empty roster + per-entry skip-and-continue (AC-8) ----


async def test_empty_roster_is_not_an_error(
    patch_http_factory: list[Any],
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _roster_responder([])
        roster = await jmri.discover_roster()

    assert isinstance(roster, Roster)
    assert len(roster) == 0


async def test_malformed_entry_skipped_good_entries_load(
    patch_http_factory: list[Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    good = {
        "type": "rosterEntry",
        "data": {"name": "Good Loco", "address": "42", "isLongAddress": False},
    }
    # Non-decimal address -> parse_roster_entry raises JMRIProtocolError for this one only.
    bad = {
        "type": "rosterEntry",
        "data": {"name": "Bad Loco", "address": "1A2B", "isLongAddress": False},
    }

    with caplog.at_level(logging.WARNING, logger="pyjmri.client"):
        async with Client() as jmri:
            fake = patch_http_factory[0]
            fake.next_response = _roster_responder([good, bad])
            roster = await jmri.discover_roster()

    assert len(roster) == 1
    assert roster["Good Loco"].dcc_address == 42
    assert any("skipping malformed roster entry" in rec.message for rec in caplog.records)


async def test_non_dict_entry_is_skipped_not_whole_roster(
    patch_http_factory: list[Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A non-dict list element must be skipped per-entry (FR58/AC-8), NOT collapse
    # the whole roster: parse_roster_entry raises JMRIProtocolError (caught by the
    # inner skip-and-continue), so the good entry still loads.
    good = {
        "type": "rosterEntry",
        "data": {"name": "Good Loco", "address": "42", "isLongAddress": False},
    }
    bad = "this is not an envelope object"

    with caplog.at_level(logging.WARNING, logger="pyjmri.client"):
        async with Client() as jmri:
            fake = patch_http_factory[0]
            fake.next_response = _roster_responder([good, bad])
            roster = await jmri.discover_roster()

    assert len(roster) == 1
    assert roster["Good Loco"].dcc_address == 42
    assert any("skipping malformed roster entry" in rec.message for rec in caplog.records)
    # NOT the whole-roster failure path:
    assert not any("roster discovery failed" in rec.message for rec in caplog.records)


# ---- AC-7: first-wins address collision (direct container construction) ----


def test_address_collision_first_wins_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    first = _mk_entry("first", 100)
    second = _mk_entry("second", 100)
    with caplog.at_level(logging.WARNING, logger="pyjmri.roster"):
        roster = Roster([first, second])

    assert roster.by_address(100) is first
    assert len(roster) == 2  # both remain reachable by name
    assert any("duplicate DCC address 100" in rec.message for rec in caplog.records)


# ---- AC-3: roster discovery must NOT touch the WS-dispatch index ----


async def test_discover_roster_does_not_touch_entity_index(
    patch_http_factory: list[Any],
) -> None:
    turnout_env = {"type": "turnout", "data": {"name": "NT400", "userName": None, "state": 0}}
    good = {
        "type": "rosterEntry",
        "data": {"name": "Good Loco", "address": "42", "isLongAddress": False},
    }

    def respond(path: str) -> dict[str, Any] | list[dict[str, Any]]:
        if path == _VERSION_PATH:
            return _version_payload()
        if path == "/json/v5/turnout":
            return [turnout_env]
        if path == _ROSTER_PATH:
            return [good]
        return []

    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = respond
        await jmri.discover()
        index_after_discover = dict(jmri._entities)
        await jmri.discover_roster()
        index_after_roster = dict(jmri._entities)

    # discover_roster() left the WS-dispatch index exactly as discover() built it.
    assert index_after_roster == index_after_discover
    assert ("turnout", "NT400") in index_after_roster
    assert not any(entity_type == "rosterEntry" for (entity_type, _name) in index_after_roster)
    assert not any(name == "Good Loco" for (_type, name) in index_after_roster)
