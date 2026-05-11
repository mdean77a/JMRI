"""Unit-test bootstrap: synthetic-fixture loader and shared fakes."""

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


@pytest.fixture
def make_fake_handle() -> Callable[[Callable[[str, str], dict[str, Any]]], Any]:
    """Return a factory that builds a :class:`ClientHandle`-shaped fake.

    The returned object structurally satisfies
    :class:`pyjmri._protocols.ClientHandle`. Each call to the factory
    creates a fresh fake whose ``calls`` list records every
    ``get_entity`` invocation as ``(entity_type, name)`` tuples.

    Example::

        handle = make_fake_handle(
            lambda entity_type, name: {
                "type": entity_type,
                "data": {"name": name, "userName": None, "state": 2},
            }
        )
        turnout = Turnout(
            name="NT9",
            user_name=None,
            state=TurnoutState.UNKNOWN,
            _handle=handle,
        )
        assert await turnout.get_state() is TurnoutState.CLOSED
    """

    def _make(
        envelope_for: Callable[[str, str], dict[str, Any]],
    ) -> Any:
        class _FakeHandle:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            async def get_entity(self, entity_type: str, name: str) -> dict[str, Any]:
                self.calls.append((entity_type, name))
                return envelope_for(entity_type, name)

        return _FakeHandle()

    return _make


@pytest.fixture
def patch_http_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> list[Any]:
    """Replace ``HTTPClient`` inside ``client.py`` with a test factory.

    Returns a list that captures every constructed fake transport so
    tests can assert on ``probed`` and ``close_count``. Each fake exposes
    a ``next_response`` attribute (default ``{}``) which controls what
    :meth:`get` returns.
    """
    from pyjmri import client as client_module

    constructed: list[Any] = []

    class FakeHTTPClient:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.host = kwargs["host"]
            self.port = kwargs["port"]
            self.probed: list[str] = []
            self.close_count = 0
            self.fail_with: BaseException | None = None
            self.next_response: dict[str, Any] | list[dict[str, Any]] = {}
            constructed.append(self)

        async def get(self, path: str) -> dict[str, Any] | list[dict[str, Any]]:
            self.probed.append(path)
            if self.fail_with is not None:
                raise self.fail_with
            return self.next_response

        async def aclose(self) -> None:
            self.close_count += 1

    monkeypatch.setattr(client_module, "HTTPClient", FakeHTTPClient)
    return constructed
