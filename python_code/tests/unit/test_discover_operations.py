"""Unit tests for ``Client.discover_operations()`` — Operations discovery.

Mirrors ``test_discover.py``: drives the ``patch_http_factory`` fake HTTP
transport so no live JMRI is required. Covers the FR50 empty path, the
populated path (against the Story 8.1 captured fixtures), parallel
fetching, the shared version gate, the not-open guard, and the invariant
that Operations discovery does NOT mutate the WS-dispatch index.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from pyjmri import Client, Operations

LoadFixture = Callable[[str], list[dict[str, Any]]]

_VERSION_PATH = "/json/v5/networkService"
_OPERATIONS_PATHS = {
    "/json/v5/location",
    "/json/v5/train",
    "/json/v5/car",
    "/json/v5/engine",
}


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


def _empty_responder(path: str) -> dict[str, Any] | list[dict[str, Any]]:
    """Version payload for the version path; empty list for everything else."""
    if path == _VERSION_PATH:
        return _version_payload()
    return []


# ---- FR50: no Operations data configured -> empty collections, no error ----


async def test_discover_operations_empty_returns_empty_collections(
    patch_http_factory: list[Any],
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _empty_responder
        ops = await jmri.discover_operations()

    assert isinstance(ops, Operations)
    assert len(ops.locations) == 0
    assert len(ops.trains) == 0
    assert len(ops.cars) == 0
    assert len(ops.engines) == 0


async def test_discover_operations_probes_all_four_types_in_parallel(
    patch_http_factory: list[Any],
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _empty_responder
        await jmri.discover_operations()

    assert _OPERATIONS_PATHS.issubset(set(fake.probed))


# ---- Populated path against the Story 8.1 captured fixtures ----


def _fixture_responder(
    load_fixture: LoadFixture,
) -> Callable[[str], dict[str, Any] | list[dict[str, Any]]]:
    per_path = {
        "/json/v5/location": load_fixture("operations/locations"),
        "/json/v5/train": load_fixture("operations/trains"),
        "/json/v5/car": load_fixture("operations/cars"),
        "/json/v5/engine": load_fixture("operations/engines"),
    }

    def _respond(path: str) -> dict[str, Any] | list[dict[str, Any]]:
        if path == _VERSION_PATH:
            return _version_payload()
        return per_path.get(path, [])

    return _respond


async def test_discover_operations_populates_collections(
    patch_http_factory: list[Any],
    load_fixture: LoadFixture,
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _fixture_responder(load_fixture)
        ops = await jmri.discover_operations()

    # Fixture set: 3 locations / 1 train / 3 cars / 4 engines.
    assert len(ops.locations) == 3
    assert len(ops.trains) == 1
    assert len(ops.cars) == 3
    assert len(ops.engines) == 4


async def test_discover_operations_dual_name_lookup(
    patch_http_factory: list[Any],
    load_fixture: LoadFixture,
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _fixture_responder(load_fixture)
        ops = await jmri.discover_operations()

    # Locations resolve by BOTH user and system name (same object).
    by_user = ops.locations["NW_Staging_Yard"]
    by_system = ops.locations["2"]
    assert by_user is by_system
    assert by_user.user_name == "NW_Staging_Yard"
    assert by_user.name == "2"

    # Trains resolve by both names too.
    assert ops.trains["TestTrainOne"] is ops.trains["1"]

    # Cars/engines have no user name — system-name (road+number) only.
    car = ops.cars["AA123"]
    assert car.user_name is None
    assert car.name == "AA123"


# ---- Version gate is shared with discover() (cached on the Client) ----


async def test_discover_operations_runs_version_check_once_then_caches(
    patch_http_factory: list[Any],
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _empty_responder
        await jmri.discover_operations()
        post_first = list(fake.probed)
        fake.probed.clear()
        # A subsequent discover() must NOT re-probe the version endpoint.
        await jmri.discover()
        post_second = list(fake.probed)

    assert post_first.count(_VERSION_PATH) == 1
    assert _VERSION_PATH not in post_second


async def test_discover_then_discover_operations_skips_repeat_version_probe(
    patch_http_factory: list[Any],
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _empty_responder
        await jmri.discover()
        fake.probed.clear()
        await jmri.discover_operations()
        ops_probed = list(fake.probed)

    assert _VERSION_PATH not in ops_probed
    assert _OPERATIONS_PATHS.issubset(set(ops_probed))


# ---- Invariant: Operations discovery must NOT touch the WS-dispatch index ----


async def test_discover_operations_does_not_clobber_entity_index(
    patch_http_factory: list[Any],
) -> None:
    """discover() builds self._entities; discover_operations() must leave it intact."""

    def respond(path: str) -> dict[str, Any] | list[dict[str, Any]]:
        if path == _VERSION_PATH:
            return _version_payload()
        if path == "/json/v5/turnout":
            return [{"type": "turnout", "data": {"name": "NT400", "userName": None, "state": 0}}]
        return []

    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = respond
        await jmri.discover()
        before = dict(jmri._entities)
        assert ("turnout", "NT400") in before  # index populated by discover()
        await jmri.discover_operations()
        after = dict(jmri._entities)

    assert after == before  # unchanged by Operations discovery


# ---- Not-open guard ----


async def test_discover_operations_raises_runtime_error_when_client_not_open() -> None:
    client = Client()
    with pytest.raises(RuntimeError, match="not open"):
        await client.discover_operations()
