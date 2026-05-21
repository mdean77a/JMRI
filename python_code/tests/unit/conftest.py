"""Unit-test bootstrap: synthetic-fixture loader and shared fakes."""

from __future__ import annotations

import asyncio
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
                self.ensure_calls: list[tuple[str, str]] = []
                self.command_calls: list[tuple[str, str, dict[str, Any]]] = []
                self.command_raises: BaseException | None = None
                # Optional gate that ``command`` awaits BEFORE recording or
                # raising. Tests that need to inspect entity state mid-call
                # (e.g. waiter registered, command not yet sent) set this to
                # a fresh ``asyncio.Event()``, start the entity call as a
                # task, inspect state, then call ``gate.set()`` to release
                # ``command``. When ``None`` (default), ``command`` returns
                # synchronously as in Story 4.1.
                self.command_gate: asyncio.Event | None = None

            async def get_entity(self, entity_type: str, name: str) -> dict[str, Any]:
                self.calls.append((entity_type, name))
                return envelope_for(entity_type, name)

            async def ensure_subscription(self, entity_type: str, name: str) -> None:
                self.ensure_calls.append((entity_type, name))

            async def command(
                self,
                entity_type: str,
                name: str,
                payload: dict[str, Any],
            ) -> None:
                if self.command_gate is not None:
                    await self.command_gate.wait()
                self.command_calls.append((entity_type, name, payload))
                if self.command_raises is not None:
                    raise self.command_raises

        return _FakeHandle()

    return _make


@pytest.fixture
def patch_http_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> list[Any]:
    """Replace ``HTTPClient`` and ``WSConnection`` inside ``client.py`` with test factories.

    Returns a list that captures every constructed fake HTTP transport so
    tests can assert on ``probed`` and ``close_count``. Each fake HTTP
    exposes a ``next_response`` attribute (default ``{}``) which controls
    what :meth:`get` returns.

    ``next_response`` may be one of:

    * A ``dict`` or ``list`` — returned verbatim for every ``get()`` call.
    * A callable ``(path: str) -> dict | list`` — invoked with the request
      path, and its return value used as the response.

    The fixture also stubs out ``WSConnection`` so unit tests do not
    require a live JMRI WebSocket. The fake WS immediately signals
    "connected" on its :class:`asyncio.Event`, records sent messages on
    ``ws_constructed[-1].sent`` (when accessible via the
    ``patch_ws_constructed`` fixture), and runs an inert receive loop
    until cancelled.
    """
    import asyncio as _asyncio

    from pyjmri import client as client_module

    constructed: list[Any] = []

    NextResponse = (
        dict[str, Any]
        | list[dict[str, Any]]
        | Callable[[str], dict[str, Any] | list[dict[str, Any]]]
    )

    class FakeHTTPClient:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.host = kwargs["host"]
            self.port = kwargs["port"]
            self.probed: list[str] = []
            self.commands: list[tuple[str, str, dict[str, Any]]] = []
            self.close_count = 0
            self.fail_with: BaseException | None = None
            self.command_raises: BaseException | None = None
            self.next_response: NextResponse = {}
            constructed.append(self)

        async def get(self, path: str) -> dict[str, Any] | list[dict[str, Any]]:
            self.probed.append(path)
            if self.fail_with is not None:
                raise self.fail_with
            if callable(self.next_response):
                return self.next_response(path)
            return self.next_response

        async def command(
            self,
            entity_type: str,
            name: str,
            payload: dict[str, Any],
        ) -> None:
            self.commands.append((entity_type, name, payload))
            if self.command_raises is not None:
                raise self.command_raises

        async def aclose(self) -> None:
            self.close_count += 1

    class FakeWSConnection:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.host = kwargs["host"]
            self.port = kwargs["port"]
            self.sent: list[dict[str, Any]] = []
            self._connected: _asyncio.Event | None = kwargs.get("connected_event")
            self.on_reconnect = kwargs.get("on_reconnect")

        async def run(
            self,
            on_message: Callable[[dict[str, Any]], Any],
        ) -> None:
            # Signal first-connect immediately; then idle until cancelled.
            if self._connected is not None:
                self._connected.set()
            never_set = _asyncio.Event()
            try:
                await never_set.wait()  # blocks forever; cancelled in __aexit__
            except _asyncio.CancelledError:
                return

        async def send(self, message: dict[str, Any]) -> None:
            self.sent.append(message)

    monkeypatch.setattr(client_module, "HTTPClient", FakeHTTPClient)
    monkeypatch.setattr(client_module, "WSConnection", FakeWSConnection)
    return constructed
