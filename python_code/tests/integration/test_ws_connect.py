"""Integration smoke test: ``Client`` establishes the WebSocket alongside HTTP.

The WS analog of ``test_connection_lifecycle.py``. Requires JMRI on
``localhost:12080``; skipped via the ``jmri_available`` session fixture
when unreachable. See architecture §Test Harness.
"""

from __future__ import annotations

import pytest

from pyjmri import Client


@pytest.mark.integration
async def test_client_opens_ws_alongside_http_against_live_jmri(
    jmri_available: None,
) -> None:
    async with Client() as jmri:
        # Both transports must be live after __aenter__ returns.
        assert jmri._http is not None
        assert jmri._ws is not None
        assert jmri._registry is not None
        assert jmri._ws_connected is not None and jmri._ws_connected.is_set()
        # TaskGroup is running the supervisor.
        assert jmri._tg is not None
        assert jmri._supervisor_task is not None
        assert not jmri._supervisor_task.done()
