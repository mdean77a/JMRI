"""Unit tests for :meth:`pyjmri.Client.power_state`."""

from __future__ import annotations

from typing import Any

import pytest

from pyjmri import Client, JMRIProtocolError, PowerState


def _envelope(state: int) -> dict[str, Any]:
    return {
        "type": "power",
        "data": {"name": "NCE", "state": state, "default": True},
    }


async def test_power_state_returns_on(patch_http_factory: list[Any]) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = [_envelope(2)]

        result = await jmri.power_state()

    assert result is PowerState.ON


async def test_power_state_returns_off(patch_http_factory: list[Any]) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = [_envelope(4)]

        result = await jmri.power_state()

    assert result is PowerState.OFF


async def test_power_state_returns_unknown(patch_http_factory: list[Any]) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = [_envelope(0)]

        result = await jmri.power_state()

    assert result is PowerState.UNKNOWN


async def test_power_state_accepts_dict_envelope(patch_http_factory: list[Any]) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = _envelope(2)

        result = await jmri.power_state()

    assert result is PowerState.ON


async def test_power_state_raises_on_empty_list(patch_http_factory: list[Any]) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = []

        with pytest.raises(JMRIProtocolError, match="empty power response"):
            await jmri.power_state()


async def test_power_state_calls_correct_endpoint(patch_http_factory: list[Any]) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = [_envelope(2)]

        await jmri.power_state()

    assert fake.probed[-1] == "/json/v5/power"


async def test_power_state_on_closed_client_raises_runtime_error() -> None:
    client = Client()

    with pytest.raises(RuntimeError, match="not open"):
        await client.power_state()


async def test_get_entity_on_closed_client_raises_runtime_error() -> None:
    client = Client()

    with pytest.raises(RuntimeError, match="not open"):
        await client.get_entity("turnout", "NT1")


async def test_get_entity_url_encodes_name(patch_http_factory: list[Any]) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = {
            "type": "turnout",
            "data": {"name": "Block 1", "userName": None, "state": 2},
        }

        await jmri.get_entity("turnout", "Block 1")

    assert "/json/v5/turnout/Block%201" in fake.probed


async def test_get_entity_url_encodes_colon(patch_http_factory: list[Any]) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = {
            "type": "sensor",
            "data": {"name": "IS:DCCAPP:1", "userName": None, "state": 2},
        }

        await jmri.get_entity("sensor", "IS:DCCAPP:1")

    assert "/json/v5/sensor/IS%3ADCCAPP%3A1" in fake.probed


async def test_get_entity_raises_on_list_payload(patch_http_factory: list[Any]) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = [
            {"type": "turnout", "data": {"name": "NT1", "state": 2}},
        ]

        with pytest.raises(JMRIProtocolError, match="expected single entity envelope, got list"):
            await jmri.get_entity("turnout", "NT1")


async def test_get_entity_raises_on_empty_list(patch_http_factory: list[Any]) -> None:
    async with Client() as jmri:
        fake = patch_http_factory[0]
        fake.next_response = []

        with pytest.raises(JMRIProtocolError, match="entity not found"):
            await jmri.get_entity("turnout", "NT404")
