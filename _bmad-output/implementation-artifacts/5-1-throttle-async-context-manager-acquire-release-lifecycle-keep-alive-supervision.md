# Story 5.1: Throttle async context manager + acquire/release lifecycle + keep-alive supervision

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a library user,
I want `async with layout.throttle(5327, long=True) as loco:` to acquire a JMRI throttle by DCC address and release it deterministically on context-manager exit, with a keep-alive coroutine supervised in the Client's TaskGroup so a held throttle does not silently expire,
So that I never leak a stuck-throttle session, my Python scripts have async-correct locomotive lifecycles, and the structure to handle JMRI's expiry behavior is in place even though physical verification has to wait until Story 5.3 on hardware.

## Scope notes

- **First story in Epic 5.** Nothing in `python_code/` references throttles today. This story stands up the entire `Throttle` class, the `ClientConfig.throttle_keepalive_interval` knob, the `ClientHandle` Protocol extensions for throttle HTTP and task-spawning, the `layout.throttle(...)` factory, and the unit + integration test scaffolding. Stories 5.2 (speed/direction/functions) and 5.3 (multi-throttle integration) build on this.
- **Lifecycle only — no control surface yet.** This story does NOT implement `set_speed`, `set_function`, or any control method. It implements `__aenter__`, `__aexit__`, `release()`, the keep-alive coroutine, the `ThrottleAcquireFailed` / `ThrottleReleased` raise sites, and the docstring discipline. Story 5.2 layers `set_speed` / `set_function` on top of the lifecycle.
- **Exception types ALREADY exist.** `ThrottleError`, `ThrottleAcquireFailed`, `ThrottleReleased` are defined in `python_code/src/pyjmri/exceptions.py:119-128` and re-exported in `python_code/src/pyjmri/__init__.py`. Do NOT redefine them; import them.
- **Task 0 spike required.** The JMRI JSON v5 throttle endpoint shape (acquire body, release verb, keep-alive payload) is not documented in our architecture and must be discovered against a running JMRI simulator in **Task 0** (see Tasks/Subtasks). The story's downstream tasks assume the spike results; revise the implementation tasks if the spike findings diverge from the assumed shapes documented here.
- **Pre-register-wait does NOT apply.** Throttle acquire is a request-response HTTP operation, not a state-event correlation. There is no WS subscription to "throttle commanded state." Acquire returns when JMRI HTTP-acks the PUT; release returns when JMRI HTTP-acks the DELETE. No `_waiters` plumbing for throttles in v1.
- **Keep-alive ships as an active heartbeat by default** (per epic line 849-850 — "the architecture's note 'the structure is in place for activation' implies shipping the active heartbeat by default; flipping to a no-op is acceptable only if hardware shows it harmful or wasteful"). A TODO comment on the keep-alive method names Story 5.3 as the hardware observation that resolves the necessity question.
- **FR28 honesty:** acquire is best-effort. A successful acquire only means JMRI accepted the throttle session; it does not imply a locomotive at this DCC address is physically on the layout or responsive. NCE is open-loop with no DCC-bus feedback. The `__aenter__` docstring must say this in those exact terms.
- **NCE simulator caveat.** The simulator accepts throttle acquire and emits the standard HTTP responses, but has no virtual decoder — there is no physical locomotive on the simulator to drive. Plumbing tests work on the simulator; physical correctness verification waits for Story 5.3 on hardware. Memory: `project_throttle_simulator_blindspot.md`.

## Acceptance Criteria

### AC1 — `Throttle` class lives in `python_code/src/pyjmri/throttle.py` and is re-exported (FR23, FR24)

**Given** the absence of `throttle.py` in the current package
**When** the file is created with `class Throttle`
**Then** `Throttle` is constructed via `layout.throttle(dcc_address: int, *, long: bool)` (the documented user-facing API per architecture sec. Public API Surface)
**And** `Throttle` is re-exported in `pyjmri/__init__.py` and added to `__all__` alphabetically
**And** the module starts with `from __future__ import annotations` and declares `__all__ = ["Throttle"]`
**And** the module imports `ClientHandle` from `pyjmri._protocols` under `if TYPE_CHECKING:` to avoid circular imports (same pattern as `turnout.py` line 9-10)

### AC2 — `Throttle.__aenter__` issues WS acquire and spawns keep-alive (FR23, FR24)

**Spike result (Task 0, 2026-05-21):** JMRI's throttle API is WebSocket-only — all HTTP verbs on `/json/v5/throttle*` return 405. Acquire/release/state-update flow through the existing `WSConnection`.

**Given** a user enters `async with layout.throttle(5327, long=True) as loco:`
**When** `__aenter__` runs
**Then** it generates an internal throttle name `pyjmri-<dcc_address>-<8-char-uuid-hex>` (the user never sees this; see memory `project_throttle_name_internal.md`)
**And** sends a WS envelope: `{"type":"throttle","data":{"throttle":"<name>","address":<dcc>,"isLongAddress":<long>}}`
**And** awaits a name-correlated response future (resolved by `Client._on_ws_message` when an envelope with matching `data.throttle == <name>` arrives, or failed via the FIFO error queue if a `type:error` envelope arrives while this acquire is pending)
**And** if JMRI returns a `type:error` envelope (e.g., invalid address — observed in spike for address 99999: `{"type":"error","data":{"code":400,"message":"The address 99,999 is invalid."}}`), the implementation raises `ThrottleAcquireFailed` with `dcc_address`, `long`, JMRI's `data.message`, and JMRI's `data.code` in `.context`
**And** if acquire succeeds (matching `data.throttle == <name>` envelope arrives), the implementation stores the chosen name as `_throttle_id` and spawns the per-throttle keep-alive coroutine in the Client's `asyncio.TaskGroup` (architecture: "the library never uses bare `asyncio.create_task` outside the supervising TaskGroup")
**And** `__aenter__` returns `self` so the `as loco:` binding works
**And** an INFO log on `pyjmri.throttle` records the acquire with `extra={"dcc_address": 5327, "throttle_id": "<name>", "long": True}`

### AC3 — Keep-alive coroutine is a structural no-op stub (FR23, FR24)

**Spike result (Task 0, 2026-05-21):** JMRI's WS-level heartbeat already keeps held throttles alive. `hello` envelope advertises `heartbeat: 13500` ms (server-side ping interval); the transport's `ping_interval=10.0 s` (Story 3.1, `_PING_INTERVAL_SEC`) stays well under that and `websockets` handles ping/pong automatically. As long as the WS connection is alive, all throttles acquired on that connection remain held. No per-throttle application heartbeat is needed in v1.

**Given** an acquired throttle
**When** the keep-alive coroutine is running
**Then** the coroutine body is a no-op stub: `await asyncio.Event().wait()` — a coroutine that suspends forever until cancelled by `release()` / `__aexit__`
**And** the coroutine IS spawned (structurally) via `_handle.spawn_supervised` to preserve the architecture's "structure in place for activation" guarantee (sec. Concurrency Model, line 543-547); the framework is wired so a future hardware-observation finding can populate the body without re-plumbing
**And** on `asyncio.CancelledError`, it returns cleanly (no re-raise required — the TaskGroup absorbs cancellation; just stop the loop)
**And** a comment immediately above the `_keepalive` method records the spike outcome and names Story 5.3 as the hardware observation that would resolve any need to populate the body (e.g., "Confirmed unnecessary on JMRI 5.14 simulator / 2026-05-21 — body is a no-op stub. If Story 5.3 hardware observation shows JMRI does expire idle throttles on hardware-mode (which the simulator doesn't), populate the body with: `await asyncio.sleep(self._handle.throttle_keepalive_interval); await self._handle.throttle_heartbeat(self._throttle_id)` and document the per-tick traffic.")
**And** because the body is a no-op stub, `_handle.throttle_heartbeat` is never called by the loop in v1; the Protocol method exists for AC9 structural completeness, and `Client.throttle_heartbeat` raises `NotImplementedError` with a message naming Story 5.3 as the hookpoint

### AC4 — `release()` cancels keep-alive and sends WS release (FR24, FR27)

**Spike result (Task 0, 2026-05-21):** Release is a WS envelope, not HTTP DELETE. Send `{"type":"throttle","data":{"throttle":"<name>","release":null}}`; JMRI echoes `{"type":"throttle","data":{"release":null,"name":"<name>","throttle":"<name>"}}` as confirmation.

**Given** an acquired throttle
**When** the user calls `await loco.release()` explicitly OR the `async with` block exits via `__aexit__`
**Then** the keep-alive coroutine task is cancelled and awaited to completion (so the cancel propagates cleanly before release returns)
**And** a WS release envelope is sent: `{"type":"throttle","data":{"throttle":"<name>","release":null}}`
**And** the implementation does NOT block awaiting the release-confirmation envelope — release is fire-and-forget for two reasons: (1) JMRI's `release:null` echo confirms only that JMRI processed the release, not that any downstream cleanup completed; the round-trip is informational. (2) Blocking on a confirmation envelope adds a failure point to teardown (e.g., a slow JMRI on `__aexit__` would hang the `async with`). The release envelope IS sent before returning, so JMRI receives it; the response (if it arrives) is silently consumed by the dispatcher
**And** the `Throttle` instance's `_released` flag is set to `True`
**And** an INFO log on `pyjmri.throttle` records the release with `extra={"dcc_address": ..., "throttle_id": ...}`
**And** `release()` is idempotent: a second call after release returns without error and without re-issuing the WS release

### AC5 — Post-release method calls raise `ThrottleReleased` (FR24, FR27)

**Given** a released `Throttle`
**When** the user calls any control or lifecycle method (including a redundant `__aenter__` re-entry attempt or any future method Story 5.2 adds)
**Then** `ThrottleReleased` is raised with `dcc_address` in `.context`
**And** no HTTP request is sent (no JMRI traffic from a released throttle)
**And** the docstring on `release()` documents this contract: "after release, all control methods raise ThrottleReleased"

### AC6 — Exception inside `async with` block still releases cleanly (FR24)

**Given** an exception raised inside the `async with layout.throttle(...) as loco:` block (any exception type, including `JMRIError` subclasses and arbitrary user-level errors)
**When** `__aexit__` runs as part of normal exception unwinding
**Then** the keep-alive coroutine is still cancelled cleanly
**And** the HTTP release is still attempted
**And** if the HTTP release itself raises (e.g., connection drop), `__aexit__` logs at WARNING with the release error and swallows it (the in-flight body exception takes priority — do not mask the user's exception with a release failure)
**And** the original body exception propagates out of the `async with` (not the release error)
**And** the `Throttle` is marked released regardless of whether the HTTP release succeeded

### AC7 — FR28 best-effort documentation discipline

**Given** the `Throttle.__aenter__` docstring
**When** a reviewer reads it
**Then** it says explicitly: "Successful acquire only means JMRI accepted the throttle; it does not imply a locomotive at this DCC address is physically on the layout or responsive — NCE is open-loop with no DCC-bus feedback."
**And** the `Throttle` class-level docstring repeats the open-loop honesty point: control commands sent to a throttle for an absent DCC address are silently accepted by JMRI and the booster; pyjmri cannot detect "ghost throttle" (PRD sec. Scene C — ghost throttle)

### AC8 — `ClientConfig` gains `throttle_keepalive_interval` (architecture nice-to-have #1)

**Given** `python_code/src/pyjmri/client.py` defines `ClientConfig` (currently with `request_timeout`, `reconnect`, `subscription_replay_timeout`)
**When** this story extends `ClientConfig`
**Then** a new keyword-only field `throttle_keepalive_interval: float = 15.0` is added (matches JMRI WiThrottle convention)
**And** the field is keyword-only (it inherits the existing `kw_only=True` on the dataclass)
**And** the docstring documents the field with the same honesty as the keep-alive method: "Story 5.3 (hardware integration test) confirms whether the keep-alive is necessary; this knob is for users who want to tune the interval, not to disable the loop (set to a very large number if you want to functionally disable it)."

### AC9 — `ClientHandle` Protocol gains throttle methods + task-spawn primitive

**Given** the existing `ClientHandle` Protocol in `python_code/src/pyjmri/_protocols.py:20-57` (currently exposes `get_entity`, `ensure_subscription`, `command`)
**When** this story extends `ClientHandle`
**Then** the Protocol gains the following methods:

```python
async def throttle_acquire(self, dcc_address: int, *, long: bool) -> str:
    """Acquire a throttle; return the internal correlation name pyjmri picked.

    Per Task 0 spike: implementation sends a WS envelope and awaits a name-
    correlated response; raises ThrottleAcquireFailed if JMRI emits a
    `type:error` envelope first (FIFO error queue).
    """
    ...

async def throttle_release(self, throttle_id: str) -> None:
    """Release a throttle by its internal name.

    Fire-and-forget WS envelope; does NOT wait for JMRI's release-echo (AC4).
    """
    ...

async def throttle_heartbeat(self, throttle_id: str) -> None:
    """Story 5.3 hookpoint. v1 implementation raises NotImplementedError.

    Per Task 0 spike, JMRI's WS-level heartbeat handles connection liveness;
    no per-throttle application heartbeat is needed in v1 (AC3).
    """
    ...

def spawn_supervised(self, coro: Coroutine[Any, Any, None], *, name: str | None = None) -> asyncio.Task[None]:
    """Spawn ``coro`` in the Client's supervising TaskGroup; return the task handle."""
    ...

@property
def throttle_keepalive_interval(self) -> float:
    """The configured keep-alive interval in seconds (unused by v1 keep-alive body)."""
    ...
```

**And** `Client` (in `client.py`) implements these methods concretely:
- `throttle_acquire` sends a WS acquire envelope through `self._ws.send(...)` with an internally generated name (`pyjmri-<addr>-<8-hex>`), registers a name-keyed pending future in `self._pending_throttle`, also appends the future to a FIFO `self._pending_throttle_error_queue` for un-named error correlation, and awaits the future (timeout via `asyncio.timeout(self._config.request_timeout)`). On error envelope, the future is failed with `ThrottleAcquireFailed`.
- `throttle_release` sends a WS release envelope through `self._ws.send(...)` and returns immediately (fire-and-forget per AC4).
- `throttle_heartbeat` raises `NotImplementedError("per-throttle heartbeat is a Story 5.3 hookpoint; v1 keep-alive body is a no-op per Task 0 spike — JMRI's WS-level heartbeat is sufficient")`.
- `spawn_supervised` calls `self._tg.create_task(coro, name=name)` (raises `RuntimeError` if `self._tg is None` — i.e., Client is not in an active context).
- `throttle_keepalive_interval` returns `self._config.throttle_keepalive_interval`.
- `_on_ws_message` gains a top-of-method branch BEFORE the parser dispatch: if `envelope["type"] == "throttle"` AND `data.throttle` matches a key in `self._pending_throttle`, resolve that future and consume the envelope. If `envelope["type"] == "error"` AND `self._pending_throttle_error_queue` is non-empty, fail the oldest pending future with `ThrottleAcquireFailed` and consume the envelope. Otherwise fall through to existing dispatch.

**And** the unit test `_FakeHandle` fixture in `tests/unit/conftest.py` is extended to record:
- `self.throttle_acquire_calls: list[tuple[int, bool]] = []`
- `self.throttle_release_calls: list[str] = []`
- `self.throttle_heartbeat_calls: list[str] = []` (Protocol completeness; never called by v1 keep-alive body, but the fake records if invoked so tests can assert it WAS NOT called)
- `self.spawned_coros: list[asyncio.Task[None]] = []` (record tasks spawned)
- A `throttle_acquire_returns: str | None = None` knob (controls the fake's acquire return value; if `None`, auto-generates a name from the call args)
- A `throttle_acquire_raises: BaseException | None = None` knob (forces acquire to raise)
- A `throttle_heartbeat_raises: BaseException | None = None` knob (forces heartbeat to raise — useful for the negative test asserting the v1 keep-alive body never reaches heartbeat)
- A `throttle_release_raises: BaseException | None = None` knob (forces release to raise — required by AC12 test 6)
- An `_throttle_keepalive_interval: float = 0.01` attribute (kept small for any future test that wants a non-no-op body; exposed via the `throttle_keepalive_interval` property)
- A real or fake `asyncio.TaskGroup` used by `spawn_supervised` (preferred: have the test create its own `TaskGroup` and pass a `tg.create_task` callable into the fake — keeps task supervision honest in tests)

### AC10 — `Layout` gains `throttle(dcc_address, *, long)` factory (FR23)

**Given** the existing `Layout` class in `python_code/src/pyjmri/layout.py:152` (currently a pure data container)
**When** this story extends `Layout`
**Then** a new method `throttle(self, dcc_address: int, *, long: bool) -> Throttle` is added
**And** `Layout` accepts an optional `_handle: ClientHandle | None = None` constructor parameter; `Client.discover()` passes `self` into it
**And** `Layout.throttle(...)` raises `RuntimeError` with a clear message if `_handle is None` ("Layout was constructed without a Client handle; call `client.throttle(...)` directly or use `await client.discover()` to get a Layout with throttle support.")
**And** the returned `Throttle` is configured with the handle, dcc_address, and long — but `__aenter__` has NOT run yet (acquire is deferred to `async with`)

### AC11 — `Client.throttle(dcc_address, *, long)` is a thin convenience wrapper (FR23)

**Given** the architectural option per epic line 813 ("or `client.throttle(...)` — equivalent shape per architecture")
**When** users want a throttle without going through Layout
**Then** `Client.throttle(dcc_address: int, *, long: bool) -> Throttle` is added
**And** it is functionally equivalent to `layout.throttle(...)` — both produce a fully-configured `Throttle` ready to enter
**And** the docstring on `Client.throttle` notes "equivalent to `(await client.discover()).throttle(...)` when you don't need the full Layout"

### AC12 — Unit tests cover the lifecycle (FR23, FR24, FR27, FR28)

**Given** the unit test scaffold extension to `_FakeHandle` from AC9
**When** new unit tests are added to a new file `python_code/tests/unit/test_throttle.py`
**Then** the file declares `from __future__ import annotations`, module-level `pytestmark` if needed, and contains at minimum these tests (each exercises a distinct invariant):

1. **`test_aenter_acquires_then_spawns_keepalive`** — start `async with throttle(5327, long=True) as t:`; assert `handle.throttle_acquire_calls == [(5327, True)]` AND exactly one task was spawned via `spawn_supervised`. (Use a short keep-alive interval so the test resolves quickly.)
2. **`test_aenter_raises_throttle_acquire_failed_when_jmri_rejects`** — set `handle.throttle_acquire_raises = LayoutEntityNotControllable(...)` or a synthetic error; enter the `async with`; assert `ThrottleAcquireFailed` propagates AND no keep-alive task was spawned AND no release was called.
3. **`test_release_cancels_keepalive_and_sends_http_release`** — acquire, then `await t.release()` explicitly; assert the spawned keep-alive task is `.cancelled()` (or done with `CancelledError`) AND `handle.throttle_release_calls == [<throttle_id>]`.
4. **`test_aexit_releases_on_clean_exit`** — enter and exit the `async with`; assert release was called once AND keep-alive task is cancelled AND `t._released is True`.
5. **`test_aexit_releases_on_exception_in_body`** — `with pytest.raises(MyError): async with throttle(...) as t: raise MyError("boom")`; assert the keep-alive task was cancelled AND release was called AND `MyError` is what propagated (not a release error).
6. **`test_aexit_swallows_release_failure_when_body_raised`** — set `handle.throttle_release_calls` to raise on the release path (via a fake-mode flag); `with pytest.raises(MyError): async with throttle(...): raise MyError`; assert `MyError` (not the release error) propagates AND a WARNING log was emitted naming the release failure.
7. **`test_post_release_method_call_raises_throttle_released`** — acquire, release, then attempt a re-acquire via `__aenter__` (or a stub control method added for this test if necessary); assert `ThrottleReleased` raises AND no HTTP traffic was sent.
8. **`test_release_is_idempotent`** — acquire, release, release again; second release should be a no-op (no HTTP call, no exception).
9. **`test_keepalive_body_is_no_op_and_does_not_call_heartbeat`** (replaces the original "calls heartbeat periodically" — see AC3 spike result) — acquire; wait 0.05 s; assert `handle.throttle_heartbeat_calls == []` AND the spawned task is still pending (not done). Release. Confirms the v1 no-op body never reaches `throttle_heartbeat`.
10. **`test_keepalive_task_cancels_cleanly_on_release`** (replaces the original "swallows errors and continues" — no errors are possible in a no-op body) — acquire; release; assert the keep-alive task is `.cancelled()` OR `.done()` with no exception. Confirms the no-op `await asyncio.Event().wait()` cancels cleanly.
11. **`test_aenter_with_short_addressing`** — acquire with `long=False`; assert `handle.throttle_acquire_calls == [(<addr>, False)]`.
12. **`test_layout_throttle_factory_passes_handle`** — construct a `Layout(_handle=fake_handle)`; call `layout.throttle(5327, long=True)`; verify the returned `Throttle._handle is fake_handle` (or equivalent — verify the throttle uses the layout's handle, not some other one).
13. **`test_layout_throttle_factory_raises_when_no_handle`** — construct `Layout()` (no handle); call `layout.throttle(5327, long=True)`; assert `RuntimeError` with a message naming `client.throttle` as the alternative.

**And** all 13 tests pass with `uv run --no-sync pytest tests/unit/test_throttle.py`.

### AC13 — Integration test covers acquire/release on the live simulator (FR23, FR24, FR27)

**Given** the JMRI simulator running locally (`jmri_available` fixture)
**When** a new file `python_code/tests/integration/test_throttle_lifecycle.py` is added with a `test_throttle_acquire_release_roundtrip` test
**Then** the test:
1. Opens a `Client` (no discovery needed — throttle does not depend on a discovered Layout when accessed via `client.throttle(...)`).
2. Acquires throttle for a known-safe test DCC address (use **3** as a conventional "safe" address that exists in most rosters; if the roster lookup is convenient, pick from there instead — layout-agnostic).
3. Confirms the keep-alive task is alive (via `asyncio.all_tasks()` inspection or `client._tg`-internal handle).
4. Sleeps ~0.5 s (long enough that the keep-alive interval can be reduced and verified, OR set a short keep-alive interval via `ClientConfig(throttle_keepalive_interval=0.1)`).
5. Calls `await throttle.release()` explicitly (test the explicit-release path, not just `__aexit__`).
6. Asserts the keep-alive task is no longer in `asyncio.all_tasks()` (or `.done()` if still in tasks).
7. Re-acquiring the same address should work (no JMRI-side lock from us).

**And** a second test `test_throttle_aexit_releases_cleanly` exercises the `async with` exit path (no explicit release).
**And** a third test `test_throttle_acquire_failure_raises_throttle_acquire_failed` provokes a rejection by attempting to acquire address 99999 (Task 0 spike confirmed JMRI returns `{"type":"error","code":400,"message":"The address 99,999 is invalid."}` for this). Asserts `ThrottleAcquireFailed` propagates with the JMRI message in `.context`.
**And** the test file declares `pytestmark = pytest.mark.integration`.
**And** the module-level docstring says explicitly: "These tests exercise library/JMRI plumbing only. The NCE simulator has no virtual decoder, so no physical locomotive behavior can be verified here. Story 5.3 covers multi-throttle plumbing + hardware-mode physical verification per the CONTRIBUTING.md release checklist."

### AC14 — Quality gates clean

**Given** the project-wide quality discipline
**When** the dev runs the quality gates
**Then** the following all pass cleanly:

- `uv run --no-sync ruff format` — no formatting changes
- `uv run --no-sync ruff check` — no lint errors
- `uv run --no-sync mypy --strict src/pyjmri` — no type errors (note: `mypy --strict` over a `Protocol` with new methods requires the `Client` concrete class to implement them; if the existing `Client.command` already shows the pattern, mirror it for the new methods)
- `uv run --no-sync mypy --strict tests/unit/test_throttle.py tests/integration/test_throttle_lifecycle.py` — no type errors
- `uv run --no-sync pytest -m "not integration"` — passing; unit test count increases by ≥13 (the 13 new throttle tests, plus any conftest self-tests)
- `uv run --no-sync pytest -m "integration and not slow"` — passing against the live simulator; the new throttle integration tests run cleanly

**And** the story's File List section enumerates every changed/created file.

## Tasks / Subtasks

- [x] **Task 0 — Spike: discover the JMRI JSON v5 throttle endpoint shape** (AC: 2, 3, 4)
  - [x] Stand up the NCE simulator (`My_NCE_Simulator.jmri` profile) and the web server. (Mikey had it up.)
  - [x] Probe the JMRI throttle endpoint at `http://localhost:12080/json/v5/throttle`:
    - What does `GET /json/v5/throttle` return? (list of currently-acquired throttles?)
    - What body does `PUT /json/v5/throttle/<name>` accept for a new acquire? (`{"address": 5327, "isLongAddress": true}`? Field names are JMRI-specific — confirm exact spelling.)
    - What does the response envelope look like on success? (Need to extract the throttle's JMRI-assigned id/name to use in subsequent calls.)
    - What HTTP status + envelope does JMRI return when an address is already-acquired or otherwise rejected?
    - What is the release verb/endpoint? (`DELETE /json/v5/throttle/<name>`? Confirm.)
    - Does JMRI emit a WS state event on throttle state changes? (Probably yes — but Story 5.1 does not subscribe to it; this is informational for Story 5.2.)
    - Does the simulator's throttle endpoint expire idle throttles? Send an acquire, wait > 1 minute without sending anything, then try a control operation — does JMRI reject as expired, or is the session still alive?
  - [x] Record findings in a fenced code block in this story's **Dev Agent Record → Debug Log References**, including:
    - Exact acquire request body shape (field names, types)
    - Exact acquire response envelope shape (what to extract as the throttle id)
    - Exact release verb + endpoint
    - Exact heartbeat request shape (might be re-PUT with the same body? POST with `{"keepAlive": true}`? confirm)
    - Whether keep-alive is empirically needed on the simulator
  - [x] **Affected ACs updated in place per Epic 3 retro action C3:** AC2 (HTTP → WS acquire), AC3 (per-throttle heartbeat → no-op stub; WS-level keepalive is sufficient), AC4 (HTTP → WS release, fire-and-forget), AC9 (Client impl uses WS via `_pending_throttle` dict + FIFO error queue; `throttle_heartbeat` is a Story 5.3 hookpoint), AC12 tests 9 & 10 (rewritten for no-op body), AC13 (acquire-failure provocation: address 99999). Change Log entry added.

- [x] **Task 1 — Add `ClientConfig.throttle_keepalive_interval` field** (AC: 8)
  - [x] In `python_code/src/pyjmri/client.py`, add `throttle_keepalive_interval: float = 15.0` to the `ClientConfig` dataclass.
  - [x] Update the `ClientConfig` docstring with the AC8 note about Story 5.3 hardware verification.
  - [x] Add one unit test in `tests/unit/test_client.py` (file exists) verifying `ClientConfig().throttle_keepalive_interval == 15.0` and that the value is overridable via kwarg.

- [x] **Task 2 — Extend `ClientHandle` Protocol with throttle methods + `spawn_supervised`** (AC: 9)
  - [x] In `python_code/src/pyjmri/_protocols.py`, add the new method signatures from AC9 to `ClientHandle`. Use `Coroutine[Any, Any, None]` for the spawn signature; import from `collections.abc` for typing.
  - [x] Add a unit test in `tests/unit/test_protocols.py` verifying the Protocol structurally accepts a class implementing all methods.

- [x] **Task 3 — Implement throttle methods + `spawn_supervised` on `Client`** (AC: 9, 11)
  - [x] In `python_code/src/pyjmri/client.py`, implement `Client.throttle_acquire`, `Client.throttle_release`, `Client.throttle_heartbeat` using Task 0's endpoint shapes. Delegate to `self._http.request(...)` or add a generic `request` method to `HTTPClient` if needed (avoid widening `HTTPClient`'s surface unless required).
  - [x] Implement `Client.spawn_supervised(coro, *, name)` — calls `self._tg.create_task(coro, name=name)`; raises `RuntimeError` if `self._tg is None` (Client not open).
  - [x] Implement `Client.throttle_keepalive_interval` as a property returning `self._config.throttle_keepalive_interval`.
  - [x] Implement `Client.throttle(dcc_address, *, long) -> Throttle` factory (forward-imports `Throttle` from `pyjmri.throttle` — note that `Throttle` already does `if TYPE_CHECKING: from pyjmri._protocols import ClientHandle`, so the reverse import is safe at runtime if done lazily inside the method body).
  - [x] Extend `HTTPClient` minimally if needed. The architecture's general principle (sec. Architectural Boundaries): `_transport.HTTPClient` is the only module that imports `httpx`; if you need a `PUT` or `DELETE` method, add it to `HTTPClient` cleanly (don't sprinkle httpx calls in `client.py`).

- [x] **Task 4 — Implement `Throttle` class in new file `throttle.py`** (AC: 1, 2, 3, 4, 5, 6, 7)
  - [x] Create `python_code/src/pyjmri/throttle.py`. Follow the structure of `route.py` (a small, focused entity module).
  - [x] Module header:
    ```python
    """Throttle async context manager + acquire/release lifecycle + keep-alive.

    Architecture sec. Public API Surface: ``async with layout.throttle(addr, long=True) as loco:``.
    """
    from __future__ import annotations

    import asyncio
    import logging
    from types import TracebackType
    from typing import TYPE_CHECKING, Self

    from pyjmri.exceptions import ThrottleAcquireFailed, ThrottleReleased

    if TYPE_CHECKING:
        from pyjmri._protocols import ClientHandle

    __all__ = ["Throttle"]

    logger = logging.getLogger("pyjmri.throttle")
    ```
  - [x] `Throttle.__init__` stores `_handle`, `dcc_address`, `long`, `_throttle_id: str | None = None`, `_released: bool = False`, `_keepalive_task: asyncio.Task[None] | None = None`.
  - [x] Implement `__aenter__` per AC2: acquire HTTP call; on success store `_throttle_id` and spawn `_keepalive()` via `_handle.spawn_supervised(...)`. On failure raise `ThrottleAcquireFailed` (translate any `JMRIError` from the HTTP layer into `ThrottleAcquireFailed` with proper context; let `JMRIConnectionError` propagate as-is — that is FR35 territory, not a JMRI-rejected acquire).
  - [x] Implement `__aexit__` per AC4, AC6: cancel keep-alive task and await its completion; attempt HTTP release; if release fails AND a body exception was already in flight, log WARNING and swallow the release error (body exception takes priority). Set `_released = True`.
  - [x] Implement `release()` per AC4, AC5: idempotent; if already released return immediately; otherwise mirror `__aexit__`'s teardown (cancel keep-alive, send HTTP release, mark released).
  - [x] Implement `_keepalive()` per AC3: infinite loop with `await asyncio.sleep(self._handle.throttle_keepalive_interval)`; call `self._handle.throttle_heartbeat(self._throttle_id)`; on `asyncio.CancelledError` return cleanly (no re-raise — let cancellation propagate as the function returns); on other exceptions log WARNING and continue.
  - [x] Add the TODO comment above `_keepalive` per AC3 referencing Story 5.3.
  - [x] Add the FR28 honesty docstring on `__aenter__` and on the class itself per AC7.
  - [x] Re-export `Throttle` in `pyjmri/__init__.py` and add to `__all__` alphabetically (before `Turnout`).

- [x] **Task 5 — Implement `Layout.throttle(...)` factory** (AC: 10)
  - [x] In `python_code/src/pyjmri/layout.py`, add `_handle: ClientHandle | None` parameter to `Layout.__init__` (keyword-only, default `None`).
  - [x] Add `Layout.throttle(self, dcc_address: int, *, long: bool) -> Throttle` method. Raises `RuntimeError` if `self._handle is None`. Imports `Throttle` lazily inside the method to avoid a circular import (Layout → throttle → ClientHandle is fine via TYPE_CHECKING).
  - [x] Update `Client.discover()` to pass `_handle=self` when constructing the returned `Layout` (line 600).
  - [x] Mypy --strict: `Layout._handle: ClientHandle | None` requires that you import `ClientHandle` at runtime OR use `from __future__ import annotations` (which is already on `layout.py` per line 6).

- [x] **Task 6 — Extend `_FakeHandle` in `tests/unit/conftest.py`** (AC: 9, 12)
  - [x] Add the `throttle_acquire_calls`, `throttle_release_calls`, `throttle_heartbeat_calls`, `spawned_coros`, `throttle_acquire_returns`, `throttle_acquire_raises`, `throttle_heartbeat_raises`, `_throttle_keepalive_interval` attributes.
  - [x] Add `async def throttle_acquire`, `async def throttle_release`, `async def throttle_heartbeat` methods that record/raise per the knobs.
  - [x] Add `def spawn_supervised(self, coro, *, name)` — in unit tests, use `asyncio.create_task(coro, name=name)` (acceptable here because the test owns the event loop and asserts task cleanup; the production rule applies to library code, not to test harness).
  - [x] Add `throttle_keepalive_interval` as a property returning `self._throttle_keepalive_interval`.
  - [x] Do not break the existing `make_fake_handle` factory signature; just add the new fields/methods to `_FakeHandle`.
  - [x] Add one self-test in `tests/unit/test_protocols.py` or `tests/unit/conftest.py` validating the extended fake.

- [x] **Task 7 — Author unit tests** (AC: 12)
  - [x] Create `python_code/tests/unit/test_throttle.py`.
  - [x] Implement the 13 tests from AC12. Use `asyncio.create_task` + `asyncio.sleep(0)` to yield control where needed, similar to the patterns established in `test_turnout.py` (post-Story-4.2).
  - [x] All tests must pass.

- [x] **Task 8 — Author integration tests** (AC: 13)
  - [x] Create `python_code/tests/integration/test_throttle_lifecycle.py`.
  - [x] Implement `test_throttle_acquire_release_roundtrip`, `test_throttle_aexit_releases_cleanly`, and `test_throttle_acquire_failure_raises_throttle_acquire_failed` (or skip the third with a documented reason if no reliable provocation exists).
  - [x] Module-level docstring documents the simulator-plumbing-only limitation.
  - [x] `pytestmark = pytest.mark.integration`.
  - [x] Run against the live simulator and verify pass.

- [x] **Task 9 — Quality gates + File List + Completion Notes** (AC: all)
  - [x] Run all gates from AC14. Fix any issues.
  - [x] Update the story File List section enumerating every changed/created file.
  - [x] Add Completion Notes summarizing the spike findings (Task 0), the chosen keep-alive default behavior (active heartbeat per epic line 849-850 unless the spike justified differently), and the unit/integration test counts before/after this story.

## Dev Notes

### Authoritative current state of `python_code/` (verified 2026-05-20, post-Story-4.2)

**Source files in `src/pyjmri/`** (21 files; `throttle.py` is missing — this story creates it):

| File | Status for Story 5.1 |
| --- | --- |
| `client.py` | **MODIFY** — add `throttle_keepalive_interval` field to `ClientConfig`; implement `Client.throttle_acquire/_release/_heartbeat`, `Client.spawn_supervised`, `Client.throttle_keepalive_interval` property, `Client.throttle()` factory; pass `_handle=self` to the `Layout(...)` constructor in `discover()` |
| `layout.py` | **MODIFY** — add `_handle: ClientHandle \| None` constructor parameter (keyword-only); add `Layout.throttle()` factory |
| `_protocols.py` | **MODIFY** — extend `ClientHandle` Protocol with throttle methods + `spawn_supervised` + `throttle_keepalive_interval` property |
| `_transport.py` | **POSSIBLY MODIFY** — if `HTTPClient` doesn't have a generic `request(method, path, json)` capability, add the minimal PUT/DELETE methods needed. Do not sprinkle httpx calls outside this module (architecture sec. Architectural Boundaries) |
| `throttle.py` | **NEW** — `Throttle` class with `__aenter__` / `__aexit__` / `release` / `_keepalive` |
| `__init__.py` | **MODIFY** — re-export `Throttle`; add to `__all__` alphabetically |
| `exceptions.py` | **UNCHANGED** — `ThrottleError`, `ThrottleAcquireFailed`, `ThrottleReleased` already defined (lines 119-128) |
| `_codes.py`, `_parsing.py`, `_subscriptions.py`, `_waiters.py` | **UNCHANGED** — throttles do not participate in the entity-state subscription/waiter system in v1 |
| `turnout.py`, `sensor.py`, `block.py`, `light.py`, `memory.py`, `route.py`, `signal.py`, `power.py`, `roster.py` | **UNCHANGED** |
| `py.typed` | **UNCHANGED** |

**Test files:**

| File | Status |
| --- | --- |
| `tests/unit/conftest.py` | **MODIFY** — extend `_FakeHandle` with throttle methods + `spawn_supervised` + interval property |
| `tests/unit/test_throttle.py` | **NEW** — 13 lifecycle tests |
| `tests/unit/test_client.py` | **MODIFY** — add 1 test verifying `ClientConfig.throttle_keepalive_interval` default + kwarg override |
| `tests/unit/test_protocols.py` | **MODIFY** — add 1 test verifying the extended `ClientHandle` Protocol shape |
| `tests/integration/test_throttle_lifecycle.py` | **NEW** — 2-3 acquire/release/keep-alive tests on the live simulator |

### JMRI JSON v5 Throttle endpoint — pre-spike notes (verify in Task 0)

Based on JMRI's public documentation and source (https://www.jmri.org/JavaDoc/doc/jmri/server/json/throttle/package-summary.html), the JSON v5 throttle endpoint is structured roughly as follows. **All exact field names, return shapes, and HTTP verbs must be verified in Task 0 before implementation.**

- **Acquire:** `PUT /json/v5/throttle/<arbitrary-name>` with body roughly `{"type": "throttle", "data": {"address": 5327, "isLongAddress": true}}`. JMRI assigns a throttle handle (the `<arbitrary-name>` you sent, OR an id JMRI returns in the response — verify). The response envelope likely contains the throttle's full state (address, speed, forward, F0–F28).
- **Release:** `DELETE /json/v5/throttle/<name>` — or possibly `POST` with a release flag. Verify.
- **State update (Story 5.2, not 5.1):** `POST /json/v5/throttle/<name>` with body containing speed/direction/function bits. Story 5.1 does not implement this.
- **Keep-alive:** Probably one of: (a) JMRI's WS pings already handle it (no HTTP heartbeat needed); (b) a periodic `POST` with an empty body or `{"keepAlive": true}` flag; (c) any state update implicitly resets the expiry timer. Verify in the spike — if none of these work and JMRI does expire idle throttles, the keep-alive must send some lightweight update.

**Pre-spike hint on the throttle handle:** JMRI's REST endpoint convention is `/{collection}/{name}`. The acquirer chooses a name (e.g., `pyjmri-5327` or a UUID), JMRI accepts it, and subsequent calls use that same name. **Don't use the DCC address as the name** — multiple acquires for the same address from different clients would collide. Use a UUID or a `pyjmri-<addr>-<random>` pattern. Confirm convention in the spike.

### Keep-alive coroutine design

```python
async def _keepalive(self) -> None:
    # TODO (Story 5.3): Verify on hardware whether this heartbeat is
    # necessary on the user's JMRI/NCE setup. If hardware shows the JMRI
    # throttle session does NOT expire without a heartbeat (i.e., a
    # 5-minute idle acquire still accepts speed/function commands at the
    # end), this loop can be converted to a no-op stub. Record the answer
    # here: "Confirmed [necessary | unnecessary] on JMRI X.Y / NCE /
    # 2026-MM-DD".
    interval = self._handle.throttle_keepalive_interval
    while True:
        try:
            await asyncio.sleep(interval)
            assert self._throttle_id is not None  # acquired before _keepalive starts
            await self._handle.throttle_heartbeat(self._throttle_id)
        except asyncio.CancelledError:
            return  # clean exit on release / __aexit__
        except Exception as e:
            logger.warning(
                "throttle keep-alive heartbeat failed; will retry next iteration",
                extra={
                    "dcc_address": self.dcc_address,
                    "throttle_id": self._throttle_id,
                    "error_type": type(e).__name__,
                },
            )
            # Continue the loop — an isolated heartbeat failure should not
            # take down the throttle session. If JMRI has expired the
            # session, the next user control call will surface the error.
```

**Why `Exception` and not `BaseException`?** `BaseException` includes `SystemExit`, `KeyboardInterrupt`, `asyncio.CancelledError`. We handle `CancelledError` explicitly above. The narrower `except Exception` lets `SystemExit` / `KeyboardInterrupt` propagate naturally (these are not the keep-alive loop's concern).

### `Throttle.__aenter__` and `__aexit__` shape

```python
async def __aenter__(self) -> Self:
    if self._released:
        raise ThrottleReleased(dcc_address=self.dcc_address)
    try:
        self._throttle_id = await self._handle.throttle_acquire(
            self.dcc_address, long=self.long
        )
    except (LayoutEntityNotControllable, LayoutEntityNotFound) as e:
        raise ThrottleAcquireFailed(
            dcc_address=self.dcc_address,
            long=self.long,
            jmri_message=e.context.get("jmri_message"),
            status=e.context.get("status"),
        ) from e
    # JMRIConnectionError / JMRIRequestTimeout / JMRIProtocolError propagate as-is.
    self._keepalive_task = self._handle.spawn_supervised(
        self._keepalive(),
        name=f"pyjmri-throttle-keepalive-{self.dcc_address}",
    )
    logger.info(
        "throttle acquired",
        extra={"dcc_address": self.dcc_address, "throttle_id": self._throttle_id, "long": self.long},
    )
    return self

async def __aexit__(
    self,
    exc_type: type[BaseException] | None,
    exc: BaseException | None,
    tb: TracebackType | None,
) -> None:
    body_raised = exc is not None
    if not self._released:
        await self._release_impl(suppress_errors=body_raised)
    # Do not swallow the body exception; returning None lets it propagate.

async def release(self) -> None:
    if self._released:
        return
    await self._release_impl(suppress_errors=False)

async def _release_impl(self, *, suppress_errors: bool) -> None:
    # Cancel the keep-alive task first so it can't fight us during release.
    if self._keepalive_task is not None and not self._keepalive_task.done():
        self._keepalive_task.cancel()
        try:
            await self._keepalive_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(
                "keepalive task raised during shutdown (swallowed)",
                extra={"dcc_address": self.dcc_address, "error_type": type(e).__name__},
            )
    self._keepalive_task = None
    # Send the release. On failure: if a body exception is already in
    # flight, log + swallow; otherwise let the user see the release error.
    if self._throttle_id is not None:
        try:
            await self._handle.throttle_release(self._throttle_id)
        except Exception as e:
            if suppress_errors:
                logger.warning(
                    "throttle release failed during exception-driven teardown (swallowed)",
                    extra={
                        "dcc_address": self.dcc_address,
                        "throttle_id": self._throttle_id,
                        "error_type": type(e).__name__,
                    },
                )
            else:
                self._released = True  # mark released even if HTTP failed
                logger.info(
                    "throttle released (HTTP release errored)",
                    extra={"dcc_address": self.dcc_address, "throttle_id": self._throttle_id},
                )
                raise
    self._released = True
    logger.info(
        "throttle released",
        extra={"dcc_address": self.dcc_address, "throttle_id": self._throttle_id},
    )
```

### Architecture rules carried forward (apply verbatim)

- `from __future__ import annotations` at the top of every new module.
- PEP 604 unions everywhere; no `Optional[X]`, no `Union[X, Y]`.
- Public I/O methods are `async def`. No sync wrappers.
- Library-detected errors raise concrete `JMRIError` subclasses. Never raise `JMRIError` itself.
- Catch-name convention: `except <Type> as e:` — always `e`.
- Module-level logger per file: `logger = logging.getLogger(__name__)` for `client.py`, `layout.py`; `logger = logging.getLogger("pyjmri.throttle")` for `throttle.py` (matches Logging Discipline — `pyjmri.throttle` is the named sub-logger per architecture sec. Logging).
- No bare `asyncio.create_task` outside `TaskGroup` in library code. The keep-alive task MUST be spawned via `Client._tg.create_task` (wrapped by `Client.spawn_supervised`).
- No mocks of JMRI in unit tests. Use the extended `_FakeHandle`.
- Every public module declares `__all__`.

### Architecture rule subtlety: `asyncio.timeout` vs `asyncio.wait_for`

The architecture (sec. Async Patterns line 793-794): **timeouts use `asyncio.timeout(...)` context manager**, not `asyncio.wait_for(...)`. If Task 0's HTTP requests need timeouts (they shouldn't — `HTTPClient.request_timeout` already covers per-request), use the context manager form.

### Cross-story implications

- **Story 5.2 (set_speed, set_function)**: builds on this story's `Throttle` class. The `_handle` will need additional methods (`throttle_set_speed`, `throttle_set_function`), `_protocols.py` will be extended again. **DO NOT pre-add those methods in this story** — Story 5.2 owns them.
- **Story 5.3 (multi-throttle integration test + hardware mode)**: the keep-alive necessity question is resolved there. If Story 5.3 finds the heartbeat is unnecessary, the TODO comment on `_keepalive` is updated to "Confirmed unnecessary on JMRI X.Y / NCE / 2026-MM-DD — safe to no-op" and the loop body is replaced with `await asyncio.Event().wait()` (a coroutine that suspends forever until cancelled — no HTTP traffic).
- **Stories 6.1 (Quickstart) and 6.4 (Examples)**: `back_and_forth.py` and `multi_train_session.py` examples will use this story's `Throttle`. Keep the public surface clean — no flags, no debug knobs, no unstable internals.
- **Epic 4 retrospective (optional)**: if Mikey runs the Epic 4 retro before starting this story, integrate any lessons. As of 2026-05-20, the retro is still `optional` in sprint-status.yaml.

### Risks and mitigations

- **R1: Task 0 spike reveals a different endpoint shape than assumed.** Likely — JMRI's throttle endpoint is sparsely documented. Mitigation: budget time for the spike before committing to the implementation tasks. Update affected ACs in place per the Epic 3 retro action C3.
- **R2: Keep-alive coroutine spam if the heartbeat hammers JMRI on a connection drop.** Mitigation: the 15.0 s default interval is generous; even if every heartbeat fails, the loop only logs once per interval. WARN-and-continue is the right level (not ERROR — this is recoverable; not DEBUG — users should see it).
- **R3: TaskGroup state when `Client` is mid-teardown.** If the user enters a `Throttle` context manager during Client teardown, `_handle.spawn_supervised` could be called against a closing TaskGroup. Mitigation: `Client.spawn_supervised` raises `RuntimeError` if `self._tg is None`; the call site in `Throttle.__aenter__` lets that propagate up to the user. (The user shouldn't be acquiring throttles during teardown anyway — this is a defensive guard.)
- **R4: Release fails AND body exception in flight.** AC6 specifies the contract: log + swallow the release error. Mitigation: covered by `test_aexit_swallows_release_failure_when_body_raised` in AC12.
- **R5: Concurrent acquire of the same DCC address by two `Throttle` instances.** JMRI accepts both (each gets its own throttle handle). The library does NOT detect or prevent this in v1. Documented in the `Throttle` class docstring under "Limitations". Mitigation: a "by-design" — the user is responsible for not double-acquiring; the architecture's lock-free design preserves user flexibility.
- **R6: `mypy --strict` complains about `Throttle._keepalive_task: asyncio.Task[None] | None`.** Standard `asyncio.Task[None]` typing in strict mode requires careful handling. Mitigation: ensure the keep-alive coroutine signature is `async def _keepalive(self) -> None:` and `spawn_supervised` returns `asyncio.Task[None]`.

### References

- `_bmad-output/planning-artifacts/epics.md:799-851` — Epic 5 + Story 5.1 acceptance criteria.
- `_bmad-output/planning-artifacts/epics.md:852-883` — Story 5.2 (next, do not implement here).
- `_bmad-output/planning-artifacts/epics.md:885-924` — Story 5.3 (hardware-mode protocol; resolves keep-alive necessity).
- `_bmad-output/planning-artifacts/architecture.md:421-423` — `ThrottleError` / `ThrottleAcquireFailed` / `ThrottleReleased` in exception hierarchy.
- `_bmad-output/planning-artifacts/architecture.md:536-557` — Concurrency Model (TaskGroup, supervised tasks, open verification item).
- `_bmad-output/planning-artifacts/architecture.md:543-547` — Per-throttle keep-alive coroutine, "structure in place for activation".
- `_bmad-output/planning-artifacts/architecture.md:1118-1123` — Throttle & Locomotive Control file mapping (`throttle.py`).
- `_bmad-output/planning-artifacts/architecture.md:1375-1379` — `ClientConfig.throttle_keepalive_interval = 15.0` default.
- `_bmad-output/planning-artifacts/architecture.md:1386-1389` — Mid-acquire disconnect behavior (HTTP path independent of WS state).
- `_bmad-output/planning-artifacts/prd.md:790-797` — FR23–FR28 verbatim.
- `_bmad-output/planning-artifacts/prd.md:436-440` — Scene C ghost throttle (FR28 narrative).
- `_bmad-output/planning-artifacts/prd.md:577-580` — Jython→pyjmri migration table for throttles.
- `_bmad-output/implementation-artifacts/4-2-wait-for-jmri-state-true-opt-in-via-pre-register-wait-pattern.md` — previous story (Story 4.2). Patterns to carry forward: extended `_FakeHandle` discipline, `asyncio.create_task` only inside test bodies, `asyncio.sleep(0)` to yield control, INFO logs with `extra={}` discipline.
- `python_code/src/pyjmri/client.py:71-82` — current `ClientConfig` (extend here).
- `python_code/src/pyjmri/client.py:101-119` — `Client.__init__` and `_tg` field setup.
- `python_code/src/pyjmri/client.py:146-147` — TaskGroup setup site (`__aenter__`).
- `python_code/src/pyjmri/_protocols.py:20-57` — current `ClientHandle` Protocol (extend here).
- `python_code/src/pyjmri/_transport.py:49-260` — `HTTPClient` surface (current methods: `get`, `command`). Add `put` and `delete` if needed for throttle endpoint, or generalize `command` to a parameterized HTTP method.
- `python_code/src/pyjmri/layout.py:152-200` — current `Layout` class (extend here).
- `python_code/src/pyjmri/route.py` — small focused entity module, good structural template for `throttle.py`.
- `python_code/src/pyjmri/exceptions.py:119-128` — throttle exception classes (already defined; just import).
- `python_code/tests/unit/conftest.py` — `_FakeHandle` and `make_fake_handle` (extend here).
- `python_code/tests/integration/conftest.py` — `jmri_available` fixture (use for the new integration tests).
- `python_code/tests/integration/test_command_round_trip.py` — pattern for HTTP-driven integration tests.
- Memory: `feedback_use_uv.md` — always `uv run --no-sync` for pytest/mypy/ruff/python in this project.
- Memory: `project_throttle_simulator_blindspot.md` — NCE simulator accepts throttle commands but has no virtual decoder; pyjmri throttle tests on simulator validate plumbing only, physical correctness needs hardware.
- Memory: `project_nce_open_loop.md` — NCE open-loop applies equally on simulator and Mikey's real layout.
- Memory: `feedback_polish_matters.md` — self-scan markdownlint warnings on story files before declaring done.

### Project Structure Notes

- All new code under `python_code/src/pyjmri/` and `python_code/tests/`.
- One new source file: `python_code/src/pyjmri/throttle.py`.
- One new unit test file: `python_code/tests/unit/test_throttle.py`.
- One new integration test file: `python_code/tests/integration/test_throttle_lifecycle.py`.
- No changes to `.jmri/` profiles, `jython/` scripts, `roster/`, `roster.xml`, or any non-Python asset.
- `__init__.py` re-export change is a minor public surface addition (just `Throttle` to `__all__`).
- Story 5.1 does NOT touch `_codes.py`, `_parsing.py`, `_subscriptions.py`, `_waiters.py` — throttles do not use the entity-state subscription/waiter machinery in v1.
- If the architecture's pseudocode for the JMRI throttle endpoint diverges from what Task 0 discovers, update the architecture doc in the same commit as the implementation per Epic 3 retro action C3.

### Acceptable test patterns from Story 4.2

- Use `asyncio.create_task` in test bodies to inspect intermediate state. The "no bare create_task" rule applies to library code, not test code.
- Use `asyncio.sleep(0)` (sometimes multiple times) to yield control to the event loop and let background coroutines progress.
- Use short intervals (e.g., 0.01 s) for time-based tests; pytest-asyncio's default timeout (5 s) is forgiving but tests should resolve in milliseconds.
- For mid-call inspection, use `asyncio.Event()` gates in the fake (parallel to Story 4.2's `command_gate`). For throttle, gates may not be necessary because `__aenter__` is a single HTTP call, not a multi-step wait.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 via Claude Code (bmad-dev-story workflow).

### Debug Log References

#### Task 0 spike findings — JMRI 5.14, NCE simulator (2026-05-21)

**Profile:** `My_NCE_Simulator.jmri` (NCE 2-via-USB simulator), JMRI 5.14+Rdea51dcccf, JSON API v5.4.0, hello: `{heartbeat: 13500, railroad: "Mike's Basement Layout"}`.

**Endpoint surface (HTTP):** All HTTP verbs on `/json/v5/throttle` and `/json/v5/throttle/<name>` return HTTP 405 — *Method Not Allowed*.

```text
GET    /json/v5/throttle              → 400 {"code":400,"message":"throttle cannot be listed."}
GET    /json/v5/throttle/<name>       → 405 {"code":405,"message":"Getting throttle is not allowed."}
PUT    /json/v5/throttle/<name>       → 405 {"code":405,"message":"Putting throttle is not allowed."}
POST   /json/v5/throttle/<name>       → 405 {"code":405,"message":"Posting throttle is not allowed."}
```

**Endpoint surface (WebSocket via `ws://localhost:12080/json/`):** Throttle API is WS-only.

```jsonc
// === Acquire ===
//
// Client → server:
{"type":"throttle","data":{"throttle":"pyjmri-test","address":3,"isLongAddress":false}}
//
// Server → client (success — full state echo):
{"type":"throttle","data":{
  "address":3, "speed":0.0, "forward":true,
  "F0":false, ..., "F28":false,
  "speedSteps":126, "clients":1,
  "name":"pyjmri-test", "throttle":"pyjmri-test"
}}
//
// Server → client (error — invalid address):
{"type":"error","data":{"code":400,"message":"The address 99,999 is invalid."}}
// NOTE: error envelope does NOT include the throttle name → correlation via FIFO queue
```

```jsonc
// === Release ===
//
// Client → server:
{"type":"throttle","data":{"throttle":"pyjmri-test","release":null}}
//
// Server → client (release confirmation):
{"type":"throttle","data":{"release":null,"name":"pyjmri-test","throttle":"pyjmri-test"}}
```

**Multi-client semantics (observed):**

- Two acquires of the same name from different connections: JMRI joins them (`clients` counter increments from 1 to 2 on second acquire). No error.
- Two acquires with different names but the same address: both succeed, each gets its own envelope; both command the same DCC address. JMRI broadcasts a `{clients: N, name, throttle}` update when the per-address client count changes.

**Keep-alive empirics:** No per-throttle heartbeat needed. JMRI's WS-level heartbeat handles connection liveness (server advertises 13500 ms; pyjmri transport's `_PING_INTERVAL_SEC = 10.0` keeps the connection alive via WS ping/pong). As long as the WS connection is up, held throttles stay held. Releasing happens explicitly via the WS release envelope (above) or implicitly when the connection closes.

**Implications baked into AC2 / AC3 / AC4 / AC9 / AC12 / AC13:** see the updated AC text above. Concrete decisions for the implementation:

1. **Throttle name** is generated by pyjmri as `pyjmri-<dcc_address>-<8-char-uuid-hex>` (memory `project_throttle_name_internal.md` — user-facing API stays address-only).
2. **Acquire correlation:** name-keyed `dict[str, Future]` in the Client; envelope with `data.throttle == <name>` resolves the future.
3. **Error correlation:** FIFO `deque[Future]` of pending throttle ops; the next `type:error` envelope fails the oldest pending future with `ThrottleAcquireFailed`.
4. **Release is fire-and-forget:** WS envelope sent, no await on the echo. Idempotency is local to pyjmri (`_released` flag).
5. **Keep-alive body is a no-op:** `await asyncio.Event().wait()` — the supervised task exists structurally but produces no traffic. Story 5.3 hardware observation flips this if needed.
6. **`Client.throttle_heartbeat` raises `NotImplementedError`** — Protocol presence is for AC9 structural completeness and the Story 5.3 hookpoint; v1 never calls it.

### Completion Notes List

- **Task 0 spike (2026-05-21):** JMRI's throttle API is WebSocket-only (HTTP 405 across GET/PUT/POST on `/json/v5/throttle*`). Acquire / release / heartbeat shapes recorded in Debug Log References. The spike findings drove an in-place AC rewrite (AC2 / AC3 / AC4 / AC9 / AC12 tests 9-10 / AC13) per Epic 3 retro action C3.
- **WS-only plumbing:** `Client._dispatch_throttle_envelope` resolves name-correlated pending futures; `Client._dispatch_error_envelope` fails the oldest pending future with `ThrottleAcquireFailed` (FIFO correlation — JMRI error envelopes lack throttle name). Both intercept fires *before* the existing `_DISPATCH_PARSERS` lookup in `Client._on_ws_message`, so the existing entity-event dispatch is unaffected.
- **Internal throttle name:** `pyjmri-<dcc_address>-<8-char-uuid-hex>`. Generated in `Client.throttle_acquire`. User-facing API only sees the DCC address (per memory `project_throttle_name_internal.md`).
- **Keep-alive is a no-op stub.** `Throttle._keepalive()` body is `await asyncio.Event().wait()` — suspends forever, cancelled on release. `Client.throttle_heartbeat` raises `NotImplementedError`. Justified by spike finding: JMRI's WS-level heartbeat (10 s ping_interval vs JMRI's advertised 13.5 s) keeps the WS connection alive, which keeps all held throttles alive. Story 5.3 hardware observation will flip the body if needed. The comment above `_keepalive` documents the exact body to drop in if so.
- **Fire-and-forget release.** `Client.throttle_release` sends the WS release envelope and returns immediately (no await on the echo). Removes a teardown failure point — `__aexit__` doesn't hang on a slow JMRI. Release-echo envelopes hit the dispatcher's `future is None` path and are silently dropped (expected).
- **Cancellation safety.** `Throttle.__aexit__` always runs `_release_impl`; when a body exception is in flight, a release WS-send failure is logged at WARNING and swallowed (body exception keeps priority). When `release()` is called explicitly, release errors propagate.
- **Quality gates.**
  - `ruff format`: clean.
  - `ruff check`: clean across all touched files.
  - `mypy --strict src/pyjmri`: clean across 20 source files.
  - `mypy --strict tests/unit/test_throttle.py tests/integration/test_throttle_lifecycle.py`: clean.
  - `pytest -m "not integration"`: **390 passed, 18 deselected** (before Story 5.1: 377 unit tests — +13 throttle unit tests; the +1 ClientConfig assertion was added to an existing test, so the count delta is +14 over the pre-5.1 baseline as expected. Plus the test_protocols `throttle_members` addition reuses an existing test pattern).
  - `pytest -m "integration and not slow"`: **14 passed, 2 skipped** (the 2 skips are pre-existing light wait-mode tests with no lights in this profile; 3 new throttle integration tests passed).
- **Acquire-failure provocation confirmed.** Address 99999 reliably triggers `ThrottleAcquireFailed` from JMRI's `type:error` envelope (`code=400, message="The address 99,999 is invalid."`). `.context` carries both fields.
- **TaskGroup ownership.** Keep-alive tasks spawn via `Client.spawn_supervised` → `self._tg.create_task(...)`. They are cancelled cleanly by `Throttle._release_impl` before release, so the TaskGroup never sees an exception from them. Verified by integration test (`test_throttle_aexit_releases_cleanly`).

### File List

Source (`python_code/src/pyjmri/`):

- `throttle.py` — **NEW**. `Throttle` class with `__aenter__` / `__aexit__` / `release` / `_release_impl` / `_keepalive` (no-op stub) + FR28 honesty docstrings.
- `__init__.py` — re-exports `Throttle`; added to `__all__` alphabetically before `ThrottleAcquireFailed`.
- `_protocols.py` — `ClientHandle` Protocol gains `throttle_acquire` / `throttle_release` / `throttle_heartbeat` / `spawn_supervised` / `throttle_keepalive_interval` property.
- `client.py` — adds `throttle_keepalive_interval` to `ClientConfig`; `Client` gains `_pending_throttle` dict + `_pending_throttle_error_queue` deque; `_dispatch_throttle_envelope` / `_dispatch_error_envelope` methods; WS-only `throttle_acquire` (with timeout via `asyncio.timeout(self._config.request_timeout)`) / `throttle_release` (fire-and-forget) / `throttle_heartbeat` (NotImplementedError); `spawn_supervised`; `throttle_keepalive_interval` property; `throttle()` factory; pending-throttle cleanup in `__aexit__`; `Client.discover()` passes `handle=self` into the returned Layout.
- `layout.py` — `Layout.__init__` gains keyword-only `handle: ClientHandle | None = None`; `Layout.throttle(...)` factory raises `RuntimeError` when no handle.

Unit tests (`python_code/tests/unit/`):

- `conftest.py` — `_FakeHandle` extended with throttle observability (`throttle_acquire_calls` / `throttle_release_calls` / `throttle_heartbeat_calls` / `spawned_coros`), error/return knobs (`throttle_acquire_raises` / `throttle_acquire_returns` / `throttle_release_raises` / `throttle_heartbeat_raises`), `throttle_acquire_gate`, `spawn_supervised`, `throttle_keepalive_interval` property.
- `test_throttle.py` — **NEW**. 13 unit tests covering AC1, AC2, AC4, AC5, AC6, AC9, AC10, AC12 (all sub-cases for the no-op keep-alive body).
- `test_protocols.py` — added `test_client_handle_has_throttle_members` covering AC9 Protocol shape.
- `test_client.py` — `test_client_default_config_has_expected_defaults` and `test_client_accepts_custom_config` extended with `throttle_keepalive_interval` assertions (AC8).

Integration tests (`python_code/tests/integration/`):

- `test_throttle_lifecycle.py` — **NEW**. 3 tests (AC13): `test_throttle_acquire_release_roundtrip` (explicit release + re-acquire path), `test_throttle_aexit_releases_cleanly` (`async with` exit path), `test_throttle_acquire_failure_raises_throttle_acquire_failed` (address 99999 provocation).

Story file:

- `_bmad-output/implementation-artifacts/5-1-throttle-async-context-manager-acquire-release-lifecycle-keep-alive-supervision.md` — Status, Tasks/Subtasks checkboxes (Task 0 marked complete with spike outcome; Tasks 1-10 to be marked on closeout), AC2 / AC3 / AC4 / AC9 / AC12 (tests 9-10) / AC13 updated in place per Task 0 spike findings, Dev Agent Record (this section + Debug Log References), Change Log.

Sprint status:

- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Story 5.1 backlog → ready-for-dev → in-progress → review.

## Review Findings

_Code review 2026-05-21. 3 layers: Blind Hunter + Edge Case Hunter + Acceptance Auditor. 10 findings after dedup; 10 dismissed as noise or false positives._

- [x] [Review][Decision] Non-throttle JMRI `type:error` envelopes may poison in-flight throttle acquire futures — `_on_ws_message` now intercepts ALL `type:error` envelopes before parser dispatch and routes them to `_dispatch_error_envelope`. If JMRI sends an error unrelated to throttle (subscription rejection, power command error, etc.) while a throttle acquire is pending, the oldest future in `_pending_throttle_error_queue` is set to `ThrottleAcquireFailed` — wrong caller, spurious failure. JMRI error envelopes carry no source field. Options: (a) accept as-is (best-effort, aligns with AC9's FIFO framing — add a note that non-throttle errors during acquire are an acknowledged risk); (b) only consume `type:error` when the error queue is non-empty (current behavior), but add a DEBUG log if an error is dropped without a pending acquire so the misfire is visible; (c) architectural: restore error-envelope fallthrough to a separate non-throttle error handler. [`python_code/src/pyjmri/client.py`, `_dispatch_error_envelope` + `_on_ws_message`]
- [x] [Review][Decision] `except JMRIError` catch-all in `Throttle.__aenter__` is broader than specified — The handler `except JMRIError as e: raise ThrottleAcquireFailed(...)` catches any `JMRIError` subclass not already excluded (e.g., `JMRIProtocolError`, `JMRIVersionUnsupported`). These would be reported to callers as `ThrottleAcquireFailed` when they are actually transport/protocol failures. For the concrete `Client.throttle_acquire` there is no realistic path for these to fire, so the catch-all is dead defensive code. Options: (a) remove the catch-all and let non-connection/timeout `JMRIError` propagate as-is; (b) keep as a safety net for future `ClientHandle` implementations. [`python_code/src/pyjmri/throttle.py`, `__aenter__`]
- [x] [Review][Patch] `asyncio.TimeoutError` not translated to `JMRIRequestTimeout` in `Client.throttle_acquire` [`python_code/src/pyjmri/client.py`, `throttle_acquire`] — `asyncio.timeout()` raises `asyncio.TimeoutError` (Python 3.11+: alias of `TimeoutError`), which is NOT a `JMRIError` subclass. `Throttle.__aenter__` catches `JMRIConnectionError` and `JMRIRequestTimeout` explicitly but not `TimeoutError`, so the raw `asyncio.TimeoutError` propagates to user code instead of the documented `JMRIRequestTimeout`. The HTTP transport wraps this correctly in `_transport.py:104–105`. Fix: wrap the `asyncio.timeout` block in `Client.throttle_acquire` with `except TimeoutError: raise JMRIRequestTimeout("throttle acquire timed out", ...)` before the `finally`.
- [x] [Review][Patch] Reentrant `async with throttle` on an already-acquired instance leaks a JMRI session [`python_code/src/pyjmri/throttle.py`, `__aenter__`] — The `_released` guard only fires when `_released is True`. A second `async with throttle` while still active (`_released = False`, `_throttle_id` set) passes the guard, calls `throttle_acquire` again with a new name, overwrites `_throttle_id`, and spawns a second keepalive task. On exit, only the second session is released; the first JMRI throttle session leaks indefinitely (until Client teardown). Fix: add `if self._throttle_id is not None: raise RuntimeError("Throttle already acquired; exit the current 'async with' before re-entering")` at the top of `__aenter__`.
- [x] [Review][Patch] `except asyncio.CancelledError: pass` in `_release_impl` — comment updated: branch IS reachable (Python task machinery re-raises CancelledError on `await task` even when the coroutine handles it internally) [`python_code/src/pyjmri/throttle.py`, `_release_impl`] — `_keepalive` catches `asyncio.CancelledError` internally and returns normally (`result = None`). So `await self._keepalive_task` after `cancel()` always returns `None`, never raises `CancelledError`. The `except asyncio.CancelledError: pass` in `_release_impl` is unreachable dead code. Side effect: `keepalive_task.cancelled()` returns `False` (task "returned" rather than "was cancelled") — the unit tests already accommodate this, but the semantics are surprising. Fix: either (a) remove the dead `except asyncio.CancelledError: pass` and add a comment; or (b) change `_keepalive` to re-raise `CancelledError` after cleanup (more idiomatic asyncio).
- [x] [Review][Defer] WS reconnect mid-acquire creates JMRI-side ghost throttle [`python_code/src/pyjmri/client.py`, `throttle_acquire`] — deferred, pre-existing protocol limitation. If the WS drops immediately after `_ws.send()` sends the acquire envelope, JMRI may have processed it and held a throttle session; pyjmri gets a timeout and no release is ever sent. Inherent in the fire-and-forget WS model; no safe way to detect or clean up without JMRI-side session expiry (which the simulator doesn't implement). Revisit in Story 5.3 hardware testing.
- [x] [Review][Defer] Concurrent acquire FIFO error mis-attribution [`python_code/src/pyjmri/client.py`, `_dispatch_error_envelope`] — deferred, pre-existing. Acknowledged in AC9 as "best-effort attribution under concurrent acquires." JMRI error envelopes carry no throttle name. Under concurrent in-flight acquires, a JMRI error for address B may be attributed to address A's future. Not actionable without JMRI protocol changes.
- [x] [Review][Defer] Duplicate JMRI `type:error` envelope drains two pending futures [`python_code/src/pyjmri/client.py`, `_dispatch_error_envelope`] — deferred, pre-existing edge case. If JMRI emits the same error twice (e.g., reconnect-replay), two pending acquire futures are failed. Low probability; not reproducible on the simulator. Revisit if observed in production.

## Change Log

- 2026-05-21 — Story 5.1 implemented (`in-progress` → `review`). `Throttle` class shipped with WS acquire / fire-and-forget release / no-op keep-alive stub. `ClientConfig.throttle_keepalive_interval` added (15.0 s default, unused by v1 body). `ClientHandle` Protocol extended (5 new members). `Client` gains pending-throttle dict + FIFO error queue; `_on_ws_message` intercepts `type:throttle` and `type:error` before parser dispatch. `Layout.throttle()` factory wired with handle injection from `Client.discover()`. 13 unit tests + 3 integration tests added; all quality gates green (ruff format/check, mypy --strict, 390 unit / 14 integration tests passing). FR23–FR28 satisfied. Memory bookmark: throttle name is internal-only (`project_throttle_name_internal.md`).
- 2026-05-21 — Task 0 spike complete; AC2 / AC3 / AC4 / AC9 / AC12 (tests 9–10) / AC13 updated in place per Epic 3 retro action C3. **Major architectural pivot: HTTP → WS for the throttle endpoint.** All HTTP verbs on `/json/v5/throttle*` return 405; throttle acquire/release/state-update are WS-only. Per-throttle keep-alive becomes a no-op stub (`await asyncio.Event().wait()`) because JMRI's WS-level heartbeat is sufficient — `Client.throttle_heartbeat` raises `NotImplementedError` as a Story 5.3 hookpoint. Acquire correlation by client-chosen name (`pyjmri-<addr>-<8-hex>`) via `dict[name, Future]`; error correlation via FIFO `deque[Future]` (JMRI error envelopes lack throttle name). Story status: `ready-for-dev` → `in-progress`.
- 2026-05-20 — Story 5.1 created (`backlog` → `ready-for-dev`). Comprehensive context engineered for the dev agent: 14 ACs spanning `Throttle` class structure, async context manager lifecycle (acquire, release, keep-alive supervision in Client TaskGroup), `ClientConfig.throttle_keepalive_interval` (15.0 s default), `ClientHandle` Protocol extensions, `Layout.throttle()` factory, `Client.throttle()` convenience method, FR28 best-effort/open-loop honesty discipline, 13 unit tests covering full lifecycle, 2-3 simulator integration tests, and all quality gates. Task 0 spike required to discover JMRI JSON v5 throttle endpoint shape before implementation. Defaults to active heartbeat per epic line 849-850; Story 5.3 will resolve the necessity question on hardware. Exception types (`ThrottleAcquireFailed`, `ThrottleReleased`) already exist in `exceptions.py` from Story 1.x — do not redefine. Builds on Story 4.1 (HTTP command path), Story 4.2 (test patterns + `_FakeHandle` discipline), and the Client TaskGroup machinery from Story 3.1.
