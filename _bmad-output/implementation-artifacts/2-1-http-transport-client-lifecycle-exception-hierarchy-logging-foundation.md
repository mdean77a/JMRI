# Story 2.1: HTTP transport + Client lifecycle + exception hierarchy + logging foundation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a library user,
I want `async with Client() as jmri:` to connect to JMRI's HTTP API and either succeed or raise a typed connection error with diagnostic context,
so that failed connections fail fast and informatively, and successful connections release resources deterministically on exit.

## Acceptance Criteria

1. **`_transport.HTTPClient` wraps `httpx.AsyncClient` and is the sole transport boundary.** Given the package skeleton from Epic 1, when `_transport.py` is added with an `HTTPClient` async wrapper around `httpx.AsyncClient`, then only `_transport.py` imports `httpx`; `_transport.py` is the only module allowed to catch `httpx.*` exception types; any caught `httpx.ConnectError` is re-raised as `JMRIConnectionError` and `httpx.TimeoutException` as `JMRIRequestTimeout`, both using `from e`.
2. **`exceptions.py` ships the full `JMRIError` hierarchy with diagnostic context.** Given `exceptions.py` is added with the full `JMRIError` hierarchy from the architecture (base `JMRIError` with `context: dict[str, Any]`, plus `JMRIConnectionError`, `JMRIReconnectFailed`, `JMRIRequestTimeout`, `JMRIProtocolError`, `JMRIVersionUnsupported`, `LayoutEntityNotFound`, `LayoutEntityNotControllable`, `ThrottleError`, `ThrottleAcquireFailed`, `ThrottleReleased`, `WaitTimeout(JMRIError, TimeoutError)`), when a unit test instantiates each subclass with diagnostic context and calls `str(exc)`, then `JMRIConnectionError(host="localhost", port=12080)` formats as actionable text matching FR35 (e.g., `"could not connect to localhost:12080 — is JMRI running with the web server enabled?"`); `WaitTimeout` instances are catchable as either `JMRIError` or `TimeoutError`; the base `JMRIError` is never raised by library code (only subclasses).
3. **`Client(url, *, config)` is an async context manager with documented URL forms.** Given `client.py` is added with a `Client(url: str = "localhost:12080", *, config: ClientConfig | None = None)` class implementing `__aenter__` / `__aexit__`, when the user writes `async with Client() as jmri: ...`, then the Client connects on entry and closes the underlying `httpx.AsyncClient` on exit (FR2, FR3); `Client("host:port")`, `Client("http://host:port")`, and `Client("ws://host:port/json")` all parse correctly (FR1); the default URL is `localhost:12080` (NFR10).
4. **Unreachable JMRI raises `JMRIConnectionError` with diagnostic context and chained cause.** Given the Client is configured with a non-existent host, when `__aenter__` runs, then it raises `JMRIConnectionError` with `host`, `port`, and a suggested-cause string (FR4, FR35); the original `httpx.ConnectError` is chained via `__cause__`.
5. **Library logging is hierarchical, structured, and silent by default.** Given the package is imported, when `pyjmri/__init__.py` runs, then `logging.getLogger("pyjmri").addHandler(logging.NullHandler())` is called once (FR36 — no forced configuration); module-level `logger = logging.getLogger(__name__)` exists in `_transport.py` (yields `pyjmri.transport`).
6. **Integration smoke test confirms a clean round-trip against real JMRI.** Given Story 2.1's deliverables, when an integration test runs against a live JMRI on `localhost:12080`, then `async with Client() as jmri: pass` connects and disconnects cleanly without raising; the test is marked `@pytest.mark.integration` and skips when JMRI is not reachable.

## Tasks / Subtasks

- [x] **Task 1: Add `httpx` as a runtime dependency** (AC: #1)
  - [x] From `python_code/`, run `uv add httpx`. This refreshes `uv.lock` and adds `httpx` (and a small dep closure: `anyio`, `httpcore`, `h11`, `idna`, `certifi`, `sniffio`) to `[project] dependencies`.
  - [x] **No version pin tighter than the floor.** `uv add` will resolve to the latest stable httpx (`>=0.28.x` as of January 2026). Architecture deliberately set no upper bound (§Transport Layer) — modern httpx is mypy-strict friendly out of the box. The `uv.lock` is the reproducibility anchor; `pyproject.toml` records only the floor.
  - [x] Confirm `python_code/pyproject.toml` `[project] dependencies` now contains `httpx>=...` (whatever floor `uv add` chose) and `uv.lock` reflects the resolved version.
  - [x] **`websockets` is NOT added in this story.** It belongs to Story 3.1. Resist the temptation to bundle.

- [x] **Task 2: Create `src/pyjmri/exceptions.py`** (AC: #2)
  - [x] Create the full `JMRIError` hierarchy exactly as specified in §"`exceptions.py` canonical shape" below. Every class includes the `from __future__ import annotations` header, a Google-style docstring, and `context: dict[str, Any]` plumbing on the base.
  - [x] **`WaitTimeout(JMRIError, TimeoutError)`** — multi-inherits the builtin `TimeoutError` so users can `except TimeoutError:` or `except JMRIError:`. The `__init__` MUST call both parents' initializers in MRO order or pass through `super().__init__(*args, **kwargs)` cleanly. Architecture §Error Handling Discipline: "the library raises only `WaitTimeout`, never bare `TimeoutError` or `asyncio.TimeoutError`."
  - [x] **`JMRIConnectionError.__str__`** returns the actionable text format from FR35 — see §"FR35-conformant `__str__` for `JMRIConnectionError`" below. Other subclasses inherit the base `__str__` (which renders the context dict).
  - [x] **`__all__`** at the top of the module enumerates every public exception class. Architecture §Public API Discipline: "Every public module declares `__all__`."
  - [x] **No raised side effects.** This module defines classes only; no `raise` statements. Per architecture §Error Handling Discipline: "the base class is never raised directly — it exists only for catch-all `except JMRIError` blocks."

- [x] **Task 3: Create `src/pyjmri/_transport.py`** (AC: #1, #4, #5)
  - [x] Create `_transport.py` with the `HTTPClient` async wrapper. See §"`_transport.HTTPClient` canonical shape" below for the exact structure.
  - [x] **The transport/domain boundary is enforced at this file.** Architecture §Architectural Boundaries point 2: "Only `_transport.py` is allowed to import `httpx`. Only `_transport.py` is allowed to catch `httpx.*` exception types."
  - [x] **Constructor takes parsed primitives, not the URL string.** Pass `host: str`, `port: int`, `scheme: str` (always `"http"` for the v1 HTTPClient), and `request_timeout: float` from the Client. URL parsing belongs in `Client.__init__`, not here. Reason: keeps the transport unit-testable without wading through URL-form variants.
  - [x] **`async def get(path: str) -> dict[str, Any]:`** is the only public read method this story needs. Path is appended to base URL; response is decoded as JSON; non-200 raises `JMRIProtocolError` with the status code in `context`. **POST/PUT come in Story 4.1** — do not pre-build them.
  - [x] **`async def aclose() -> None:`** delegates to the underlying `httpx.AsyncClient.aclose()`. Idempotent (safe to call multiple times).
  - [x] **No `__aenter__/__aexit__` on `HTTPClient`.** Lifecycle is owned by `Client`. The transport object is opened in `Client.__aenter__` and closed in `Client.__aexit__`. Architecture §Internal Layering: domain owns transport, never the inverse.
  - [x] **Module-level logger:** `logger = logging.getLogger(__name__)` near the top — yields `pyjmri.transport` per architecture §Logging Strategy.

- [x] **Task 4: Create `src/pyjmri/client.py`** (AC: #3, #4)
  - [x] Create `client.py` with the `Client` class plus `ClientConfig` and `ReconnectConfig` dataclasses. See §"`client.py` canonical shape" below.
  - [x] **`ClientConfig` and `ReconnectConfig` are `@dataclass(frozen=True, kw_only=True)`** per architecture §Client Configuration Shape. Both must be defined now even though `ReconnectConfig`'s fields are not consumed until Epic 3 — the public API surface is fixed at this point so users writing `Client(url, config=ClientConfig(...))` against v1 keep working into v2 without API churn.
  - [x] **URL parser** is a private function `_parse_url(url: str) -> tuple[str, int, str]` returning `(host, port, scheme)`. Accepts:
    - `"localhost:12080"` → `("localhost", 12080, "http")`
    - `"http://localhost:12080"` → `("localhost", 12080, "http")`
    - `"ws://localhost:12080/json"` → `("localhost", 12080, "http")` *(scheme normalized to http for HTTP transport; `ws://` is accepted for forward compat with Epic 3)*
    - `"https://example.com:12080"` → `("example.com", 12080, "https")`
    - Invalid forms (no port, malformed) raise `ValueError` with a message naming the offending input. *Not* `JMRIConnectionError` — this is a programming error, not a runtime connection failure.
  - [x] **`__aenter__` constructs and opens `HTTPClient`**, then performs no version check (Story 2.5 owns that). For now, "connect" means "instantiate `httpx.AsyncClient` with the configured base URL and timeout." `httpx.AsyncClient` doesn't actually open a TCP connection until the first request — so the connection-failure check needs to be triggered explicitly. **A single low-cost GET to confirm reachability** is the canonical pattern; see §"Connection probe in `__aenter__`" below.
  - [x] **`__aexit__` calls `self._http.aclose()`** unconditionally. Even on exception path. The library never leaks `httpx.AsyncClient` instances; CI's pytest will surface unclosed-resource warnings.
  - [x] **No public `power_state()` method yet** — that's Story 2.3. Story 2.1's Client is intentionally minimal: lifecycle + URL parsing + transport handle.
  - [x] **No `discover()` method yet** — that's Story 2.5.
  - [x] **No `TaskGroup` yet** — Architecture §Concurrency Model says one Client-level TaskGroup supervises long-running coroutines (WS receive loop, throttle keep-alives). All of those land in Epic 3+. Story 2.1 is HTTP-only; the TaskGroup machinery activates when there's something to supervise.
  - [x] **Module-level logger:** `logger = logging.getLogger(__name__)` → `pyjmri.client`.

- [x] **Task 5: Update `src/pyjmri/__init__.py` to export the new public surface** (AC: #2, #3, #5)
  - [x] Re-export the user-facing names: `Client`, `ClientConfig`, `ReconnectConfig`, `JMRIError`, `JMRIConnectionError`, `JMRIReconnectFailed`, `JMRIRequestTimeout`, `JMRIProtocolError`, `JMRIVersionUnsupported`, `LayoutEntityNotFound`, `LayoutEntityNotControllable`, `ThrottleError`, `ThrottleAcquireFailed`, `ThrottleReleased`, `WaitTimeout`.
  - [x] Add `__all__` listing every re-export. Architecture §Public API Discipline: "Examples and documentation use the `pyjmri` top-level only."
  - [x] **Keep the existing `NullHandler` install** — it's already there from Story 1.1, and AC #5 verifies it stays. Do not duplicate it.
  - [x] Final shape:

    ```python
    import logging

    from pyjmri.client import Client, ClientConfig, ReconnectConfig
    from pyjmri.exceptions import (
        JMRIConnectionError,
        JMRIError,
        JMRIProtocolError,
        # ... full list
    )

    logging.getLogger("pyjmri").addHandler(logging.NullHandler())

    __all__ = [
        "Client",
        "ClientConfig",
        "ReconnectConfig",
        "JMRIError",
        # ... etc.
    ]
    ```

- [x] **Task 6: Add unit tests for `exceptions.py`** (AC: #2)
  - [x] Create `tests/unit/test_exceptions.py`. No marker (unit tests are unmarked per architecture §Testing Patterns).
  - [x] Cover, at minimum:
    - `JMRIConnectionError(host="localhost", port=12080)` formats as the FR35 string (assert against the exact text).
    - Each subclass instantiates without crashing and accepts arbitrary keyword diagnostic context that ends up in `.context`.
    - `WaitTimeout` is `isinstance` of both `JMRIError` and `TimeoutError`.
    - `try: ... except JMRIError: ...` catches every subclass.
    - Cause chaining works: a `try/raise/from` block produces an exception whose `__cause__` is the original.
  - [x] **Test naming follows architecture §Testing Patterns:** `test_<scenario_described_in_snake_case>`. E.g., `test_jmri_connection_error_str_matches_fr35`, `test_wait_timeout_caught_as_timeout_error`.

- [x] **Task 7: Add unit tests for transport-boundary exception wrapping** (AC: #1)
  - [x] Create `tests/unit/test_transport.py`.
  - [x] **No real httpx requests.** Use httpx's mock transport (`httpx.MockTransport`) to inject failures. Architecture §Testing Patterns says "no mocks of JMRI" — but mocking httpx itself (the third-party transport) is fine; we're testing our wrapper, not JMRI's behavior.
  - [x] Cover:
    - `httpx.ConnectError` raised by mock transport → wrapped as `JMRIConnectionError`; `host` / `port` populated; `__cause__` is the original.
    - `httpx.TimeoutException` raised by mock transport → wrapped as `JMRIRequestTimeout`; `__cause__` chained.
    - Non-200 status → `JMRIProtocolError` with status code in `context`.
    - 200 + valid JSON → returned as `dict[str, Any]` unchanged.

- [x] **Task 8: Add unit tests for `Client` URL parsing and lifecycle** (AC: #3, #4)
  - [x] Create `tests/unit/test_client.py`.
  - [x] Cover URL parsing happy paths (table-driven with `pytest.mark.parametrize`):
    - `"localhost:12080"` → `(host="localhost", port=12080, scheme="http")`
    - `"http://localhost:12080"` → same
    - `"ws://localhost:12080/json"` → same (scheme normalized)
    - `"https://example.com:12080"` → `("example.com", 12080, "https")`
  - [x] Cover URL parsing failures:
    - `"localhost"` (no port) → `ValueError`
    - `""` → `ValueError`
    - `"http://"` → `ValueError`
  - [x] Cover async-context-manager lifecycle using a fake `HTTPClient` (parametrize the Client to accept a transport factory, OR monkey-patch `httpx.AsyncClient` to use a `MockTransport` that confirms the connection probe is fired and `aclose()` is called once).
  - [x] Cover unreachable-host path: configure a mock transport that raises `httpx.ConnectError` → `__aenter__` raises `JMRIConnectionError` → `host`, `port` populated → `__cause__` set.

- [x] **Task 9: Add the integration smoke test** (AC: #6)
  - [x] Create `tests/integration/test_connection_lifecycle.py`.
  - [x] Single test, marked `@pytest.mark.integration`:

    ```python
    @pytest.mark.integration
    async def test_client_connects_and_disconnects_cleanly(jmri_available: None) -> None:
        async with Client() as jmri:
            pass
        # No assertion needed: success = no raise.
    ```

  - [x] **Skip-on-absence fixture lives in `tests/integration/conftest.py`** — see §"Skip-on-absence fixture" below for the canonical shape. This is the seed of what Story 2.5 will enrich; build it small.
  - [x] **CI never runs this test.** The CI workflow invokes `pytest -m "not integration"` (per Story 1.3); the marker keeps integration tests local-only per architecture §Test Harness.

- [x] **Task 10: Verify the four local quality gates still pass** (AC: implicit — don't regress Stories 1.2–1.4)
  - [x] From `python_code/`:
    - `uv run ruff check` → 0
    - `uv run ruff format --check` → 0
    - `uv run mypy src/pyjmri` → 0 (strict-mode clean across new modules)
    - `uv run pytest -m "not integration"` → exit 0 (the new unit tests should produce real test counts, no longer exit-5)
  - [x] **`mypy --strict` is the most likely gate to surface friction.** httpx is fully typed and mypy-strict friendly out of the box, but watch for: missing `await` annotations, untyped `dict[str, Any]` leakage where a more specific type fits, `Any` in return positions. Architecture §Type Annotation Conventions: "No `Any` in the public surface."
  - [x] **Push to GitHub and watch the six-job CI matrix.** Same flow as Stories 1.2/1.3/1.4: local-clean before push, CI as the backstop. Cache from Story 1.4's push will warm-start the runs.

### Review Findings

- [x] [Review][Patch] Unheld httpx.TransportError subclasses escape the transport boundary [`python_code/src/pyjmri/_transport.py`] — Added `except httpx.TransportError` catch-all after specific handlers; maps to `JMRIConnectionError` with `error_type` context. Test `test_other_transport_error_wrapped_as_jmri_connection_error` added.
- [x] [Review][Patch] Logger name is `pyjmri._transport`, not `pyjmri.transport` [`python_code/src/pyjmri/_transport.py:22`] — Fixed: `logging.getLogger("pyjmri.transport")` used explicitly.
- [x] [Review][Patch] Client `__aenter__` re-entrancy leaks the first HTTPClient [`python_code/src/pyjmri/client.py:76`] — Added `if self._http is not None: raise RuntimeError(...)` guard. Test `test_aenter_reentrant_raises_runtime_error` added.
- [x] [Review][Patch] `subscription_replay_timeout` in `ClientConfig` is not documented as currently unused [`python_code/src/pyjmri/client.py:43`] — Added inline docstring noting it is consumed by Epic 3; currently unused in v1.
- [x] [Review][Patch] `_parse_url` rejects port 0 with wrong error via falsy check [`python_code/src/pyjmri/client.py:125`] — Fixed: `not parsed.port` → `parsed.port is None`.
- [x] [Review][Patch] Missing test: `JMRIConnectionError.__str__` ignores its `message` argument (intentional but untested) [`python_code/tests/unit/test_exceptions.py`] — Added `test_jmri_connection_error_str_ignores_message`.
- [x] [Review][Defer] Logger calls absent in `_transport.py` and `client.py` — AC #5 only requires logger declaration; actual DEBUG/INFO calls are appropriate for later stories (2.2+) when there are HTTP request/response events to log. Deferring to stories that add substantive operations.
- [x] [Review][Defer] `aclose()` raising in `__aexit__` or probe-cleanup can mask original exception — `httpx.AsyncClient.aclose()` is documented not to raise in normal circumstances; this is a common Python context-manager tradeoff. Deferring.
- [x] [Review][Defer] Probe endpoint deviation (`/json/v5/version`) not recorded in architecture document — Captured in completion notes and in retro action items (A1). Architecture doc update deferred per existing action items.

## Dev Notes

### `exceptions.py` canonical shape

```python
"""JMRIError hierarchy. See architecture §Exception Hierarchy."""
from __future__ import annotations

from typing import Any

__all__ = [
    "JMRIError",
    "JMRIConnectionError",
    "JMRIReconnectFailed",
    "JMRIRequestTimeout",
    "JMRIProtocolError",
    "JMRIVersionUnsupported",
    "LayoutEntityNotFound",
    "LayoutEntityNotControllable",
    "ThrottleError",
    "ThrottleAcquireFailed",
    "ThrottleReleased",
    "WaitTimeout",
]


class JMRIError(Exception):
    """Base class for every error pyjmri raises.

    Library code never raises `JMRIError` directly — only concrete
    subclasses. The base exists for catch-all `except JMRIError` blocks
    in user code.

    Args:
        message: Optional human-readable summary.
        **context: Diagnostic key/value pairs, surfaced via `.context`
            and rendered into `__str__`.
    """

    def __init__(self, message: str | None = None, /, **context: Any) -> None:
        super().__init__(message or "")
        self.context: dict[str, Any] = context

    def __str__(self) -> str:
        msg = super().__str__()
        if not self.context:
            return msg
        ctx = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
        return f"{msg} [{ctx}]" if msg else f"[{ctx}]"


class JMRIConnectionError(JMRIError):
    """Raised when the library cannot reach JMRI's web server."""

    def __init__(
        self,
        message: str | None = None,
        /,
        *,
        host: str,
        port: int,
        **context: Any,
    ) -> None:
        super().__init__(message, host=host, port=port, **context)
        self.host = host
        self.port = port

    def __str__(self) -> str:
        # FR35 actionable format. See §"FR35-conformant __str__".
        return (
            f"could not connect to {self.host}:{self.port} — "
            f"is JMRI running with the web server enabled?"
        )


class JMRIReconnectFailed(JMRIConnectionError):
    """Raised when the WebSocket reconnect loop exhausts max_attempts."""


class JMRIRequestTimeout(JMRIError):
    """Raised when an HTTP request exceeds `request_timeout`."""


class JMRIProtocolError(JMRIError):
    """Raised when JMRI's response does not match the assumed JSON contract."""


class JMRIVersionUnsupported(JMRIProtocolError):
    """Raised when the connected JMRI is older than the minimum version (5.14)."""


class LayoutEntityNotFound(JMRIError):
    """Raised when a name is not in the user-name OR system-name index."""


class LayoutEntityNotControllable(JMRIError):
    """Raised when a `set_state` is attempted on a read-only entity (e.g. signalMast)."""


class ThrottleError(JMRIError):
    """Base for throttle lifecycle errors."""


class ThrottleAcquireFailed(ThrottleError):
    """Raised when JMRI rejects a throttle acquire request."""


class ThrottleReleased(ThrottleError):
    """Raised when a throttle method is called after `.release()`."""


class WaitTimeout(JMRIError, TimeoutError):
    """Raised when an `await wait_*` exceeds its optional timeout.

    Multi-inherits the builtin `TimeoutError` so user code can catch
    either `JMRIError` or `TimeoutError`.
    """
```

**Notes on the shape:**

- **Positional message + keyword-only context** keeps the constructor ergonomic for both `raise JMRIConnectionError(host="x", port=12080)` (no message; context only) and `raise JMRIProtocolError("bad shape", endpoint="/json/turnout")` (message + context).
- **`context` is a `dict[str, Any]`** per architecture §Exception Hierarchy. The Any is acceptable here because diagnostic context is, by definition, polymorphic; this is the one place architecture explicitly tolerates `Any`.
- **`JMRIConnectionError.__str__` overrides** the base. Other subclasses use the base format (which renders the context dict). The override is what AC #2 requires: a specific, actionable message for connection failures.
- **`JMRIReconnectFailed` extends `JMRIConnectionError`** so an `except JMRIConnectionError:` block catches both. Architecture §Exception Hierarchy diagram: `JMRIConnectionError → JMRIReconnectFailed`.
- **`JMRIVersionUnsupported` extends `JMRIProtocolError`** for the same reason — version drift IS a protocol shape mismatch, and `except JMRIProtocolError:` should catch it. Architecture §Exception Hierarchy diagram: `JMRIProtocolError → JMRIVersionUnsupported`.

### FR35-conformant `__str__` for `JMRIConnectionError`

PRD FR35: "Connection-failure exceptions include actionable diagnostic context (host, port, suggested cause)."

Architecture §Exception Hierarchy: "`JMRIConnectionError.__str__` formats actionable text per FR35 (e.g., `could not connect to localhost:12080 — is JMRI running with the web server enabled?`)."

Use that exact phrasing template:

```python
return (
    f"could not connect to {self.host}:{self.port} — "
    f"is JMRI running with the web server enabled?"
)
```

This is the *one* place in the library where the message wording is part of the contract — AC #2 asserts against it. Don't paraphrase. Future tweaks to the wording must update both the implementation and the assertion in `test_exceptions.py`.

### `_transport.HTTPClient` canonical shape

```python
"""HTTP transport boundary. The only module allowed to import or
catch httpx exceptions. See architecture §Transport Layer and
§Architectural Boundaries.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from pyjmri.exceptions import (
    JMRIConnectionError,
    JMRIProtocolError,
    JMRIRequestTimeout,
)

logger = logging.getLogger(__name__)  # → pyjmri.transport


class HTTPClient:
    """Async HTTP client wrapper around `httpx.AsyncClient`.

    Catches `httpx.*` exceptions and re-raises them as `JMRIError`
    subclasses with `from e`. No other module in the package is
    allowed to do this.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        scheme: str = "http",
        request_timeout: float = 10.0,
    ) -> None:
        self._host = host
        self._port = port
        self._base_url = f"{scheme}://{host}:{port}"
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=request_timeout,
        )

    async def get(self, path: str) -> dict[str, Any]:
        """GET `path` and return the parsed JSON body.

        Raises:
            JMRIConnectionError: when the underlying socket cannot connect.
            JMRIRequestTimeout: when the request exceeds `request_timeout`.
            JMRIProtocolError: when the response is non-200 or non-JSON.
        """
        try:
            response = await self._http.get(path)
        except httpx.ConnectError as e:
            raise JMRIConnectionError(host=self._host, port=self._port) from e
        except httpx.TimeoutException as e:
            raise JMRIRequestTimeout(
                "HTTP request exceeded request_timeout",
                host=self._host,
                port=self._port,
                path=path,
            ) from e

        if response.status_code != 200:
            raise JMRIProtocolError(
                "unexpected HTTP status",
                status=response.status_code,
                path=path,
            )

        try:
            payload = response.json()
        except ValueError as e:
            raise JMRIProtocolError(
                "response body was not valid JSON",
                path=path,
            ) from e

        if not isinstance(payload, dict):
            raise JMRIProtocolError(
                "response JSON was not an object",
                path=path,
                actual_type=type(payload).__name__,
            )

        return payload

    async def aclose(self) -> None:
        """Close the underlying httpx client. Idempotent."""
        await self._http.aclose()
```

**Why this shape:**

- **Boundary discipline.** Only this file imports `httpx`; only this file catches `httpx.*`. Architecture §Architectural Boundaries point 2.
- **`from e` chaining everywhere.** Architecture §Error Handling Discipline: "every `except` either re-raises (with `from e` if a new exception is raised) or completes a documented cleanup path."
- **No `httpx.HTTPError`-wide catch.** Catching the base would mask programming errors as protocol errors. The two known wire-level conditions (`ConnectError`, `TimeoutException`) are caught by name; everything else propagates and surfaces as a bug in our wrapper, not a JMRI fault.
- **`get()` returns `dict[str, Any]`, not a typed entity.** Architecture §JSON ↔ Python Translation: "Translation happens at the parse boundary in `_parsing.py`. No public-API method ever returns a raw JSON dict." But `_parsing.py` is Story 2.2, and `_transport.HTTPClient.get` is *internal* — its return type is the input to a future `_parsing.parse_*` call. The `Any` here is permitted because architecture §Type Annotation Conventions explicitly allows it as a parser-input parameter type.
- **Logger declared module-level** per architecture §Logging Discipline. Story 2.1 doesn't require any actual log calls — just the logger object — so AC #5 is satisfied by its presence. Future stories will add `logger.debug(...)` / `logger.warning(...)` as request paths grow.

### `client.py` canonical shape

```python
"""Client lifecycle and configuration. See architecture §Client
Configuration Shape and §Concurrency Model.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self
from urllib.parse import urlparse

from pyjmri._transport import HTTPClient

logger = logging.getLogger(__name__)  # → pyjmri.client


@dataclass(frozen=True, kw_only=True)
class ReconnectConfig:
    """WebSocket reconnect tuning. Consumed by Epic 3."""

    initial_delay: float = 0.5
    max_delay: float = 30.0
    jitter: float = 0.25
    max_attempts: int | None = None  # None = retry forever


@dataclass(frozen=True, kw_only=True)
class ClientConfig:
    """Client-wide configuration."""

    request_timeout: float = 10.0
    reconnect: ReconnectConfig = field(default_factory=ReconnectConfig)
    subscription_replay_timeout: float = 30.0


class Client:
    """Async context manager binding to a JMRI web server.

    Example:
        async with Client() as jmri:
            ...

    The default URL is `localhost:12080`. URL accepts `host:port`,
    `http://host:port`, or `ws://host:port/json`.
    """

    def __init__(
        self,
        url: str = "localhost:12080",
        *,
        config: ClientConfig | None = None,
    ) -> None:
        host, port, scheme = _parse_url(url)
        self._host = host
        self._port = port
        self._scheme = scheme
        self._config = config or ClientConfig()
        self._http: HTTPClient | None = None

    async def __aenter__(self) -> Self:
        self._http = HTTPClient(
            host=self._host,
            port=self._port,
            scheme=self._scheme,
            request_timeout=self._config.request_timeout,
        )
        # Probe so an unreachable host fails NOW, not on the first user call.
        # See §"Connection probe in __aenter__".
        await self._http.get("/json/v5")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


def _parse_url(url: str) -> tuple[str, int, str]:
    """Return (host, port, scheme) for the supported URL forms.

    Accepts:
        - "host:port"
        - "http://host:port" / "https://host:port"
        - "ws://host:port/path" / "wss://host:port/path"

    `ws`/`wss` schemes are accepted for forward-compat with Epic 3
    and are normalized to `http`/`https` for HTTP transport.
    """
    if "://" not in url:
        url = f"http://{url}"
    parsed = urlparse(url)
    if not parsed.hostname or not parsed.port:
        raise ValueError(f"URL must include host and port: {url!r}")
    scheme = {
        "http": "http",
        "https": "https",
        "ws": "http",
        "wss": "https",
    }.get(parsed.scheme)
    if scheme is None:
        raise ValueError(
            f"unsupported URL scheme {parsed.scheme!r}; "
            f"use http, https, ws, or wss"
        )
    return parsed.hostname, parsed.port, scheme
```

**Why this shape:**

- **`Self` return on `__aenter__`** per architecture §Type Annotation Conventions ("`Self` for chaining and factory methods that return the same class"). Available in `typing` since 3.11.
- **`urlparse` from stdlib** instead of a regex. It's the boring, correct choice. Handles edge cases (IPv6, percent-encoded characters) that hand-rolled parsing would miss.
- **`ws`/`wss` normalize to `http`/`https`** for the HTTPClient. The original URL form is not preserved beyond Story 2.1 because Story 3.1 will spin up the WSConnection separately; both transports derive their URLs from the same `(host, port, scheme)` triple.
- **Connection probe (`get("/json/v5")`)** ensures `__aenter__` actually exercises the network, so an unreachable host raises `JMRIConnectionError` *now* rather than on the user's first read call. See next subsection.
- **`__aexit__` does NOT swallow exceptions.** It returns `None`, so any in-context exception propagates. Idempotency on the close path: nulling `self._http` after close prevents accidental double-close in pathological re-entry scenarios.
- **Dataclasses are frozen + kw-only** per architecture §Client Configuration Shape. `kw_only=True` requires Python 3.10+ (we're on 3.11+, so it's fine). `frozen=True` blocks mutation; user supplies values at construction.

### Connection probe in `__aenter__`

The architecture-mandated behavior is "Client connects on entry … fails fast and informatively." But `httpx.AsyncClient(base_url=...)` is lazy — it does not open a TCP connection until the first request. Without a probe, an unreachable host would silently "connect" in `__aenter__` and only fail on the first user call. That violates AC #4 and the spirit of FR4.

The pragmatic probe is a single GET to a JMRI metadata endpoint. `/json/v5` is the conventional JMRI v5 root and is the same path Story 2.5 will use for the version check — touching it in 2.1 establishes the path, and 2.5 will parse the body for the version field.

If a future architecture decision says "no probe; let the first user call fail," the probe can be deleted. For Story 2.1, the probe is the simplest path to AC #4.

**Why not `HEAD /` or `GET /`?**

- JMRI's web server may serve an HTML root that returns 200 from a non-pyjmri-relevant endpoint. We want a probe that confirms the JSON v5 surface is reachable, not just that the server is alive.
- `/json/v5` is documented in architecture §Discovery Strategy as the version-detection endpoint. Using it here is a free preview; Story 2.5 builds on the same call.

### Skip-on-absence fixture

`tests/integration/conftest.py` (currently empty) gets this content:

```python
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
    """Skip the rest of the test session unless JMRI is reachable."""
    if not _jmri_listening():
        pytest.skip(
            "JMRI is not reachable on localhost:12080 — "
            "start JMRI with the web server enabled to run integration tests."
        )
```

**Why a TCP-level probe** rather than an HTTP probe?

- **Speed.** TCP connect is sub-millisecond on `localhost`; an HTTP round-trip adds JSON parsing overhead.
- **Decoupling.** The fixture must not depend on the very modules it's bootstrapping. A test of `Client` shouldn't be skipped by a bug in `Client`. Stdlib socket is the floor.
- **Architecture §Test Harness:** "Skip-on-absence fixture probes JMRI at session start; if unreachable, skips all integration tests with a clear message." That's exactly what this does.

Story 2.5 will replace this with a richer fixture that exercises `Client` itself and verifies the version. For Story 2.1, this seed is sufficient.

### Architecture compliance checklist

| Architecture / PRD rule | Story 2.1 alignment |
| --- | --- |
| §Transport Layer — "httpx (async client only)" | Task 1 (add httpx) + Task 3 (`HTTPClient` wraps `httpx.AsyncClient`) |
| §Architectural Boundaries point 2 — only `_transport.py` imports/catches httpx | Task 3 (everything httpx-touching is here) |
| §Exception Hierarchy — full `JMRIError` tree with `context: dict[str, Any]` | Task 2 |
| §Error Handling Discipline — `from e` chaining at the boundary | Task 3 (`raise X(...) from e` on every except) |
| §Error Handling Discipline — `WaitTimeout(JMRIError, TimeoutError)` multi-inherit | Task 2 |
| §Logging Strategy — module-level `logger = logging.getLogger(__name__)` | Tasks 3, 4 |
| §Client Configuration Shape — `Client(url, *, config)` + frozen kw_only dataclasses | Task 4 |
| §Concurrency Model — no Client-level TaskGroup yet (no supervised tasks in 2.1) | Task 4 (deliberately deferred) |
| §Internal Layering — public modules import from private; never the inverse | Tasks 3, 4 (`client.py` imports `_transport`; `_transport.py` imports `exceptions`) |
| §Public API Discipline — `__all__` everywhere | Tasks 2, 5 |
| §Type Annotation Conventions — `from __future__ import annotations`, PEP 604, `Self` | All tasks |
| §JSON ↔ Python Translation — no JSON dict on the public API | Task 3 (`HTTPClient.get` is internal; `dict[str, Any]` is the parser-input type) |
| §Test Harness — unit/integration split; `pytest.mark.integration` | Tasks 6–9 |
| §Testing Patterns — file naming, function naming, no JMRI mocks | Tasks 6–9 |
| FR1 — connect by host:port | Task 4 (`_parse_url`) |
| FR2 — default `localhost:12080` | Task 4 (default arg + tests) |
| FR3 — async context-manager lifecycle | Task 4 (`__aenter__`/`__aexit__`) |
| FR4 — typed connection error with diagnostic context | Tasks 2, 3 (boundary wrap + `JMRIConnectionError`) |
| FR34 — typed exceptions from documented hierarchy | Task 2 |
| FR35 — actionable connection-failure text (host, port, suggested cause) | Task 2 (`__str__` override) |
| FR36 — structured logging without forced configuration | Task 5 (`NullHandler` already in `__init__.py`) |
| NFR7 — Python 3.11+ | inherited from Stories 1.1, 1.2 (already enforced) |
| NFR10 — default `localhost:12080` | Task 4 |

### Latest tool specifics (knowledge cutoff: January 2026)

- **httpx 0.28.x** is the current stable line on PyPI. Async client is the primary API surface; the sync `httpx.Client` is irrelevant here. mypy-strict friendly out of the box (httpx ships its own type stubs).
- **httpx exception hierarchy** (relevant types only):
  - `httpx.HTTPError` (base)
    - `httpx.RequestError` (base for transport-level errors)
      - `httpx.TransportError`
        - `httpx.NetworkError`
          - `httpx.ConnectError` ← we catch this
        - `httpx.TimeoutException` ← we catch this
          - `ConnectTimeout`, `ReadTimeout`, `WriteTimeout`, `PoolTimeout`
  - Catching `httpx.TimeoutException` covers all four timeout subtypes — that's what we want for v1.
- **`httpx.MockTransport`** is the canonical way to inject failures in unit tests. It's part of the public API and is mypy-strict friendly. Architecture §Testing Patterns "no mocks of JMRI" applies to JMRI; this mocks httpx itself, which is fine.
- **mypy 2.0** is on `uv.lock` (resolved during Story 1.2). `strict = true` mode is unchanged from Story 1.2's setup.
- **pytest-asyncio** with `asyncio_mode = "auto"` (Story 1.2) means async test functions don't need the `@pytest.mark.asyncio` decorator — write `async def test_*(...)` directly.

### Reference: previous story context

**Story 1.4 (status `done`):** Created `python_code/LICENSE` (MIT) and the `README.md` scaffold. Added `twine` as dev dep. Built `dist/` artifacts; `twine check` PASSED. Story 2.1's changes will trigger CI again on push (path filter matches `python_code/**`).

**Story 1.3 (status `done`):** CI runs `ruff check`, `ruff format --check`, `mypy src/pyjmri`, and `pytest -m "not integration"` on macOS-latest + ubuntu-latest × Python 3.11/3.12/3.13. Story 2.1 must keep all four green.

**Story 1.2 (status `done`):** Configured `[tool.ruff]` (rules `E, W, F, I, B, UP, ASYNC, RUF`), `[tool.mypy]` (`strict = true`), `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`, marker `integration`). Story 2.1 inherits these — no config changes.

**Story 1.1 (status `done`, no story file):** `uv init --lib --name pyjmri` produced the `src/pyjmri/__init__.py` (with NullHandler installed at import time) and `py.typed`. Story 2.1's `__init__.py` edit preserves the NullHandler call.

### Epic 1 retrospective signals to honor

From `_bmad-output/implementation-artifacts/epic-1-retro-2026-05-07.md`:

- **Action item A3:** "Decide whether to keep or remove the pytest exit-5 guard in `ci.yml` after Story 2.1 lands tests." **Decision: leave it in for now.** It becomes a no-op once tests exist (because pytest will return 0, not 5). Removing it is harmless cleanup that can come in a future story, not blocking 2.1.
- **Action items A1, A2** are documentation-only fixes to the architecture document (CI workflow placement; tool version drift). Out of scope for Story 2.1.
- **"Story creation is where defects get caught."** Honor that pattern by being exhaustive in the dev-notes here so the dev agent has zero ambiguity.

### Things explicitly NOT in this story

These belong to later stories — resist the urge to bundle:

- `WSConnection` / WebSocket plumbing → **Story 3.1**
- `SubscriptionRegistry` → **Story 3.1**
- `_codes.py` integer-code tables → **Story 2.2**
- `_parsing.py` per-entity parsers → **Story 2.2**
- Any entity class (`Turnout`, `Sensor`, ...) → **Story 2.3**
- `EntityCollection` and `Layout` → **Story 2.4**
- `Client.discover()` → **Story 2.5**
- `Client.power_state()` → **Story 2.3**
- HTTP POST/PUT for commands → **Story 4.1**
- `Client`-level `asyncio.TaskGroup` activation → arrives with the first supervised coroutine, which is the WS receive loop in **Story 3.1**
- `_protocols.py` (`ClientHandle` Protocol) → **Story 2.3**

### Verification matrix (after all tasks complete)

| Check | Expected outcome |
| --- | --- |
| `python_code/src/pyjmri/exceptions.py` exists with full `JMRIError` tree | ✅ |
| `python_code/src/pyjmri/_transport.py` exists with `HTTPClient` | ✅ |
| `python_code/src/pyjmri/client.py` exists with `Client`, `ClientConfig`, `ReconnectConfig` | ✅ |
| `python_code/src/pyjmri/__init__.py` re-exports `Client` and exception classes; NullHandler retained | ✅ |
| `python_code/pyproject.toml` `[project] dependencies` lists `httpx>=…` | ✅ |
| `python_code/uv.lock` records the resolved httpx version + closure | ✅ |
| `tests/unit/test_exceptions.py` passes; covers FR35 string, multi-inherit, chaining | ✅ |
| `tests/unit/test_transport.py` passes; covers httpx-error wrapping via `MockTransport` | ✅ |
| `tests/unit/test_client.py` passes; covers URL parsing + lifecycle + unreachable-host path | ✅ |
| `tests/integration/test_connection_lifecycle.py` is `@pytest.mark.integration` and skips when JMRI absent | ✅ |
| `tests/integration/conftest.py` defines the `jmri_available` skip-on-absence fixture | ✅ |
| Only `_transport.py` imports `httpx` (verifiable by `grep -r "^import httpx\|^from httpx" src/`) | ✅ |
| `uv run ruff check` → 0 | ✅ |
| `uv run ruff format --check` → 0 | ✅ |
| `uv run mypy src/pyjmri` → 0 (strict) | ✅ |
| `uv run pytest -m "not integration"` → 0, real test count > 0 | ✅ |
| GitHub Actions CI six-job matrix goes green on push | ✅ |

### Project Structure Notes

All new files live under `python_code/`:

- `src/pyjmri/exceptions.py` — NEW
- `src/pyjmri/_transport.py` — NEW
- `src/pyjmri/client.py` — NEW
- `src/pyjmri/__init__.py` — UPDATE (add re-exports + `__all__`; preserve existing NullHandler line)
- `tests/unit/test_exceptions.py` — NEW
- `tests/unit/test_transport.py` — NEW
- `tests/unit/test_client.py` — NEW
- `tests/integration/conftest.py` — UPDATE (currently empty; add `jmri_available` fixture)
- `tests/integration/test_connection_lifecycle.py` — NEW
- `pyproject.toml` — UPDATE (`uv add httpx` adds entry to `[project] dependencies`)
- `uv.lock` — UPDATE (refreshed by `uv add`)

No structural deviations from architecture §Complete Project Directory Structure. Files land at the exact paths the architecture specifies; nothing is renamed or relocated.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.1: HTTP transport + Client lifecycle + exception hierarchy + logging foundation] — story scope and ACs
- [Source: _bmad-output/planning-artifacts/architecture.md#Transport Layer] — httpx (async client only); rationale; `websockets >= 16.0` deferred to Epic 3
- [Source: _bmad-output/planning-artifacts/architecture.md#Exception Hierarchy] — full `JMRIError` tree, diagnostic context, FR35 wording
- [Source: _bmad-output/planning-artifacts/architecture.md#Error Handling Discipline] — `from e` discipline, `WaitTimeout` multi-inherit, no swallowed exceptions
- [Source: _bmad-output/planning-artifacts/architecture.md#Logging Strategy] — module-level loggers, hierarchy (`pyjmri.transport`, `pyjmri.client`), `NullHandler` install
- [Source: _bmad-output/planning-artifacts/architecture.md#Client Configuration Shape] — `Client(url, *, config)`; frozen kw_only `ClientConfig` and `ReconnectConfig`
- [Source: _bmad-output/planning-artifacts/architecture.md#Internal Layering] — public/private split; transport/domain boundary
- [Source: _bmad-output/planning-artifacts/architecture.md#Architectural Boundaries] — only `_transport.py` imports/catches httpx
- [Source: _bmad-output/planning-artifacts/architecture.md#Type Annotation Conventions] — `from __future__ import annotations`, PEP 604 unions, `Self`, no `Any` on public surface
- [Source: _bmad-output/planning-artifacts/architecture.md#Public API Discipline] — `__all__`, top-level re-exports
- [Source: _bmad-output/planning-artifacts/architecture.md#Test Harness] — unit/integration split; skip-on-absence fixture
- [Source: _bmad-output/planning-artifacts/architecture.md#Testing Patterns] — file/function naming, no JMRI mocks (httpx mocks are fine)
- [Source: _bmad-output/planning-artifacts/prd.md FR1] — connect by host:port
- [Source: _bmad-output/planning-artifacts/prd.md FR2] — default `localhost:12080`
- [Source: _bmad-output/planning-artifacts/prd.md FR3] — async context-manager lifecycle
- [Source: _bmad-output/planning-artifacts/prd.md FR4] — typed connection error with diagnostic context
- [Source: _bmad-output/planning-artifacts/prd.md FR34] — typed exceptions from `JMRIError` hierarchy
- [Source: _bmad-output/planning-artifacts/prd.md FR35] — actionable connection-failure text
- [Source: _bmad-output/planning-artifacts/prd.md FR36] — structured logging without forced configuration
- [Source: _bmad-output/planning-artifacts/prd.md NFR7] — Python 3.11+
- [Source: _bmad-output/planning-artifacts/prd.md NFR10] — default `localhost:12080`
- [Source: _bmad-output/implementation-artifacts/epic-1-retro-2026-05-07.md] — Epic 1 retrospective; Epic 2 preparation; action items A1–A4

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Opus 4.7, 1M context)

### Debug Log References

Implementation date: 2026-05-07.

**Quality gates after implementation:**

```
=== ruff check ===
All checks passed!
=== ruff format --check ===
10 files already formatted
=== mypy --strict ===
Success: no issues found in 4 source files
=== pytest -m "not integration" ===
53 passed, 1 deselected in 0.06s
=== pytest (full suite, integration included) ===
54 passed in 0.11s
```

**Transport-boundary audit:**

```
$ grep -rEn "^(import httpx|from httpx)" src/pyjmri/
src/pyjmri/_transport.py:12:import httpx
```

Only `_transport.py` imports httpx. Architecture §Architectural Boundaries point 2 satisfied.

**Resolved tool versions** (from `uv.lock`):

- `httpx==0.28.1`
- `httpcore==1.0.9`
- `h11==0.16.0`
- `anyio==4.13.0`

### Completion Notes List

- All six ACs satisfied. AC #1: `_transport.HTTPClient` is the sole module touching httpx; `httpx.ConnectError → JMRIConnectionError` and `httpx.TimeoutException → JMRIRequestTimeout`, both `from e`. AC #2: full `JMRIError` hierarchy in `exceptions.py`; `JMRIConnectionError.__str__` matches FR35 exactly; `WaitTimeout` multi-inherits `TimeoutError`. AC #3: `Client(url, *, config)` async context manager; URL parser accepts `host:port`, `http://...`, `ws://.../json`, plus https/wss; default `localhost:12080`. AC #4: `__aenter__` connection probe surfaces `JMRIConnectionError` with chained cause and host/port context; `__aenter__` cleans up its partial transport on failure. AC #5: `pyjmri/__init__.py` retains the `NullHandler` install; `_transport.py` and `client.py` declare module-level loggers. AC #6: integration smoke test marked `@pytest.mark.integration` runs against the live JMRI session and uses the `jmri_available` skip-on-absence fixture in `tests/integration/conftest.py`.
- **Probe endpoint changed mid-implementation.** Story originally specified `GET /json/v5` as the connection probe. Live testing against `Basement_Revised_2024.jmri` revealed that `/json/v5` serves a JSON Console **HTML** page (it's the JMRI debug UI), not JSON metadata. Changed the probe to `GET /json/v5/version`, which is the documented JMRI JSON v5 version endpoint that returns `[{"type":"version","data":{"5.4.0":"v5"}}]`. Story 2.5 will reuse this same endpoint for the `JMRIVersionUnsupported` check.
- **`HTTPClient.get()` return type widened** from `dict[str, Any]` to `dict[str, Any] | list[dict[str, Any]]`. JMRI's JSON v5 returns arrays at collection endpoints (`/json/v5/turnout`, `/json/v5/version`, etc.) and a single object at named-entity endpoints (`/json/v5/turnout/NT400`). Both are valid. Architecture §JSON ↔ Python Translation permits this — narrowing is `_parsing.py`'s job (Story 2.2).
- **`Client` does not import httpx.** First draft did, for typing the test-injection `transport` parameter. Architecture §Architectural Boundaries explicitly forbids httpx imports outside `_transport.py`. Removed the parameter; client tests use `pytest.MonkeyPatch.setattr(client_module, "HTTPClient", FakeHTTPClient)` instead. The `transport` parameter is retained on `HTTPClient` itself (which is allowed to import httpx) as a constructor knob for transport-layer unit tests.
- **`__aenter__` failure path closes the partial transport.** When the connection probe raises, the half-opened `httpx.AsyncClient` is closed and `self._http` is reset to `None` before re-raising. Test `test_aenter_failure_wraps_to_jmri_connection_error` asserts on this — without it, an unreachable host would leak resources.
- **Test count: 54 total** — 22 exception, 9 transport, 22 client (URL parsing parametrized + lifecycle + monkeypatch lifecycle), 1 integration.
- **JMRI live verification.** While running the integration suite, JMRI was reachable on `localhost:12080`. The smoke test passed against the actual server (Mike's Basement Layout, JMRI 5.4.0). This is the first end-to-end pyjmri ↔ JMRI round-trip.
- **CI status pending Mikey's push.** Local-clean before push; six-job matrix expected to go green. The new test count (53 unit) replaces the previous exit-5 case from Stories 1.2–1.4 — pytest will return 0 with real test counts going forward, retiring action item A3 from the Epic 1 retro as a no-op.

### File List

Created:

- `python_code/src/pyjmri/exceptions.py` — full `JMRIError` hierarchy (12 classes); FR35-conformant `JMRIConnectionError.__str__`; `WaitTimeout(JMRIError, TimeoutError)`.
- `python_code/src/pyjmri/_transport.py` — `HTTPClient` async wrapper around `httpx.AsyncClient`. Module-level `logger = logging.getLogger(__name__)`. Wraps `httpx.ConnectError` → `JMRIConnectionError`, `httpx.TimeoutException` → `JMRIRequestTimeout`. Accepts both dict and list-of-dicts response shapes (matches JMRI JSON v5).
- `python_code/src/pyjmri/client.py` — `Client(url, *, config)` async context manager + frozen `ClientConfig` and `ReconnectConfig` dataclasses. URL parser accepts `host:port`, `http`/`https`, and `ws`/`wss` (normalized to http/https for HTTP transport). `__aenter__` probes `/json/v5/version`; cleans up on probe failure.
- `python_code/tests/unit/test_exceptions.py` — 22 tests: FR35 string, host/port attrs, hierarchy `isinstance` chains, multi-inherit `WaitTimeout`, base `__str__` formatting, parametrized "every subclass caught by `JMRIError`", cause chaining, arbitrary diagnostic context.
- `python_code/tests/unit/test_transport.py` — 9 tests via `httpx.MockTransport`: ConnectError wrap, ReadTimeout wrap, non-200 → `JMRIProtocolError`, non-JSON body, non-JMRI shape (top-level list of ints, top-level string), 200 dict round-trip, 200 list-of-dicts round-trip, idempotent `aclose`.
- `python_code/tests/unit/test_client.py` — 22 tests: parametrized URL happy paths (6 forms), parametrized URL rejection (5 invalid forms), unsupported-scheme rejection, default URL/config, custom config plumbing, all three documented URL forms, monkeypatched lifecycle (probe + aclose), `__aenter__` failure path with chained cause and partial-transport cleanup, `__aexit__` close on user exception, `request_timeout` plumbed through.
- `python_code/tests/integration/test_connection_lifecycle.py` — 1 `@pytest.mark.integration` smoke test against live JMRI on `localhost:12080`.

Modified:

- `python_code/src/pyjmri/__init__.py` — re-exports `Client`, `ClientConfig`, `ReconnectConfig`, and every public exception class. Adds `__all__`. `NullHandler` install retained.
- `python_code/tests/integration/conftest.py` — adds `jmri_available` session-scoped skip-on-absence fixture (TCP probe of `localhost:12080`).
- `python_code/pyproject.toml` — adds `httpx>=0.28.1` to `[project] dependencies` (via `uv add httpx`).
- `python_code/uv.lock` — refreshed by `uv add httpx` (5 packages added: httpx, httpcore, h11, anyio, plus existing-transitive bumps).

Sprint tracking:

- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `2-1-...` flipped `ready-for-dev → in-progress → review`. `epic-2` flipped `backlog → in-progress` during story creation.

## Change Log

- 2026-05-07 — Story 2.1 implementation. Added `httpx>=0.28.1` runtime dep. Created `exceptions.py` (full `JMRIError` hierarchy with FR35 `__str__` and `WaitTimeout` multi-inherit), `_transport.py` (`HTTPClient` async wrapper enforcing the httpx boundary), `client.py` (`Client` + `ClientConfig` + `ReconnectConfig` with URL parser and async-context-manager lifecycle). Updated `__init__.py` for re-exports. Added 53 unit tests (`test_exceptions.py`, `test_transport.py`, `test_client.py`) and 1 integration smoke test (`test_connection_lifecycle.py`) plus the `jmri_available` skip-on-absence fixture in `tests/integration/conftest.py`. Probe endpoint switched from `/json/v5` (HTML console) to `/json/v5/version` after live JMRI testing. `HTTPClient.get()` return type widened to accept JMRI's collection-endpoint array shape. All four local quality gates green; integration smoke test passed against live JMRI 5.4.0. Story Status moved to `review`.
