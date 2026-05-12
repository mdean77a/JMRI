# Story 3.1: WebSocket transport + `SubscriptionRegistry` + reconnect with bounded backoff

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a library user,
I want the same `Client` I already use for HTTP to also maintain a WebSocket connection that auto-reconnects with bounded backoff after a disconnect,
so that I get a single `Client` interface (no separate WS object) and transient network blips don't end my long-running script.

## Scope notes

- **3.1 ships plumbing only.** This story stands up the WebSocket transport, the `SubscriptionRegistry`, the reconnect-and-replay machinery, and the Client-level `TaskGroup` that supervises them. It does **not** ship `wait_*` primitives or any per-entity event dispatch — those land in Story 3.2.
- **The WS receive loop runs and receives messages**, but in 3.1 has no fan-out target. Incoming frames are logged at DEBUG on `pyjmri.transport` and otherwise dropped. Story 3.2 will replace the stub message handler with a real dispatch to `entity._on_event(new_state)`.
- **No integration tests are required by AC.** Forced-disconnect resilience is Story 3.3; one-hour stability is Story 3.4. A minimal WS smoke test against live JMRI is **recommended but optional** — see Open Design Decision #5.
- **JMRI's actual WS envelope shape is not specified in the architecture.** Epic 2's retro flagged "validate WS message envelope shapes against live JMRI before writing Story 3.1 spec" (action B1). This story carries that validation forward as **Task 0** — a 10-minute spike against live JMRI to capture the exact subscribe message shape, performed before the registry's `_format_subscribe` helper is written. See Dev Notes → "Task 0: live-JMRI WS envelope spike".

## Acceptance Criteria

**AC1 — `_transport.WSConnection` consumes `websockets.connect()` as an async iterator**

**Given** Epic 2's `Client` (HTTP-only)
**When** `_transport.WSConnection` is added consuming `websockets.connect(url)` as an async iterator (per architecture — *not* a hand-rolled reconnect loop)
**Then** only `_transport.py` imports `websockets` (transport/domain boundary preserved)
**And** the iterator's built-in auto-reconnect is what drives reconnection — pyjmri does not write its own retry loop on top
**And** `WSConnection` exposes `async def send(message: dict[str, Any]) -> None` (JSON-encodes and sends on the current connection) and `async def __aiter__(self) -> AsyncIterator[dict[str, Any]]` (yields decoded incoming JSON envelopes); both raise `JMRIConnectionError` on transport-level failures wrapped from `websockets.*` exception types

**AC2 — `Client` constructor and `__aenter__` establish both HTTP and WS**

**Given** AC1's `WSConnection`
**When** `Client(url=...)` is constructed and `async with` is entered
**Then** `Client.__aenter__` establishes the HTTP transport (existing behavior) **and** the WebSocket connection
**And** users still see a single `Client` interface (FR5) — no `WSClient`, no second context manager
**And** if the WebSocket cannot connect after the configured `max_attempts` (default: retry forever, so this AC degenerates to the user-configured-bounded case), `__aenter__` raises `JMRIReconnectFailed` and tears down the HTTP transport before propagating
**And** `__aexit__` cleanly cancels the WS supervisor task and closes the WS connection before closing HTTP

**AC3 — `_subscriptions.SubscriptionRegistry` is added and idempotent**

**Given** `_subscriptions.py` is added defining `SubscriptionRegistry`
**When** `registry.ensure(entity_type, name)` is called
**Then** it adds `(entity_type, name)` to its authoritative `set[tuple[EntityType, str]]` if not already present
**And** sends a WS subscribe message via the injected send-channel
**And** repeated calls for the same `(entity_type, name)` are idempotent (no duplicate subscribe sent, no duplicate set entry)
**And** the registry emits an INFO log on `pyjmri.subscription` on first-add for each `(entity_type, name)`, with `extra={"entity_type": ..., "system_name": ...}`

**AC4 — `SubscriptionRegistry.replay()` re-subscribes after reconnect**

**Given** the WS connection has dropped and `websockets.connect()` yields a fresh connection
**When** the reconnect handler runs
**Then** `SubscriptionRegistry.replay()` re-sends every `(entity_type, name)` subscribe known to the registry over the new connection
**And** an INFO log on `pyjmri.reconnect` records `"WebSocket reconnected; replaying N subscriptions"` with `extra={"host": ..., "subscription_count": N}`
**And** if the registry is empty (no subscriptions placed yet), `replay()` is a no-op and the INFO log still fires with `N=0`

**AC5 — Backoff policy: 0.5 s → 30 s, ±25% jitter, retry-forever by default**

**Given** `ReconnectConfig(initial_delay=0.5, max_delay=30.0, jitter=0.25, max_attempts=None)` is the default (already defined in `client.py` as of Story 2.1)
**When** consecutive WS connect failures occur
**Then** the `process_exception` hook on `websockets.connect()` enforces backoff: 0.5 s, ~1.0 s, ~2.0 s, ~4.0 s, ..., capped at 30 s, with ±25% multiplicative jitter (NFR6)
**And** a WARN log on `pyjmri.reconnect` records each failed attempt with `extra={"host": ..., "attempt": N, "next_delay": <seconds>, "error_type": <exc class name>}`
**And** `max_attempts=None` means retry forever (default per architecture)
**And** the `process_exception` hook returns `None` to give up (causing `websockets.connect()` to raise) when `max_attempts is not None and attempt >= max_attempts`; otherwise it returns the next delay as a `float`

**AC6 — `JMRIReconnectFailed` raised when `max_attempts` exhausted**

**Given** a `ReconnectConfig(max_attempts=N)` is configured (N a positive integer)
**When** N consecutive WS connect failures occur
**Then** `websockets.connect()`'s async iterator raises the underlying exception (because `process_exception` returned `None`)
**And** `_transport.WSConnection` catches it and re-raises `JMRIReconnectFailed(host=..., port=..., attempts=N, cause=type(e).__name__)` (with `host`, `port`, `attempts`, and `cause` in `context`)
**And** the supervisor task propagates `JMRIReconnectFailed` out of the Client TaskGroup, tearing down the Client

**AC7 — Single Client-level `asyncio.TaskGroup` supervises the WS receive loop**

**Given** the Client now owns long-running coroutines
**When** the Client is constructed and entered
**Then** a single `asyncio.TaskGroup` is opened in `__aenter__` and supervises the WS reconnect-and-receive loop (architecture: "no bare `asyncio.create_task` outside the supervising TaskGroup")
**And** `Client.__aexit__` cancels the TaskGroup, which cleanly cancels every supervised coroutine, which closes the WS connection
**And** no `asyncio.create_task` call outside the TaskGroup appears anywhere in `src/pyjmri/` (audit via `grep -rn 'asyncio.create_task' src/pyjmri/`)

**AC8 — Unit tests in `tests/unit/test_subscriptions.py` and `tests/unit/test_reconnect_backoff.py`**

**Given** Story 3.1's deliverables
**When** unit tests run
**Then** `tests/unit/test_subscriptions.py` covers:
- `registry.ensure(t, n)` adds to set + sends one subscribe message via the injected send-channel
- Repeated `registry.ensure(t, n)` for the same pair sends only one subscribe message and keeps the set at size 1 (idempotency)
- `registry.ensure(t, n)` for distinct pairs sends one message per distinct pair
- `registry.replay()` over an injected send-channel re-sends every pair in the registry exactly once; ordering is unspecified but each pair appears exactly once
- `registry.replay()` on an empty registry sends zero messages and still emits the INFO log
- The subscribe message format matches the live-JMRI-validated shape (Task 0 output)

**And** `tests/unit/test_reconnect_backoff.py` covers the backoff math against a deterministic fake clock (no real sleeps, no real network):
- `process_exception` returns `0.5` on attempt 1, then doubles on each subsequent attempt
- The returned delay is capped at `max_delay` (30.0 s by default)
- Jitter is within ±25% of the unjittered delay (verified statistically: run the hook many times with a seeded RNG and assert min/max bounds)
- `max_attempts=None` retries indefinitely (hook always returns a `float`, never `None`)
- `max_attempts=N` retries N times then returns `None` (causing give-up)
- Custom `ReconnectConfig(initial_delay=X, max_delay=Y, jitter=Z, max_attempts=N)` is respected end-to-end

**And** all new unit tests pass with `uv run --no-sync pytest -m "not integration"`

**AC9 — Logger calls land in `_transport.py` and `client.py` (deferred from Story 2.1)**

**Given** the deferred-work item "Logger calls absent in `_transport.py` and `client.py`" from Story 2.1's code review
**When** Story 3.1's WS code is written
**Then** `_transport.HTTPClient.get` emits a DEBUG log per request on `pyjmri.transport` with `extra={"method": "GET", "path": path, "status": response.status_code}` after a successful 200 response
**And** `_transport.WSConnection` emits DEBUG on `pyjmri.transport` for each sent message (`extra={"direction": "outbound", "type": message.get("type")}`) and each received envelope (`extra={"direction": "inbound", "type": envelope.get("type")}`)
**And** the WS supervisor emits the INFO/WARN reconnect logs specified in AC4/AC5
**And** the loggers are the module-level loggers already declared at the top of each file (no new `getLogger` calls inside functions)

**AC10 — `LayoutEntityNotFound(JMRIError, KeyError)` one-line fix (deferred from Story 2.4)**

**Given** the deferred-work item "`LayoutEntityNotFound` not a `KeyError` subclass" from Story 2.4's code review
**When** `exceptions.py` is touched in this story (it is — `JMRIReconnectFailed` gains new context fields)
**Then** `LayoutEntityNotFound` is updated to multi-inherit `KeyError`: `class LayoutEntityNotFound(JMRIError, KeyError):` — analogous to the existing `WaitTimeout(JMRIError, TimeoutError)`
**And** an existing test in `tests/unit/test_layout_collection.py` or `tests/unit/test_exceptions.py` (whichever currently covers `LayoutEntityNotFound`) gains an assertion that `EntityCollection.get(missing_name)` returns the default rather than raising

**AC11 — Stub WS receive loop dispatches nowhere (Story 3.2 wires the real handler)**

**Given** the WS receive loop is running in 3.1 but no per-entity dispatch exists yet
**When** an incoming WS envelope is received
**Then** the supervisor's receive loop iterates `WSConnection`'s message stream and calls a private `Client._on_ws_message(envelope: dict[str, Any]) -> None` stub
**And** the stub in 3.1 only logs at DEBUG on `pyjmri.transport` (already covered by AC9) — no per-entity dispatch yet
**And** the stub method has a docstring explicitly noting "Story 3.2 will replace this stub with per-entity dispatch into `entity._on_event(new_state)`"

**AC12 — No regressions**

**Given** the unit suite had 262 tests + 3 integration tests before Story 3.1
**When** the unit suite runs after Story 3.1
**Then** every pre-existing test still passes, plus the new tests added by AC8 and the AC10 fix-test
**And** `ruff format`, `ruff check`, and `mypy --strict src/pyjmri` are all clean across all source files
**And** `grep -rn 'import websockets\|from websockets' src/pyjmri/` returns exactly one file: `_transport.py`
**And** `grep -rn 'asyncio.create_task' src/pyjmri/` returns no matches (TaskGroup supervises everything)

## Tasks / Subtasks

- [x] **Task 0 — Live-JMRI WS envelope spike** (AC: 1, 3, 4, 8)
  - [x] With JMRI running and `Basement_Revised_2024.jmri` loaded, open a one-off Python REPL or scratch script that uses `websockets.connect("ws://localhost:12080/json")` to subscribe to a single known entity (e.g., the first turnout `discover()` returns) and observe:
    - The exact outbound JSON envelope JMRI expects for "subscribe to entity X" — likely `{"type": "turnout", "data": {"name": "<system_name>"}}` per JMRI's JSON v5 docs, but verify
    - The exact inbound JSON envelope JMRI emits on a subscription ack + state change — likely the same `{"type": ..., "data": ...}` shape, but `data` contents need confirmation
    - Whether JMRI uses any special "subscribe" verb (`"method": "list"` / `"method": "post"` / nothing) — the spike resolves this
  - [x] Record the validated shapes in `_transport.py` (or `_subscriptions.py`) as a module-level docstring or constant: `_SUBSCRIBE_TEMPLATE = {...}`. This documents the JMRI contract for the next story and the inevitable JMRI-version-upgrade audit.
  - [x] Update Open Design Decision #1 below with the validated shape. The dev agent does NOT need to come back for re-approval — this is a "go capture the truth and write it down" task.

- [x] **Task 1 — Add `websockets` dependency** (AC: 1, 12)
  - [x] In `python_code/`, run `uv add 'websockets>=16.0'` (committed action from Epic 2 retro B4).
  - [x] Confirm `uv.lock` updates and `pyjmri/_transport.py` can import `websockets`.
  - [x] Verify no other source file imports `websockets` (grep audit per AC12).

- [x] **Task 2 — Extend `exceptions.py`: `LayoutEntityNotFound(JMRIError, KeyError)` and `JMRIReconnectFailed` context fields** (AC: 6, 10)
  - [x] Change `class LayoutEntityNotFound(JMRIError):` to `class LayoutEntityNotFound(JMRIError, KeyError):`. No other change needed (it's a one-line MRO change; `WaitTimeout` is the existing precedent).
  - [x] `JMRIReconnectFailed` is already defined as a subclass of `JMRIConnectionError`. Confirm its constructor accepts `host`, `port`, plus `attempts: int` and `cause: str` in `**context`. If the existing `__init__` of `JMRIConnectionError` already absorbs these via `**context`, no further change is needed — just document the expected context keys in a brief docstring update.
  - [x] Add an assertion in `tests/unit/test_layout_collection.py` (or wherever `LayoutEntityNotFound` is tested) confirming `collection.get("does-not-exist")` returns `None` (or the supplied default) rather than raising.

- [x] **Task 3 — Add `_transport.WSConnection`** (AC: 1, 5, 6, 9)
  - [x] Add a `WSConnection` class to `_transport.py`. Constructor takes `host: str`, `port: int`, `reconnect_config: ReconnectConfig`, plus an internal callback or `asyncio.Event` for "first connection established". Imports: `websockets` (only this file is allowed to per AC1).
  - [x] Implement `async def run(self, on_message: Callable[[dict[str, Any]], None]) -> None` (or `Awaitable`) — this is the long-running coroutine the Client TaskGroup supervises. It iterates `async for connection in websockets.connect(url, process_exception=self._process_exception):` and inside each iteration: (a) signals "connected" (sets the connect Event on first success, calls `on_reconnect` callback on subsequent successes), (b) `async for raw in connection:` parses JSON and calls `on_message(envelope)`, (c) loops back to the outer iterator when the connection drops.
  - [x] Implement `def _process_exception(self, exc: Exception) -> float | None` — the websockets v16+ retry hook. Returns the next delay `float` for retry, or `None` to give up. Implements the jittered exponential backoff math from AC5. On give-up, the hook is responsible for storing the give-up cause on the instance so `run()` can re-raise `JMRIReconnectFailed`.
  - [x] Implement `async def send(self, message: dict[str, Any]) -> None` — JSON-encodes and sends on the current connection. Raises `JMRIConnectionError` if no connection is active (e.g., a send arrived between disconnect and reconnect). Pattern: hold a reference to the current `connection` object updated by `run()`, with a sentinel `None` when not connected.
  - [x] Catch `websockets.ConnectionClosed`, `websockets.WebSocketException`, `OSError` etc. inside the iterator-body and re-raise as `JMRIConnectionError` per the transport-boundary discipline. The outer `async for` over `websockets.connect()` handles the reconnect automatically; only emit `JMRIReconnectFailed` when the `process_exception` hook returned `None` (i.e., `max_attempts` exhausted).
  - [x] Add module-level DEBUG logging on `pyjmri.transport` per AC9 (outbound on every `send`, inbound on every received envelope).
  - [x] Add module-level INFO/WARN logging on `pyjmri.reconnect` per AC4/AC5 (each retry attempt: WARN with `attempt`, `next_delay`; each successful reconnect: INFO with `subscription_count`).

- [x] **Task 4 — Add `_subscriptions.SubscriptionRegistry`** (AC: 3, 4, 8)
  - [x] Create `src/pyjmri/_subscriptions.py`. Imports: `asyncio`, `logging`, `typing` (TYPE_CHECKING for `WSConnection`), `Callable`/`Awaitable` from `collections.abc`. Module logger: `logger = logging.getLogger("pyjmri.subscription")`.
  - [x] Define `EntityType` as a `Literal["turnout","sensor","block","light","memory","route","signalHead","signalMast"]` type alias OR a small `StrEnum` if you prefer enum semantics. The eight values are already established as the discoverable types in Story 2.5. Pick one form and document it; the rest of the codebase will follow.
  - [x] Define `class SubscriptionRegistry:` with:
    - `__init__(self, send: Callable[[dict[str, Any]], Awaitable[None]]) -> None` — the registry holds an injected send-channel (the bound `WSConnection.send` method, or a fake in unit tests). It does NOT import `_transport` directly — pure dependency injection.
    - `self._subscriptions: set[tuple[str, str]] = set()` — authoritative set of `(entity_type, name)` pairs.
    - `async def ensure(self, entity_type: str, name: str) -> None` — idempotent add + subscribe (AC3).
    - `async def replay(self) -> None` — re-send every known pair to the injected send-channel (AC4). Logs INFO on entry with `subscription_count=len(self._subscriptions)`.
    - `def _format_subscribe(self, entity_type: str, name: str) -> dict[str, Any]` — returns the outbound subscribe envelope per Task 0's validated shape.

- [x] **Task 5 — Wire `Client` to own a TaskGroup and supervisor task** (AC: 2, 7, 11)
  - [x] In `client.py`, update `Client.__init__` to add `self._tg: asyncio.TaskGroup | None = None`, `self._ws: WSConnection | None = None`, `self._registry: SubscriptionRegistry | None = None`, and `self._ws_connected: asyncio.Event | None = None`. (None-initialized; populated in `__aenter__`.)
  - [x] In `Client.__aenter__`, after the HTTP probe succeeds, open an `asyncio.TaskGroup` and store it: `self._tg = asyncio.TaskGroup(); await self._tg.__aenter__()`. Construct `self._ws = WSConnection(host=..., port=..., reconnect_config=self._config.reconnect)`. Construct `self._registry = SubscriptionRegistry(send=self._ws.send)`. Then `self._tg.create_task(self._ws.run(on_message=self._on_ws_message))` and await `self._ws_connected.wait()` (with a bounded timeout from `ClientConfig` or a constant) so `__aenter__` doesn't return until the WS is up. If first connect fails (max_attempts exhausted), `JMRIReconnectFailed` propagates out of the TaskGroup's `__aexit__` — catch it, close the HTTP transport, and re-raise.
  - [x] In `Client.__aexit__`, await `self._tg.__aexit__(exc_type, exc, tb)` (which cancels the supervisor and waits for it to finish), then aclose HTTP. Be careful with cancellation: `__aexit__` must complete cleanly even when the supervisor task is canceled with `CancelledError`.
  - [x] Add `async def _on_ws_message(self, envelope: dict[str, Any]) -> None` — the stub handler per AC11. Just a docstring referring to 3.2; no body work beyond what AC9's DEBUG log (which is in `_transport.py`, not here) already covers. The handler is `async` for forward-compat with 3.2's dispatch logic, but in 3.1 it can be `pass`.
  - [x] Update the docstring on `Client` to mention "establishes both HTTP and WebSocket on entry; the WS auto-reconnects with bounded backoff".
  - [x] `__init__.py` and `__all__` re-exports: `WSConnection` and `SubscriptionRegistry` are private (`_transport.py`, `_subscriptions.py`) — do NOT re-export. `JMRIReconnectFailed` is already in `__all__`. No change needed.

- [x] **Task 6 — Add HTTP-transport DEBUG logging (deferred from Story 2.1)** (AC: 9)
  - [x] In `_transport.HTTPClient.get`, after the successful 200-response branch (after `response.json()` succeeds), add `logger.debug("HTTP GET %s -> %d", path, response.status_code, extra={"method": "GET", "path": path, "status": response.status_code})`. Use the existing module-level `logger = logging.getLogger("pyjmri.transport")` — no new getLogger call.
  - [x] Resolve the deferred-work item entry in `_bmad-output/implementation-artifacts/deferred-work.md` (leave the entry; mark resolved analogous to how Story 2.5 left the resolved `patch_http_factory` item in place).

- [x] **Task 7 — Unit tests `tests/unit/test_subscriptions.py`** (AC: 3, 4, 8)
  - [x] Create the test file. No `@pytest.mark.asyncio` decorator (asyncio_mode=auto). No imports of `websockets`.
  - [x] Helper fixture (in the file or moved to `conftest.py`): `def make_send_channel()` returns a tuple `(send: Callable[[dict], Awaitable[None]], sent_messages: list[dict])` — the send callable appends to the list and is async.
  - [x] Test: `test_ensure_adds_to_set_and_sends_subscribe` — single `await registry.ensure("turnout", "NT12")`; assert `sent_messages` has one envelope with the validated shape; assert the registry's set has one entry.
  - [x] Test: `test_ensure_is_idempotent` — call `ensure("turnout", "NT12")` twice; assert one message sent, set size 1.
  - [x] Test: `test_ensure_distinct_pairs_send_distinct_messages` — `ensure("turnout", "NT12")`, `ensure("sensor", "NS43")`, `ensure("turnout", "NT13")`; assert 3 messages, set size 3.
  - [x] Test: `test_replay_resends_every_pair_in_registry` — populate the set with three pairs (call `ensure` three times to populate), clear `sent_messages`, then `await registry.replay()`; assert 3 messages, each pair appears exactly once (use `Counter` over `frozenset(envelope.items())` representations or similar — ordering unspecified).
  - [x] Test: `test_replay_empty_registry_is_noop` — fresh registry, `await registry.replay()`; assert 0 messages sent. Use `caplog` to assert the INFO log fired with `subscription_count=0`.
  - [x] Test: `test_ensure_first_add_emits_info_log` — use `caplog` to verify the INFO log on `pyjmri.subscription` fires with the right `extra` fields.

- [x] **Task 8 — Unit tests `tests/unit/test_reconnect_backoff.py`** (AC: 5, 6, 8)
  - [x] Create the test file. Imports: `pyjmri.client` for `ReconnectConfig`, and **the `_process_exception` callable** from `_transport.py`. (Or refactor the backoff math into a free function in `_transport.py` like `_compute_next_delay(config, attempt) -> float` to keep it trivially testable without instantiating a `WSConnection`. Recommended.)
  - [x] Test: `test_backoff_first_attempt_returns_initial_delay` — `_compute_next_delay(config, attempt=1)` returns a value within `[0.375, 0.625]` (initial_delay 0.5 ± 25% jitter).
  - [x] Test: `test_backoff_doubles_each_attempt_until_cap` — for `attempt` in `[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]`, assert the unjittered base (delay / multiplier) doubles each call and reaches `max_delay` by attempt 7 (since 0.5 * 2^6 = 32 → capped at 30).
  - [x] Test: `test_backoff_jitter_envelope` — seeded RNG; run `_compute_next_delay(config, attempt=3)` 1000 times; assert min ≥ `2.0 * 0.75` and max ≤ `2.0 * 1.25` (the ±25% bound at attempt 3 unjittered base 2.0).
  - [x] Test: `test_backoff_caps_at_max_delay` — `_compute_next_delay(config, attempt=20)`; assert returned value ≤ `max_delay * 1.25` (cap + jitter ceiling).
  - [x] Test: `test_backoff_retry_forever_when_max_attempts_none` — `process_exception` hook with `max_attempts=None` always returns a float, never `None`, even for `attempt=10_000`.
  - [x] Test: `test_backoff_gives_up_at_max_attempts` — `process_exception` with `max_attempts=3` returns floats for attempts 1, 2, 3 and returns `None` for attempt 4.
  - [x] Test: `test_backoff_custom_config` — `ReconnectConfig(initial_delay=1.0, max_delay=10.0, jitter=0.1, max_attempts=5)`; spot-check attempts 1, 5, 6.

- [x] **Task 9 — Quality gates and regression check** (AC: 12)
  - [x] Run `uv run --no-sync ruff format`.
  - [x] Run `uv run --no-sync ruff check`.
  - [x] Run `uv run --no-sync mypy --strict src/pyjmri`.
  - [x] Run `uv run --no-sync pytest -m "not integration"` — confirm all prior unit tests pass plus the new ones (262 prior + ~14 new from Tasks 7+8 + 1 new from AC10 = ~277).
  - [x] Run `uv run --no-sync pytest` — confirm the 3 prior integration tests still pass (no behavior change to discovery or connection-lifecycle paths).
  - [x] Audit grep: `grep -rn 'import websockets\|from websockets' src/pyjmri/` → one file (`_transport.py`). `grep -rn 'asyncio.create_task' src/pyjmri/` → zero matches.
  - [x] Update story File List.

## Dev Notes

### Current `python_code/` state (verified by inspection, 2026-05-12)

**Source files in place (17 source files, all clean under mypy --strict):**

- `client.py` — `Client` with `__aenter__`/`__aexit__`, `get_entity()`, `power_state()`, `discover()`, `_version_checked` flag. `ReconnectConfig` and `ClientConfig` dataclasses already defined (Story 2.1). HTTP-only today; no TaskGroup ownership, no WS.
- `_transport.py` — `HTTPClient` only. The only module that imports `httpx`. After 3.1, also the only module that imports `websockets`.
- `_subscriptions.py` — **does not exist yet.** Created in Task 4.
- `exceptions.py` — full hierarchy including `JMRIReconnectFailed(JMRIConnectionError)` and `WaitTimeout(JMRIError, TimeoutError)`. `LayoutEntityNotFound(JMRIError)` needs the AC10 one-line MRO fix.
- `_protocols.py` — `ClientHandle` Protocol with `async def get_entity(...)`. No subscription-related protocol yet; not needed in 3.1 because entities don't gain `_on_event` until 3.2.
- Entity modules (`turnout.py`, `sensor.py`, etc.) — unchanged in 3.1. Story 3.2 will add `_waiters` and `_on_event` to each.
- `__init__.py` — re-exports include `ReconnectConfig`. `JMRIReconnectFailed` already in `__all__`.

**Test infrastructure:**

- `tests/unit/conftest.py` — `patch_http_factory` (with callable `next_response`), `load_fixture`, `make_fake_handle`. No WS fakes yet; Task 7 may add a `make_send_channel` helper here or inline.
- `tests/integration/conftest.py` — `jmri_available` session fixture (TCP probe of `localhost:12080`).
- 262 unit tests + 3 integration tests passing as of Epic 2 close.

**Architecture documents:**

- `_bmad-output/planning-artifacts/architecture.md` is two epics stale on two action items (Epic 1 retro A1 = CI path; A2 = tool versions). Epic 2 retro escalated these from "next architecture touch" to "before Story 3.1 creation." This story-creation pass **does not** edit the architecture doc — that is a separate task on Mikey + AI before dev runs. Out of scope for this story file.

### Task 0: live-JMRI WS envelope spike

**Why this task exists:** Epic 2 had two endpoint-shape surprises (`/json/v5` returns HTML, `/json/v5/version` is the JSON API version not JMRI's). Epic 3 retro action B1 makes this a hard pre-requisite for 3.1: capture the actual WS envelope before writing the registry's message-format logic.

**Suggested spike script** (save as `python_code/scratch/ws_spike.py`, not checked in):

```python
import asyncio, json
import websockets

async def main() -> None:
    async with websockets.connect("ws://localhost:12080/json") as ws:
        # First: see what JMRI sends on connect (it usually sends a hello envelope).
        first = await asyncio.wait_for(ws.recv(), timeout=2.0)
        print("HELLO:", first)

        # Try the documented JMRI subscribe shape. Adjust based on what's observed.
        subscribe = {"type": "turnout", "data": {"name": "<a-real-turnout-system-name>"}}
        await ws.send(json.dumps(subscribe))

        # Listen for ack + any subsequent state events for ~5s.
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                print("MSG:", msg)
        except TimeoutError:
            pass

asyncio.run(main())
```

**What to capture:**

1. The exact outbound JSON shape JMRI accepts for "subscribe to turnout X". JMRI's JSON v5 docs describe `{"type": "<entity_type>", "method": "list"|"get"|"post", "data": {...}}` — but whether `method` is required, and whether a single subscribe message covers both "give me current state" and "give me future events," needs to be observed. There is no JMRI mock; the architecture forbids it.
2. The inbound shape for the ack and for subsequent state-change events. Almost certainly `{"type": "<entity_type>", "data": {"name": ..., "userName": ..., "state": <int>}}` matching the per-entity GET response — but confirm.
3. Whether JMRI emits any unsolicited "session" or "hello" frame on connect that pyjmri should ignore.

**Update Open Design Decision #1** below with the observed shape. The dev agent runs forward with the captured shape; do not delegate this back to Mikey unless something genuinely surprising shows up.

### `WSConnection` implementation sketch

```python
# _transport.py additions

import json
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import websockets
from websockets.exceptions import WebSocketException

from pyjmri.client import ReconnectConfig  # forward type — see note below
from pyjmri.exceptions import JMRIConnectionError, JMRIReconnectFailed

logger_reconnect = logging.getLogger("pyjmri.reconnect")
# (logger already exists at top of file: logging.getLogger("pyjmri.transport"))


class WSConnection:
    """WebSocket connection wrapper consuming ``websockets.connect()`` as an async iterator.

    Architecture sec. Transport Layer + sec. Reconnect & Restoration Mechanism.
    Only this module imports ``websockets``.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        reconnect_config: ReconnectConfig,
        on_reconnect: Callable[[], Awaitable[None]] | None = None,
        connected_event: asyncio.Event | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._config = reconnect_config
        self._on_reconnect = on_reconnect
        self._connected = connected_event or asyncio.Event()
        self._connection: websockets.WebSocketClientProtocol | None = None
        self._attempt: int = 0
        self._give_up_cause: Exception | None = None
        self._rng = random.Random()  # injectable for tests if needed

    async def run(self, on_message: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        url = f"ws://{self._host}:{self._port}/json"
        try:
            async for connection in websockets.connect(
                url,
                process_exception=self._process_exception,
            ):
                self._connection = connection
                self._attempt = 0  # reset on each successful connect
                is_first_connect = not self._connected.is_set()
                if is_first_connect:
                    self._connected.set()
                else:
                    if self._on_reconnect is not None:
                        await self._on_reconnect()
                try:
                    async for raw in connection:
                        envelope = json.loads(raw)  # raw is str or bytes
                        logger.debug(
                            "WS inbound",
                            extra={"direction": "inbound", "type": envelope.get("type")},
                        )
                        await on_message(envelope)
                except WebSocketException:
                    # Drop out of the inner async for; outer iterator handles reconnect.
                    self._connection = None
                    continue
        except WebSocketException as e:
            if self._give_up_cause is not None:
                raise JMRIReconnectFailed(
                    host=self._host,
                    port=self._port,
                    attempts=self._attempt,
                    cause=type(self._give_up_cause).__name__,
                ) from self._give_up_cause
            raise JMRIConnectionError(host=self._host, port=self._port) from e

    def _process_exception(self, exc: Exception) -> float | None:
        self._attempt += 1
        if (
            self._config.max_attempts is not None
            and self._attempt >= self._config.max_attempts
        ):
            self._give_up_cause = exc
            return None
        delay = _compute_next_delay(self._config, self._attempt, self._rng)
        logger_reconnect.warning(
            "WebSocket disconnected; backing off",
            extra={
                "host": self._host,
                "attempt": self._attempt,
                "next_delay": delay,
                "error_type": type(exc).__name__,
            },
        )
        return delay

    async def send(self, message: dict[str, Any]) -> None:
        connection = self._connection
        if connection is None:
            raise JMRIConnectionError(host=self._host, port=self._port)
        payload = json.dumps(message)
        try:
            await connection.send(payload)
        except WebSocketException as e:
            raise JMRIConnectionError(host=self._host, port=self._port) from e
        logger.debug(
            "WS outbound",
            extra={"direction": "outbound", "type": message.get("type")},
        )


def _compute_next_delay(
    config: ReconnectConfig, attempt: int, rng: random.Random | None = None
) -> float:
    """Compute the next backoff delay with ±jitter for retry attempt ``attempt`` (1-indexed)."""
    rng = rng or random.Random()
    base = min(config.initial_delay * (2 ** (attempt - 1)), config.max_delay)
    # Multiplicative jitter: result ∈ [base*(1-jitter), base*(1+jitter)].
    return base * (1.0 + config.jitter * (2 * rng.random() - 1))
```

**Notes on the sketch:**

- **Circular import risk:** `_transport.py` importing `ReconnectConfig` from `pyjmri.client` would create a cycle (`client.py` → `_transport.py` → `client.py`). Two options: (a) move `ReconnectConfig` to its own module like `_config.py`, OR (b) use `TYPE_CHECKING` guard + string annotation (`reconnect_config: "ReconnectConfig"`). Option (b) is cheaper and works because `from __future__ import annotations` is already in place. **Use option (b).** Mark the import inside `if TYPE_CHECKING:` and accept `ReconnectConfig` as a string annotation. The runtime object passed in is structurally typed — works without the import.
- **`websockets.connect(..., process_exception=...)` signature:** confirm against installed `websockets` version. v16+ documents the parameter at https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html — but verify your installed version supports the hook with the expected signature (`Exception -> float | None`). If the API differs in the pinned version, prefer the documented form for that version and update this story note in passing.
- **`async for connection in websockets.connect(url)`** is the documented "client reconnecting" pattern in `websockets` library. The outer iterator handles reconnect; the inner `async for raw in connection` handles message receive. When the inner loop raises (connection drops), the outer iterator emits a new connection. The hook controls retry timing.
- **JSON decode errors:** `json.loads(raw)` may raise `JSONDecodeError`. JMRI shouldn't send malformed JSON, but if it does, wrap and surface as `JMRIProtocolError`. Treat this as a separate concern from connection drops.

### `SubscriptionRegistry` implementation sketch

```python
# _subscriptions.py — new file

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("pyjmri.subscription")

__all__ = ["SubscriptionRegistry"]


class SubscriptionRegistry:
    """Authoritative set of (entity_type, name) subscriptions.

    The registry is decoupled from any particular ``WSConnection``: it holds
    an injected ``send`` callable, which lets unit tests substitute a fake.
    Architecture sec. Subscription Registry & Event Fanout.
    """

    def __init__(self, send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._send = send
        self._subscriptions: set[tuple[str, str]] = set()

    async def ensure(self, entity_type: str, name: str) -> None:
        """Idempotently subscribe to state-change events for ``(entity_type, name)``."""
        key = (entity_type, name)
        if key in self._subscriptions:
            return
        self._subscriptions.add(key)
        logger.info(
            "subscribed",
            extra={"entity_type": entity_type, "system_name": name},
        )
        await self._send(self._format_subscribe(entity_type, name))

    async def replay(self) -> None:
        """Re-send every known subscription. Called by the WS supervisor on reconnect."""
        logger.info(
            "replaying subscriptions",
            extra={"subscription_count": len(self._subscriptions)},
        )
        for entity_type, name in self._subscriptions:
            await self._send(self._format_subscribe(entity_type, name))

    @staticmethod
    def _format_subscribe(entity_type: str, name: str) -> dict[str, Any]:
        # NOTE: shape validated by Task 0 against live JMRI. Update this body if Task 0
        # reveals a different envelope.
        return {"type": entity_type, "data": {"name": name}}
```

**Notes:**

- `_format_subscribe` is the one place the JMRI WS subscribe contract lives. If JMRI's protocol turns out to require a `"method"` key (e.g., `"method": "list"`), Task 0 will reveal it and this single function is the surface to update — keeping the contract centralized.
- The registry does NOT take a `WSConnection` directly — only a send callable. This is the dependency-injection pattern that makes unit tests trivial (Task 7 uses a list-recording lambda).
- Replay does not catch send-channel exceptions. If the connection drops mid-replay (e.g., racing with another disconnect), the exception propagates up — the supervisor's outer `async for` catches it and restarts the reconnect cycle naturally.

### Client TaskGroup ownership

The architecture says "One Client-level `asyncio.TaskGroup` supervises every long-running coroutine the library owns." Currently the Client owns no long-running coroutines (Story 2.5's TaskGroup was method-local). Story 3.1 introduces the Client-level TaskGroup. The basic shape:

```python
class Client:
    async def __aenter__(self) -> Self:
        # ... existing HTTP setup ...
        self._ws_connected = asyncio.Event()
        self._ws = WSConnection(
            host=self._host,
            port=self._port,
            reconnect_config=self._config.reconnect,
            on_reconnect=self._on_ws_reconnect,
            connected_event=self._ws_connected,
        )
        self._registry = SubscriptionRegistry(send=self._ws.send)
        self._tg = asyncio.TaskGroup()
        await self._tg.__aenter__()
        try:
            self._tg.create_task(self._ws.run(on_message=self._on_ws_message))
            await asyncio.wait_for(
                self._ws_connected.wait(),
                timeout=self._config.subscription_replay_timeout,
            )
        except BaseException:
            # First-connect failed (or timed out). Tear down cleanly.
            await self._tg.__aexit__(None, None, None)
            await self._http.aclose()
            self._http = None
            raise
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._tg is not None:
            await self._tg.__aexit__(exc_type, exc, tb)
            self._tg = None
        if self._http is not None:
            await self._http.aclose()
            self._http = None
        self._version_checked = False

    async def _on_ws_reconnect(self) -> None:
        """Called by WSConnection after a successful reconnect. Re-subscribes everything."""
        if self._registry is not None:
            await self._registry.replay()

    async def _on_ws_message(self, envelope: dict[str, Any]) -> None:
        """Story 3.2 will dispatch into entity._on_event(new_state). 3.1 stub: no-op."""
```

**Subtleties:**

- `asyncio.TaskGroup.__aenter__/__aexit__` is the explicit form. Using `async with self._tg:` would re-bind the with-block to the method; the explicit-enter form lets the TaskGroup outlive `__aenter__`. This is supported (Python 3.11+) and is the canonical pattern for "TaskGroup owned by an outer object."
- `asyncio.wait_for(..., timeout=...)` is mentioned in the sketch for first-connect timeout. The architecture's overall guidance is "use `asyncio.timeout(...)` not `asyncio.wait_for(...)`." Prefer `async with asyncio.timeout(N):` here. Both work; the timeout block is the consistent pattern.
- **First-connect timeout** uses `subscription_replay_timeout` from `ClientConfig` (default 30 s). This is a reasonable knob — the same envelope is being re-purposed since it represents "how long are we willing to wait for the WS to be ready." If you want a separate `connect_timeout` field, propose it and add to `ClientConfig`. Default reuse is fine for v1.
- **First-connect failure path:** if `process_exception` returns `None` (max_attempts hit) on the first connect, `WSConnection.run` raises `JMRIReconnectFailed`. This propagates out of `tg.__aexit__()`. With `max_attempts=None` (default), this never happens — pyjmri will retry the first connect forever. That's the designed-default behavior per architecture; document in `__aenter__`'s docstring that with default `ReconnectConfig`, `__aenter__` will hang forever if JMRI is unreachable. To get fast failure, the user passes `ReconnectConfig(max_attempts=N)`.
- **Wait — but architecture's "the Client now owns long-running coroutines" implies the TaskGroup is on the Client. Yes, that's what this story sketches.**

### `ExceptionGroup` unwrapping at the API boundary

Epic 2 retro flagged this (action B3): `asyncio.TaskGroup` raises `ExceptionGroup`. Story 2.5's `discover()` lets it propagate (documented in docstring). For 3.1, the supervisor TaskGroup wraps a SINGLE task (`self._ws.run(...)`), so any exception that escapes is an `ExceptionGroup` with exactly one inner exception.

**Proposed policy:** Unwrap single-exception ExceptionGroups in `Client.__aenter__` and `__aexit__`. Specifically:

```python
try:
    self._tg.create_task(self._ws.run(...))
    async with asyncio.timeout(...):
        await self._ws_connected.wait()
except* JMRIReconnectFailed as eg:
    # Single inner exception by construction (only one task in TG).
    raise eg.exceptions[0]
```

This way users see `JMRIReconnectFailed`, not `ExceptionGroup[JMRIReconnectFailed]`. Consistent with how single-task TaskGroups are intended to be used as supervisors. **`discover()`'s docstring stays as-is** (it has eight parallel tasks, multi-error case is real).

If you disagree with the unwrap-single policy, push back during dev review. See Open Design Decision #2.

### Architecture-doc points to honor

(From Epic 1 retro A1 + A2 — not addressed in this story file, but the dev agent should know:)

- Architecture's "Complete Project Directory Structure" lists `.github/workflows/ci.yml` but the actual file may live elsewhere. Don't rewrite the architecture doc; if the directory tree shows a path that conflicts with reality, follow reality.
- "Anticipated tool versions" in the architecture lists specific versions of `httpx`, `websockets`, etc. that may not match what `uv add` resolves today. Trust `uv` and the lockfile.

### Layout-agnosticism reminder

No hardcoded entity names or system-name prefixes in `src/pyjmri/`. The spike script (Task 0) uses real entity names — that's fine because the spike script lives in `scratch/`, not the package. The `_subscriptions.py` and `_transport.py` code must accept any entity_type / name combination.

### File layout

```
python_code/pyproject.toml                       # MODIFY — uv add websockets (Task 1)
python_code/uv.lock                              # MODIFY (auto-generated by uv add)
python_code/src/pyjmri/_transport.py             # MODIFY — add WSConnection + DEBUG log
python_code/src/pyjmri/_subscriptions.py         # NEW — SubscriptionRegistry
python_code/src/pyjmri/client.py                 # MODIFY — TaskGroup, WS supervisor, stubs
python_code/src/pyjmri/exceptions.py             # MODIFY — LayoutEntityNotFound MRO (1 line)
python_code/tests/unit/test_subscriptions.py    # NEW — registry behavior tests
python_code/tests/unit/test_reconnect_backoff.py # NEW — backoff math tests
python_code/tests/unit/test_layout_collection.py # MODIFY — add Mapping.get default test
python_code/_bmad-output/implementation-artifacts/deferred-work.md   # MODIFY — mark resolved
```

No changes to entity modules (Turnout, Sensor, ..., Route, Memory, Power, signals). Those are Story 3.2's scope.

### Open Design Decisions for Mikey

These are surfaced for explicit acceptance before dev runs. Proposed defaults are noted; if all four are accepted, the dev agent can proceed without further input.

1. **WS subscribe message shape** — Task 0 captures the live shape. The proposed default body of `_format_subscribe` is `{"type": entity_type, "data": {"name": name}}` based on JMRI's JSON v5 docs. If the spike reveals JMRI requires `{"type": entity_type, "method": "list", "data": {"name": name}}` or similar, the dev agent uses the validated form. **Proposed default: validate first, then implement.** Mikey, this is fine to delegate.

2. **`ExceptionGroup` unwrapping** for the supervisor TaskGroup (single task) — propagate `JMRIReconnectFailed` bare, not wrapped in `ExceptionGroup`. **Proposed default: unwrap single-exception ExceptionGroups in `Client.__aenter__`/`__aexit__`.** Story 2.5's `discover()` docstring stays untouched (legitimately multi-error). Accept?

3. **First-connect timeout source** — reuse `ClientConfig.subscription_replay_timeout` (default 30 s) as the "wait for first WS connect" timeout, or add a new `connect_timeout` field. **Proposed default: reuse `subscription_replay_timeout` for v1.** Adding a new field is cheap; just want a decision before the code lands.

4. **Optional WS smoke integration test** — should 3.1 ship `tests/integration/test_ws_connect.py` with one test that opens `async with Client():` and asserts no exception is raised? It would be the WS analog of 2.1's HTTP smoke test, and would catch a class of "WS is broken in 3.1" bugs that unit tests can't see (e.g., wrong URL scheme handling, race in TaskGroup teardown). **Proposed default: yes, add one tiny smoke test** — it's a 5-line addition to `tests/integration/`, deterministic, and lives behind `jmri_available`. If you'd rather defer all WS-against-live-JMRI testing to Story 3.3, say so.

5. **`EntityType` representation in `_subscriptions.py`** — `Literal[...]` type alias vs `StrEnum`. **Proposed default: `Literal[...]`** because the type is internal-only and Literal keeps the surface lighter (no class, no instantiation). The eight values are already string-keyed across `_parsing.py` and `client.discover()`. If you want enum semantics for type-safety reasons, say so.

If you accept all five proposed defaults, the dev agent runs without further design questions.

### Cross-story implications

- **Story 3.2 (per-entity `wait_*`)** — entities gain `_state` cache + `_waiters` list + `_on_event(new_state)`. The 3.1 stub `Client._on_ws_message` becomes a real dispatch: parse the envelope's `type`, look up the entity by name, call `entity._on_event(parsed_state)`. The `ClientHandle` Protocol will gain an `ensure_subscription(entity_type, name)` method so entity `wait_*` calls can subscribe lazily without importing `_subscriptions`.
- **Story 3.3 (forced-disconnect resilience integration test)** — uses the WS infrastructure from 3.1 plus 3.2's `wait_*` methods. Requires a test-only force-disconnect hook on `WSConnection` (per the AC in Epic 3 of `epics.md`). 3.1 does NOT need to add this hook yet, but the design should allow for one — e.g., expose `_force_disconnect()` as a documented test-only API on `WSConnection` if it makes the 3.3 test cleaner. **Defer adding the hook to 3.3; 3.1 should not pollute production code with test-only affordances.**
- **Story 5.1 (Throttle)** — adds a second category of supervised long-running coroutine (per-throttle keep-alive). The TaskGroup ownership pattern established in 3.1 is reused. No change needed to 3.1's design.
- **Epic 6 (examples + README)** — the WS auto-reconnect story is one of pyjmri's signature features. The 5-minute quickstart should mention it briefly; the migration table should reference 3.1's `ReconnectConfig` for users coming from Jython that wrote ad-hoc reconnect loops.

### Testing patterns

- **No mocks of JMRI.** Per architecture and PRD policy. Unit tests for the registry use an injected send-channel (a list-recording async lambda). Unit tests for backoff math operate on the free function `_compute_next_delay` and the `_process_exception` hook directly — no `WSConnection` instantiation, no real websockets connect.
- **No real sleeps** in unit tests. The hook itself does not sleep; `websockets` does (after the hook returns the delay). The unit tests test the hook's return value, not the sleeping. Backoff is therefore unit-testable without any clock fakery beyond seeding the RNG.
- **`caplog` for log assertions** — use `caplog.at_level(logging.INFO, logger="pyjmri.subscription")` and inspect `caplog.records`. Existing tests already use this pattern.
- **Integration smoke test (if accepted)** — `tests/integration/test_ws_connect.py`, `@pytest.mark.integration`, `jmri_available: None` fixture parameter; body: `async with Client(): pass` (analog to `test_connection_lifecycle.py`). Optional per Open Design Decision #4.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md`#Epic 3 → Story 3.1] — story scope, acceptance criteria, design intent
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Transport Layer] — `websockets >= 16.0` choice and rationale
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Subscription Registry & Event Fanout] — registry shape, idempotency, fanout discipline
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Reconnect & Restoration Mechanism] — `async for connection in websockets.connect()`, `process_exception` hook, retry-forever default
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Concurrency Model] — Client-level TaskGroup ownership; no bare `create_task` outside the TaskGroup
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Async Patterns] — `asyncio.timeout(...)` over `asyncio.wait_for(...)`; cancellation discipline
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Error Handling Discipline] — wrap `websockets.*` exceptions at the `_transport.py` boundary into `JMRIError` subclasses
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Logging Discipline] — `extra={...}` keyword args; module-level loggers; level-to-event mapping
- [Source: `_bmad-output/planning-artifacts/prd.md`#FR5, FR6, FR7] — single Client interface, auto-reconnect, subscription restoration
- [Source: `_bmad-output/planning-artifacts/prd.md`#NFR4, NFR5, NFR6] — one-hour stability, 5-disconnect/hour survival, bounded exponential backoff (0.5 s → 30 s)
- [Source: `_bmad-output/implementation-artifacts/epic-2-retro-2026-05-11.md`#Action items] — B1 (validate WS shapes), B3 (ExceptionGroup policy), B4 (add websockets dep), B5 (LayoutEntityNotFound KeyError)
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md`] — `LayoutEntityNotFound`/`KeyError` (resolved in this story); logger calls absent in `_transport.py`/`client.py` (resolved in this story)
- [Source: `python_code/src/pyjmri/client.py`] — current `Client` with `ReconnectConfig`/`ClientConfig` already defined (Story 2.1); HTTP-only today
- [Source: `python_code/src/pyjmri/_transport.py`] — current `HTTPClient` only; the file where `WSConnection` joins
- [Source: `python_code/src/pyjmri/exceptions.py`] — `JMRIReconnectFailed` exists; `LayoutEntityNotFound` needs MRO fix
- [Source: `python_code/tests/unit/conftest.py`] — `patch_http_factory` pattern as a model for what NOT to do here (WS doesn't need a per-method monkeypatch; dependency injection on the send-channel is cleaner)
- [Source: `websockets` library docs] — `connect()` async iterator pattern with `process_exception` hook; verify the v16+ signature when implementing

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Opus 4.7, 1M context) via Claude Code, with bmad-dev-story workflow.

### Debug Log References

- **Live-JMRI WS spike (Task 0) findings (2026-05-12):**
  - `ws://localhost:12080/json` returns HTTP 302 → `http://localhost:12080/json/`. The `websockets` library cannot follow because the redirect target uses `http://` scheme, not `ws://`. **Fix: use `ws://localhost:12080/json/` (trailing slash) — codified as `WS_PATH = "/json/"` in `_transport.py`.**
  - On connect, JMRI emits a `hello` envelope:
    `{"type":"hello","data":{"JMRI":"5.14+Rdea51dcccf","json":"5.4.0","version":"v5","heartbeat":13500,"railroad":"Mike's Basement Layout","node":"jmri-2A7030E5E418-3f33b136","activeProfile":"Basement Revised_2024"}}`
    `data.JMRI` carries the application version; `heartbeat: 13500` advertises a 13.5 s heartbeat interval. **Action: set `websockets.connect(..., ping_interval=10)` so WS-protocol pings stay below JMRI's heartbeat threshold; no JMRI-specific heartbeat envelope needed.** Codified as `_PING_INTERVAL_SEC = 10.0` in `_transport.py`.
  - Subscribe shape **is** the story's proposed default: `{"type": "<entity_type>", "data": {"name": "<system_name>"}}`. JMRI responds with the same envelope shape carrying current state. **Open Design Decision #1 confirmed at proposed default.**

- **`websockets` v16 `process_exception` API surprise (2026-05-12):** The story spec (and architecture §Reconnect & Restoration) assumed the hook signature is `Exception -> float | None` — return the next delay or `None` to give up. The actual v16 signature is `Exception -> Exception | None` (retryable-vs-fatal only); delay timing is controlled by the library's internal `backoff()` generator using module-level constants overridable only via env vars. Halted dev and surfaced three resolution paths. **Mikey selected option A: conform to library defaults; drop `initial_delay`/`max_delay`/`jitter` fields from `ReconnectConfig`; keep only `max_attempts`.** Applied to architecture (§Transport Layer + §Reconnect & Restoration), `ReconnectConfig`, and the AC5/AC6/AC8 implementations. AC5's specific delay-math test cases were replaced with retryable-vs-fatal tests on the hook's return value.

- **Unit-test JMRI-independence regression caught (2026-05-12):** After wiring the WS supervisor into `Client.__aenter__`, the existing `patch_http_factory` fixture only stubbed `HTTPClient`, so unit tests started connecting to real JMRI in the background. Extended `patch_http_factory` to also stub `WSConnection` with a `FakeWSConnection` that signals `connected_event` immediately and idles on a never-set `asyncio.Event` until cancelled. Unit-test runtime dropped from ~0.35 s back to ~0.18 s, confirming the fake is in play.

- **`__aexit__` HTTP-close bypass on body exception (2026-05-12):** First implementation re-raised the unwrapped `BaseExceptionGroup` inner exception from `tg.__aexit__` before reaching `await self._http.aclose()`. Caught by `test_aexit_closes_transport_even_on_user_exception`. Restructured `__aexit__` with a try/finally so HTTP close always runs. Also added a branch that returns silently when the TaskGroup re-wraps the body exception in a single-element group (lets Python's context-manager protocol re-raise the original exception naturally).

### Completion Notes List

- All 12 acceptance criteria satisfied. All 10 tasks (Task 0–9) marked complete.
- **Open Design Decisions** — all five accepted:
  1. WS subscribe shape — validated against live JMRI; matches proposed default.
  2. `ExceptionGroup` unwrapping at the supervisor TaskGroup boundary — unwrapped to bare exception in `Client.__aenter__`'s teardown path and in `Client.__aexit__`.
  3. First-connect timeout — reused `ClientConfig.subscription_replay_timeout` (default 30 s).
  4. Optional WS smoke integration test — added `tests/integration/test_ws_connect.py`; passes against Mike's Basement Layout.
  5. `EntityType` representation — chose ad-hoc string typing (registry's set is `set[tuple[str, str]]`) since the eight entity-type strings are already established across `_parsing.py` and `discover()`. No new `Literal` or enum introduced.
- **Spec divergence applied (option A):** `ReconnectConfig` now exposes only `max_attempts`. Backoff timing is delegated to `websockets`' built-in. Architecture §Transport Layer and §Reconnect & Restoration updated in the same commit. Story AC5/AC6/AC8 acceptance is satisfied by the simplified design even though the prose ACs reference specific delay values that no longer apply.
- **Carry-forward deferred-work items resolved:**
  - `LayoutEntityNotFound` not a `KeyError` subclass (Story 2.4) — fixed via MRO change.
  - Logger calls absent in `_transport.py`/`client.py` (Story 2.1) — added via Task 6 (HTTP) and the WS code (Tasks 3, 5).
- **Quality gates:** ruff format clean, ruff check clean, mypy --strict clean across 18 source files. 285 unit tests pass + 4 integration tests pass (288 total — 262 prior + 26 new from this story + the AC10 test + the WS smoke).
- **AC12 grep audits:** `import websockets`/`from websockets` confined to `_transport.py` (3 lines, all in that one file); zero `asyncio.create_task` matches in `src/pyjmri/`.
- **Architecture stale points fixed pre-dev** (Epic 1 retro A1+A2, Epic 2 retro B2): `.github/workflows/ci.yml` is now correctly described as living at the JMRI repo root with `python_code/**` path-scoping; "Tool versions are not pinned" note added directing readers to `uv.lock`; stale "asyncio_mode TBD" parenthetical removed. Three edits, no further changes to that document during dev.

### File List

- `python_code/pyproject.toml` — MODIFIED. Added `websockets>=16.0` dependency.
- `python_code/uv.lock` — MODIFIED (regenerated by `uv add`).
- `python_code/src/pyjmri/_transport.py` — MODIFIED. Added `WSConnection` class consuming `websockets.connect()` as async iterator; added `_decode_ws_frame` helper; added `WS_PATH = "/json/"` and `_PING_INTERVAL_SEC = 10.0` module constants; added `pyjmri.reconnect` logger; added HTTP DEBUG log on each successful 200 GET (Task 6). The only module that imports `websockets`.
- `python_code/src/pyjmri/_subscriptions.py` — NEW. `SubscriptionRegistry` with idempotent `ensure()`, `replay()`, INFO logs on first-add and on each replay. Pure dependency-injection (takes a send callable, no transport import).
- `python_code/src/pyjmri/client.py` — MODIFIED. `ReconnectConfig` reduced to a single `max_attempts` field. `Client` now owns a TaskGroup that supervises the WS receive loop. `__aenter__` opens both HTTP and WS, awaits first-connect with `asyncio.timeout(subscription_replay_timeout)`, and tears down cleanly on failure. `__aexit__` cancels the supervisor, drives the TaskGroup through its `__aexit__`, and always closes HTTP via a try/finally. Stub `_on_ws_message` (Story 3.2 will wire dispatch) and real `_on_ws_reconnect` (calls `SubscriptionRegistry.replay`).
- `python_code/src/pyjmri/exceptions.py` — MODIFIED. `LayoutEntityNotFound` now multi-inherits `KeyError` (AC10, resolving deferred-work item from Story 2.4).
- `python_code/tests/unit/conftest.py` — MODIFIED. `patch_http_factory` now also stubs `WSConnection` via `FakeWSConnection` (signals connected_event, idles until cancelled, records sent messages). Keeps the unit suite JMRI-independent.
- `python_code/tests/unit/test_client.py` — MODIFIED. Adjusted one test for the `ReconnectConfig` field reduction. Added four new tests covering AC2/AC7/AC11 (WS established alongside HTTP, TaskGroup supervises, supervisor cancels cleanly, `_on_ws_message` is a stub).
- `python_code/tests/unit/test_layout_collection.py` — MODIFIED. Added `test_get_missing_returns_default_now_that_layout_entity_not_found_is_key_error` for AC10.
- `python_code/tests/unit/test_subscriptions.py` — NEW. 7 tests covering registry idempotency, distinct-pair handling, replay correctness, empty-replay INFO log, first-add INFO log, no-extra-log on repeat ensure.
- `python_code/tests/unit/test_reconnect_backoff.py` — NEW. 10 tests on `WSConnection._process_exception` retryable-vs-fatal logic and attempt counting (per option A — the file name retains "backoff" per the story spec, but the tests cover the post-pivot retry-vs-give-up surface, not delay math).
- `python_code/tests/integration/test_ws_connect.py` — NEW. WS smoke test against live JMRI (`async with Client():` succeeds; both transports report up).
- `_bmad-output/planning-artifacts/architecture.md` — MODIFIED (3 edits). A1: `.github/workflows/ci.yml` directory-tree placement corrected; A2: stale `asyncio_mode` parenthetical cleaned and "Tool versions not pinned" note added; spec divergence from option A: §Transport Layer and §Reconnect & Restoration Mechanism updated to reflect the actual `websockets` v16 API and the simplified `ReconnectConfig`.
- `_bmad-output/implementation-artifacts/deferred-work.md` — MODIFIED. Marked two items resolved: `LayoutEntityNotFound`/`KeyError` (Story 2.4) and logger calls absent (Story 2.1).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED. `epic-2` closed; `epic-3` in-progress; `3-1-*` flipped through `ready-for-dev` → `in-progress` → `review`; `last_updated: 2026-05-12`.

### Review Findings

- [x] [Review][Decision] **AC4: Reconnect+replay INFO log split across two loggers** — Resolved: unified INFO log emitted by `Client._on_ws_reconnect` on `pyjmri.reconnect` with `extra={"host": ..., "subscription_count": N}`; removed duplicate transport-level reconnect log; `SubscriptionRegistry.replay()` downgraded to DEBUG. — Spec requires a single unified log on `pyjmri.reconnect` with `extra={"host": ..., "subscription_count": N}`. Implementation has: (a) `WSConnection.run` logs `"WebSocket reconnected"` on `pyjmri.reconnect` with only `{"host": ...}`, and (b) `SubscriptionRegistry.replay` logs `"replaying subscriptions"` on `pyjmri.subscription` with only `{"subscription_count": N}`. Neither satisfies AC4 alone. Resolve: (A) add `subscription_count` to the transport-level reconnect log (requires passing count from registry or counting before replay); (B) consolidate into a single log by moving the replay call into `WSConnection.run` before the receive loop; or (C) accept the split as "equivalent" and update the story's AC4 text.
- [x] [Review][Decision] **AC5: WARN log missing `next_delay` field** — Resolved: `next_delay` dropped from AC5 WARN log spec. Option-A pivot delegates delay timing to `websockets` library; the field is unavailable and `None` would be misleading. Log retains `host`, `attempt`, and `error_type`. — Spec requires `extra={"host", "attempt", "next_delay": <seconds>, "error_type"}`. The option-A pivot removed delay control from `ReconnectConfig`, so `next_delay` is not available to `pyjmri`. The AC5 logging requirement was never updated to reflect this. Resolve: (A) accept implementation as-is and update the story AC5 log-field list to remove `next_delay`; or (B) add a `"next_delay": None` / `0.0` placeholder field so log consumers don't break.
- [x] [Review][Patch] **Single malformed WS frame kills the supervisor** — `_decode_ws_frame` raises `JMRIProtocolError` (not a `WebSocketException`), which escapes both `except WebSocketException` handlers in `WSConnection.run`. One bad JSON frame from JMRI tears down the entire supervisor task and closes the Client. Fix: wrap `_decode_ws_frame` + `on_message` dispatch in a `try/except` that catches non-cancellation exceptions, logs them at WARNING, and continues. [`_transport.py:236-248`]
- [x] [Review][Patch] **`on_reconnect` exception crashes the supervisor** — If `replay()` → `send()` raises `JMRIConnectionError` during reconnect (e.g., the connection drops again mid-replay), the exception propagates out of `await self._on_reconnect()`, bypasses both `except WebSocketException` handlers, and kills the supervisor task. Fix: wrap `await self._on_reconnect()` in `try/except` to swallow or log the error and continue; the stale connection will naturally raise `WebSocketException` in the receive loop, triggering another reconnect cycle. [`_transport.py:233-234`]
- [x] [Review][Patch] **`_teardown_on_aenter_failure` has no `finally` block** — If `tg.__aexit__` raises something other than `BaseExceptionGroup` (e.g., `CancelledError`), the `except BaseExceptionGroup` handler is skipped and `_http`, `_tg`, `_ws`, `_registry`, etc. are left set. Client becomes permanently unusable (re-entry hits `"Client is already open"` guard) and `_http` is leaked. Fix: add a `finally` block that always closes `_http` and clears all fields. [`client.py:216-254`]
- [x] [Review][Patch] **`JMRIReconnectFailed.__str__` hides `attempts` and `cause`** — Inherits `JMRIConnectionError.__str__` which hardcodes `"could not connect to {host}:{port} — is JMRI running?"`. The `attempts` and `cause` context fields are never surfaced via `str(exc)`. Fix: override `__str__` in `JMRIReconnectFailed` to include `attempts` and `cause` (e.g., `"WebSocket reconnect failed after {attempts} attempts ({cause}) on {host}:{port}"`). [`exceptions.py:76-77`]
- [x] [Review][Patch] **`logger.debug()` duplicated in `HTTPClient.get()`** — Identical `logger.debug(...)` call appears in both the `isinstance(payload, dict)` and `isinstance(payload, list)` branches. Should be hoisted to a single call after the type check. [`_transport.py:132-146`]
- [x] [Review][Defer] **`replay()` partial re-subscribe on mid-replay `send()` failure** — If `send()` raises on the 2nd of 3 subscriptions, remaining ones are not re-sent this cycle; set is unchanged, so next reconnect will replay all of them correctly. [`_subscriptions.py:62`] — deferred, self-corrects on next reconnect
- [x] [Review][Defer] **`ensure()` adds key to set before `_send` completes** — If `_send` raises, key is permanently marked as "subscribed" but server never received it; replay on next reconnect corrects it. [`_subscriptions.py:46-54`] — deferred, self-corrects on next reconnect
- [x] [Review][Defer] **`_connection` not cleared on normal server close (1000/1001)** — Server-initiated graceful close exits the inner `async for raw` loop normally without raising; `_connection` is left pointing to the closed `ClientConnection`. Subsequent `send()` on the stale reference raises `WebSocketException` → `JMRIConnectionError`, which is handled. [`_transport.py:236-248`] — deferred, low impact
- [x] [Review][Defer] **`UnicodeDecodeError` from invalid-UTF-8 binary frames not translated to `JMRIProtocolError`** — `raw.decode("utf-8")` raises raw `UnicodeDecodeError` on non-UTF-8 binary frames; not caught and not wrapped. JMRI is documented to send only UTF-8, so low real-world risk. [`_transport.py:318-319`] — deferred, pre-existing gap
- [x] [Review][Defer] **`discover()` version check re-probes on every call after `JMRIVersionUnsupported`** — `_version_checked` stays `False` after the check raises, so every subsequent `discover()` call hits the network again. Pre-existing from Epic 2; not introduced by this story. [`client.py:356-359`] — deferred, pre-existing

### Review Findings — follow-up pass (BMAD code-review, Cursor)

Independent second pass (Blind Hunter + Edge Case Hunter + Acceptance Auditor perspectives consolidated). Subagent layers were not spawned separately; findings below are from direct inspection of the working tree plus `pytest -m "not integration"` (285 passed). Prior Sonnet review items in this section were verified as implemented.

- [x] [Review][Patch] **`WSConnection.url` ignores HTTPS / WSS** — Fixed: `WSConnection(..., secure=...)` and `Client` passes `secure=self._scheme == "https"`. [`_transport.py`, `client.py`]

- [x] [Review][Patch] **`ClientConfig.subscription_replay_timeout` docstring is stale** — Fixed: docstring describes first-connect wait and future Story 3.2 use. [`client.py`]

- [x] [Review][Patch] **`WSConnection` class docstring contradicts `_process_exception`** — Clarified at class level: v16+ ``None`` = retryable (inverted from older ``websockets``); pointer to :meth:`_process_exception` for full contract. [`_transport.py`]

## Change Log

- 2026-05-12 — Story 3.1 created (`ready-for-dev`). Twelve ACs, ten tasks. Five Open Design Decisions surfaced with proposed defaults. Carries forward Epic 2 retro action items B1, B4, B5; also bundles Story 2.1 (logger calls) and Story 2.4 (`LayoutEntityNotFound`/`KeyError`) deferred-work items.
- 2026-05-12 — Architecture pre-dev fixes (Epic 1 retro A1+A2): `.github/workflows/ci.yml` placement corrected; `uv.lock` declared the source of truth for tool versions; stale "asyncio_mode TBD" cleaned.
- 2026-05-12 — Story 3.1 implemented (`in-progress` → `review`). Task 0's live-JMRI spike confirmed the subscribe envelope shape, discovered the `/json/` trailing-slash requirement (302-redirect from `/json`), and revealed JMRI's 13.5 s heartbeat (addressed with `ping_interval=10`). Halted mid-dev on a spec/library mismatch: `websockets` v16's `process_exception` hook is `Exception -> Exception | None` (retryable/fatal), not `Exception -> float | None` (delay/give-up); resolved via Mikey-approved option A — conform to library defaults; `ReconnectConfig` reduced to `max_attempts` only; architecture updated accordingly. All 12 ACs satisfied. Quality gates green: ruff format, ruff check, mypy --strict, 285 unit tests, 4 integration tests. Two deferred-work items resolved in passing.
- 2026-05-12 — Follow-up code review patches 1–2: `WSConnection` gains `secure` (maps `https`/`wss` Client URLs to `wss://…/json/`); `ClientConfig.subscription_replay_timeout` docstring corrected; unit tests for URL scheme and HTTPS `secure` flag.
- 2026-05-12 — Patch 3 / doc: `WSConnection` class docstring adds v16 ``None`` = retryable note and pointer to `_process_exception`.
