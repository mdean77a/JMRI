"""Sanity tests for the ``ClientHandle`` Protocol."""

from __future__ import annotations

from typing import Any, cast

from pyjmri._protocols import ClientHandle


def test_client_handle_has_get_entity_member() -> None:
    assert hasattr(ClientHandle, "get_entity")


def test_client_handle_has_command_member() -> None:
    assert hasattr(ClientHandle, "command")


def test_client_handle_has_throttle_members() -> None:
    assert hasattr(ClientHandle, "throttle_acquire")
    assert hasattr(ClientHandle, "throttle_release")
    assert hasattr(ClientHandle, "throttle_heartbeat")
    assert hasattr(ClientHandle, "spawn_supervised")
    assert hasattr(ClientHandle, "throttle_keepalive_interval")


async def test_structurally_conforming_class_satisfies_protocol() -> None:
    class Conforming:
        async def get_entity(self, entity_type: str, name: str) -> dict[str, Any]:
            return {"type": entity_type, "data": {"name": name}}

    handle: ClientHandle = cast(ClientHandle, Conforming())
    payload = await handle.get_entity("turnout", "NT1")
    assert payload == {"type": "turnout", "data": {"name": "NT1"}}
