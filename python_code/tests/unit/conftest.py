"""Unit-test bootstrap: synthetic-fixture loader."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def load_fixture() -> Callable[[str], list[dict[str, Any]]]:
    """Return a function that loads ``tests/unit/fixtures/<name>.json``.

    Example:
        envelopes = load_fixture("turnouts")
    """

    def _load(name: str) -> list[dict[str, Any]]:
        path = _FIXTURES_DIR / f"{name}.json"
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, list):
            raise TypeError(f"fixture {name!r} must be a JSON array, got {type(payload).__name__}")
        return payload

    return _load
