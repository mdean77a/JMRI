"""Integration test bootstrap. See architecture §Test Harness."""

from __future__ import annotations

import socket

import pytest


def _jmri_listening(host: str = "localhost", port: int = 12080) -> bool:
    """Return True iff a TCP connection to the given address completes."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def jmri_available() -> None:
    """Skip integration tests unless JMRI is reachable on localhost:12080."""
    if not _jmri_listening():
        pytest.skip(
            "JMRI is not reachable on localhost:12080 — "
            "start JMRI with the web server enabled to run integration tests."
        )
