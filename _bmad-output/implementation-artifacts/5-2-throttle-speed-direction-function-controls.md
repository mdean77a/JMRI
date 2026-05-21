# Story 5.2: Throttle speed/direction/function controls

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a library user,
I want `await loco.set_speed(0.4, forward=True)` and `await loco.set_function(2, True)` to drive a held `Throttle` with input-validated, fire-and-forget WS updates,
So that I can write the locomotive-control core of any automation script in straightforward Python — speed and direction in one call, function bits one at a time — without my script blocking on JMRI confirmation envelopes that wouldn't be authoritative anyway (NCE is open-loop).

## Scope notes

- **Second story in Epic 5.** Story 5.1 stood up the `Throttle` async context manager, the `ClientHandle` throttle methods (acquire, release, heartbeat, spawn_supervised), the `Layout.throttle()` factory, and the `_FakeHandle` extensions. This story layers `set_speed` and `set_function` onto that lifecycle. Story 5.3 (multi-throttle integration test + hardware-mode protocol) closes the epic.
- **Control surface only — no lifecycle changes.** This story does NOT touch `__aenter__`, `__aexit__`, `release()`, the keep-alive coroutine, or the FIFO error queue. It adds two new public methods to `Throttle` plus one new method on `ClientHandle`.
- **WebSocket transport (not HTTP).** Story 5.1's Task 0 spike (2026-05-21) found JMRI's throttle endpoint is WS-only — HTTP verbs on `/json/v5/throttle*` return 405. State updates (this story) use the same WS connection. The epic AC text says "HTTP" — that wording predates the spike; AC2 in this story corrects it.
- **Fire-and-forget semantics.** `set_speed` / `set_function` send a WS envelope through `WSConnection.send(...)` and return when the bytes are written to the socket. They do NOT await JMRI's state-echo envelope. Rationale (mirrors Story 5.1 AC4 for release): (1) waiting for the echo adds a teardown failure point with no information gain — JMRI's echo confirms only that JMRI processed the update; it cannot confirm the locomotive actually moved (NCE is open-loop); (2) consistency with `throttle_release`'s fire-and-forget shape; (3) keeps the user's control loop tight under slow JMRI conditions.
- **`async def` is mandatory.** Per architecture sec. Async Patterns line 794 ("Public I/O methods are `async def`. No sync wrappers."), both `set_speed` and `set_function` are `async def`; users must `await` them. The PRD's Scene B example (`loco.set_speed(0.4, forward=True)` with no `await`) is illustrative shorthand and is corrected to `await loco.set_speed(...)` once example scripts ship in Story 6.4 — not in this story.
- **Exception types ALREADY exist.** `ThrottleReleased` (raised on post-release method calls) is defined in `python_code/src/pyjmri/exceptions.py:127-128`. Do NOT redefine; import.
- **Mini-spike required (Task 0).** Story 5.1's spike enumerated the acquire / release envelopes but did NOT exercise state-update envelopes. The exact field names for client→server speed/direction/function updates need confirmation. Pre-spike hypothesis (based on JMRI's acquire echo, which uses `speed` / `forward` / `F0`...`F28` field names per Story 5.1 spike findings): the update envelope mirrors the echo. Task 0 confirms before AC2 / AC3 / AC8 are implemented.
- **NCE simulator caveat (still applies).** The simulator accepts state-update envelopes and echoes back fresh state, but no virtual decoder exists — no physical loco motion. Integration tests for this story verify *library plumbing only* (envelope shape sent, no exception, no error envelope back). Story 5.3 covers physical correctness on hardware. Memory: `project_throttle_simulator_blindspot.md`.

## Acceptance Criteria

### AC1 — `Throttle.set_speed(value, *, forward)` validates and sends a WS update (FR25)

**Given** an acquired `Throttle` (i.e., `__aenter__` has run, `_throttle_id is not None`, `_released is False`)
**When** the user calls `await loco.set_speed(value: float, *, forward: bool)`
**Then** `value` is validated to be in the closed range `[0.0, 1.0]`; values outside this range (including NaN, since `0.0 <= NaN` is `False`) raise `ValueError` with a diagnostic message naming the bad value
**And** validation runs BEFORE any WS traffic; an invalid `value` produces zero side effects (no envelope sent, no log line emitted at INFO)
**And** on valid input, the implementation sends a SINGLE WS envelope carrying both `speed` and `forward` in `data` (Task 0 spike confirms the exact field names; pre-spike assumption is `{"type":"throttle","data":{"throttle":"<id>","speed":<value>,"forward":<forward>}}`)
**And** the call is fire-and-forget: it returns as soon as `WSConnection.send(...)` completes; it does NOT await JMRI's state-echo envelope
**And** an `INFO` log on logger `pyjmri.throttle` records the update with `extra={"dcc_address": <addr>, "throttle_id": <id>, "speed": <value>, "forward": <forward>}`

### AC2 — `Throttle.set_function(n, on)` validates and sends a WS update (FR26)

**Given** an acquired `Throttle`
**When** the user calls `await loco.set_function(n: int, on: bool)`
**Then** `n` is validated to be in the closed range `[0, 28]`; values outside this range (negative, or 29+) raise `ValueError` with a diagnostic message naming the bad value
**And** validation runs BEFORE any WS traffic; an invalid `n` produces zero side effects
**And** on valid input, the implementation sends a WS envelope of the form `{"type":"throttle","data":{"throttle":"<id>","F<n>":<on>}}` (Task 0 spike confirms field-naming convention — `F0`, `F1`, …, `F28` per Story 5.1 acquire-echo evidence)
**And** the call is fire-and-forget (same shape as AC1)
**And** an `INFO` log on logger `pyjmri.throttle` records the update with `extra={"dcc_address": <addr>, "throttle_id": <id>, "function": <n>, "on": <on>}`
**And** the method docstring states explicitly: "Higher function bits (F29+, used by some decoders such as ScaleTrains) are deferred to Growth (FR26)."

### AC3 — Post-release calls raise `ThrottleReleased` with no WS traffic (FR27)

**Given** a `Throttle` whose `_released` flag is `True` (after `release()` or `__aexit__`)
**When** the user calls `await loco.set_speed(...)` or `await loco.set_function(...)` with ANY arguments (valid or invalid)
**Then** `ThrottleReleased` is raised carrying `dcc_address` in `.context` (matches existing `Throttle.__aenter__` pattern at `throttle.py:91-95`)
**And** the released check runs BEFORE argument validation — a released throttle ignores arguments entirely (the throttle is dead; what the user asked for doesn't matter)
**And** NO WS envelope is sent (Story 5.1's lifecycle invariant: a released throttle produces no JMRI traffic)
**And** NO log line is emitted at INFO (release-state methods are silent at INFO; they raise)

### AC4 — Calls on a never-acquired `Throttle` raise `RuntimeError`

**Given** a `Throttle` instance constructed via `layout.throttle(...)` but never entered (`_throttle_id is None`, `_released is False`)
**When** the user calls `await loco.set_speed(...)` or `await loco.set_function(...)`
**Then** `RuntimeError` is raised with a message naming the API misuse: e.g., "Throttle not acquired; enter the 'async with' block before calling set_speed/set_function"
**And** NO WS envelope is sent
**And** the check order is: `_released` first, then `_throttle_id is None`, then argument validation. (User error precedence: explicit release > acquire-never-happened > bad args.)

### AC5 — `ClientHandle` Protocol gains `throttle_update`

**Given** the existing `ClientHandle` Protocol in `python_code/src/pyjmri/_protocols.py:22-115` (currently exposes `get_entity`, `ensure_subscription`, `command`, `throttle_acquire`, `throttle_release`, `throttle_heartbeat`, `spawn_supervised`, `throttle_keepalive_interval`)
**When** this story extends `ClientHandle`
**Then** a new abstract method is added with this exact signature:

```python
async def throttle_update(
    self,
    throttle_id: str,
    payload: dict[str, Any],
) -> None:
    """Send a fire-and-forget WS state-update envelope for ``throttle_id``.

    Wraps ``payload`` in ``{"type":"throttle","data":{"throttle":<id>,**payload}}``
    and writes it to the WS connection. Returns as soon as the bytes are
    written; does NOT await JMRI's state-echo (Story 5.2 AC1 — symmetric
    with :meth:`throttle_release`'s fire-and-forget design).
    """
    ...
```

**And** the new method appears in the Protocol declaration order immediately after `throttle_heartbeat` (alphabetical-ish grouping: acquire / heartbeat / release / update)
**And** the docstring on the existing `command()` method is NOT touched (Story 4.1 ownership)

### AC6 — `Client.throttle_update` implements the WS send

**Given** the existing `Client.throttle_release` implementation in `python_code/src/pyjmri/client.py:525-540`
**When** this story adds `Client.throttle_update`
**Then** the method body mirrors `throttle_release`'s shape:

```python
async def throttle_update(
    self,
    throttle_id: str,
    payload: dict[str, Any],
) -> None:
    """Implementation of :class:`pyjmri._protocols.ClientHandle`.

    Fire-and-forget WS state-update envelope. Story 5.2 AC1 documents the
    contract: returns as soon as the WS bytes are written; no awaiting
    JMRI's echo. State echoes arrive on the WS dispatcher and fall through
    :meth:`_dispatch_throttle_envelope` to the ``future is None`` path
    (silently dropped — no pending acquire matches a held throttle's echo).
    """
    if self._ws is None:
        raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
    await self._ws.send(
        {
            "type": "throttle",
            "data": {"throttle": throttle_id, **payload},
        }
    )
```

**And** the method is placed in `client.py` immediately after `throttle_release` (declaration order matches Protocol order from AC5)
**And** NO test-only hooks or `if TYPE_CHECKING` guards are added — the method is plain runtime code

### AC7 — `_FakeHandle` is extended with `throttle_update` observability

**Given** the existing `_FakeHandle` in `python_code/tests/unit/conftest.py:64-153` (currently records `throttle_acquire_calls`, `throttle_release_calls`, `throttle_heartbeat_calls`, etc.)
**When** this story extends `_FakeHandle`
**Then** the fake gains these new attributes:

- `self.throttle_update_calls: list[tuple[str, dict[str, Any]]] = []` — records every `(throttle_id, payload)` invocation in order
- `self.throttle_update_raises: BaseException | None = None` — knob for forcing `throttle_update` to raise (useful for negative tests)

**And** the new async method:

```python
async def throttle_update(
    self,
    throttle_id: str,
    payload: dict[str, Any],
) -> None:
    self.throttle_update_calls.append((throttle_id, dict(payload)))
    if self.throttle_update_raises is not None:
        raise self.throttle_update_raises
```

**And** the new method appears in `_FakeHandle` immediately after `throttle_heartbeat` (mirrors the Protocol order from AC5)
**And** the existing throttle attributes (`throttle_acquire_calls`, etc.) are NOT renamed or reordered
**And** `dict(payload)` is used at append time so a caller that re-uses a payload dict (mutating after the call) cannot retroactively corrupt the recorded call

### AC8 — Mini-spike (Task 0) confirms the WS envelope shape

**Given** Story 5.1's Task 0 spike confirmed the acquire / release / error envelope shapes but NOT the state-update envelope shape
**When** Task 0 of this story is executed against the running NCE simulator (`My_NCE_Simulator.jmri` profile)
**Then** the dev agent confirms or refutes the pre-spike hypothesis:

```jsonc
// Pre-spike hypothesis (based on Story 5.1's acquire-response echo,
// which carries `speed`, `forward`, `F0`-`F28` as snake-named fields):
//
// Speed + direction update (single envelope per FR25):
{"type":"throttle","data":{"throttle":"<id>","speed":0.4,"forward":true}}
//
// Function bit update:
{"type":"throttle","data":{"throttle":"<id>","F2":true}}
```

**And** the spike answers, at minimum:

1. Do `speed` and `forward` work as field names? (alternatives JMRI sometimes uses: `setSpeed`, `setIsForward`, camelCase variants)
2. Can `speed` and `forward` be combined in a SINGLE envelope, or must they be sent as separate updates? (FR25 requires single-call API; if JMRI requires separate envelopes, the AC1 implementation sends two envelopes back-to-back from one `set_speed` call — but this should be unnecessary)
3. Is the function-bit field literally `F<n>` (`F0`, `F2`, …) or something else (`function`, `f<n>`, indexed object, etc.)?
4. Does JMRI echo a state envelope after a state update? (Informational — pyjmri does NOT await it.) Does the echo carry the full state or just the changed fields?
5. Does JMRI emit a `type:error` envelope on out-of-bounds values (e.g., `speed: 5.0`)? (Pyjmri validates client-side so this never reaches JMRI in normal use, but the spike confirms the safety net.)

**And** the findings are recorded in this story's **Dev Agent Record → Debug Log References** in a fenced code block, including: the exact envelope sent, the exact echo received (or absence thereof), and any deviations from the pre-spike hypothesis
**And** if the spike findings diverge from the hypothesis, AC1 / AC2 / AC6 / AC7 are updated IN PLACE per Epic 3 retro action C3, with a Change Log entry naming the divergence

### AC9 — Unit tests cover validation, transport, and lifecycle gating

**Given** the unit test scaffolding extended in AC7 (`throttle_update_calls` on `_FakeHandle`)
**When** new unit tests are added to the existing `python_code/tests/unit/test_throttle.py`
**Then** the file gains AT LEAST these tests, each exercising one invariant:

1. **`test_set_speed_sends_single_envelope_with_speed_and_forward`** — acquire; `await t.set_speed(0.4, forward=True)`; assert `handle.throttle_update_calls == [("pyjmri-5327-fake", {"speed": 0.4, "forward": True})]` (or the spike-corrected payload shape).
2. **`test_set_speed_with_reverse_direction`** — acquire; `await t.set_speed(0.25, forward=False)`; assert the recorded payload's `forward` is `False`.
3. **`test_set_speed_zero_is_valid`** — acquire; `await t.set_speed(0.0, forward=True)`; assert no exception and one update recorded. (Edge: emergency stop.)
4. **`test_set_speed_one_is_valid`** — acquire; `await t.set_speed(1.0, forward=True)`; assert no exception. (Edge: closed-range upper bound.)
5. **`test_set_speed_rejects_negative`** — acquire; `with pytest.raises(ValueError): await t.set_speed(-0.1, forward=True)`; assert `handle.throttle_update_calls == []`. (Validation runs before transport per AC1.)
6. **`test_set_speed_rejects_above_one`** — acquire; `with pytest.raises(ValueError): await t.set_speed(1.1, forward=True)`; assert `handle.throttle_update_calls == []`.
7. **`test_set_speed_rejects_nan`** — acquire; `with pytest.raises(ValueError): await t.set_speed(float("nan"), forward=True)`; assert no update sent. (`0.0 <= NaN` is `False`, so the `[0.0, 1.0]` check catches it cleanly.)
8. **`test_set_function_sends_F_indexed_envelope`** — acquire; `await t.set_function(2, True)`; assert `handle.throttle_update_calls == [("pyjmri-5327-fake", {"F2": True})]`.
9. **`test_set_function_zero_and_twentyeight_are_valid`** — acquire; `await t.set_function(0, True)`; `await t.set_function(28, False)`; assert two updates recorded with payloads `{"F0": True}` and `{"F28": False}`.
10. **`test_set_function_rejects_negative`** — acquire; `with pytest.raises(ValueError): await t.set_function(-1, True)`; assert no update sent.
11. **`test_set_function_rejects_above_twentyeight`** — acquire; `with pytest.raises(ValueError): await t.set_function(29, True)`; assert no update sent.
12. **`test_set_speed_after_release_raises_throttle_released`** — acquire; `await t.release()`; `with pytest.raises(ThrottleReleased): await t.set_speed(0.4, forward=True)`; assert `handle.throttle_update_calls == []`.
13. **`test_set_function_after_release_raises_throttle_released`** — acquire; `await t.release()`; `with pytest.raises(ThrottleReleased): await t.set_function(2, True)`; assert `handle.throttle_update_calls == []`.
14. **`test_set_speed_on_never_acquired_throttle_raises_runtime_error`** — construct `_make_throttle(handle)` without entering; `with pytest.raises(RuntimeError, match=r"not acquired"): await throttle.set_speed(0.4, forward=True)`; assert no update sent.
15. **`test_set_speed_with_invalid_value_on_released_throttle_raises_throttle_released`** — acquire; release; `with pytest.raises(ThrottleReleased): await t.set_speed(-0.1, forward=True)`. Confirms AC3 ordering: released check before validation.

**And** the existing 13 Story 5.1 tests continue to pass unchanged
**And** all new tests pass with `uv run --no-sync pytest tests/unit/test_throttle.py`
**And** test docstring style matches the existing 5.1 tests (one-line summary, no decorative headers)

### AC10 — Integration test exercises `set_speed` + `set_function` on the live simulator

**Given** the running JMRI simulator (`jmri_available` fixture)
**When** a new test `test_set_speed_and_set_function_plumbing` is added to `python_code/tests/integration/test_throttle_lifecycle.py`
**Then** the test:

1. Opens a `Client` and acquires throttle for DCC address `3` (same convention as Story 5.1's integration tests — conventional safe test address).
2. Calls `await throttle.set_speed(0.1, forward=True)`.
3. Calls `await throttle.set_function(0, True)`. (F0 is headlight on most decoders — semantic, but pyjmri doesn't care; the field is `F0`.)
4. Calls `await throttle.set_speed(0.0, forward=True)`. (Stop.)
5. Calls `await throttle.set_function(0, False)`.
6. Releases via `__aexit__`.

**And** the test asserts NO exception was raised at any of steps 2-5 (the JMRI simulator accepts the envelopes — there are no client-side validation failures since all values are in-range, and JMRI should accept them; if JMRI emits a `type:error` envelope, the next acquire's pending future would fail, but this test never acquires twice, so the error envelope would be silently dropped at `_dispatch_error_envelope` with an empty queue)
**And** the test's module-level docstring (already present from Story 5.1) covers this — no changes to the docstring needed
**And** the test does NOT assert any physical-correctness property (no decoder, no observable motion — by design; Story 5.3 covers this on hardware)
**And** if a known-responsive locomotive happens to be on the test layout, the test still passes — it never claims physical state
**And** the file already has `pytestmark = pytest.mark.integration`; the new test inherits this

### AC11 — Quality gates clean

**Given** the project-wide quality discipline (`feedback_use_uv.md` memory: always `uv run --no-sync`)
**When** the dev runs the quality gates
**Then** ALL the following pass cleanly:

- `uv run --no-sync ruff format` — no formatting changes pending
- `uv run --no-sync ruff check` — no lint errors across changed files
- `uv run --no-sync mypy --strict src/pyjmri` — no type errors (the new `throttle_update` Protocol method requires `Client` to implement it; `mypy --strict` over the `Protocol` enforces this)
- `uv run --no-sync mypy --strict tests/unit/test_throttle.py tests/integration/test_throttle_lifecycle.py` — no type errors in new tests
- `uv run --no-sync pytest -m "not integration"` — passing; unit test count increases by ≥15 (the 15 new throttle tests from AC9), plus 1 self-test for the extended `_FakeHandle` if added (optional)
- `uv run --no-sync pytest -m "integration and not slow"` — passing against the live simulator; the new `test_set_speed_and_set_function_plumbing` test runs cleanly

**And** the story's `File List` section enumerates every changed/created file
**And** no markdownlint warnings on this story file (memory `feedback_polish_matters.md`)

## Tasks / Subtasks

- [x] **Task 0 — Mini-spike: confirm WS state-update envelope shape** (AC: 8)
  - [x] Probed the live `My_NCE_Simulator.jmri` profile via a throwaway `websockets` script (deleted post-spike).
  - [x] Confirmed all envelope shapes for: `speed` alone, `forward` alone, combined `speed + forward`, `F0`, `F28`, out-of-range values.
  - [x] Recorded findings in `Dev Agent Record → Debug Log References`. Pre-spike hypothesis confirmed — no AC text updates required.
  - [x] Throwaway spike script deleted; no commit footprint.

- [x] **Task 1 — Extend `ClientHandle` Protocol with `throttle_update`** (AC: 5)
  - [x] Added `throttle_update` to `_protocols.py` immediately after `throttle_heartbeat`.

- [x] **Task 2 — Implement `Client.throttle_update`** (AC: 6)
  - [x] Added `Client.throttle_update` to `client.py` immediately after `throttle_heartbeat`. Fire-and-forget WS send mirroring `throttle_release`.

- [x] **Task 3 — Implement `Throttle.set_speed` and `Throttle.set_function`** (AC: 1, 2, 3, 4)
  - [x] Added both methods to `throttle.py` after `release()`. Released → `ThrottleReleased`; never-acquired → `RuntimeError`; out-of-range → `ValueError`; valid → single WS envelope + INFO log.

- [x] **Task 4 — Extend `_FakeHandle` with `throttle_update` observability** (AC: 7)
  - [x] Added `throttle_update_calls` + `throttle_update_raises` attributes and the async `throttle_update` method to `_FakeHandle` in `tests/unit/conftest.py`. `dict(payload)` snapshot defeats post-call mutation.

- [x] **Task 5 — Author unit tests** (AC: 9)
  - [x] Added 15 tests to `tests/unit/test_throttle.py` per AC9 (envelope shape, range bounds, NaN, post-release `ThrottleReleased`, never-acquired `RuntimeError`, released-beats-validation ordering). All pass.

- [x] **Task 6 — Author integration test** (AC: 10)
  - [x] Added `test_set_speed_and_set_function_plumbing` to `tests/integration/test_throttle_lifecycle.py`. Verified green against the live simulator.

- [x] **Task 7 — Quality gates + File List + Completion Notes** (AC: 11)
  - [x] All gates green (see Completion Notes).
  - [x] File List updated.
  - [x] Completion Notes written.
  - [x] Story status set to `review`.

### Review Findings

- [x] **\[Review/Patch\]** `bool`/`float` as `n` in `set_function` produces malformed JMRI key (`"FTrue"`, `"F2.5"`) — added `isinstance(n, bool) or not isinstance(n, int)` guard before range check [`throttle.py`]
- [x] **\[Review/Patch\]** Payload key `"throttle"` silently overwrites correlation ID — swapped to `{**payload, "throttle": throttle_id}` so `throttle_id` always wins [`client.py`]
- [x] **\[Review/Patch\]** Missing test: `set_function` on never-acquired throttle (AC4 says "set_speed **or** set_function"; only set_speed had test #14) — added `test_set_function_on_never_acquired_throttle_raises_runtime_error` [`test_throttle.py`]
- [x] **\[Review/Patch\]** `ThrottleReleased.context["dcc_address"]` never asserted in post-release tests (AC3 requires it) — added `excinfo.value.context["dcc_address"]` assertion to tests 12, 13, 15 [`test_throttle.py`]
- [x] **\[Review/Patch\]** INFO log with `extra` fields untested — added `test_set_speed_logs_info_with_extra_fields` and `test_set_function_logs_info_with_extra_fields` using `caplog` (AC1, AC2) [`test_throttle.py`]
- [x] **\[Review/Patch\]** `throttle_update` not placed immediately after `throttle_release` in `client.py` — moved `throttle_update` before `throttle_heartbeat` per AC6 [`client.py`]
- [x] **\[Review/Patch\]** `throttle_update_raises` knob added to `_FakeHandle` but never exercised — added `test_set_speed_propagates_transport_error` + bool/float rejection tests [`test_throttle.py`]
- [x] **\[Review/Patch\]** `set_speed` docstring omits `±inf` from invalid-input description — updated to document NaN and ±inf rejection [`throttle.py`]
- [x] **\[Review/Defer\]** TOCTOU race between `set_speed`/`set_function` and concurrent `release()` [`throttle.py`] — deferred, pre-existing (acknowledged in Dev Notes R4 as by-design lock-free architecture)
- [x] **\[Review/Defer\]** `RuntimeError` from client-not-open path undocumented in method docstrings [`throttle.py`] — deferred, pre-existing (same pattern as all Story 5.1 methods)
- [x] **\[Review/Defer\]** Reconnect-window silent command loss undocumented [`client.py`] — deferred, pre-existing (applies to all fire-and-forget WS operations since Story 5.1)

## Dev Notes

### Authoritative current state of `python_code/` (verified 2026-05-21, post-Story-5.1)

**Source files in `src/pyjmri/`** (21 files; `throttle.py` exists with lifecycle only):

| File | Status for Story 5.2 |
| --- | --- |
| `throttle.py` | **MODIFY** — add `set_speed` and `set_function` methods after `release()` (around line 144) |
| `_protocols.py` | **MODIFY** — extend `ClientHandle` Protocol with `throttle_update` |
| `client.py` | **MODIFY** — implement `Client.throttle_update` after `throttle_release` |
| `exceptions.py` | **UNCHANGED** — `ThrottleReleased` already defined (line 127-128) |
| `__init__.py` | **UNCHANGED** — `Throttle`, `ThrottleAcquireFailed`, `ThrottleReleased`, `ThrottleError` already re-exported |
| `layout.py` | **UNCHANGED** — `Layout.throttle()` factory already exists from Story 5.1 |
| `_transport.py` | **UNCHANGED** — `WSConnection.send` already in use for `throttle_acquire` / `throttle_release` |
| `_codes.py`, `_parsing.py`, `_subscriptions.py`, `_waiters.py` | **UNCHANGED** — throttle state updates do not participate in the entity-state subscription/waiter system in v1 |
| `turnout.py`, `sensor.py`, `block.py`, `light.py`, `memory.py`, `route.py`, `signal.py`, `power.py`, `roster.py` | **UNCHANGED** |
| `py.typed` | **UNCHANGED** |

**Test files:**

| File | Status |
| --- | --- |
| `tests/unit/conftest.py` | **MODIFY** — extend `_FakeHandle` with `throttle_update_calls` + `throttle_update_raises` + the async method |
| `tests/unit/test_throttle.py` | **MODIFY** — add 15 new tests (Story 5.2 AC9) |
| `tests/unit/test_protocols.py` | **OPTIONAL** — extend `test_client_handle_has_throttle_members` to assert `throttle_update` is callable on `Client` (mirrors Story 5.1's pattern) |
| `tests/integration/test_throttle_lifecycle.py` | **MODIFY** — add `test_set_speed_and_set_function_plumbing` |
| All other test files | **UNCHANGED** |

### Architecture rules carried forward (apply verbatim)

- `from __future__ import annotations` at the top of every Python module (already present in all touched files).
- PEP 604 unions everywhere; no `Optional[X]`, no `Union[X, Y]`.
- Public I/O methods are `async def`. No sync wrappers.
- Library-detected errors raise concrete `JMRIError` subclasses. `ValueError` is fine for input validation (it's a Python builtin, not a JMRI-protocol error).
- Catch-name convention: `except <Type> as e:` — always `e`.
- Module-level logger per file: `pyjmri.throttle` for `throttle.py` (already set up line 30).
- No bare `asyncio.create_task` outside `TaskGroup` in library code. (Not applicable to Story 5.2 — no new tasks spawned here.)
- No mocks of JMRI in unit tests. Use the extended `_FakeHandle`.
- Every public module declares `__all__`. (Not modified in Story 5.2 — no new public symbols.)

### Payload-composition discipline

The throttle module composes the payload dict; the Protocol's `throttle_update(throttle_id, payload)` is a thin wrapper that prepends `throttle_id` into the envelope's `data` block.

**Why a generic `throttle_update(payload)` rather than specific `throttle_set_speed(value, forward)` and `throttle_set_function(n, on)` Protocol methods?**

1. Mirrors the existing `command(entity_type, name, payload)` pattern — pyjmri's Protocol layer has historically used `payload: dict` for state updates (Story 4.1).
2. Keeps the Protocol lean (one new method vs. two).
3. Pushes payload-shape knowledge into the `Throttle` class where it belongs — `Throttle` knows what JMRI's update envelopes look like; the Client / Protocol just sends bytes.
4. Future Growth-deferred function bits (F29+) or additional state fields don't require Protocol changes.

### Fire-and-forget design rationale

`throttle_update` does NOT await JMRI's state-echo envelope, mirroring Story 5.1's `throttle_release` design (Story 5.1 AC4). Recap:

- JMRI's echo confirms only that JMRI processed the update; it cannot confirm the locomotive physically moved (NCE is open-loop).
- Waiting for the echo would add a teardown / partial-failure hazard (slow JMRI hangs `__aexit__`).
- The echo arrives on the WS dispatcher and falls through `_dispatch_throttle_envelope`'s `future is None` path → silently dropped. No instrumentation needed.

If a future story wants to observe state-update echoes (e.g., a "wait for JMRI to confirm speed" pattern, analogous to Story 4.2's `wait_for_jmri_state=True`), that is a separate, opt-in API surface and would require a new pending-update future system. Story 5.2 stays strictly fire-and-forget.

### Validation discipline

- **`set_speed` range:** `[0.0, 1.0]` closed. Python's `0.0 <= value <= 1.0` evaluates to `False` for `NaN` (NaN comparisons return `False`), so the same check catches NaN without an explicit `math.isnan` call.
- **`set_function` range:** `[0, 28]` closed (FR26). `n = 29+` is Growth-deferred; the docstring on `set_function` must say so per AC2.
- **Diagnostic messages:** Always include the offending value via `{value!r}` or `{n!r}` so the user can paste the error and immediately see what they passed.
- **Order of checks (AC3, AC4):** released → not-acquired → arg validation. A released throttle ignores everything else; a never-acquired throttle is an API misuse; only an active throttle reaches arg validation.

### Cross-story implications

- **Story 5.3 (multi-throttle integration test + hardware mode):** uses `set_speed` and `set_function` to drive `2–3` locos in parallel via `asyncio.gather`. Test patterns for parallel acquire/control are owned by 5.3; 5.2 establishes the single-throttle plumbing.
- **Story 6.4 (shipped examples):** `back_and_forth.py` and `multi_train_session.py` will call `set_speed` and `set_function`. The PRD's Scene B example (`loco.set_speed(0.4, forward=True)` without `await`) should be corrected to `await loco.set_speed(...)` in those examples. Out of scope for 5.2.
- **Story 6.3 (Jython→pyjmri migration table):** PRD line 578-580 already documents the migration:
  - `throttle.setSpeedSetting(0.4)` → `t.set_speed(0.4)` *(note: PRD's mapping omits `forward=`; the correct pyjmri call is `await t.set_speed(0.4, forward=True)`. Tracked but not changed in 5.2.)*
  - `throttle.setIsForward(True)` → `t.set_speed(0.4, forward=True)`
  - `throttle.setF2(True)` → `t.set_function(2, True)`

### Risks and mitigations

- **R1: Task 0 spike reveals a different envelope shape than the pre-spike hypothesis.** Likely (JMRI's update API is sparsely documented). Mitigation: budget time for the spike before Task 3; update affected ACs in place per Epic 3 retro action C3.
- **R2: JMRI rejects a combined `speed + forward` envelope and requires two separate updates.** Possible but unlikely given the acquire-response echo carries both in one envelope. Mitigation: if the spike forces two envelopes, `Throttle.set_speed` sends them back-to-back (still a single user-facing call); document in AC1 and `Completion Notes`.
- **R3: Function-bit field naming differs (e.g., `function: {n: 2, value: true}` instead of `F2: true`).** Possible. Mitigation: spike covers this; AC2's payload shape is spike-dependent.
- **R4: Race condition between `set_speed` and `release` from concurrent tasks.** A user could call `set_speed` from task A while task B calls `release` — possible if the user is multi-tasking. The `_released` check is a TOCTOU snapshot. Mitigation: same pattern as Story 5.1's `release`; documented as a "by-design" — the architecture's lock-free design assumes the user doesn't fight themselves. If a user concurrently releases-then-updates, the update might briefly send a WS envelope for an already-released throttle; JMRI emits a `type:error` envelope, which lands on the FIFO error queue. If no acquire is pending, the error is silently dropped (`_dispatch_error_envelope` short-circuits on empty queue per Story 5.1 review-finding fix). No corrupting effect on other throttles.
- **R5: `mypy --strict` complaints on `dict[str, Any]` payload typing.** Standard pattern in pyjmri — `command(entity_type, name, payload: dict[str, Any])` is already in use (`_protocols.py:46-51`). Mitigation: mirror that signature exactly.
- **R6: `ValueError` raised in `set_speed`/`set_function` is not a `JMRIError` subclass and therefore doesn't appear in FR35's diagnostic-context discipline.** Intentional — `ValueError` is for API misuse (programmer error), not JMRI-detected errors. The architecture's FR35 discipline applies to `JMRIError` subclasses only. `ValueError`'s message is the diagnostic context.

### References

- `_bmad-output/planning-artifacts/epics.md:852-883` — Epic 5 + Story 5.2 acceptance criteria.
- `_bmad-output/planning-artifacts/epics.md:885-924` — Story 5.3 (next; do not pre-implement multi-throttle test patterns here).
- `_bmad-output/planning-artifacts/architecture.md:543-544` — `Throttle.set_speed`, `set_function`, `release` signatures.
- `_bmad-output/planning-artifacts/architecture.md:792-805` — Async Patterns (`async def` rule, `asyncio.timeout` over `wait_for`).
- `_bmad-output/planning-artifacts/architecture.md:806-833` — Error Handling Discipline (concrete subclasses, FR35 context).
- `_bmad-output/planning-artifacts/architecture.md:834-860` — Logging Discipline (`pyjmri.throttle` logger, INFO lifecycle, `extra={...}`).
- `_bmad-output/planning-artifacts/architecture.md:861-875` — Public API Discipline.
- `_bmad-output/planning-artifacts/architecture.md:893-916` — Testing Patterns (no JMRI mocks, marker discipline).
- `_bmad-output/planning-artifacts/architecture.md:918-934` — Documentation Patterns (Google-style docstrings).
- `_bmad-output/planning-artifacts/architecture.md:1118-1123` — Throttle & Locomotive Control file mapping.
- `_bmad-output/planning-artifacts/prd.md:216-222` — FR23–FR28 narrative.
- `_bmad-output/planning-artifacts/prd.md:577-580` — Jython→pyjmri throttle migration table.
- `_bmad-output/planning-artifacts/prd.md:790-797` — FR23–FR28 verbatim.
- `_bmad-output/implementation-artifacts/5-1-throttle-async-context-manager-acquire-release-lifecycle-keep-alive-supervision.md` — Previous story (Story 5.1, status `done`). Spike findings, AC patterns, `_FakeHandle` extension discipline, lifecycle invariants all carry forward.
- `python_code/src/pyjmri/throttle.py` — Existing `Throttle` class; add `set_speed` and `set_function` here.
- `python_code/src/pyjmri/throttle.py:91-95` — Existing `ThrottleReleased` raise pattern (mirror for `set_speed`/`set_function`).
- `python_code/src/pyjmri/throttle.py:96-100` — Existing `RuntimeError` raise pattern for "already acquired" (mirror tone for "not acquired" error in AC4).
- `python_code/src/pyjmri/_protocols.py:74-91` — `ClientHandle.throttle_release` and `throttle_heartbeat`; new `throttle_update` placement is between them or after `throttle_heartbeat`.
- `python_code/src/pyjmri/client.py:525-540` — `Client.throttle_release` implementation; mirror its shape for `throttle_update`.
- `python_code/tests/unit/conftest.py:78-152` — `_FakeHandle` throttle observability; extend with `throttle_update_calls`.
- `python_code/tests/unit/test_throttle.py` — Existing 13 tests from Story 5.1; add 15 new tests from AC9.
- `python_code/tests/integration/test_throttle_lifecycle.py` — Existing 3 tests from Story 5.1; add 1 new test from AC10.
- Memory: `feedback_use_uv.md` — always `uv run --no-sync` for pytest/mypy/ruff/python in this project.
- Memory: `project_throttle_simulator_blindspot.md` — NCE simulator accepts throttle commands but has no virtual decoder; plumbing-only verification on simulator.
- Memory: `project_nce_open_loop.md` — NCE open-loop applies equally on simulator and on Mikey's real layout. Only throttle/loco testing requires real hardware.
- Memory: `project_throttle_name_internal.md` — Throttle WS correlation name is pyjmri-internal; user-facing API exposes only DCC address. No `name=` kwarg on factories or methods.
- Memory: `feedback_polish_matters.md` — self-scan markdownlint warnings on story files before declaring done.

### Project Structure Notes

- All new code under `python_code/src/pyjmri/` and `python_code/tests/`.
- No new files in this story — `throttle.py`, `_protocols.py`, `client.py`, `conftest.py`, `test_throttle.py`, `test_throttle_lifecycle.py` already exist from Story 5.1.
- No changes to `.jmri/` profiles, `jython/` scripts, `roster/`, `roster.xml`, or any non-Python asset.
- No `__init__.py` re-export changes (no new public symbols).
- Story 5.2 does NOT touch `_codes.py`, `_parsing.py`, `_subscriptions.py`, `_waiters.py` — state updates are fire-and-forget and do not participate in the entity-state subscription/waiter system.
- If the architecture document's wording about HTTP throttle endpoints (e.g., line 1118-1123 mentions HTTP-style command path for throttles) needs updating in light of Story 5.1's WS-only spike finding, defer that to a follow-up doc-only commit — out of scope for Story 5.2.

### Acceptable test patterns from Story 5.1

- Use `asyncio.create_task` in test bodies to inspect intermediate state (the "no bare create_task" rule applies to library code, not test code).
- Use `asyncio.sleep(0)` (sometimes multiple times) to yield control to the event loop and let background coroutines progress.
- `_make_throttle(handle, ...)` helper at top of `test_throttle.py` (lines 20-21) is the convenient constructor — reuse for new tests.
- Cast `handle` to `ClientHandle` via `cast(ClientHandle, handle)` to satisfy mypy strict (already imported in `test_throttle.py:17`).
- For mid-call inspection, use `asyncio.Event()` gates in the fake (parallel to Story 5.1's `throttle_acquire_gate`). For `throttle_update`, gates may not be necessary — there is no async wait inside `set_speed` / `set_function` other than the WS-send.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 via Claude Code (bmad-dev-story workflow).

### Debug Log References

#### Task 0 mini-spike findings — JMRI 5.14, NCE simulator (2026-05-21)

**Profile:** `My_NCE_Simulator.jmri` (NCE 2-via-USB simulator), JMRI 5.14+Rdea51dcccf, JSON API v5.4.0.

**Pre-spike hypothesis confirmed across the board.** No AC text updates required.

```jsonc
// === Speed alone ===
//
// Client → server:
{"type":"throttle","data":{"throttle":"<id>","speed":0.4}}
//
// Server → client (delta echo, not full state):
{"type":"throttle","data":{"speed":0.4,"name":"<id>","throttle":"<id>"}}
```

```jsonc
// === Direction alone ===
//
// Client → server:
{"type":"throttle","data":{"throttle":"<id>","forward":false}}
//
// Server → client:
{"type":"throttle","data":{"forward":false,"name":"<id>","throttle":"<id>"}}
```

```jsonc
// === Combined speed + forward (FR25 single-call shape) ===
//
// Client → server (single envelope):
{"type":"throttle","data":{"throttle":"<id>","speed":0.6,"forward":true}}
//
// Server → client (TWO delta echoes, one per changed field — informational only):
{"type":"throttle","data":{"speed":0.6,"name":"<id>","throttle":"<id>"}}
{"type":"throttle","data":{"forward":true,"name":"<id>","throttle":"<id>"}}
```

```jsonc
// === Function bits ===
//
// Client → server (F0 and F28 work identically):
{"type":"throttle","data":{"throttle":"<id>","F0":true}}
//
// Server → client:
{"type":"throttle","data":{"F0":true,"name":"<id>","throttle":"<id>"}}
```

```jsonc
// === JMRI does NOT validate range ===
//
// Client → server:
{"type":"throttle","data":{"throttle":"<id>","speed":5.0}}
//
// Server → client (echoed as if valid — no type:error):
{"type":"throttle","data":{"speed":5.0,"name":"<id>","throttle":"<id>"}}
//
// Same for speed: -0.1 — accepted and echoed. Confirms client-side validation
// in AC1/AC2 is REQUIRED, not optional; JMRI is permissive about garbage.
```

**Key takeaways:**

1. **Field names** are exactly `speed`, `forward`, `F<n>` — snake-cased, lowercase, matching the acquire-response echo from Story 5.1.
2. **Single envelope works** for combined speed+forward (FR25 satisfied with one user call → one WS send → two delta echoes from JMRI, which pyjmri silently drops).
3. **Echo shape is a delta**, not full state (unlike the acquire echo which carries the full state snapshot). Confirms `_dispatch_throttle_envelope`'s "future is None" silent-drop path handles all post-acquire echoes correctly.
4. **JMRI does not validate value range.** A `speed: 5.0` envelope is accepted and echoed back. Client-side `ValueError` validation in `Throttle.set_speed` is the only guardrail — the spike justifies the AC1/AC2 validation requirement empirically.
5. **No `type:error` envelopes observed** during state updates. The Story 5.1 FIFO error queue remains the correlation mechanism for any future error envelopes, but state updates in v1 do not generate them.

### Completion Notes List

- **Task 0 mini-spike (2026-05-21):** Pre-spike hypothesis confirmed verbatim — JMRI accepts `{"speed":<f>,"forward":<b>,"F<n>":<b>}` field names; combined `speed + forward` ships in a single envelope (JMRI echoes two per-field deltas, silently dropped by `_dispatch_throttle_envelope`'s `future is None` path); JMRI does NOT validate value range (it echoed `speed: 5.0` back), so client-side `ValueError` in `set_speed` is the only guardrail. No AC text updates required. Findings recorded in **Debug Log References**.
- **Payload shapes that shipped:**
  - `set_speed(value, forward=...)` → `{"speed": value, "forward": forward}`
  - `set_function(n, on)` → `{f"F{n}": on}`
- **Client-side validation (justified by spike):** `set_speed` rejects `value < 0.0 or value > 1.0 or NaN` via `ValueError` (Python's `0.0 <= NaN` is `False`, so the combined comparison handles NaN naturally — no `math.isnan` import needed). `set_function` rejects `n < 0 or n > 28`.
- **Lifecycle ordering enforced (AC3 + AC4):** released → `ThrottleReleased`; then never-acquired → `RuntimeError`; then arg validation → `ValueError`. The "released beats invalid args" test (`test_set_speed_with_invalid_value_on_released_throttle_raises_throttle_released`) is the regression guard.
- **Fire-and-forget design (mirrors Story 5.1 release):** `Client.throttle_update` writes the envelope to the WS socket and returns. JMRI's per-field delta echoes arrive on the dispatcher and silently drop. No state-update waiter system in v1 — out of scope for FR25/FR26.
- **Quality gates (all green):**
  - `uv run --no-sync ruff format --check` — clean.
  - `uv run --no-sync ruff check` — clean.
  - `uv run --no-sync mypy --strict src/pyjmri` — clean across 20 source files.
  - `uv run --no-sync mypy --strict tests/unit/test_throttle.py tests/integration/test_throttle_lifecycle.py` — clean.
  - `uv run --no-sync pytest -m "not integration"` — **405 passed, 19 deselected** (pre-Story-5.2: 390; +15 from this story, matching AC9 exactly).
  - `uv run --no-sync pytest -m "integration and not slow"` — **15 passed, 2 skipped** (pre-Story-5.2: 14; +1 from this story; the 2 skips are pre-existing light wait-mode tests with no lights in this profile).
- **Tests added:** 15 unit tests in `tests/unit/test_throttle.py` (lines 202-364) + 1 integration test in `tests/integration/test_throttle_lifecycle.py`. Unit-test count for `test_throttle.py` is now 28 (up from 13 in Story 5.1).
- **No new dependencies.** No `pyproject.toml` changes. No `__init__.py` re-export changes (Throttle / ThrottleAcquireFailed / ThrottleError / ThrottleReleased already public).
- **No architecture-doc changes.** Architecture wording about HTTP throttle endpoints (line 1118-1123) remains as a known doc-stale item from Story 5.1 spike outcome; deferred to a follow-up doc-only commit per Story 5.2 Project Structure Notes.
- **Full-suite flake (pre-existing, unrelated to Story 5.2):** The unmarked `uv run --no-sync pytest` (no marker filter — includes the slow `test_long_run.py` 5-min stability test from Story 3.4) surfaced 1 flake: `tests/integration/test_command_round_trip.py::test_turnout_wait_for_jmri_state_round_trip` timed out waiting for a JMRI turnout state-echo. The test passes in isolation and when run with `pytest tests/integration/test_command_round_trip.py`. Story 5.2 does not touch the turnout / `wait_for_jmri_state` machinery (Story 4.2 territory). Root cause is a timing collision with the long-run test sharing the simulator. Not a Story 5.2 regression; flagged for a future stability pass.

### File List

Source (`python_code/src/pyjmri/`):

- `_protocols.py` — `ClientHandle` Protocol gains `throttle_update(throttle_id, payload) -> None` after `throttle_heartbeat`.
- `client.py` — `Client.throttle_update` implementation added after `throttle_heartbeat`; fire-and-forget WS send mirroring `throttle_release`.
- `throttle.py` — `Throttle.set_speed(value, *, forward)` and `Throttle.set_function(n, on)` added after `release()`; both async, fire-and-forget, validated, with `pyjmri.throttle` INFO logs.

Unit tests (`python_code/tests/unit/`):

- `conftest.py` — `_FakeHandle` extended with `throttle_update_calls: list[tuple[str, dict[str, Any]]]`, `throttle_update_raises: BaseException | None`, and the async `throttle_update` method (snapshots payload via `dict(payload)`).
- `test_throttle.py` — 15 new tests for the Story 5.2 control surface (see Completion Notes for coverage breakdown). Module total: 28 tests.

Integration tests (`python_code/tests/integration/`):

- `test_throttle_lifecycle.py` — Added `test_set_speed_and_set_function_plumbing` covering AC10 (drive 0.1 forward + F0 on, then 0.0 + F0 off; release via `__aexit__`).

Story file:

- `_bmad-output/implementation-artifacts/5-2-throttle-speed-direction-function-controls.md` — Status backlog → ready-for-dev → in-progress → review. Task 0 spike findings recorded. All tasks checked. File List + Completion Notes + Change Log updated.

Sprint status:

- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Story 5.2 backlog → ready-for-dev → in-progress → review.

## Change Log

- 2026-05-21 — Story 5.2 implemented (`in-progress` → `review`). `Throttle.set_speed(value, *, forward)` and `Throttle.set_function(n, on)` shipped: input-validated (`ValueError` on out-of-range / NaN for speed; `[0, 28]` for function bits), fire-and-forget WS updates, lifecycle-gated (`ThrottleReleased` after `release`; `RuntimeError` if never acquired). New `ClientHandle.throttle_update` Protocol method + `Client.throttle_update` implementation (mirrors `throttle_release`'s fire-and-forget shape). `_FakeHandle` extended with `throttle_update_calls` observability. 15 unit tests + 1 integration test added; all quality gates green (ruff format/check, mypy --strict, 405 unit / 15 integration tests passing). Task 0 mini-spike confirmed pre-spike hypothesis verbatim — no AC text updates required. FR25, FR26, FR27, FR28 satisfied.
- 2026-05-21 — Task 0 mini-spike complete. Pre-spike hypothesis confirmed: combined `{"speed":<f>,"forward":<b>}` envelope works as a single WS message; function-bit field naming is literal `F<n>`; JMRI does NOT validate value range (echoes `speed: 5.0` as if valid — confirms client-side `ValueError` validation is the only guardrail). Story status: `ready-for-dev` → `in-progress`.
- 2026-05-21 — Story 5.2 created (`backlog` → `ready-for-dev`). Comprehensive context engineered for the dev agent: 11 ACs spanning `Throttle.set_speed` + `set_function` (input-validated, fire-and-forget WS updates), the new `ClientHandle.throttle_update` Protocol method, `Client.throttle_update` implementation (mirrors Story 5.1's `throttle_release` shape), `_FakeHandle` extension for `throttle_update_calls` observability, 15 new unit tests covering validation / transport / lifecycle gating, 1 new integration test for simulator plumbing, and all quality gates. Task 0 mini-spike required to confirm WS state-update envelope field names (pre-spike hypothesis is `{speed, forward, F0..F28}` per Story 5.1 acquire-echo evidence). Lifecycle (acquire/release/keep-alive) is OFF-LIMITS to this story — Story 5.1 owns it. Function bits F29+ are Growth-deferred per FR26 and are documented in `set_function`'s docstring per AC2. Exception types (`ThrottleReleased`) already exist; do not redefine. Architecture sec. Async Patterns mandates `async def` for public I/O — PRD's missing-`await` example is illustrative shorthand, not the API.
