"""Sanity tests for the ``ClientHandle`` Protocol."""

from __future__ import annotations

from typing import Any, cast

from pyjmri._protocols import ClientHandle


def test_client_handle_has_get_entity_member() -> None:
    assert hasattr(ClientHandle, "get_entity")


async def test_structurally_conforming_class_satisfies_protocol() -> None:
    class Conforming:
        async def get_entity(self, entity_type: str, name: str) -> dict[str, Any]:
            return {"type": entity_type, "data": {"name": name}}

    handle: ClientHandle = cast(ClientHandle, Conforming())
    payload = await handle.get_entity("turnout", "NT1")
    assert payload == {"type": "turnout", "data": {"name": "NT1"}}
