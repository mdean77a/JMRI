"""Unit tests for ``Client.discover()`` — parallel discovery + version gate."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from pyjmri import (
    Client,
    JMRIProtocolError,
    JMRIVersionUnsupported,
    Layout,
    TurnoutState,
)

_ENTITY_PATHS = {
    "/json/v5/turnout",
    "/json/v5/sensor",
    "/json/v5/block",
    "/json/v5/light",
    "/json/v5/memory",
    "/json/v5/route",
    "/json/v5/signalHead",
    "/json/v5/signalMast",
}


_VERSION_PATH = "/json/v5/networkService"


def _version_payload(version: str) -> list[dict[str, Any]]:
    """Return the JMRI ``/json/v5/networkService`` envelope shape.

    The JMRI version lives in ``data.jmri``; ``/json/v5/version`` only
    carries the JSON-API version, not JMRI itself.
    """
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


def _responder(
    *,
    version: str = "5.14.0",
    per_path: dict[str, list[dict[str, Any]]] | None = None,
) -> Callable[[str], dict[str, Any] | list[dict[str, Any]]]:
    """Build a ``next_response`` callable for ``patch_http_factory``.

    Returns the networkService version payload for
    ``/json/v5/networkService`` and an empty list for any other entity
    path, except those overridden in ``per_path``.
    """
    overrides = per_path or {}

    def _respond(path: str) -> dict[str, Any] | list[dict[str, Any]]:
        if path == _VERSION_PATH:
            return _version_payload(version)
        if path in overrides:
            return overrides[path]
        return []

    return _respond


async def test_discover_returns_layout_with_eight_empty_collections(
    patch_http_factory: list[Any],
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _responder()
        layout = await jmri.discover()

    assert isinstance(layout, Layout)
    assert len(layout.turnouts) == 0
    assert len(layout.sensors) == 0
    assert len(layout.blocks) == 0
    assert len(layout.lights) == 0
    assert len(layout.memories) == 0
    assert len(layout.routes) == 0
    assert len(layout.signal_heads) == 0
    assert len(layout.signal_masts) == 0
    issued = set(fake.probed)
    assert _ENTITY_PATHS.issubset(issued)


async def test_discover_raises_runtime_error_when_client_not_open() -> None:
    client = Client()
    with pytest.raises(RuntimeError, match="not open"):
        await client.discover()


async def test_discover_version_check_raises_jmri_version_unsupported_below_5_14(
    patch_http_factory: list[Any],
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _responder(version="5.13.9")
        with pytest.raises(JMRIVersionUnsupported) as exc_info:
            await jmri.discover()

    assert exc_info.value.context["detected"] == "5.13.9"
    assert exc_info.value.context["required"] == "5.14"
    # Version gate must run BEFORE entity discovery — no entity paths probed.
    fake = patch_http_factory[0]
    assert not (_ENTITY_PATHS & set(fake.probed))


async def test_discover_version_check_passes_for_exactly_5_14(
    patch_http_factory: list[Any],
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _responder(version="5.14")
        layout = await jmri.discover()

    assert isinstance(layout, Layout)


async def test_discover_version_check_passes_for_5_14_with_patch(
    patch_http_factory: list[Any],
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _responder(version="5.14.0")
        layout = await jmri.discover()

    assert isinstance(layout, Layout)


async def test_discover_version_check_accepts_build_suffixed_version(
    patch_http_factory: list[Any],
) -> None:
    """JMRI sometimes emits versions like ``5.14+Rdea51dcccf`` — accept the prefix."""
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _responder(version="5.14+Rdea51dcccf")
        layout = await jmri.discover()

    assert isinstance(layout, Layout)


async def test_discover_version_check_rejects_non_numeric_version(
    patch_http_factory: list[Any],
) -> None:
    """A version with no leading numeric prefix raises ``JMRIProtocolError``."""
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _responder(version="not-a-version")
        with pytest.raises(JMRIProtocolError):
            await jmri.discover()


async def test_discover_version_check_skipped_on_second_call(
    patch_http_factory: list[Any],
) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _responder()
        await jmri.discover()
        post_first_probed = list(fake.probed)
        fake.probed.clear()
        await jmri.discover()
        second_call_probed = list(fake.probed)

    # First discover() hit /json/v5/networkService exactly once.
    assert post_first_probed.count(_VERSION_PATH) == 1
    # __aenter__ probes /json/v5/version (separate endpoint), not networkService.
    assert "/json/v5/version" in post_first_probed
    # Second call must NOT re-probe networkService.
    assert _VERSION_PATH not in second_call_probed
    assert _ENTITY_PATHS.issubset(set(second_call_probed))


async def test_discover_protocol_error_from_entity_type_propagates(
    patch_http_factory: list[Any],
) -> None:
    """One entity-type endpoint returns a non-list payload — fail-fast.

    A non-list response triggers ``JMRIProtocolError`` inside
    ``_fetch_collection``. ``asyncio.TaskGroup`` propagates the error
    wrapped in an ``ExceptionGroup``; callers use ``except*`` (3.11+).
    """

    def respond(path: str) -> dict[str, Any] | list[dict[str, Any]]:
        if path == _VERSION_PATH:
            return _version_payload("5.14.0")
        if path == "/json/v5/turnout":
            return {"not": "a list"}
        return []

    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = respond
        with pytest.raises(ExceptionGroup) as exc_info:
            await jmri.discover()

    flat = exc_info.value.exceptions
    assert any(isinstance(exc, JMRIProtocolError) for exc in flat)


async def test_discover_empty_entity_collection_is_valid(
    patch_http_factory: list[Any],
) -> None:
    """One entity type returns ``[]`` while others have data — empty collection is valid."""

    def respond(path: str) -> dict[str, Any] | list[dict[str, Any]]:
        if path == _VERSION_PATH:
            return _version_payload("5.14.0")
        if path == "/json/v5/sensor":
            return [
                {
                    "type": "sensor",
                    "data": {"name": "NS1", "userName": None, "state": 4},
                }
            ]
        return []

    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = respond
        layout = await jmri.discover()

    assert len(layout.lights) == 0
    assert len(layout.sensors) == 1


async def test_discover_populates_turnout_collection(
    patch_http_factory: list[Any],
) -> None:
    def respond(path: str) -> dict[str, Any] | list[dict[str, Any]]:
        if path == _VERSION_PATH:
            return _version_payload("5.14.0")
        if path == "/json/v5/turnout":
            return [
                {
                    "type": "turnout",
                    "data": {
                        "name": "NT400",
                        "userName": "Yard Lead",
                        "state": 0,
                    },
                }
            ]
        return []

    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = respond
        layout = await jmri.discover()

    assert len(layout.turnouts) == 1
    turnout = layout.turnouts["NT400"]
    assert turnout.name == "NT400"
    assert turnout.user_name == "Yard Lead"
    assert turnout.state is TurnoutState.UNKNOWN
    # Dual-name lookup via user_name works too.
    assert layout.turnouts["Yard Lead"] is turnout


def _basic_mast(name: str) -> dict[str, Any]:
    """A signal mast in the supported ``basic`` signalling system."""
    return {
        "type": "signalMast",
        "data": {"name": name, "userName": None, "aspect": "Clear", "held": False, "lit": True},
    }


def _non_basic_mast(name: str, aspect: str) -> dict[str, Any]:
    """A mast whose aspect is outside the ``basic`` enum (e.g. BR-2003)."""
    return {
        "type": "signalMast",
        "data": {"name": name, "userName": None, "aspect": aspect, "held": False, "lit": True},
    }


async def test_discover_skips_unparseable_signal_mast_and_keeps_other_entities(
    patch_http_factory: list[Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-``basic`` mast must be skipped, not abort the whole discovery.

    Regression for discussion #2: a layout whose masts use BR-2003
    ('Danger', 'Off', ...) previously raised ``JMRIProtocolError`` out of
    ``discover()``, discarding every turnout/sensor already fetched.
    """

    def respond(path: str) -> dict[str, Any] | list[dict[str, Any]]:
        if path == _VERSION_PATH:
            return _version_payload("5.14.0")
        if path == "/json/v5/turnout":
            return [{"type": "turnout", "data": {"name": "NT1", "userName": None, "state": 0}}]
        if path == "/json/v5/signalMast":
            return [_non_basic_mast("IF$shsm:BR-2003:2-h(SH9)", "Danger")]
        return []

    with caplog.at_level("WARNING", logger="pyjmri.client"):
        async with Client() as jmri:
            fake = patch_http_factory[0]
            fake.next_response = respond
            layout = await jmri.discover()

    # Discovery succeeds and the turnout survives the bad mast.
    assert len(layout.turnouts) == 1
    assert layout.turnouts["NT1"].state is TurnoutState.UNKNOWN
    # The unparseable mast is omitted, not stored.
    assert len(layout.signal_masts) == 0
    # ...and it is reported at WARNING so the omission is visible.
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("signalMast" in r.getMessage() for r in warnings)
    assert any("Danger" in r.getMessage() for r in warnings)


async def test_discover_keeps_valid_masts_when_one_is_unparseable(
    patch_http_factory: list[Any],
) -> None:
    """Only the unsupported mast is dropped; a valid ``basic`` mast survives."""

    def respond(path: str) -> dict[str, Any] | list[dict[str, Any]]:
        if path == _VERSION_PATH:
            return _version_payload("5.14.0")
        if path == "/json/v5/signalMast":
            return [
                _basic_mast("IM1"),
                _non_basic_mast("IF$shsm:BR-2003:ply(Ground 1)", "Off"),
            ]
        return []

    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = respond
        layout = await jmri.discover()

    assert len(layout.signal_masts) == 1
    assert layout.signal_masts["IM1"].name == "IM1"


async def test_discover_version_check_reset_on_client_reuse(
    patch_http_factory: list[Any],
) -> None:
    """_version_checked must reset to False on __aexit__ so client reuse re-probes."""
    client = Client()
    async with client:
        fake = patch_http_factory[0]
        fake.next_response = _responder()
        await client.discover()
        assert client._version_checked is True

    # After exit, flag must be cleared.
    assert client._version_checked is False

    # Re-enter the same Client instance — version probe must fire again.
    async with client:
        fake2 = patch_http_factory[1]
        fake2.next_response = _responder()
        await client.discover()
        assert _VERSION_PATH in fake2.probed
