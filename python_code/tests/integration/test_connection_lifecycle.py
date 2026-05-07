"""Integration smoke test: Client connects to JMRI and disconnects cleanly."""

from __future__ import annotations

import pytest

from pyjmri import Client


@pytest.mark.integration
async def test_client_connects_and_disconnects_cleanly(jmri_available: None) -> None:
    async with Client():
        pass
