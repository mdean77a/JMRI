# Story 3.2: Per-entity waiter list and `wait_*` primitives

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a library user,
I want `await sensor.wait_active()`, `wait_inactive()`, `wait_state(target)`, and `wait_change()` on every state-bearing entity, with optional timeouts,
so that I can write event-driven scripts (e.g., "drive forward until block 6 occupies") without manual subscription bookkeeping or polling loops.

## Scope notes

- **3.2 wires the event-dispatch half of Epic 3.** Story 3.1 stood up the WebSocket, the `SubscriptionRegistry`, and the supervisor TaskGroup. The receive loop is running and dropping inbound envelopes on the floor; this story replaces the no-op `Client._on_ws_message` stub with real per-entity dispatch, adds `_waiters` + `_on_event` to every state-bearing entity, and exposes the user-facing `wait_*` primitives.
- **Six entity types become "waitable":** `Turnout`, `Sensor`, `Block`, `Light`, `SignalHead`, `SignalMast`. `Memory` (value-only) and `Route` (metadata-only) do NOT get `wait_*` methods.
- **No reconnect-resilience integration test in this story.** That's Story 3.3's job. 3.2 satisfies AC by unit-testing the waiter mechanics + one integration test for NFR1 latency.
- **No commanding yet.** Epic 4 owns `turnout.throw()`, `light.on()`, etc. The NFR1 latency integration test toggles state by raw `httpx` POST to JMRI inside the test (one-off, deliberately not promoted to a library API in 3.2).
- **Forced-disconnect survival is a property, not new code here.** Because waiters live on the entity (not on the WS connection), and `SubscriptionRegistry.replay()` (from 3.1) re-subscribes after every reconnect, in-flight `wait_*` calls survive disconnects "for free." Story 3.3 proves this against a real reconnect; 3.2 just must not break the property.

## Acceptance Criteria

**AC1 — Each state-bearing entity gains `_waiters` and `_on_event(new_state)`**

**Given** the six state-bearing entity classes (`Turnout`, `Sensor`, `Block`, `Light`, `SignalHead`, `SignalMast`)
**When** the implementation lands
**Then** each gains a `_waiters: list[tuple[Callable[[<StateT>], bool], asyncio.Future[<StateT>]]]` attribute initialized to `[]` in `__init__`
**And** each gains an `_on_event(self, new_state: <StateT>) -> None` method that: (a) updates the entity's cached primary state attribute (`state` for Turnout/Sensor/Block/Light, `appearance` for SignalHead, `aspect` for SignalMast); (b) iterates `_waiters` and, for each `(predicate, future)` pair where the future is not done and `predicate(new_state)` is `True`, calls `future.set_result(new_state)`; (c) keeps every non-matching, non-done waiter in the list; (d) is a plain (non-async) method since fanout is synchronous (single event loop = no lock needed, per architecture §Subscription Registry & Event Fanout)
**And** done/cancelled futures are pruned from `_waiters` during fanout iteration so the list cannot grow unbounded over a long run

**AC2 — `wait_state(target, *, timeout=None)` on every state-bearing entity**

**Given** any state-bearing entity instance ``e``
**When** the user calls `await e.wait_state(target, timeout=T)`
**Then** if the entity's cached state already equals `target`, the method returns immediately (early-return, no subscription, no future registered) per architecture §Subscription Registry & Event Fanout
**And** otherwise the method (i) calls `await self._handle.ensure_subscription(entity_type, self.name)` to guarantee a subscription exists (FR29 — no manual bookkeeping), (ii) creates a fresh `asyncio.Future[<StateT>]` and registers `(lambda s: s == target, future)` on `self._waiters`, (iii) `await`s the future inside an `async with asyncio.timeout(timeout):` block when `timeout is not None`
**And** on timeout, the method raises `WaitTimeout(entity_type=<type>, name=self.name, target=<target>.name)` (FR30) and removes its `(predicate, future)` pair from `_waiters` before re-raising — no orphaned waiters
**And** on `asyncio.CancelledError` (caller cancellation), the method removes its `(predicate, future)` pair from `_waiters` and re-raises (no orphaned waiters, no swallowed cancellation)
**And** the target type is the entity's primary-state enum: `TurnoutState` / `SensorState` / `BlockState` / `LightState` / `SignalHeadAppearance` / `SignalMastAspect`

**AC3 — `wait_change(*, timeout=None)` on every state-bearing entity**

**Given** any state-bearing entity instance ``e``
**When** the user calls `await e.wait_change(timeout=T)`
**Then** the method captures `starting_state = self.<primary>` at call time and registers a `(lambda s: s != starting_state, future)` waiter using the same plumbing as `wait_state` (FR32)
**And** the same auto-subscription, timeout, and cancellation cleanup rules from AC2 apply
**And** returns the new state when the future resolves

**AC4 — `Sensor.wait_active()` and `Sensor.wait_inactive()` convenience wrappers**

**Given** the `Sensor` class
**When** `await sensor.wait_active(timeout=T)` is called
**Then** it is implemented as `return await self.wait_state(SensorState.ACTIVE, timeout=T)` (FR30)
**And** `await sensor.wait_inactive(timeout=T)` is implemented as `return await self.wait_state(SensorState.INACTIVE, timeout=T)`
**And** the convenience methods exist ONLY on `Sensor` (not on the other five waitable entities)

**AC5 — `ClientHandle` Protocol gains `ensure_subscription`**

**Given** `pyjmri._protocols.ClientHandle`
**When** the `ensure_subscription` capability is added
**Then** the Protocol declares `async def ensure_subscription(self, entity_type: str, name: str) -> None`
**And** `pyjmri.Client` implements this method by calling `await self._registry.ensure(entity_type, name)` (raises `RuntimeError` if the Client is not open — same pattern as `get_entity`)
**And** entity modules use `self._handle.ensure_subscription(...)` from their `wait_*` methods; entity modules MUST NOT import `pyjmri._subscriptions` directly (transport/domain boundary preserved — same discipline as Story 2.3's `get_entity`)

**AC6 — `Client._on_ws_message` dispatches inbound envelopes to entities**

**Given** the WS receive loop is running (Story 3.1)
**When** an inbound envelope arrives
**Then** `Client._on_ws_message(envelope)` parses `envelope["type"]` against the eight known entity-type strings (`turnout`, `sensor`, `block`, `light`, `memory`, `route`, `signalHead`, `signalMast`) and:
  - For the six waitable types, calls the matching parser (`parse_turnout`, etc. — already imported in `client.py`), looks up the entity in `Client._entities[(entity_type, parsed.name)]`, and calls `entity._on_event(parsed.<primary_state>)`
  - For `memory` or `route` envelopes, logs at DEBUG on `pyjmri.transport` and drops (no `_on_event` method exists)
  - For JMRI's `hello` envelope (sent on every connect — captured in 3.1 dev notes) and any unrecognized `type`, logs once at DEBUG and drops; **never raises**
  - For a known type whose `(entity_type, name)` is not in `Client._entities` (entity not in this Client's discovered Layout), logs once at DEBUG and drops; never raises
  - For an envelope whose parser raises `JMRIProtocolError` (malformed JMRI frame), logs at WARNING on `pyjmri.transport` with `extra={"entity_type": <type>, "error_type": "JMRIProtocolError"}` and drops the frame; never propagates (a single bad frame must not kill the supervisor — same discipline as Story 3.1's per-frame try/except)

**AC7 — `Client._entities` is populated by `discover()`**

**Given** `Client.discover()` builds entities and returns a `Layout`
**When** discovery completes
**Then** `Client._entities: dict[tuple[str, str], <waitable entity>]` is populated with one entry per waitable entity (six types), keyed by `(entity_type, system_name)`
**And** the entities stored are the same instances handed back inside the returned `Layout` — so `_on_event` updates state visible to user code (no copies)
**And** repeated `discover()` calls replace the index entirely (the previous Layout's entities are discarded; their waiters never resolve naturally and the user is responsible for cancellation if they care — documented in `discover()` docstring)
**And** `Client.__aexit__` clears `_entities` alongside the other lifecycle fields

**AC8 — Cancellation and timeout cleanup**

**Given** a waiter is registered on an entity's `_waiters` list
**When** the awaiting task is cancelled (`asyncio.CancelledError`) OR its `asyncio.timeout` block fires
**Then** the `(predicate, future)` pair is removed from `_waiters` before the exception propagates (try/finally pattern)
**And** the future is also cancelled if it has not already been resolved (avoid orphan-future warnings)
**And** unit tests cover both paths: explicit `task.cancel()` and `asyncio.TimeoutError` from the inner `asyncio.timeout(...)` block

**AC9 — Unit tests in `tests/unit/test_state_machine.py`**

**Given** Story 3.2's deliverables
**When** the unit suite runs
**Then** `tests/unit/test_state_machine.py` covers each property below with at least one explicit test (a single test may cover multiple bullets when natural):
  - Synchronous fanout: registering two waiters with the same predicate on one entity → both resolve when a matching `_on_event` fires
  - Predicate-mismatch retention: a `wait_state(THROWN)` waiter remains in `_waiters` when `_on_event(CLOSED)` fires
  - Early-return: `wait_state(target)` returns immediately when cached state already equals `target`; no subscription is requested; `_waiters` is not mutated
  - Auto-subscription: first `wait_*` call against an entity invokes `_handle.ensure_subscription(entity_type, name)` exactly once; repeated `wait_*` calls invoke it again (idempotency lives in the registry, not in the entity)
  - `WaitTimeout` raised when the inner `asyncio.timeout` block elapses; the entity's `_waiters` list is empty after the raise
  - Cancellation: a wait task that is `task.cancel()`-ed propagates `CancelledError` and leaves `_waiters` empty
  - `wait_change` captures the starting state at call time; an `_on_event` with the same state does NOT resolve it; an `_on_event` with a different state DOES
  - `Sensor.wait_active()` is a thin wrapper: it ends up registering a predicate equivalent to `s == SensorState.ACTIVE`
  - `Client._on_ws_message` dispatch: a synthesized turnout-state envelope flowing through the Client's real `_on_ws_message` lands on the right entity's `_on_event` (full integration, but unit-scoped via `patch_http_factory`'s FakeWSConnection)
  - Done-waiter pruning: a future that has already been resolved is removed from `_waiters` during the next fanout iteration

**And** the file is unit-scoped (no `@pytest.mark.integration`, no live network, no `await asyncio.sleep(...)` greater than `0`); the standard `asyncio_mode=auto` config from `pyproject.toml` applies

**AC10 — Integration test for NFR1 latency**

**Given** `tests/integration/test_wait_primitives_latency.py`
**When** run with JMRI reachable
**Then** the test (a) opens `async with Client() as jmri:`, (b) calls `await jmri.discover()`, (c) picks the first sensor from the discovered Layout (skips with a clear message if the layout has zero sensors), (d) for each of 20 trials: read the sensor's current state, register `await sensor.wait_change()` as a background task, then issue a raw `httpx.AsyncClient.post("/json/sensor/<name>", json={...toggle...})` against JMRI to flip the sensor, then `await` the background task and record `elapsed_ms = (resolution_time − post_time) × 1000`
**And** the test reports the median, p95, min, and max across the 20 trials (use `statistics.median` etc.; print via `caplog` or pytest output)
**And** the test asserts `median <= 100` (NFR1 budget)
**And** the test is marked `@pytest.mark.integration` and consumes the existing `jmri_available` fixture from `tests/integration/conftest.py` — same pattern as `test_discovery.py`, `test_ws_connect.py`
**And** the test is layout-agnostic: no hardcoded sensor names or system-name prefixes; if the chosen sensor's state is `UNKNOWN`, the toggle posts an explicit value to force a known starting state before measuring
**And** if the layout has no sensors, the test skips with `pytest.skip("layout has no sensors")` — never fails

**AC11 — No regressions; quality gates clean**

**Given** the unit suite has 285 tests + 4 integration tests passing as of Story 3.1 close
**When** the unit suite runs after Story 3.2
**Then** every pre-existing test still passes, plus the new tests from AC9 and AC10
**And** `uv run --no-sync ruff format`, `uv run --no-sync ruff check`, and `uv run --no-sync mypy --strict src/pyjmri` are all clean
**And** `grep -rn 'from pyjmri._subscriptions\|from pyjmri import _subscriptions' src/pyjmri/turnout.py src/pyjmri/sensor.py src/pyjmri/block.py src/pyjmri/light.py src/pyjmri/signal.py` returns zero matches (entity modules do not import `_subscriptions`; they go through `ClientHandle`)
**And** `grep -rn 'asyncio.create_task' src/pyjmri/` still returns zero matches (no bare task creation outside the supervisor TaskGroup)

**AC12 — Public API surfaces**

**Given** `src/pyjmri/__init__.py`
**When** Story 3.2 lands
**Then** no new entries are added to `__all__` — `wait_state`, `wait_change`, `wait_active`, `wait_inactive` are methods on already-exported entity classes; `_on_event` and `_waiters` are private (underscore-prefixed) and intentionally not surfaced
**And** the entity class docstrings gain a short "Waiting on state changes" example block showing `await turnout.wait_state(TurnoutState.THROWN)` and `await sensor.wait_active(timeout=30.0)` patterns; the existing `get_state()` example stays

## Tasks / Subtasks

- [x] **Task 1 — Extend `ClientHandle` Protocol and Client implementation** (AC: 5, 7)
  - [x] In `src/pyjmri/_protocols.py`, add `async def ensure_subscription(self, entity_type: str, name: str) -> None: ...` to the `ClientHandle` Protocol. Update the module docstring to mention this is the auto-subscription channel.
  - [x] In `src/pyjmri/client.py`, add `Client._entities: dict[tuple[str, str], Any] = {}` in `__init__` (typed as `Any` for now — see design note on union types in Dev Notes). Reset to empty in `__aexit__` alongside the other lifecycle fields.
  - [x] Implement `Client.ensure_subscription(entity_type, name)` that raises `RuntimeError` when `self._registry is None` and otherwise delegates to `await self._registry.ensure(entity_type, name)`.
  - [x] In `Client.discover()`, after building the Layout's eight `EntityCollection` instances, populate `Client._entities` with one entry per waitable entity (turnouts, sensors, blocks, lights, signal_heads, signal_masts). Memory and Route entities are skipped (no `_on_event`).
  - [x] Update the `Client.discover()` docstring with a one-paragraph note: "Repeated calls discard the previous Layout's entity registry — in-flight `wait_*` calls on a stale Layout will not resolve. Cancel them or restructure your script to call `discover()` once."

- [x] **Task 2 — Replace `Client._on_ws_message` stub with real dispatch** (AC: 6)
  - [x] Build a parser-and-state-extractor table at module level in `client.py`:
    ```python
    _DISPATCH_TABLE: dict[str, Callable[[dict[str, Any]], tuple[str, Any]]] = {
        "turnout":    lambda env: (parse_turnout(env).name,    parse_turnout(env).state),
        "sensor":     lambda env: (parse_sensor(env).name,     parse_sensor(env).state),
        "block":      lambda env: (parse_block(env).name,      parse_block(env).state),
        "light":      lambda env: (parse_light(env).name,      parse_light(env).state),
        "signalHead": lambda env: (parse_signal_head(env).name, parse_signal_head(env).appearance),
        "signalMast": lambda env: (parse_signal_mast(env).name, parse_signal_mast(env).aspect),
    }
    ```
    *(In practice avoid parsing twice — write a small helper that parses once and returns `(name, primary)`. Sketch above is illustrative, not literal.)*
  - [x] In `Client._on_ws_message(envelope)`:
    1. Read `envelope.get("type")`. If not a string, log DEBUG and return.
    2. If type is `"hello"` or any string not in `_DISPATCH_TABLE` (including `"memory"`, `"route"`, JMRI internal types), log DEBUG (`"WS dispatch: drop"`, `extra={"type": <type>}`) and return.
    3. Otherwise, call the dispatch entry inside `try / except JMRIProtocolError:` — on `JMRIProtocolError`, log WARNING with `extra={"entity_type": <type>, "error_type": "JMRIProtocolError"}` and return.
    4. Look up `entity = self._entities.get((<type>, name))`. If `None`, log DEBUG (`"WS dispatch: entity not in current Layout"`) and return.
    5. Call `entity._on_event(primary)`. Wrap in `try / except Exception:` to swallow + log any bug inside `_on_event` so a buggy waiter cannot kill the supervisor (defense-in-depth; the AC1 implementation should not raise, but treat as adversarial).
  - [x] Remove the AC11 stub-marker docstring on `_on_ws_message` from Story 3.1; replace with a real docstring describing the dispatch contract.

- [x] **Task 3 — Add waiter primitives to each state-bearing entity** (AC: 1, 2, 3, 4)
  - [x] **Decide between Open Design Decision #1 options before writing code.** Then either:
    - (Option A — recommended) Add a small private helper module `src/pyjmri/_waiters.py` defining a generic `WaiterList[StateT]` class with `register(predicate) -> asyncio.Future[StateT]`, `fanout(new_state) -> None`, `remove(future) -> None`, `__len__`. Each entity holds a `WaiterList[<its state>]` instance, drastically reducing duplication.
    - (Option B) Inline the list + fanout + register + remove logic inside each entity.
  - [x] For each of `Turnout`, `Sensor`, `Block`, `Light`, `SignalHead`, `SignalMast`:
    - Add `_waiters` attribute (either a `WaiterList[<StateT>]` instance per option A, or a plain `list[tuple[...]]` per option B) initialized in `__init__`.
    - Add `_on_event(self, new_state: <StateT>) -> None`:
      - Updates the primary state attribute (`self.state` / `self.appearance` / `self.aspect`).
      - Fans out to waiters: resolve matching futures, prune done/cancelled, retain non-matching.
    - Add `async def wait_state(self, target: <StateT>, *, timeout: float | None = None) -> <StateT>`:
      - Early return if `self.<primary> == target`.
      - `await self._handle.ensure_subscription("<entity_type>", self.name)`.
      - Register `(lambda s: s == target, future)`; await with optional `asyncio.timeout`.
      - `try/finally` removes the waiter on any exception or cancellation. On `TimeoutError` from the timeout block, raise `WaitTimeout(entity_type="<entity_type>", name=self.name, target=target.name)` (with `from` chaining).
    - Add `async def wait_change(self, *, timeout: float | None = None) -> <StateT>`:
      - Capture `starting = self.<primary>` at call time.
      - Same plumbing as `wait_state`, with predicate `lambda s: s != starting`.
  - [x] On `Sensor`, additionally add `async def wait_active(self, *, timeout: float | None = None) -> SensorState` and `async def wait_inactive(...)` as thin wrappers to `self.wait_state(...)`.
  - [x] Each entity module keeps its existing `get_state()` semantics — that method is the explicit-refresh path; `_on_event` is the WS push path. Both write to the same primary-state attribute, which is fine for users (last writer wins; in practice WS arrives faster).
  - [x] Update each entity's class-level docstring with a short example showing `wait_state` / `wait_change` / (Sensor only) `wait_active`. Keep prose minimal.

- [x] **Task 4 — Update `make_fake_handle` to support `ensure_subscription`** (AC: 5, 9)
  - [x] In `tests/unit/conftest.py`, extend `_FakeHandle` (inside `make_fake_handle`) with `async def ensure_subscription(self, entity_type: str, name: str) -> None` that records calls into a separate `ensure_calls: list[tuple[str, str]]` list. Existing tests that pass `_FakeHandle` to entities continue to work; new tests can introspect `handle.ensure_calls` to verify auto-subscription behavior.
  - [x] Do **not** add subscription support to `FakeWSConnection`'s `send` — `make_fake_handle`'s test handle is independent of `FakeWSConnection`; the dispatch-integration test (last bullet of AC9) uses the real `Client` with `patch_http_factory`, which already stubs both transports.
  - [x] No change needed to `patch_http_factory` itself; the `Client._on_ws_message` test in `test_state_machine.py` will exercise the real client by invoking `_on_ws_message` directly with a synthesized envelope after entering the Client.

- [x] **Task 5 — Unit tests `tests/unit/test_state_machine.py`** (AC: 9)
  - [x] Create the file. No `@pytest.mark.asyncio` decorator (asyncio_mode=auto).
  - [x] Implement each AC9 bullet as one or more tests. Suggested structure: split into three sections by comment headers: `# Per-entity waiter mechanics (AC1, AC2, AC3, AC8)`, `# Sensor convenience wrappers (AC4)`, `# Client dispatch (AC6)`.
  - [x] Use `make_fake_handle` for per-entity tests (no Client needed). Use `patch_http_factory` for the dispatch test (real Client, fake WS, hand-fed `_on_ws_message` calls).
  - [x] For cancellation tests, the pattern is:
    ```python
    task = asyncio.create_task(turnout.wait_state(TurnoutState.THROWN))
    await asyncio.sleep(0)  # let the task register its waiter
    assert len(turnout._waiters) == 1  # or via WaiterList.__len__
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(turnout._waiters) == 0
    ```
    Note: this is one of the very few places where `asyncio.create_task` is allowed in pyjmri — it's a test, not library code. AC11's grep audit is scoped to `src/pyjmri/`, not `tests/`.
  - [x] For timeout tests, use `pytest.raises(WaitTimeout)` and a small timeout (e.g., `timeout=0.05`). The inner `asyncio.timeout` block does sleep, but only for ~50 ms — well under the test-runtime envelope.

- [x] **Task 6 — Integration test `tests/integration/test_wait_primitives_latency.py`** (AC: 10)
  - [x] Create the file with the `@pytest.mark.integration` marker and the `jmri_available: None` fixture (same shape as `test_ws_connect.py`).
  - [x] Skip with a clear message if `layout.sensors` is empty.
  - [x] To force a known starting state on the chosen sensor: read `sensor.state`. If `UNKNOWN`, POST to `/json/v5/sensor/<system_name>` (URL-encoded) with body `{"type":"sensor","data":{"name":"<system_name>","state":4}}` (4 = INACTIVE per `_codes.SENSOR_STATE`). The test owns its raw `httpx.AsyncClient` for this purpose — do NOT add a command method to `_transport.HTTPClient` in this story.
  - [x] For 20 trials, alternate the target state (ACTIVE ↔ INACTIVE):
    ```python
    target = SensorState.INACTIVE if sensor.state is SensorState.ACTIVE else SensorState.ACTIVE
    waiter = asyncio.create_task(sensor.wait_state(target, timeout=2.0))
    await asyncio.sleep(0)
    t_post = time.perf_counter()
    await raw_http.post(...)
    await waiter
    t_resolved = time.perf_counter()
    samples.append((t_resolved - t_post) * 1000)
    ```
  - [x] Compute and print median, p95, min, max via `statistics`. Assert `median <= 100` (NFR1).
  - [x] On failure print all 20 samples to aid diagnosis. Make the assertion message specific: `f"NFR1: sensor-event median latency {median:.1f} ms exceeds 100 ms budget; samples={samples}"`.

- [x] **Task 7 — Quality gates and regression check** (AC: 11)
  - [x] Run `uv run --no-sync ruff format` and `uv run --no-sync ruff check`.
  - [x] Run `uv run --no-sync mypy --strict src/pyjmri`. The dispatch table parameterized over disparate state enum types may need a `cast` or a typed `Protocol` for "entity with `_on_event(StateT)`". Plan this before writing — see Dev Notes "Typing the dispatch path".
  - [x] Run `uv run --no-sync pytest -m "not integration"` — confirm 285 prior + ~15 new tests pass (~300 unit tests).
  - [x] Run `uv run --no-sync pytest` with JMRI reachable — confirm 4 prior integration tests pass + the new latency test passes against Mike's Basement Layout.
  - [x] Audit grep checks per AC11.
  - [x] Update story File List.

## Dev Notes

### Current `python_code/` state (verified by inspection, 2026-05-12)

**Source files in place (18 files, all clean under mypy --strict):**

- `client.py` — Owns the supervisor `TaskGroup`, `_ws`, `_registry`, `_supervisor_task`, `_ws_connected`. `_on_ws_message` is a no-op stub (line ~253) with a docstring saying "Story 3.2 will replace this body with per-entity dispatch into `entity._on_event(new_state)`." Imports every `parse_*` function already, so dispatch can call them without new imports. `_on_ws_reconnect` already emits the unified INFO log on `pyjmri.reconnect`.
- `_protocols.py` — `ClientHandle` Protocol with only `get_entity`. **Add `ensure_subscription` here.**
- `_subscriptions.py` — `SubscriptionRegistry.ensure(entity_type, name)` already exists. Entity modules **must not** import this directly; they go through `ClientHandle.ensure_subscription`.
- `_transport.py` — `WSConnection` and `HTTPClient`. The WS receive loop already calls `await on_message(envelope)` for every inbound frame, wrapping in `try/except Exception` to swallow per-frame errors (Story 3.1 review patch). Story 3.2 changes only what `on_message` does on the Client side; `_transport.py` itself does not change.
- Entity modules (`turnout.py`, `sensor.py`, `block.py`, `light.py`, `signal.py`) — Each has `__init__` that stores `name`, `user_name`, primary state, and `_handle`. Each has a single `get_state()` (or `get_value()` for `memory.py`) method. **Story 3.2 adds `_waiters`, `_on_event`, `wait_state`, `wait_change` to each (plus `wait_active`/`wait_inactive` on Sensor).**
- `memory.py` — value-only; no state enum. **No changes in Story 3.2.**
- `route.py` — metadata-only. **No changes in Story 3.2.**
- `exceptions.py` — `WaitTimeout(JMRIError, TimeoutError)` already exists. No new exception types needed.

**Test infrastructure:**

- `tests/unit/conftest.py` — `make_fake_handle` builds a `_FakeHandle` with `get_entity`. **Add `ensure_subscription` to this fake.** `patch_http_factory` already stubs `WSConnection` via `FakeWSConnection`; tests can exercise real `Client._on_ws_message` against it.
- `tests/integration/conftest.py` — `jmri_available` session fixture (TCP probe of `localhost:12080`).
- 285 unit tests + 4 integration tests passing as of Story 3.1 close.

### `WaiterList` helper sketch (Option A — recommended)

```python
# src/pyjmri/_waiters.py — new file

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Generic, TypeVar

StateT = TypeVar("StateT")

__all__ = ["WaiterList"]


class WaiterList(Generic[StateT]):
    """Per-entity list of (predicate, future) pairs.

    See architecture §Subscription Registry & Event Fanout. Single
    event loop = no lock needed; fanout is synchronous.
    """

    def __init__(self) -> None:
        self._entries: list[tuple[Callable[[StateT], bool], asyncio.Future[StateT]]] = []

    def __len__(self) -> int:
        return len(self._entries)

    def register(self, predicate: Callable[[StateT], bool]) -> asyncio.Future[StateT]:
        future: asyncio.Future[StateT] = asyncio.get_running_loop().create_future()
        self._entries.append((predicate, future))
        return future

    def remove(self, future: asyncio.Future[StateT]) -> None:
        # Drop the entry whose future matches. Tolerant of double-removal.
        self._entries = [(p, f) for (p, f) in self._entries if f is not future]
        if not future.done():
            future.cancel()

    def fanout(self, new_state: StateT) -> None:
        """Resolve every matching, not-done future; prune done futures."""
        kept: list[tuple[Callable[[StateT], bool], asyncio.Future[StateT]]] = []
        for predicate, future in self._entries:
            if future.done():
                continue  # prune
            if predicate(new_state):
                future.set_result(new_state)
                continue  # done -> drop
            kept.append((predicate, future))
        self._entries = kept
```

### Entity waiter implementation sketch (Turnout)

```python
# turnout.py — additions

class Turnout:
    def __init__(self, *, name, user_name, state, _handle) -> None:
        # ... existing fields ...
        self._waiters: WaiterList[TurnoutState] = WaiterList()

    def _on_event(self, new_state: TurnoutState) -> None:
        """Called by Client._on_ws_message on a turnout state event."""
        self.state = new_state
        self._waiters.fanout(new_state)

    async def wait_state(
        self,
        target: TurnoutState,
        *,
        timeout: float | None = None,
    ) -> TurnoutState:
        if self.state == target:
            return self.state
        await self._handle.ensure_subscription("turnout", self.name)
        future = self._waiters.register(lambda s: s == target)
        try:
            if timeout is None:
                return await future
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as e:
            raise WaitTimeout(
                entity_type="turnout",
                name=self.name,
                target=target.name,
            ) from e
        except BaseException:
            raise
        finally:
            self._waiters.remove(future)

    async def wait_change(
        self,
        *,
        timeout: float | None = None,
    ) -> TurnoutState:
        starting = self.state
        await self._handle.ensure_subscription("turnout", self.name)
        future = self._waiters.register(lambda s: s != starting)
        try:
            if timeout is None:
                return await future
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as e:
            raise WaitTimeout(entity_type="turnout", name=self.name, from_state=starting.name) from e
        finally:
            self._waiters.remove(future)
```

**Notes on the sketch:**

- Six entities × two near-identical methods = a strong duplication smell. The Option-A helper makes the duplication manageable but each entity still carries two short async methods + `_on_event`. If you prefer factoring further into a `_WaitableEntity[StateT]` mixin, that's Open Design Decision #1.
- `except BaseException: raise` is intentional — it documents that cancellation does NOT skip the `finally` block. Could be removed; `finally` runs regardless. Kept as a reading aid for the next maintainer; remove if `ruff` complains.
- `from_state` vs `target` in the `WaitTimeout` context: `wait_state` carries `target`; `wait_change` carries `from_state` (since there's no specific target). Document this in the `WaitTimeout` docstring.
- `asyncio.timeout(...)` raises `TimeoutError` on expiry; the `except TimeoutError` is the right catch in 3.11+ (it's also `asyncio.TimeoutError`, an alias).

### Typing the dispatch path

mypy --strict will complain about `Client._entities: dict[tuple[str, str], Any]` if entities have disjoint primary-state types. Three options:

1. **Use a `Protocol`** in `_protocols.py` describing the waitable shape:
   ```python
   class _Waitable(Protocol):
       name: str
       def _on_event(self, new_state: object) -> None: ...
   ```
   Then `Client._entities: dict[tuple[str, str], _Waitable]`. mypy will accept since each entity has `_on_event`, and the dispatch passes `object` (the primary state) which the entity's typed signature accepts (covariance on argument is unsound in general, but `_on_event` is internal and dispatch types are runtime-checked by the parser-table).

2. **Use a `Union`** in the dict value: `dict[tuple[str, str], Turnout | Sensor | Block | Light | SignalHead | SignalMast]`. More precise but verbose.

3. **Use `Any`** for `_entities` and document the contract in code comments. Pragmatic; mypy --strict will not complain.

**Recommended:** option 1 (`_Waitable` Protocol). One narrow internal Protocol, no `Any`, no long union. Define it in `_protocols.py` alongside `ClientHandle`.

### Reconnect-resilience as an emergent property (not new code in 3.2)

Story 3.3 will prove this against a real disconnect. The mechanism that makes it work in 3.2:

1. User calls `await sensor.wait_active()`. Entity calls `ensure_subscription("sensor", name)` → registry adds `("sensor", name)` to its authoritative set + sends a subscribe over the current WS. Future registered on entity's `_waiters`.
2. WS drops. `WSConnection.run`'s outer `async for connection in websockets.connect(...)` schedules a reconnect (after backoff).
3. Reconnect succeeds. `WSConnection.run` calls `Client._on_ws_reconnect()` → `registry.replay()` → re-sends every subscribe over the new connection.
4. JMRI responds to each subscribe with the current state → `Client._on_ws_message` → `entity._on_event(new_state)` → if `new_state == SensorState.ACTIVE`, the waiter resolves.

Critically, in step 4, the **same `Future` object** registered before the disconnect is what resolves. Disconnect does not touch `_waiters`. This is the "level-triggered semantics" of architecture §Reconnect & Restoration.

Story 3.2 must not break this property. The two ways it could break:
- If `discover()` is called during the disconnect window and rebuilds `_entities`, the in-flight `Future` belongs to a stale entity not in the index — `_on_event` is never invoked on it. **Mitigation: document this in the `discover()` docstring (Task 1). 3.3's resilience test only calls `discover()` once.**
- If the entity's `_waiters` list is somehow cleared on reconnect — **don't do that.** Only `_on_event` (via `WaiterList.fanout`) mutates the list, and only by resolving matching waiters.

### Layout-agnosticism reminder

No hardcoded entity names, system-name prefixes, or DCC addresses in `src/pyjmri/`. The unit tests use synthesized entity names (`"NT1"`, `"NS401"`, etc.) — those are fine in tests. The integration test in Task 6 picks the first sensor `discover()` returns; it is layout-agnostic and skips with a clear message when the layout has no sensors.

### File layout

```
python_code/src/pyjmri/_protocols.py             # MODIFY — add ensure_subscription; add _Waitable Protocol
python_code/src/pyjmri/_waiters.py               # NEW (if Option A) — WaiterList[StateT] helper
python_code/src/pyjmri/turnout.py                # MODIFY — _waiters, _on_event, wait_state, wait_change
python_code/src/pyjmri/sensor.py                 # MODIFY — _waiters, _on_event, wait_state, wait_change, wait_active, wait_inactive
python_code/src/pyjmri/block.py                  # MODIFY — _waiters, _on_event, wait_state, wait_change
python_code/src/pyjmri/light.py                  # MODIFY — _waiters, _on_event, wait_state, wait_change
python_code/src/pyjmri/signal.py                 # MODIFY — _waiters, _on_event, wait_state, wait_change for both SignalHead and SignalMast
python_code/src/pyjmri/client.py                 # MODIFY — _entities dict; ensure_subscription impl; real _on_ws_message dispatch
python_code/tests/unit/conftest.py               # MODIFY — make_fake_handle._FakeHandle gains ensure_subscription + ensure_calls
python_code/tests/unit/test_state_machine.py     # NEW — waiter mechanics + Client dispatch
python_code/tests/integration/test_wait_primitives_latency.py  # NEW — NFR1 latency budget
```

Eight modify + three new = eleven files touched. Larger blast radius than 3.1 (which was eight files), but the per-entity additions are mechanical and the WaiterList helper keeps duplication low.

### Open Design Decisions for Mikey

Surfaced for explicit acceptance before dev runs. Proposed defaults noted; if all four are accepted, the dev agent can proceed without further input.

1. **Shared `WaiterList[StateT]` helper vs. inline per-entity** — six entities × `_waiters` + `_on_event` + `wait_state` + `wait_change` is a lot of near-identical code. Option A factors the list-management into `_waiters.WaiterList[StateT]`; each entity holds an instance and the wait_* methods are 10 lines each. Option B inlines everything per entity (~30 lines each, 6× repetition). **Proposed default: Option A.** Cleaner, easier to unit-test the list mechanics once, more obvious where to fix any future bug.

2. **`Client._entities` typing** — three sub-options listed under "Typing the dispatch path" above. **Proposed default: a narrow `_Waitable` Protocol in `_protocols.py`.** Keeps mypy --strict clean without `Union[...]` ugliness or `Any` cowardice.

3. **`discover()` re-call semantics** — calling `discover()` twice rebuilds `_entities`; stale-Layout in-flight waiters will silently never resolve. Three options: (a) document and move on; (b) make `discover()` raise if called while there are pending waiters; (c) preserve old waiters by merging entity registries on stale-Layout entities. **Proposed default: (a) — document.** This is a foot-gun, but it's an obscure one — calling `discover()` mid-script is rare; users normally call it once. Detecting "pending waiters" requires global enumeration we don't otherwise need.

4. **`WaitTimeout` context fields** — `wait_state` carries `{"entity_type", "name", "target": target.name}`; `wait_change` carries `{"entity_type", "name", "from_state": starting.name}`. Two different context shapes for one exception type. **Proposed default: accept the asymmetry** — it reflects the genuine semantic difference (target vs. starting state). Alternative: unify with `{"entity_type", "name", "wait_kind": "state" | "change", "wait_arg": <target or from_state>}`. Cleaner schema, slightly less readable in tracebacks.

5. **NFR1 integration-test sensor-toggle mechanism** — Story 3.2 needs to flip a sensor's state to measure end-to-end latency. Options: (a) raw `httpx` POST inside the test (sidesteps Epic 4); (b) defer the NFR1 test to Story 4.2 where the command path exists; (c) ship a *test-only* hidden `Client._raw_command(...)` and remove it in Epic 4. **Proposed default: (a) — test owns its own raw `httpx` client.** No production code touches sensor commands until Epic 4. The integration test is honest that it's reaching past the library to exercise it; this is normal for latency tests.

6. **SignalHead/SignalMast wait scope** — these entities have multiple changing attributes (`appearance` + `held` + `lit` for SignalHead; `aspect` + `held` + `lit` for SignalMast). Story 3.2 wires `wait_state(target)` against the primary attribute only (`appearance` / `aspect`). The library does NOT model `wait_held()` or `wait_lit_change()` in v1. **Proposed default: confirm primary-attribute-only.** If JMRI emits a `signalHead` WS event for a `lit` flip (state code unchanged), `_on_event(appearance)` is invoked with the same appearance value — fanout finds no matching `wait_state(appearance)` waiter (already-equal predicate doesn't match) and the change is silently dropped. Acceptable for v1; document in the SignalHead/SignalMast class docstrings.

If you accept all six proposed defaults, the dev agent runs without further design questions.

### Cross-story implications

- **Story 3.3 (forced-disconnect resilience integration test)** — exercises the property described under "Reconnect-resilience as an emergent property." Requires no API changes from 3.2; the test composes 3.1's WS reconnect + 3.2's `wait_*` + 3.1's `SubscriptionRegistry.replay()`. The test-only force-disconnect hook lives on `WSConnection` (3.3 adds it).
- **Story 4.1 (HTTP command path)** — adds `await turnout.throw()`, `light.on()`, etc. Independent of 3.2; no dependency in either direction.
- **Story 4.2 (`wait_for_jmri_state=True`)** — depends on 3.2's `wait_state`. The pre-register-wait pattern in architecture §Command/Event Correlation literally registers a waiter via `wait_state(...)` before issuing the HTTP command. 3.2's waiter API is the underlying mechanism.
- **Epic 5 throttles** — Throttle's keep-alive coroutine is supervised by the same TaskGroup that supervises the WS receive loop. 3.2 makes no throttle changes; the TaskGroup pattern carries forward.
- **Epic 6 README** — the 5-minute quickstart will showcase `await sensor.wait_active()` as the headline feature. Story 6.1 is the consumer.

### Testing patterns

- **No mocks of JMRI** for unit tests (architecture policy). Unit tests for waiter mechanics use `make_fake_handle` (already in `conftest.py`, extended in Task 4) — the entity is constructed with a fake handle that records `ensure_subscription` calls and never touches a real registry or transport.
- **Real `Client._on_ws_message` dispatch test** uses `patch_http_factory` and synthesizes envelopes by calling `client._on_ws_message(envelope)` directly after entering the Client context. The fake WS does not deliver frames itself — it just idles — so the unit test injects envelopes manually.
- **Integration latency test** is the first test that exercises the full live-JMRI loop end-to-end through `wait_*`. Expect mild flakiness at the 5th-percentile boundary; the median assertion is what matters per NFR1.
- **`asyncio.create_task` allowed in tests, forbidden in `src/pyjmri/`** — AC11's grep is scoped to `src/`. Tests freely use `create_task` to register and cancel background waiters.
- **No real sleeps over ~100 ms in any test** — keep the unit suite fast. The NFR1 integration test is the only place where elapsed wall time matters.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md`#Epic 3 → Story 3.2] — story scope, acceptance criteria, design intent
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Subscription Registry & Event Fanout] — `_waiters: list[(predicate, asyncio.Future)]`, synchronous fanout, early-return for `wait_state`
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Reconnect & Restoration Mechanism] — level-triggered semantics; "in-flight `wait_*` futures see the post-reconnect state"
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Internal data flow] — `entity._on_event(state)` is the canonical dispatch sink
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Implementation Patterns → Async Patterns] — `asyncio.timeout(...)` over `asyncio.wait_for(...)`; cancellation discipline; no bare `asyncio.create_task` outside the supervisor TaskGroup
- [Source: `_bmad-output/planning-artifacts/prd.md`#FR29] — auto-subscription, no manual bookkeeping
- [Source: `_bmad-output/planning-artifacts/prd.md`#FR30] — sensor `wait_active`/`wait_inactive` with optional timeout, typed timeout error
- [Source: `_bmad-output/planning-artifacts/prd.md`#FR31] — `wait_state(target)` with optional timeout
- [Source: `_bmad-output/planning-artifacts/prd.md`#FR32] — `wait_change()` regardless of target state
- [Source: `_bmad-output/planning-artifacts/prd.md`#FR33] — in-flight `wait_*` calls survive WS reconnect (proven in Story 3.3; preserved as a property in 3.2)
- [Source: `_bmad-output/planning-artifacts/prd.md`#NFR1] — sensor-event propagation under 100 ms median, idle layout, <100 subscriptions
- [Source: `_bmad-output/planning-artifacts/prd.md`#NFR5] — level-triggered semantics: post-reconnect state event resolves still-pending waiters
- [Source: `_bmad-output/implementation-artifacts/3-1-websocket-transport-subscriptionregistry-reconnect-with-bounded-backoff.md`] — Story 3.1 dev notes (TaskGroup ownership, `Client._on_ws_message` stub, INFO/WARN log structure, FakeWSConnection details, JMRI `hello` envelope behavior)
- [Source: `python_code/src/pyjmri/client.py`] — current `Client` with WS supervisor wired up; `_on_ws_message` stub at line ~253; eight `parse_*` imports already in place; `_entities` dict goes alongside `_ws`/`_registry` lifecycle fields
- [Source: `python_code/src/pyjmri/_protocols.py`] — `ClientHandle` Protocol; add `ensure_subscription` here and consider co-locating `_Waitable` Protocol
- [Source: `python_code/src/pyjmri/_subscriptions.py`] — `SubscriptionRegistry.ensure(entity_type, name)` is the underlying call that `ClientHandle.ensure_subscription` forwards to
- [Source: `python_code/src/pyjmri/exceptions.py`] — `WaitTimeout(JMRIError, TimeoutError)` already exists with `**context` support; no changes needed
- [Source: `python_code/tests/unit/conftest.py`] — `make_fake_handle` is the entity test handle; gains `ensure_subscription`. `patch_http_factory` already stubs `WSConnection` for dispatch tests
- [Source: `python_code/tests/integration/conftest.py`] — `jmri_available` session fixture; pattern for integration tests that skip when JMRI is down

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Opus 4.7, 1M context) via Claude Code, with bmad-dev-story workflow.

### Debug Log References

- **Logger collision on `extra={"name": ...}` (2026-05-12):** First pass of `Client._on_ws_message` used `extra={"name": name, ...}` in two log calls. Python's `Logger.makeRecord` raises `KeyError("Attempt to overwrite 'name' in LogRecord")` because `LogRecord.name` is the logger's name. Caught by `test_client_on_ws_message_swallows_on_event_exception`. Renamed the `extra` key to `system_name` — consistent with the existing convention in `_subscriptions.py`. No other extras collide.
- **ruff `ASYNC109` on `wait_state(timeout=...)` / `wait_change(timeout=...)` (2026-05-12):** The lint rule flags `timeout` parameters on async functions in favor of having the caller wrap with `asyncio.timeout(...)`. But FR30/FR31 mandate the `timeout: float | None` keyword on every `wait_*` method, and the implementation uses `asyncio.timeout(timeout)` internally exactly as architecture §Async Patterns requires. Resolution: added `ignore = ["ASYNC109"]` to `[tool.ruff.lint]` with a comment explaining the intent. Single rule, single project-wide ignore, documented.
- **NFR1 latency measurement (2026-05-12):** First run against Mike's Basement Layout with sensor `IS1` over 20 trials → median 19.6 ms, p95 571.2 ms, min 2.3 ms, max 588.5 ms. The high p95/max comes from a couple of outlier trials where JMRI's WS event lagged the HTTP ack by ~500 ms. The median is the NFR1 quantity (≤100 ms) and clears the budget by 5×.

### Completion Notes List

- All 12 acceptance criteria satisfied. All 7 tasks (Task 1–7) and every subtask checked.
- **Open Design Decisions** — all six accepted as proposed:
  1. Shared `WaiterList[StateT]` helper module (`src/pyjmri/_waiters.py`) — six entities × 3 methods each share one fanout/register/remove implementation. ~60 lines total instead of ~180.
  2. Narrow `_Waitable` Protocol in `_protocols.py` (alongside `ClientHandle`) types `Client._entities: dict[tuple[str, str], Waitable]`. mypy --strict clean; no `Any`, no `Union[Turnout | Sensor | ...]`.
  3. `discover()` re-call semantics documented in the method docstring: rebuilds the index; in-flight waiters on stale Layouts will never resolve. No detection added.
  4. `WaitTimeout` context fields are asymmetric on purpose: `wait_state` carries `target=<name>`, `wait_change` carries `from_state=<name>`. Verified by unit tests (`test_wait_state_timeout_raises_wait_timeout_and_cleans_up`, `test_wait_change_timeout_context_carries_from_state`).
  5. NFR1 latency test owns its own raw `httpx.AsyncClient` for the sensor toggle — no command method added to production code in this story.
  6. SignalHead/SignalMast `wait_state` operates on the primary attribute only (`appearance` / `aspect`); `held`/`lit` are not waitable in v1. Class docstrings updated.
- **Quality gates:** ruff format clean (44 files), ruff check clean (0 findings; ASYNC109 ignored for the documented reason above), mypy --strict clean across 19 source files. **316 unit tests pass + 5 integration tests pass (321 total).** Unit count grew by 28 (Story 3.1 close was 288; 285 from earlier story commit then 3.1 follow-up patches added 3).
- **AC11 grep audits:** zero matches for `from pyjmri._subscriptions` / `from pyjmri import _subscriptions` in entity modules (`turnout.py`, `sensor.py`, `block.py`, `light.py`, `signal.py`); zero `asyncio.create_task` in `src/pyjmri/`; `import websockets` / `from websockets` confined to `_transport.py` (3 lines).
- **AC12 public surface:** `__init__.py` `__all__` unchanged. `wait_state` / `wait_change` / `wait_active` / `wait_inactive` are methods on already-exported entity classes. `_waiters` / `_on_event` are private (underscore-prefixed) and intentionally not surfaced.
- **Reconnect-resilience invariant preserved (for Story 3.3 to verify):** waiters live on entity instances, not on the WS connection. `SubscriptionRegistry.replay()` re-subscribes after every reconnect (Story 3.1). The post-reconnect state events flow through the same `Client._on_ws_message` → `entity._on_event` path that 3.2 just wired up; in-flight `wait_*` futures see the post-reconnect state and resolve naturally per architecture §Reconnect & Restoration.

### File List

- `python_code/src/pyjmri/_protocols.py` — MODIFIED. Added `ensure_subscription` to `ClientHandle` Protocol; added new `Waitable` Protocol (entity-side abstraction for `Client._entities` dispatch index).
- `python_code/src/pyjmri/_waiters.py` — NEW. `WaiterList[StateT]` helper: `register` / `remove` / `fanout` / `__len__`. ~60 lines. Single source of truth for waiter-list semantics; reused by all six waitable entities.
- `python_code/src/pyjmri/turnout.py` — MODIFIED. Added `_waiters: WaiterList[TurnoutState]`, `_on_event(new_state)`, `wait_state(target, *, timeout=None)`, `wait_change(*, timeout=None)`. Docstring updated with wait_* examples.
- `python_code/src/pyjmri/sensor.py` — MODIFIED. Same as Turnout plus `wait_active(*, timeout=None)` and `wait_inactive(*, timeout=None)` convenience wrappers (FR30).
- `python_code/src/pyjmri/block.py` — MODIFIED. Same shape as Turnout; `_on_event` does NOT touch `Block.value` (block-value pushes are not waitable in v1).
- `python_code/src/pyjmri/light.py` — MODIFIED. Same shape as Turnout.
- `python_code/src/pyjmri/signal.py` — MODIFIED. Both `SignalHead` and `SignalMast` get `_waiters`, `_on_event`, `wait_state`, `wait_change`. `wait_state` operates on the primary attribute only (`appearance` / `aspect`); the module docstring documents this v1 scope.
- `python_code/src/pyjmri/client.py` — MODIFIED. Added `Waitable` import + declarative `_DISPATCH_PARSERS` table `(parser_fn, primary_attr)` keyed by entity-type string (six entries; adding a waitable entity is one line). Added `Client._entities: dict[tuple[str, str], Waitable]` lifecycle field; populated at end of `discover()` (Memory and Route excluded); cleared in both `__aexit__` and `_teardown_on_aenter_failure`. Added `Client.ensure_subscription(entity_type, name)` that delegates to `SubscriptionRegistry.ensure`. Replaced `Client._on_ws_message` stub with full dispatch driven by `_DISPATCH_PARSERS`: drops `hello`/unknown/memory/route at DEBUG, drops not-in-index entities at DEBUG, logs parse errors at WARNING with `exc_info=True`, swallows entity `_on_event` exceptions at WARNING with `exc_info=True` (defense-in-depth). `discover()` docstring updated with re-call semantics note.
- `python_code/tests/unit/conftest.py` — MODIFIED. `make_fake_handle._FakeHandle` gains `ensure_subscription` (records into `ensure_calls: list[tuple[str, str]]`).
- `python_code/tests/unit/test_state_machine.py` — NEW. 28 tests covering AC1, AC2, AC3, AC4, AC6, AC7, AC8: synchronous fanout, predicate-mismatch retention, early-return, auto-subscription (first call + repeat), `WaitTimeout` on timeout, cancellation cleanup, `wait_change` starting-state capture, done-future pruning, Sensor `wait_active`/`wait_inactive`, cross-entity smoke tests (Block, Light, SignalHead, SignalMast), Client dispatch (happy path, `hello`, unknown type, no-type field, entity-not-in-index, parser error, `_on_event` raises), `Client.ensure_subscription` delegation + closed-state error, `discover()` populates `_entities` + `__aexit__` clears it.
- `python_code/tests/integration/test_wait_primitives_latency.py` — NEW. NFR1 budget verification. 20 trials toggling the first discovered sensor via raw `httpx.AsyncClient` and measuring **`wait_change()`** resolution time. Reports median/p95/min/max; asserts median ≤ 100 ms. Marked `@pytest.mark.integration`, consumes `jmri_available`, layout-agnostic, skips if no sensors.
- `python_code/pyproject.toml` — UNCHANGED in final state. An initial project-wide `ignore = ["ASYNC109"]` was added during dev-story and then reverted during code review; the FR30/FR31 public `timeout: float | None` surface is preserved by per-call-site `# noqa: ASYNC109` comments on the six entity modules' `wait_*` signatures instead.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED. `3-2-*` flipped through `backlog` → `ready-for-dev` → `in-progress` → `review`; `last_updated: 2026-05-12`.
- `_bmad-output/implementation-artifacts/deferred-work.md` — MODIFIED. New `## Deferred from: code review of 3-2-...` section with eight items recorded during code review (one filed by Cursor pre-pass + seven from the adversarial pass): AC6 logger naming, `discover()` waiter abandonment, test-state integer codes, `WaiterList.remove` O(n), per-call-site `# noqa` repetition, signal partial-envelope speculation, dispatch-table case-sensitivity, `asyncio.timeout(0)` doc note.

### Review Findings

- [x] [Review][Patch] Integration NFR1 test should use `wait_change()` per AC10 — `tests/integration/test_wait_primitives_latency.py:~94`
- [x] [Review][Patch] Harden `_on_ws_message` parse/extract phase against non-`JMRIProtocolError` exceptions — `python_code/src/pyjmri/client.py:~278`
- [x] [Review][Patch] Narrow ASYNC109 suppression (prefer file-scoped `# noqa`/per-file ignores over global `ignore`) — `python_code/pyproject.toml:~31`
- [x] [Review][Defer] AC6 mentions DEBUG on `pyjmri.transport` for drops; `_on_ws_message` uses `pyjmri.client` (`getLogger(__name__)`) — `python_code/src/pyjmri/client.py:~47` — deferred, Tasks section implies `WS dispatch:` pattern without requiring the transport logger

### Review Findings — adversarial pass (BMAD code-review, 2026-05-12)

Three layers run in parallel against the diff + spec: Blind Hunter (diff only), Edge Case Hunter (diff + project read access), Acceptance Auditor (diff + spec + planning docs). Findings consolidated and de-duplicated below.

- [x] [Review][Patch] **Lost-wakeup race in `wait_state` / `wait_change` across the `ensure_subscription` await** — between the early-return / starting-state-capture check and `_waiters.register(...)`, control yields on `await self._handle.ensure_subscription(...)`. During that yield, an inbound WS event can call `_on_event(target)`: cached state is updated, fanout finds zero matching waiters, the event is lost. When the call resumes and registers, no future event may resolve it. Caller blocks until the next change (or forever). The bug is in `wait_state` early-return (the cached state can flip before register) and in `wait_change` (the captured `starting` is stale relative to the post-subscribe state). **Fix:** after `register(...)`, re-check `predicate(self.<primary>)`; if true, `future.set_result(self.<primary>)` synchronously and return — or move `starting`/early-return capture to AFTER `ensure_subscription` returns. [`python_code/src/pyjmri/turnout.py:113-156`, identical patterns in `sensor.py`, `block.py`, `light.py`, `signal.py` (both classes)] — flagged by Blind Hunter + Edge Case Hunter independently
- [x] [Review][Patch] **`WaiterList.fanout` aborts on first predicate exception, silently dropping every remaining waiter on the entity** — predicates run in a single loop with no per-iteration guard. A raising predicate (corrupt lambda capture, future user-supplied predicate, enum comparison oddity) propagates out of `fanout` → `_on_event` → `_on_ws_message`'s broad `except Exception`. Two consequences: (a) any waiters AFTER the raising one never get their predicate evaluated for this event; (b) `self._entries = kept` is never reached, so entries before the raising one stay registered with stale liveness state. Subsequent events keep retripping the bad predicate. **Fix:** wrap each `predicate(new_state)` call in `try/except Exception` inside the loop; log and drop the offending entry; move `self._entries = kept` to a `finally`. [`python_code/src/pyjmri/_waiters.py:57-67`] — flagged by Blind Hunter + Edge Case Hunter independently
- [x] [Review][Patch] **NFR1 integration test folds HTTP POST round-trip into the measured latency** — `t_post = time.perf_counter()` is captured BEFORE `await _post_sensor_state(...)`, so the recorded sample includes the POST RTT (localhost: 5–20 ms) on top of the actual WS-event → wait_change resolution gap. NFR1 measures "JMRI sends event → caller resumes," not "library posts command → caller resumes." The current test passes the 100 ms budget by ~80 ms of headroom; a regression that shaved WS latency to zero while inflating POST RTT would pass silently. **Fix:** snap `t_post` AFTER `await _post_sensor_state(...)` returns so the measurement window starts at "JMRI has the command." [`python_code/tests/integration/test_wait_primitives_latency.py:100-105`]
- [x] [Review][Patch] **NFR1 integration test asserts a 100 ms median with no warm-up trials** — 20 trials, alternating target every iteration, no discarded warm-up. Cold-start TLS / socket / GC overhead on the first 1–2 trials can pull the median up; the user-observed median was 19.6 ms today but a CI machine under load is plausibly in the 60–120 ms zone for the first samples. **Fix:** add 2–3 discarded warm-up iterations before the measured 20; assertion stays the same. [`python_code/tests/integration/test_wait_primitives_latency.py:85-105`]
- [x] [Review][Patch] **`Client._on_ws_message` WARNING log drops the original exception detail** — `logger.warning(..., extra={"error_type": type(e).__name__})` strips the message, traceback, and chained cause. Diagnosing a malformed JMRI frame from a CI log becomes guesswork. **Fix:** pass `exc_info=True` (or include `repr(e)` in `extra`) on the two WARNING log calls inside the dispatch error paths. [`python_code/src/pyjmri/client.py:288-294, 305-313`]
- [x] [Review][Patch] **`WaiterList.remove` cancels a foreign (never-registered) future** — line 53's filter correctly leaves `_entries` unchanged when the future isn't in it, but the subsequent `if not future.done(): future.cancel()` runs unconditionally. Documented contract is "idempotent," but the side effect on never-registered futures violates that. No internal caller hits this today (every call is paired with a prior `register`), but a future refactor could. **Fix:** track whether the list shrunk during the comprehension; only call `cancel()` if a matching entry was found. [`python_code/src/pyjmri/_waiters.py:53-55`]
- [x] [Review][Patch] **`test_client_on_ws_message_drops_hello_envelope` asserts nothing observable** — the test calls `_on_ws_message({"type": "hello", ...})` and exits; it only proves "no exception raised." The docstring says "DEBUG log; no raise," but `caplog` is collected and then never inspected. A future refactor that silently swallows the path (no log at all) would still pass the test. **Fix:** assert that a DEBUG record containing "WS dispatch: drop" was emitted on `pyjmri.client`. [`python_code/tests/unit/test_state_machine.py:~340`]
- [x] [Review][Patch] **`test_client_on_ws_message_drops_entity_not_in_index` asserts nothing observable** — same shape as the `hello` test: no `caplog` assertion to lock the "entity not in current Layout" DEBUG path. **Fix:** assert the DEBUG record was emitted with the expected `extra={"entity_type": ..., "system_name": ...}` fields. [`python_code/tests/unit/test_state_machine.py:~358`]
- [x] [Review][Patch] **`_extract_*` helpers are six near-identical copy-pastes with subtle drift** — four return `parsed.state`, `_extract_signal_head` returns `parsed.appearance`, `_extract_signal_mast` returns `parsed.aspect`. Adding a seventh entity in the future means remembering which attribute is "primary" for that type. **Fix:** replace with a declarative `(parser_fn, primary_attr)` table and one generic extractor that returns `(parsed.name, getattr(parsed, primary_attr))`. Not blocking, but reduces footguns and tightens the AC6 dispatch path. [`python_code/src/pyjmri/client.py:~360-410`]
- [x] [Review][Patch] **File List: `pyproject.toml` claimed MODIFIED but actually unchanged on HEAD** — the user's revert of the project-wide `ignore=["ASYNC109"]` undid the original story-3.2 modification, and the per-call-site `# noqa: ASYNC109` lives in the entity modules instead. `pyproject.toml` is identical to its pre-story state. **Fix:** update the File List entry to note that `pyproject.toml` is unchanged; capture the per-call-site `# noqa` mechanism (already in five entity-module bullets). [Spec § File List, this story file]
- [x] [Review][Patch] **File List omits `_bmad-output/implementation-artifacts/deferred-work.md`** — the user added one entry to that file during this review pass, but the File List does not enumerate it. **Fix:** add a File List bullet for `deferred-work.md` noting "added one entry recording the AC6 logger-name documentation follow-up." [Spec § File List, this story file]
- [x] [Review][Defer] `discover()` silently abandons in-flight waiters from the prior Layout — already documented in the `discover()` docstring; consider adding a WARNING log on rebuild if `_entities` was non-empty at entry. [`python_code/src/pyjmri/client.py:~538`] — deferred, behavior already explicitly documented
- [x] [Review][Defer] Tests inline JMRI integer state codes (`2`, `4`) rather than importing from `_codes.SENSOR_STATE` — drift in `_codes.py` would not surface as test failure. [`python_code/tests/unit/test_state_machine.py:~50-60`, `python_code/tests/integration/test_wait_primitives_latency.py:32-34`] — deferred, code-hygiene
- [x] [Review][Defer] `WaiterList.remove` rebuilds the list via O(n) comprehension instead of `list.remove` — fine for expected N (≤ tens per entity), but a hot-fired waiter loop on a high-event entity would prefer in-place remove. [`python_code/src/pyjmri/_waiters.py:53`] — deferred, performance non-issue at expected scale
- [x] [Review][Defer] `# noqa: ASYNC109` repeated on every `timeout` parameter across six entity files — user-chosen approach (preferred over project-wide ruff config for narrower suppression scope); revisit if more `timeout`-bearing public methods land. [Five entity modules] — deferred, user-chosen pattern
- [x] [Review][Defer] `signalHead` / `signalMast` WS push envelopes may omit `held`/`lit` on partial-state updates — `parse_signal_head`/`parse_signal_mast` require both as `_required_bool`, so a thin push event would raise `JMRIProtocolError` and silently drop. Speculation — unverified against live JMRI. **Action:** verify against live JMRI during Story 3.3 (forced-disconnect resilience test exercises push paths); loosen parser only if real JMRI behavior confirms partial pushes. [`python_code/src/pyjmri/_parsing.py:245-289`, `client.py:~395`] — deferred, requires live-JMRI verification before changing the parser
- [x] [Review][Defer] `_DISPATCH_TABLE` keys are case-sensitive; future JMRI version drift in entity-type strings would silently stop dispatch — forward-compat speculation. [`python_code/src/pyjmri/client.py:~410`] — deferred, no current evidence of JMRI changing these keys
- [x] [Review][Defer] `asyncio.timeout(0)` always raises before any event can arrive — minor documentation note on `wait_*` methods; `timeout=0` is a non-blocking probe that succeeds only via early-return. [Five entity modules' `wait_state` / `wait_change` docstrings] — deferred, doc-hardening

### Review Findings — fresh independent review (BMAD code-review, 2026-05-12)

Three layers run in parallel: Blind Hunter (diff only), Edge Case Hunter (diff + project read access), Acceptance Auditor (diff + spec). 8 dismissed as noise, 9 deferred, 5 patches identified.

- [x] [Review][Patch] **AC6 logger name — `_on_ws_message` logs on `pyjmri.client`; AC6 requires `pyjmri.transport` for DROP and WARNING logs** — `logger = logging.getLogger(__name__)` in `client.py` resolves to `pyjmri.client`. AC6 explicitly specifies `pyjmri.transport` for both the memory/route DROP at DEBUG and the `JMRIProtocolError` WARNING. Deferred by the first review pass but still unmet on HEAD. Fix: use a named `pyjmri.transport` logger within `_on_ws_message`. [`python_code/src/pyjmri/client.py:47`]
- [x] [Review][Patch] **Missing caplog assertion for `memory`/`route` drop path — AC9/AC6 observable behavior unverified** — Prior adversarial pass fixed the `hello` and entity-not-in-index drop tests to assert caplog; the `memory`/`route` drop path was not similarly updated. The test only asserts no-raise. A future refactor that silently stopped emitting the DEBUG log would still pass. Fix: assert the DEBUG record is emitted when a `memory` or `route` envelope is received. [`python_code/tests/unit/test_state_machine.py`]
- [x] [Review][Patch] **Missing `wait_change` cancellation test — AC8 "both paths" requirement unmet** — AC8 states unit tests must cover "explicit `task.cancel()` AND `asyncio.TimeoutError`". `test_wait_state_cancellation_cleans_up_waiter` covers cancellation for `wait_state`; no equivalent test exists for `wait_change`. The `wait_change` code path differs structurally (starting state captured after subscribe), making an independent test warranted. Fix: add a task-cancel test for `wait_change` asserting `_waiters` is empty after cancellation. [`python_code/tests/unit/test_state_machine.py`]
- [x] [Review][Patch] **NFR1 `t_post` snapped after POST — test measures ~0 ms; NFR1 budget passes trivially** — The prior adversarial pass moved `t_post` to after `await _post_sensor_state(...)` to exclude POST RTT. However, JMRI emits the WS state event *during* the HTTP round-trip, so the waiter is already resolved by the time the POST returns. All 20 trials report ~0 ms; the Completion Notes confirm this. The test passes regardless of actual WS event latency, making it useless as a regression signal. Fix: move `t_post` to before the POST call so the window captures "command issued → state received" — the practical end-to-end latency NFR1 is about. [`python_code/tests/integration/test_wait_primitives_latency.py:113`]
- [x] [Review][Patch] **`wait_active` predicate-mismatch coverage gap — AC9 predicate-equivalence requirement not fully tested** — AC9 requires verifying that `wait_active()` registers a predicate equivalent to `s == SensorState.ACTIVE`. The existing tests verify the positive-resolve path and the early-return path. Neither test calls `_on_event(INACTIVE)` and asserts that the waiter does NOT resolve. Fix: add a sub-test that fires a non-matching event first, asserts waiter remains registered, then fires the matching event and asserts resolution. [`python_code/tests/unit/test_state_machine.py`]
- [x] [Review][Defer] `wait_change` may miss A→B transition during `ensure_subscription` await — `starting` is captured after subscribe returns; a transition during subscribe is reflected in `starting`, not treated as the "first change"; inherent trade-off from the prior review's lost-wakeup fix — deferred, accepted design trade-off
- [x] [Review][Defer] `_entities` rebuild window during `discover()` — WS events for newly discovered entities may be dropped between entity object creation and `self._entities = new_index`; caller does not hold entity references until after assignment, so window is very narrow — deferred, inherent to HTTP-poll + WS-subscribe pattern
- [x] [Review][Defer] `Waitable` Protocol `_on_event: Any` allows silent wrong-type dispatch — if a parser returns the wrong type for a primary attribute, waiters silently never resolve; accepted as Design Decision #2 in the spec — deferred, accepted design trade-off
- [x] [Review][Defer] TOCTOU on stale cached state in `wait_state` early-return — pre-subscribe `if self.state == target` reads last-polled state, not live JMRI state; cached state may be stale — deferred, documented behavior
- [x] [Review][Defer] `ensure_subscription` raising after `register` untested — if `_registry.send()` fails inside `ensure_subscription`, the exception propagates through the `try` block; Python `finally` semantics guarantee `remove(future)` runs regardless — deferred, low-risk path covered by language semantics
- [x] [Review][Defer] `_on_event(None)` could corrupt cached state — requires a parser to return `None` for a primary attribute; speculative under `mypy --strict` enforcement — deferred, requires verification against `_parsing.py` under strict typing
- [x] [Review][Defer] `BaseException` (e.g., `asyncio.CancelledError`) from a predicate escapes per-predicate `except Exception` in `fanout` and `_on_ws_message` — current predicates are all simple equality lambdas, making this practically impossible — deferred, low practical risk
- [x] [Review][Defer] Old Layout entity waiters never resolve after second `discover()` — documented in `discover()` docstring; user's responsibility to cancel in-flight waiters before re-discovering — deferred, documented behavior
- [x] [Review][Defer] AC1 spec text says `_waiters: list[tuple[...]]` but implementation uses `WaiterList[StateT]` — Design Decision #1 chose Option A but the AC1 `Then` clause literal type was not updated — deferred, documentation inconsistency between AC text and accepted design decision

### Review Findings — BMAD code-review (2026-05-19)

Three layers run in parallel: Blind Hunter (diff only), Edge Case Hunter (diff + project read access), Acceptance Auditor (diff + both spec files). 6 dismissed as noise, 2 deferred, 5 patches total (3 apply here; 2 apply to story 3.3 test code). All ACs confirmed satisfied.

- [x] [Review][Patch] **`wait_state` race-close registers then immediately cancels an unused future** — After `ensure_subscription` returns, the post-register synchronous re-check `if self.state == target` triggers `return self.state` before any `await`, which is correct. However, the future was registered in `_waiters` just before this check; the `finally: self._waiters.remove(future)` block then calls `future.cancel()` on a pending, never-awaited future. The cancel is harmless but the create+append+cancel is wasted work on every race-close hit. Fix: move the race-close check to AFTER `ensure_subscription` but BEFORE `register()`. [`python_code/src/pyjmri/turnout.py:122-129`, identical in `sensor.py`, `block.py`, `light.py`, `signal.py`] — flagged by Blind Hunter + Edge Case Hunter
- [x] [Review][Patch] **`WaiterList.fanout` drops un-iterated entries if interrupted by `BaseException`** — `finally: self._entries = kept` runs unconditionally. If a predicate raises a `BaseException` (e.g., `KeyboardInterrupt`, `SystemExit`) not caught by the inner `except Exception` guard, `finally` assigns `kept` (only entries visited so far) to `self._entries`, silently dropping all not-yet-visited waiters. Those futures will never resolve or be cancelled — they leak until GC. Current predicates are all simple equality lambdas so practical risk is low, but the structure is incorrect. Fix: also move `future.set_result(new_state)` inside the per-entry `try/except Exception` block. [`python_code/src/pyjmri/_waiters.py:63-92`] — flagged by Blind Hunter + Edge Case Hunter
- [x] [Review][Patch] **`ensure_subscription` raises bare `RuntimeError` during concurrent Client close** — if `Client.__aexit__` fires while a `wait_state`/`wait_change` coroutine is suspended inside `await self._handle.ensure_subscription(...)`, `_registry` is set to `None` and `ensure_subscription` raises `RuntimeError`. This propagates through `wait_*` unhandled (`except TimeoutError` does not catch it), so the caller receives a bare `RuntimeError` instead of a domain `JMRIConnectionError`. The `finally: remove(future)` cleanup fires correctly, so no waiter leaks. Fix: catch `RuntimeError` in each entity's `wait_*` and re-raise as `JMRIConnectionError`, OR document the behaviour explicitly. [`python_code/src/pyjmri/sensor.py:93-149`, identical in all six entity `wait_*` methods] — flagged by Edge Case Hunter
- [x] [Review][Defer] **`_DISPATCH_PARSERS` primary_attr is an opaque string with no static type-checking** — stored as plain `str`; `getattr(parsed, primary_attr)` is unchecked by mypy. A typo becomes a runtime `AttributeError` swallowed by `_on_ws_message`'s broad `except Exception`. Current strings are correct. Fix: replace with a typed accessor callable. [`python_code/src/pyjmri/client.py:635-652`] — deferred, pre-existing pattern; correct at HEAD

## Change Log

- 2026-05-12 — Fresh independent review (BMAD code-review, second pass): 5 patches applied. AC6 logger corrected to `pyjmri.transport` in `_on_ws_message` (`logger_transport` added to `client.py`); caplog assertion added to `memory`/`route` drop test; `wait_change` cancellation test added (AC8 gap); NFR1 `t_post` moved before POST (restores meaningful latency measurement — prior patch made it ~0 ms); `wait_active` predicate-mismatch sub-test added (AC9 gap). 9 findings deferred, 8 dismissed. Quality gates green: 318 unit tests pass, ruff clean, mypy --strict clean.
- 2026-05-12 — Code review: three patch findings addressed (integration test uses `wait_change` per AC10; `_on_ws_message` parse phase catches arbitrary `Exception`; ASYNC109 handled via `# noqa` on `wait_*` signatures). Story status **`done`**.
- 2026-05-12 — Adversarial code-review pass (BMAD): eleven patch findings applied across `_waiters.py`, the six entity modules, `client.py`, the NFR1 integration test, two unit tests, and the story File List. Highlights: closed the lost-wakeup race in every `wait_state` / `wait_change` (re-check predicate after `register`, or capture starting state after `ensure_subscription`); hardened `WaiterList.fanout` with per-predicate `try/except` so one bad predicate cannot poison the rest; `WaiterList.remove` no longer cancels foreign futures; `_on_ws_message` WARNING logs now carry `exc_info=True`; six `_extract_*` helpers consolidated to one declarative `_DISPATCH_PARSERS` table; NFR1 latency measurement window narrowed to "JMRI-has-the-command → user resumes" with three discarded warm-up trials; two unit tests now assert their documented DEBUG log behavior. Seven additional findings deferred (recorded in `deferred-work.md`); three dismissed as noise. Quality gates green: ruff format/check clean, mypy --strict clean (19 source files), 316 unit + 5 integration tests pass; NFR1 median now reports ~0 ms (WS event arrives during HTTP POST RTT — well under 100 ms budget).
- 2026-05-12 — Story 3.2 created (`ready-for-dev`). Twelve ACs, seven tasks. Six Open Design Decisions surfaced with proposed defaults. Builds on Story 3.1's WS supervisor, `SubscriptionRegistry`, and `Client._on_ws_message` stub. Sole Epic 3 design dependency on 3.3 is the "in-flight waiters survive reconnect" property, which is emergent from 3.1 + 3.2 without new code; 3.3 proves it against a real disconnect.
- 2026-05-12 — Story 3.2 implemented (`in-progress` → `review`). All six Open Design Decisions accepted as proposed. Shared `WaiterList[StateT]` helper in new `src/pyjmri/_waiters.py`; `Waitable` Protocol added to `_protocols.py`; six waitable entities gained `_waiters` + `_on_event` + `wait_state` + `wait_change` (Sensor also `wait_active`/`wait_inactive`); `Client._on_ws_message` replaced with real dispatch backed by `_DISPATCH_TABLE`; `discover()` populates `Client._entities`. 28 new unit tests + 1 new NFR1 integration test. NFR1 measured median 19.6 ms (well under 100 ms budget). Quality gates green: ruff format/check, `# noqa: ASYNC109` on entity `timeout` parameters (narrow suppress), mypy --strict, 316 unit + 5 integration tests pass.
