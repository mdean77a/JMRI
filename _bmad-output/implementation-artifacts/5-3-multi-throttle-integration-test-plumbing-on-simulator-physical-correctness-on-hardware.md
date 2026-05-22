# Story 5.3: Multi-throttle integration test (plumbing on simulator; physical correctness on hardware)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a library user,
I want a multi-throttle integration test that validates the library/JMRI plumbing on the simulator (parallel acquire, command shape, keep-alive task lifecycle, release, partial-acquire failure recovery), and a cross-reference to the hardware-mode validation protocol owned by Story 6.5's `CONTRIBUTING.md` release checklist,
So that CI-eligible tests stay simulator-runnable and layout-agnostic, while the claim "throttles work" is grounded in real DCC hardware before each release.

## Scope notes

- **Third and last story in Epic 5.** Story 5.1 stood up acquire/release lifecycle + keep-alive supervision. Story 5.2 layered `set_speed` and `set_function` onto that lifecycle. Story 5.3 exercises the full lifecycle in parallel against multiple DCC addresses and documents the simulator/hardware split.
- **Test-only story.** NO new source files under `python_code/src/pyjmri/`. NO changes to `Throttle`, `Client`, `_protocols.py`, or `_FakeHandle`. All new code lives in `python_code/tests/integration/test_throttle_lifecycle.py`.
- **Layout-agnostic by roster lookup.** The test reads the running layout's roster at session time via raw `httpx.AsyncClient.get("/json/v5/roster")` — same pattern as `test_reconnect_resilience.py`, `test_command_latency.py`, `test_long_run.py`, `test_wait_primitives_latency.py` (5 existing precedents). NO DCC addresses are hardcoded except the conventional failure-test address `99999` (already in use at `test_throttle_lifecycle.py:76`) and the conventional safe test address `3` (already in use at the same file's existing tests — not removed).
- **Roster public API is OUT OF SCOPE.** `python_code/src/pyjmri/roster.py` is currently a stub (`__all__ = []`); `Client.discover()` enumerates 8 entity types (turnout / sensor / block / light / memory / route / signalHead / signalMast) but NOT rosterEntry. Implementing the public `Layout.roster` / `Roster` / `RosterEntry` API is **Growth-deferred** (architecture line 587 documents the intent; Story 2.5 shipped without it; no AC requires it for v1). Story 5.3 reads the roster via raw HTTP only — this is a deliberate, documented scope choice, NOT an architectural compromise.
- **Hardware-mode protocol is owned by Story 6.5.** This story produces a cross-reference (module docstring + test-level comment) pointing at the future `CONTRIBUTING.md` release checklist, NOT the protocol itself. Story 6.5 (FR42 / Epic 6) creates the actual documented procedure. The cross-reference is forward-looking — Story 6.5 is currently `backlog`.
- **Simulator-only plumbing verification.** Per `project_throttle_simulator_blindspot.md` memory: the NCE simulator accepts throttle command envelopes and emits responses, but has no virtual decoder — no physical loco motion is observable. The test verifies *library plumbing only*: no exception raised, WS envelopes accepted by JMRI, task lifecycle traced through `asyncio.all_tasks()`, post-release `ThrottleReleased` invariant. The test makes ZERO claims about physical correctness.
- **NCE open-loop applies on simulator AND on hardware** (`project_nce_open_loop.md`): JMRI's reported throttle state is "last commanded," not observed. Even on real hardware running this test, the only post-condition we could verify by reading JMRI is "JMRI thinks the throttle is at speed X" — NOT that the locomotive at the corresponding DCC address physically moved. Story 5.3 does NOT attempt JMRI-state-read verification, because it adds no information over "no exception was raised."
- **`Throttle.set_speed` and `Throttle.set_function` are AC-validated by Story 5.2.** This story exercises them as a customer; it does NOT re-test their validation contracts (already covered by 28 unit tests + 1 integration test from 5.2). New assertions cover *only* the multi-throttle invariants this story owns (parallel acquire / release / task cleanup / failure recovery).
- **No mini-spike required.** Story 5.1 + 5.2 confirmed the full WS envelope shape catalog (acquire, release, error, state-update). Story 5.3 composes existing primitives; no new JMRI behavior is exercised at the wire level.

## Acceptance Criteria

### AC1 — `test_throttle_lifecycle.py` gains a roster-reader fixture

**Given** the existing `tests/integration/test_throttle_lifecycle.py` (4 tests from Stories 5.1 + 5.2 at lines 27–99; `pytestmark = pytest.mark.integration` at line 24)
**When** this story extends it with multi-throttle test scaffolding
**Then** a module-level async helper is added (NOT a pytest fixture — fixtures are awkward for "needs a session-scoped HTTP call + skip-if-fewer-than-2 behavior"):

```python
async def _fetch_test_dcc_addresses(count: int = 2) -> list[tuple[int, bool]]:
    """Fetch ``count`` DCC ``(address, long)`` tuples from JMRI's live roster.

    Calls ``pytest.skip`` if the roster has fewer than ``count`` entries —
    layout-agnostic per Epic 5 AC9. Uses raw ``httpx`` (same pattern as
    ``test_reconnect_resilience.py`` etc.) because pyjmri has no public
    ``Layout.roster`` API in v1 — that surface is Growth-deferred.

    Returns:
        First ``count`` entries from JMRI's ``/json/v5/roster`` response,
        as ``[(dcc_address, is_long_address), ...]``.
    """
```

**And** the helper:

1. Opens an `httpx.AsyncClient(base_url="http://localhost:12080")` context.
2. `GET`s `/json/v5/roster`.
3. Parses the JSON response (a list of `{"type": "rosterEntry", "data": {...}}` envelopes per `_parsing.parse_roster_entry`'s contract).
4. Extracts `(int(data["address"]), bool(data["isLongAddress"]))` from each entry.
5. Validates `len(entries) >= count`; if not, calls `pytest.skip(f"roster has {len(entries)} entries; multi-throttle test requires >= {count}")`.
6. Returns the FIRST `count` entries (deterministic ordering — JMRI returns roster in alphabetical name order per JSON API v5.4 observation).

**And** the helper is module-level (not inside a function); other tests can call it directly.

**And** the helper does NOT use `pyjmri.Client` — opening a separate raw HTTP client avoids tangling the test's `Client()` lifecycle with the roster pre-fetch. Pattern justification: `test_command_latency.py:59` does exactly this for warmup POSTs.

### AC2 — `test_multi_throttle_parallel_acquire_drive_release` exercises N=2 throttles end-to-end

**Given** the roster reader from AC1
**When** a new test `test_multi_throttle_parallel_acquire_drive_release` is added to `tests/integration/test_throttle_lifecycle.py`
**Then** the test:

1. Fetches the first 2 DCC addresses from the roster via `await _fetch_test_dcc_addresses(2)`.
2. Opens a `Client()` and constructs 2 `Throttle` instances via `jmri.throttle(addr, long=long_flag)` per entry.
3. Acquires BOTH throttles in parallel via `contextlib.AsyncExitStack` + `asyncio.gather`:

   ```python
   from contextlib import AsyncExitStack
   async with AsyncExitStack() as stack:
       throttles = await asyncio.gather(
           *[stack.enter_async_context(t) for t in throttle_objs],
       )
       # ... drive each ...
   # AsyncExitStack unwinds: each Throttle.__aexit__ runs in LIFO order.
   ```

4. Drives EACH throttle:

   ```python
   for t in throttles:
       await t.set_speed(0.1, forward=True)
       await t.set_function(0, True)
       await t.set_speed(0.0, forward=True)
       await t.set_function(0, False)
   ```

5. Exits the `AsyncExitStack`, releasing both throttles.
6. Asserts post-conditions outside the stack (see AC3 + AC4).

**And** the test does NOT use `asyncio.gather` for the drive phase — sequential per-throttle drive keeps assertions simple. The PARALLEL invariant is the *acquire* (proves the library handles concurrent `__aenter__` correctly).

**And** ALL 4 method calls per throttle complete without raising. (If any single call raised, the `AsyncExitStack` would unwind through `__aexit__` with `body_raised=True`, swallowing the release error; the original exception would propagate. The test would fail naturally — no `try/except` needed.)

**And** the test docstring (one line, per existing-test style at lines 28-30, 53-54, 73-75) names the invariant: "Acquire 2 throttles in parallel via AsyncExitStack; drive speed + function on each; verify clean parallel release."

### AC3 — Keep-alive task lifecycle is traceable via `asyncio.all_tasks()`

**Given** the test from AC2
**When** the `AsyncExitStack` is open (throttles acquired) and again after it closes (throttles released)
**Then** the test inspects `asyncio.all_tasks()` to verify keep-alive task lifecycle:

1. INSIDE the stack, before the drive phase: each acquired throttle's `_keepalive_task` is non-`None`, not `done()`, and has a task name matching `f"pyjmri-throttle-keepalive-{dcc_address}"` (Story 5.1 naming convention — see `Throttle.__aenter__` line 111).
2. INSIDE the stack: `asyncio.all_tasks()` includes BOTH keep-alive tasks. Filter via:

   ```python
   keepalive_tasks = [
       t for t in asyncio.all_tasks()
       if t.get_name().startswith("pyjmri-throttle-keepalive-")
   ]
   assert len(keepalive_tasks) == 2
   ```

3. AFTER the stack exits (one `await asyncio.sleep(0)` to let the cancelled tasks finalize — same pattern as `test_throttle_lifecycle.py:41` and `:63`): EVERY `_keepalive_task` is `done()` and `keepalive_tasks` (re-queried via `asyncio.all_tasks()`) is empty.

**And** the assertions are added as a SEPARATE test `test_multi_throttle_keepalive_tasks_cancel_on_release` to keep AC2's test focused on the user-visible flow. The new test re-uses the AC1 roster helper and follows the same AsyncExitStack pattern.

**And** the task-name match is `startswith("pyjmri-throttle-keepalive-")`, NOT exact equality — the suffix depends on the runtime-fetched DCC addresses and the test must not assume which addresses come back from the roster.

### AC4 — Post-release `ThrottleReleased` invariant holds across all acquired throttles

**Given** the test from AC2
**When** the `AsyncExitStack` has exited
**Then** the test additionally asserts that every released `Throttle` raises `ThrottleReleased` on `set_speed`/`set_function`:

```python
for t in throttles:
    assert t._released is True
    with pytest.raises(ThrottleReleased) as excinfo:
        await t.set_speed(0.1, forward=True)
    assert excinfo.value.context["dcc_address"] == t.dcc_address
    with pytest.raises(ThrottleReleased):
        await t.set_function(0, True)
```

**And** these assertions go INSIDE `test_multi_throttle_parallel_acquire_drive_release` (AC2's test), AFTER the `AsyncExitStack` exits — they confirm the multi-throttle lifecycle invariant the user actually cares about: "after the `async with` exits, the throttle is dead."

**And** `t._released is True` AND the `ThrottleReleased` raise are BOTH asserted — `_released` is the lifecycle flag; the raise is the user-visible contract. Story 5.2 review (P4) established that `excinfo.value.context["dcc_address"]` must be asserted explicitly.

### AC5 — Partial-acquire failure releases successful sibling throttles cleanly

**Given** a test `test_multi_throttle_partial_acquire_failure_releases_siblings`
**When** the test attempts to acquire 3 throttles in parallel where one is the conventional failure address `99999` (already used by `test_throttle_acquire_failure_raises_throttle_acquire_failed` at line 76)
**Then** the test verifies that the AsyncExitStack pattern unwinds correctly:

```python
async with Client() as jmri:
    valid_addrs = await _fetch_test_dcc_addresses(2)  # 2 valid from roster
    throttle_valid_1 = jmri.throttle(valid_addrs[0][0], long=valid_addrs[0][1])
    throttle_valid_2 = jmri.throttle(valid_addrs[1][0], long=valid_addrs[1][1])
    throttle_invalid = jmri.throttle(99999, long=True)

    with pytest.raises((ThrottleAcquireFailed, ExceptionGroup)) as excinfo:
        async with AsyncExitStack() as stack:
            await asyncio.gather(
                stack.enter_async_context(throttle_valid_1),
                stack.enter_async_context(throttle_valid_2),
                stack.enter_async_context(throttle_invalid),
            )
    # Whichever acquires entered the stack BEFORE the failure must have
    # been released by AsyncExitStack's unwind. Whichever were in-flight
    # at the moment of failure: their state is timing-dependent; assert
    # only on those that reached the entered state.
```

**And** the test asserts:

1. `excinfo` carries `ThrottleAcquireFailed` either as the top-level exception or inside an `ExceptionGroup` (Python 3.11+; `asyncio.gather` propagates the first exception by default, but the cancellation semantics under task supervision can wrap). Tolerate both shapes — the existing Story 5.1 test at line 77 catches `ThrottleAcquireFailed` directly via a single `async with`; this story's test catches one of the two shapes because gather + AsyncExitStack composes them differently.
2. For each `throttle_valid_*`, after the `pytest.raises` block exits: if `_throttle_id` was set (acquire succeeded for that one before the failure landed), then `_released is True` (AsyncExitStack unwound it). If `_throttle_id` is `None` (acquire was cancelled mid-flight), `_released is False` is acceptable — never-acquired throttles cannot be "released."

**And** the test docstring states: "Partial-acquire failure: AsyncExitStack must release whatever entered before the failure landed; never-acquired siblings are not released (and cannot be — they hold no JMRI session)."

**And** if the test discovers that `asyncio.gather`'s semantics under partial failure produce a non-deterministic mix of "entered vs cancelled-mid-flight" results, the test asserts on the INVARIANT ("nothing leaks; all `_throttle_id is not None` throttles are `_released`") NOT on a specific count. This is a deliberate looseness — the test guards against leaks, not against a specific timing outcome.

**And** the test does NOT assert on the JMRI server side (no follow-up GET to inspect server-side held sessions). The library invariant is what we own.

### AC6 — Module docstring documents the simulator/hardware split explicitly

**Given** the existing module docstring on `test_throttle_lifecycle.py` (lines 1–14)
**When** this story extends the file
**Then** the module docstring is updated to add a section covering:

1. The fact that the multi-throttle tests added in Story 5.3 verify *library plumbing only* on the simulator.
2. The simulator has no virtual decoder — see `project_throttle_simulator_blindspot.md` memory and Story 5.2 plumbing comment.
3. Physical-correctness verification requires real NCE hardware; the procedure is documented in `CONTRIBUTING.md`'s release checklist (Story 6.5, currently `backlog`). Reviewer reading the test must NOT mistake "test passes" for "throttles drive real locos."
4. The existing 4 tests from Stories 5.1 + 5.2 are also plumbing-only by the same reasoning; the docstring expansion applies retroactively to the file, not just the new tests.

**And** the docstring text uses the existing module-docstring style (declarative paragraphs, no decorative headers). The existing lines 3–8 already touch this topic ("These tests exercise library / JMRI plumbing only..."); the Story 5.3 expansion makes it more explicit and adds the cross-reference.

**And** the cross-reference to `CONTRIBUTING.md` uses the phrase "Story 6.5 (currently backlog)" so a reader doing time-traveling reads (e.g., on a 2026-old branch) understands the doc is forward-referenced and may not exist yet.

### AC7 — Existing 4 tests in `test_throttle_lifecycle.py` continue to pass unchanged

**Given** the file already contains:

- `test_throttle_acquire_release_roundtrip` (Story 5.1, line 27)
- `test_throttle_aexit_releases_cleanly` (Story 5.1, line 52)
- `test_throttle_acquire_failure_raises_throttle_acquire_failed` (Story 5.1, line 69)
- `test_set_speed_and_set_function_plumbing` (Story 5.2, line 85)

**When** this story adds the new tests from AC2, AC3, AC5
**Then** the 4 existing tests are NOT modified except for the module docstring update at AC6
**And** all 4 pre-existing tests continue to pass against the live JMRI simulator after the changes
**And** the total integration-test count for `test_throttle_lifecycle.py` rises from 4 to AT LEAST 7 (AC2 + AC3 + AC5 = 3 new tests; AC1's helper is not a test).

### AC8 — Test layout assumptions: live roster has ≥ 2 entries

**Given** the running JMRI simulator (`My_NCE_Simulator.jmri` profile shares the basement roster of ~45 locomotives via `jmri-jmrit-roster.directory=home:JMRI/`)
**When** the multi-throttle tests run
**Then** the roster-reader helper from AC1 gracefully `pytest.skip`s when the roster has fewer than the required entries; it does NOT fail.
**And** the skip message is informative: `"roster has {N} entries; multi-throttle test requires >= {required}"`.
**And** the test is layout-agnostic: a JMRI installation with an empty roster, a single-entry roster, or a roster of 100 entries all work without code change. Skips on insufficient, runs on sufficient.

### AC9 — Quality gates clean

**Given** the project-wide quality discipline (`feedback_use_uv.md` memory: always `uv run --no-sync`)
**When** the dev runs the quality gates
**Then** ALL the following pass cleanly:

- `uv run --no-sync ruff format` — no formatting changes pending
- `uv run --no-sync ruff check` — no lint errors across changed files
- `uv run --no-sync mypy --strict tests/integration/test_throttle_lifecycle.py` — no type errors
- `uv run --no-sync pytest -m "not integration"` — unchanged count vs. post-Story-5.2 baseline (411 passed, 19 deselected). Story 5.3 adds NO unit tests.
- `uv run --no-sync pytest -m "integration and not slow"` — passing against the live simulator; unit test count increases by ≥3 (the 3 new integration tests from AC2 + AC3 + AC5); pre-Story-5.3 baseline was 15 passed, 2 skipped.

**And** the story's `File List` section enumerates every changed/created file (1 modified file: `test_throttle_lifecycle.py`; the story file + sprint-status update bring the total to 3).
**And** no markdownlint warnings on this story file (memory `feedback_polish_matters.md`).

### AC10 — Hardware-mode protocol cross-reference is forward-compatible

**Given** the cross-reference added by AC6 to Story 6.5's `CONTRIBUTING.md`
**When** Story 6.5 is later implemented (FR42 / Epic 6) and creates `CONTRIBUTING.md` with the actual hardware validation procedure
**Then** the cross-reference text from AC6 must remain valid without modification.
**And** the cross-reference text MUST NOT name a specific path to a section header within `CONTRIBUTING.md` that does not yet exist — use the file name only, or a stable phrase like "the release checklist section" without a specific anchor.
**And** the cross-reference notes that the protocol is "documented in `CONTRIBUTING.md`'s release checklist (Story 6.5)" rather than a brittle anchor link. Story 6.5's author is responsible for adding a release-checklist section; this story is responsible for pointing at it conceptually.

## Tasks / Subtasks

- [x] **Task 1 — Add the roster-reader helper** (AC: 1, 8)
  - [x] Add `from __future__ import annotations`-compatible imports at the top of `test_throttle_lifecycle.py`: `import httpx`, `from typing import Any` (only if needed for type annotations). Imports go right after the existing `import asyncio` / `import pytest` block.
  - [x] Add the async helper `_fetch_test_dcc_addresses(count: int = 2) -> list[tuple[int, bool]]` at module level (after the existing `pytestmark = pytest.mark.integration` line and before the first test function).
  - [x] Helper validates count, opens raw `httpx.AsyncClient(base_url="http://localhost:12080")`, GETs `/json/v5/roster`, parses each entry's `data["address"]` and `data["isLongAddress"]`, returns first `count` entries.
  - [x] Helper calls `pytest.skip(...)` with an informative message if roster has < `count` entries.

- [x] **Task 2 — Update module docstring with simulator/hardware split** (AC: 6, 10)
  - [x] Replace the existing module docstring at `test_throttle_lifecycle.py:1-14` with an expanded version that explicitly covers: (1) plumbing-only verification on simulator (FR28 / NCE open-loop reminder), (2) hardware-mode protocol cross-reference to Story 6.5's `CONTRIBUTING.md` release checklist (currently backlog — forward-reference is intentional), (3) the existing 4 tests from 5.1 + 5.2 are governed by the same plumbing-only rule.
  - [x] Keep the existing Story 5.1 Task 0 spike note about WS-only throttle API (lines 10–14) — it remains accurate and is relevant to the new tests too.

- [x] **Task 3 — Implement `test_multi_throttle_parallel_acquire_drive_release`** (AC: 2, 4)
  - [x] Add the test function after `test_set_speed_and_set_function_plumbing` (current line 99). Follow the existing test naming and one-line-docstring style.
  - [x] Import `from contextlib import AsyncExitStack` at the top of the file alongside existing imports.
  - [x] Inside the test: open `Client()` context, fetch 2 roster entries, build 2 `Throttle` instances, enter both via `AsyncExitStack` + `asyncio.gather`, drive each (set_speed 0.1 fwd → set_function 0 on → set_speed 0.0 fwd → set_function 0 off), exit the stack.
  - [x] After the stack exits: assert each throttle's `_released is True`, then assert post-release `ThrottleReleased` raise on both `set_speed` and `set_function`, with `excinfo.value.context["dcc_address"] == t.dcc_address` (Story 5.2 review P4 pattern).

- [x] **Task 4 — Implement `test_multi_throttle_keepalive_tasks_cancel_on_release`** (AC: 3)
  - [x] Add a second multi-throttle test (separate function) right after Task 3's test.
  - [x] Acquire 2 throttles via AsyncExitStack (same pattern as Task 3).
  - [x] INSIDE the stack: assert each throttle's `_keepalive_task` is not `None` and not `done()`; assert task name `startswith("pyjmri-throttle-keepalive-")`; filter `asyncio.all_tasks()` for keep-alive tasks and assert exactly 2.
  - [x] AFTER the stack exits + one `await asyncio.sleep(0)`: assert each `_keepalive_task.done() is True`; re-filter `asyncio.all_tasks()` and assert no keep-alive tasks remain.

- [x] **Task 5 — Implement `test_multi_throttle_partial_acquire_failure_releases_siblings`** (AC: 5)
  - [x] Add the third multi-throttle test after Task 4's test.
  - [x] Open `Client()`, fetch 2 valid roster entries, build 2 valid + 1 invalid (`addr=99999, long=True`) `Throttle` instances.
  - [x] Wrap an AsyncExitStack + gather in `pytest.raises((ThrottleAcquireFailed, ExceptionGroup))` — tolerate both shapes per AC5's clarification.
  - [x] After the raise: for each valid throttle, if `_throttle_id is not None` (acquire succeeded before the failure landed), assert `_released is True` (AsyncExitStack unwound it). If `_throttle_id is None` (acquire was cancelled mid-flight), no assertion needed — never-acquired throttles cannot be released.
  - [x] Test docstring: "Partial-acquire failure: AsyncExitStack must release whatever entered before the failure landed; never-acquired siblings are not released."

- [x] **Task 6 — Quality gates + File List + Completion Notes** (AC: 9)
  - [x] Run `uv run --no-sync ruff format` — verify clean.
  - [x] Run `uv run --no-sync ruff check` — verify clean.
  - [x] Run `uv run --no-sync mypy --strict tests/integration/test_throttle_lifecycle.py` — verify clean.
  - [x] Run `uv run --no-sync pytest -m "not integration"` — verify unchanged count (411 passed).
  - [x] Run `uv run --no-sync pytest -m "integration and not slow"` — verify 3 new integration tests pass; baseline 15 → 18 passed; 2 skips unchanged.
  - [x] Self-scan story file for markdownlint warnings before declaring done (`feedback_polish_matters.md`).
  - [x] Update File List, Completion Notes, Change Log; set Status to `review`.

### Review Findings (AI code review — 2026-05-22)

- [x] [Review][Defer] `_fetch_test_dcc_addresses` unchecked JSON key access — `envelope["data"]`, `data["address"]`, and `data["isLongAddress"]` accessed without guard; a malformed roster entry raises `KeyError` rather than a clean skip. Pre-existing project pattern: 5 existing integration tests do identical unchecked roster/entity JSON access. [tests/integration/test_throttle_lifecycle.py] — deferred, pre-existing
- [x] [Review][Defer] Partial-acquire test: single `asyncio.sleep(0)` may not drain in-flight gather siblings — `asyncio.gather` propagates the first exception without cancelling sibling tasks; one event-loop tick may not be enough to complete WS round-trips in-flight when the failure lands. By-design per spec Dev Notes: "the test asserts on the INVARIANT (nothing leaks; all `_throttle_id is not None` throttles are `_released`) NOT on a specific count." [tests/integration/test_throttle_lifecycle.py] — deferred, pre-existing

## Dev Notes

### Authoritative current state of `python_code/` (verified 2026-05-21, post-Story-5.2-review)

**Source files in `src/pyjmri/`** (NOT modified by this story):

| File | Story 5.3 status |
| --- | --- |
| `throttle.py` | **UNCHANGED** — `Throttle.__aenter__`, `release`, `set_speed`, `set_function` already shipped (5.1 + 5.2). Keep-alive task naming: `f"pyjmri-throttle-keepalive-{dcc_address}"` (line 111). `_throttle_id: str \| None`, `_released: bool`, `_keepalive_task: asyncio.Task[None] \| None` are the lifecycle private attrs the test inspects. |
| `client.py` | **UNCHANGED** — `Client.throttle(dcc_address, long=...)` factory at line 600+; `Client.discover()` at line 655 (does NOT enumerate roster — Story 5.3 fetches roster directly). |
| `layout.py` | **UNCHANGED** — `Layout.throttle()` exists but is not invoked by the test (tests use `Client.throttle` per existing pattern). |
| `_protocols.py` | **UNCHANGED** — `ClientHandle.throttle_acquire` / `throttle_release` / `throttle_update` / `throttle_heartbeat` already defined. |
| `roster.py` | **UNCHANGED stub** — `__all__ = []`; no `Roster` / `RosterEntry` class. Story 5.3 does NOT implement these. |
| `_parsing.py` | **UNCHANGED** — `parse_roster_entry` exists (line 292) but is private. Story 5.3 fetches roster via raw HTTP, NOT via this function (keeps the test stand-alone). |
| `exceptions.py` | **UNCHANGED** — `ThrottleReleased`, `ThrottleAcquireFailed` already defined and re-exported in `__init__.py`. |
| All other source files | **UNCHANGED** |

**Test files:**

| File | Story 5.3 status |
| --- | --- |
| `tests/integration/test_throttle_lifecycle.py` | **MODIFY** — 4 tests exist (5.1 + 5.2); add 3 new tests + 1 module-level async helper. Update module docstring. |
| `tests/integration/conftest.py` | **UNCHANGED** — `jmri_available` session fixture probes TCP at `localhost:12080`; the new tests inherit it. |
| `tests/unit/conftest.py` | **UNCHANGED** — no `_FakeHandle` changes; this story has no unit tests. |
| `tests/unit/test_throttle.py` | **UNCHANGED** — Story 5.2's 28 tests stay as-is. |
| All other test files | **UNCHANGED** |

### Architecture rules carried forward (apply verbatim)

- `from __future__ import annotations` at the top of every Python module (already present in `test_throttle_lifecycle.py`).
- PEP 604 unions everywhere; no `Optional[X]`, no `Union[X, Y]`.
- Async tests: `async def test_*`; pytest-asyncio `asyncio_mode = "auto"` is set in `pyproject.toml`.
- `@pytest.mark.integration` is applied via `pytestmark = pytest.mark.integration` at module level (already in the file).
- Catch-name convention: `except <Type> as e:` — always `e`. Not used in this story (no `try/except` blocks needed).
- No mocks of JMRI. Integration tests use the real running JMRI. Raw `httpx` is allowed and precedented.
- Module-level logger NOT needed for tests.

### Roster fetch design rationale (read this before Task 1)

**Why fetch via raw `httpx` instead of `pyjmri.Client.discover()`?**

1. `Client.discover()` returns a `Layout` populated with 8 entity types — NOT rosterEntry. To make `discover()` populate the roster, one would extend `Client.discover()`'s TaskGroup and the `Layout` container — substantial scope creep that doesn't belong in a throttle-test story.
2. `Layout.roster` accessor doesn't exist — even if `Client.discover()` fetched the roster, there's no public API to read it. Adding the API is a Growth item.
3. The 5 existing integration tests that need raw HTTP (`test_reconnect_resilience.py:39, 57, 70, 134`; `test_wait_primitives_latency.py:31, 54, 84, 94`; `test_command_latency.py:32, 59`; `test_long_run.py:41, 77, 198`; `test_command_round_trip.py`) all use raw `httpx.AsyncClient` for similar reasons — they need a JMRI behavior that pyjmri's public API doesn't expose. This is an established pattern.

**Why not use `_parsing.parse_roster_entry` from the test?**

It's `_` -prefixed — private. Tests SHOULD respect the privacy boundary even when running in-process. The roster envelope shape is stable (per architecture line 39-43 and `_parsing.py:292-321`): each entry has `data.address` (string of int) and `data.isLongAddress` (bool). The test parses these two fields inline — adequate for picking test DCC addresses.

**Why not fetch the roster ONCE per session via a fixture?**

The 3 new tests each call `_fetch_test_dcc_addresses(2 or 3)` independently. The cost is one HTTP GET per test — negligible (~10 ms on localhost). A session-scoped fixture would shave milliseconds at the cost of fixture-scoping complexity. Choosing simplicity.

### Parallel acquire pattern: `AsyncExitStack` + `asyncio.gather`

**Why `AsyncExitStack` instead of raw `asyncio.gather` of `async with` blocks?**

`async with` blocks can only be opened in the source-code order they appear; they cannot be opened in parallel without `AsyncExitStack` (Python 3.11+ stdlib). The pattern:

```python
async with AsyncExitStack() as stack:
    throttles = await asyncio.gather(
        stack.enter_async_context(throttle1),
        stack.enter_async_context(throttle2),
    )
```

Has key properties:

1. **Parallel acquire:** `stack.enter_async_context(t)` returns a coroutine that calls `t.__aenter__()`; `asyncio.gather` runs them concurrently.
2. **LIFO unwind on exit:** When the `AsyncExitStack` exits (normally or on exception), it calls `__aexit__` on every successfully-entered context, in reverse order. This is exactly what we want for cleanup.
3. **Partial-failure handling:** If `t1.__aenter__()` succeeds but `t2.__aenter__()` raises, `asyncio.gather` raises and the stack has only `t1` entered — the stack's exit unwinds `t1` cleanly. (`t2` was never entered, so nothing to unwind.)

**Caveat on cancellation semantics under `asyncio.gather`:**

`asyncio.gather` with default args propagates the first exception and *does not* cancel siblings automatically — the siblings keep running. Mid-flight `__aenter__` calls on the other throttles may complete after the gather call raises; if `stack.enter_async_context(t).__aenter__()` completed, it was registered with the stack and will be unwound. If it didn't complete (cancellation-injected mid-`await`), it's not registered and won't be unwound. This is timing-dependent.

For the partial-acquire failure test (AC5), the invariant we test is "no leaks" — every throttle whose `_throttle_id is not None` is `_released`. We do NOT test a specific count.

### Keep-alive task inspection pattern

`Throttle.__aenter__` spawns the keep-alive at `throttle.py:109-112`:

```python
self._keepalive_task = self._handle.spawn_supervised(
    self._keepalive(),
    name=f"pyjmri-throttle-keepalive-{self.dcc_address}",
)
```

The current v1 keep-alive body is a no-op stub (`asyncio.Event().wait()`) — Story 5.1 confirmed JMRI's WS-level heartbeat keeps held throttles alive. The task is structurally supervised by `Client._task_group`. On `release()` or `__aexit__`, `throttle.py:258-267` cancels the task and awaits its `CancelledError`-driven termination.

**Filter pattern for `asyncio.all_tasks()`:**

```python
keepalive_tasks = [
    t for t in asyncio.all_tasks()
    if t.get_name().startswith("pyjmri-throttle-keepalive-")
]
```

This matches Story 5.3's specific tasks AND excludes:

- The current test task (we're not inside one named `pyjmri-throttle-keepalive-*`).
- The Client TaskGroup's WS reconnect-and-receive loop (named differently per `_transport.py`).
- Any pytest-internal tasks.
- Any other supervised tasks the architecture grows in future stories (they'll have different naming prefixes — see `Throttle.__aenter__:111` for the convention).

**Cancellation-finalization yield:**

Tests that observe `task.done()` after cancel MUST yield with `await asyncio.sleep(0)` once (or more — `test_throttle_lifecycle.py:41, 63` use single yield) so the cancelled task's `CancelledError` handler completes. The Python asyncio task machinery sets `Task._must_cancel`; `super().cancel()` runs before `super().set_result()` only after the event loop iterates. Without the yield, `task.done()` can race-spuriously be `False`. Story 5.1's existing tests use exactly one `await asyncio.sleep(0)` — sufficient empirically.

### Cross-story implications

- **Story 6.5 (CONTRIBUTING.md release checklist):** Story 5.3's module docstring cross-references it. Story 6.5 is currently `backlog`. The cross-reference uses the phrase "Story 6.5 (currently backlog)" so a reader on an old branch understands the forward reference. AC10 mandates that no specific anchor link is used — only the file name and section description.
- **Story 6.4 (shipped examples):** `back_and_forth.py` and `multi_train_session.py` will use the same `set_speed`/`set_function` patterns the multi-throttle test exercises. Story 5.3 is the canonical reference for "how to drive multiple throttles in parallel" — the shipped examples should not invent a different pattern. (Out of scope for 5.3 — just a forward-looking note.)
- **Roster public API (Growth):** When a future story implements `Layout.roster` and the `Roster` / `RosterEntry` classes, the `_fetch_test_dcc_addresses` helper from AC1 SHOULD be refactored to use the public API. That's a Growth refactor, not a Story 5.3 obligation. The helper's signature (`-> list[tuple[int, bool]]`) is stable across that refactor.

### Risks and mitigations

- **R1: Roster on the simulator profile has fewer than 2 entries.** Unlikely — the basement layout has ~45 locos and all profiles share `~/JMRI/roster/`. Mitigation: the AC1 helper `pytest.skip`s cleanly; no test failure. A reviewer who runs on an empty-roster profile sees the skip message and knows what to do.
- **R2: `asyncio.gather` partial-failure semantics differ across Python versions.** The test pins to Python 3.11+ (per `pyproject.toml`) and the AsyncExitStack pattern has been stable since 3.7. Mitigation: AC5's test asserts on the leak invariant, not on a specific count of cancelled-vs-completed siblings.
- **R3: Task name `startswith` match catches keep-alive tasks from PREVIOUS test functions that leaked.** If a previous test in the file leaked a keep-alive task, AC3's count assertion (`len == 2`) would fail. Mitigation: the existing 4 tests (5.1 + 5.2) all release their throttles cleanly; if a leak ever appears, it's a 5.1/5.2 regression that this test would catch — desirable behavior. Defensively, AC3's test runs `await asyncio.sleep(0)` before the count check to let any straggler tasks finalize.
- **R4: Roster JSON shape changes in a future JMRI release.** The `_parsing.parse_roster_entry` function in `_parsing.py:292` is the authoritative parser; it expects `data.address` and `data.isLongAddress`. If JMRI 5.15+ changes those field names, both the parser AND the AC1 helper would break together — symmetric breakage, easy to spot. Mitigation: the test pins to JMRI 5.14+ (NFR8 / Story 2.5 version check); if a future JMRI changes the wire format, that's a separate breakage story.
- **R5: `httpx.AsyncClient` opened inside the helper does not close cleanly on test failure.** Mitigation: the helper uses `async with httpx.AsyncClient(...) as raw_http:` — Python's async context manager handles cleanup on exception. Pattern verified in 5 other integration tests.
- **R6: `ExceptionGroup` vs `ThrottleAcquireFailed` shape difference under `asyncio.gather`.** Per Python's stdlib docs, `asyncio.gather` with `return_exceptions=False` raises the first exception directly — usually `ThrottleAcquireFailed`. But when wrapped in an `AsyncExitStack` whose unwind itself can raise during a body exception, Python may wrap them as `ExceptionGroup`. AC5 mandates `pytest.raises((ThrottleAcquireFailed, ExceptionGroup))` to tolerate both shapes. Dev should run the test once to verify which shape it actually produces and tighten the tuple if the broader catch is unnecessary.

### Carry-forward learnings from Story 5.2 code review (2026-05-21)

- **P4 — `ThrottleReleased.context["dcc_address"]` assertion pattern:** Established by Story 5.2 review. Story 5.3's AC4 + AC5 inherit this pattern explicitly — every `pytest.raises(ThrottleReleased) as excinfo:` block asserts `excinfo.value.context["dcc_address"] == <expected_addr>`. This is the AC3-style discipline from Story 5.2.
- **P5 — `caplog` for INFO log verification:** Not relevant to this story. Story 5.2 added two caplog tests for `set_speed` / `set_function` logging. Story 5.3 doesn't add new logging contracts; the existing 5.1/5.2 INFO logs are exercised but not asserted on (would duplicate unit-test assertions for no integration-test gain).
- **P1 — `bool`/`float` type discipline for `set_function(n, ...)`:** Story 5.2 added an `isinstance(n, int) and not isinstance(n, bool)` guard. Story 5.3's tests call `set_function(0, True)` and `set_function(0, False)` — `0` is a valid `int`, NOT a `bool`. No regression risk.
- **D1 — TOCTOU lock-free design:** Acknowledged in Story 5.2's Dev Notes R4. Story 5.3 does NOT concurrently call `release()` from one task while another calls `set_speed` on the same throttle — that's still a user-doesn't-fight-themselves invariant.
- **Polish discipline:** Self-scan story file for markdownlint warnings before declaring done. The `\[Review/Patch\]` escape pattern from Story 5.2 review findings is an example of the discipline; this story has no Review Findings section yet but the markdownlint scan applies to all sections.

### References

- `_bmad-output/planning-artifacts/epics.md:885-924` — Epic 5 + Story 5.3 acceptance criteria (this story's source).
- `_bmad-output/planning-artifacts/architecture.md:536-558` — Concurrency Model (TaskGroup ownership, supervised tasks, keep-alive structure).
- `_bmad-output/planning-artifacts/architecture.md:670-707` — Test Harness (integration markers, `jmri_available` fixture, layout-agnostic discipline).
- `_bmad-output/planning-artifacts/architecture.md:893-916` — Testing Patterns (file naming, marker discipline, no JMRI mocks, raw httpx allowed).
- `_bmad-output/planning-artifacts/architecture.md:1118-1123` — Throttle & Locomotive Control file mapping.
- `_bmad-output/planning-artifacts/prd.md:790-797` — FR23–FR28 verbatim.
- `_bmad-output/planning-artifacts/prd.md:437-438` — Scene C ghost throttle (FR28 honesty).
- `_bmad-output/implementation-artifacts/5-2-throttle-speed-direction-function-controls.md` — Previous story (Story 5.2, status `done` post-review). Pattern source for: integration test docstrings, `ThrottleReleased.context["dcc_address"]` assertions, fire-and-forget semantics, integration test layout.
- `_bmad-output/implementation-artifacts/5-1-throttle-async-context-manager-acquire-release-lifecycle-keep-alive-supervision.md` — Story 5.1, status `done`. Pattern source for: keep-alive task naming, lifecycle invariants, integration tests at `test_throttle_lifecycle.py:27-82`.
- `_bmad-output/implementation-artifacts/deferred-work.md:1-7` — Story 5.2 deferred items (D1, D2, D3 acknowledged as by-design or pre-existing).
- `python_code/tests/integration/test_throttle_lifecycle.py` — Existing 4 tests; extend with 3 new tests + 1 helper.
- `python_code/tests/integration/test_reconnect_resilience.py:39, 57, 70, 134` — Raw `httpx.AsyncClient` precedent (fixture pattern).
- `python_code/tests/integration/test_wait_primitives_latency.py:31, 54, 84, 94` — Raw httpx precedent (in-test client).
- `python_code/tests/integration/test_long_run.py:41, 77, 136, 198` — Raw httpx + `asyncio.all_tasks()` filtering precedent.
- `python_code/src/pyjmri/throttle.py:109-112` — Keep-alive task spawn line (naming convention).
- `python_code/src/pyjmri/throttle.py:258-267` — Keep-alive task cancellation in `_release_impl`.
- `python_code/src/pyjmri/_parsing.py:292-321` — `parse_roster_entry` (private; reference for envelope shape, NOT called from the test).
- `python_code/src/pyjmri/client.py:655` — `Client.discover()` (8 entity types; does NOT include roster).
- `python_code/src/pyjmri/exceptions.py:23-45` — `JMRIError` base class with `.context` dict.
- `python_code/src/pyjmri/exceptions.py:123-128` — `ThrottleAcquireFailed`, `ThrottleReleased`.
- Memory: `feedback_use_uv.md` — always `uv run --no-sync` for pytest/mypy/ruff/python in this project.
- Memory: `project_throttle_simulator_blindspot.md` — NCE simulator accepts throttle commands but has no virtual decoder; plumbing-only verification on simulator. Story 5.3 codifies this in the module docstring.
- Memory: `project_nce_open_loop.md` — NCE open-loop applies equally on simulator and on Mikey's real layout. Only throttle/loco testing requires real hardware.
- Memory: `project_throttle_name_internal.md` — Throttle WS correlation name is pyjmri-internal; user-facing API exposes only DCC address.
- Memory: `feedback_polish_matters.md` — self-scan markdownlint warnings on story files before declaring done.

### Project Structure Notes

- ALL new code lives under `python_code/tests/integration/test_throttle_lifecycle.py`. NO new files.
- NO changes to `python_code/src/pyjmri/` — Story 5.3 is test-only.
- NO changes to `python_code/tests/unit/` — Story 5.3 adds NO unit tests.
- NO changes to `.jmri/` profiles, `jython/` scripts, `roster/` directory, or `roster.xml`. The test READS the roster via JMRI's JSON API; it does not modify any layout assets.
- NO `__init__.py` re-export changes.
- The `_bmad-output/implementation-artifacts/deferred-work.md` file is NOT updated by this story (no new deferred items expected — Story 5.3's scope is fully addressable).

### Acceptable test patterns from Stories 5.1 + 5.2 (inherit verbatim)

- One-line docstrings on each test function describing the invariant (NOT multi-paragraph). Match existing style at lines 28-30, 53-54, 73-75, 86-89.
- `await asyncio.sleep(0)` after cancelling/releasing to let tasks finalize. Existing precedent: lines 41 and 63.
- `with pytest.raises(...) as excinfo:` then assert `excinfo.value.context.get("...") == ...` for diagnostic context (existing precedent: line 77, line 81-82).
- `async with Client() as jmri:` and `jmri.throttle(addr, long=...)` factory — NOT `Layout.throttle()` from `layout.py` (consistency with the existing 4 tests in this file).
- Test names follow `test_<scenario>` snake_case; length is fine; clarity beats brevity. Architecture line 900 mandates this.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Opus 4.7, 1M context) via Claude Code dev-story workflow.

### Debug Log References

- Initial run of `test_multi_throttle_keepalive_tasks_cancel_on_release` failed at the post-stack assertion `assert keepalive is not None` because `Throttle._release_impl` sets `self._keepalive_task = None` after cancelling (`throttle.py:281`). Fixed by saving keep-alive task references into a local `keepalive_refs` list before exiting the stack — same pattern Story 5.1 uses at `test_throttle_aexit_releases_cleanly:100-108`. After the fix all 7 tests in the file pass on the simulator.
- One transient failure observed in `test_command_round_trip.py::test_turnout_wait_for_jmri_state_round_trip` during the full integration run; passed in isolation and on the next full-suite run. Unrelated to Story 5.3 — that test was unchanged.

### Completion Notes List

- Added the `_fetch_test_dcc_addresses` module-level async helper (AC1, AC8). Reads JMRI's `/json/v5/roster` via raw `httpx` and skips cleanly if the roster has fewer than the required entries. Public `Layout.roster` remains Growth-deferred — the helper is the documented test-only workaround.
- Added three new integration tests in `test_throttle_lifecycle.py` (AC2/AC4, AC3, AC5):
  - `test_multi_throttle_parallel_acquire_drive_release` — parallel acquire of 2 throttles via `AsyncExitStack` + `asyncio.gather`; sequential drive (set_speed / set_function round-trip); post-release `ThrottleReleased` invariant on every throttle with `excinfo.value.context["dcc_address"]` discipline carried forward from Story 5.2 review P4.
  - `test_multi_throttle_keepalive_tasks_cancel_on_release` — keep-alive task lifecycle via `asyncio.all_tasks()` filter (`startswith("pyjmri-throttle-keepalive-")`) plus exact-equality name check per throttle. Task references saved into a local list before stack exit because `_release_impl` clears the throttle's `_keepalive_task` attribute.
  - `test_multi_throttle_partial_acquire_failure_releases_siblings` — 2 valid + 1 invalid (99999) parallel acquire; tolerates `(ThrottleAcquireFailed, ExceptionGroup)` per AC5; `await asyncio.sleep(0)` after the `pytest.raises` block lets any in-flight `enter_async_context` tasks settle before assertion. Invariant asserted: every valid throttle with `_throttle_id is not None` is `_released is True`; the invalid throttle has `_throttle_id is None` and `_released is False`.
- Expanded the module docstring (AC6, AC10) to document the simulator/hardware split explicitly and forward-reference Story 6.5's `CONTRIBUTING.md` release checklist (currently backlog) using the conceptual phrase rather than a brittle anchor link. The Story 5.1 Task 0 spike note about WS-only throttle API is preserved at the bottom of the docstring.
- Quality gates clean (AC9): `ruff format`, `ruff check`, `mypy --strict tests/integration/test_throttle_lifecycle.py`, unit suite `411 passed, 22 deselected` (unchanged), integration suite `18 passed, 2 skipped, 413 deselected` (baseline 15 + 3 new = 18; skips unchanged).
- Story 5.3 is test-only — NO changes to `python_code/src/pyjmri/`. NO new unit tests. NO new files. `test_throttle_lifecycle.py` is the sole modified source file in `python_code/`.

### File List

- `python_code/tests/integration/test_throttle_lifecycle.py` (modified — expanded module docstring; added `_fetch_test_dcc_addresses` helper and three new integration tests)
- `_bmad-output/implementation-artifacts/5-3-multi-throttle-integration-test-plumbing-on-simulator-physical-correctness-on-hardware.md` (modified — task checkboxes, Dev Agent Record, Change Log, Status)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — Story 5.3 ready-for-dev → in-progress → review; `last_updated` advanced to 2026-05-22)

## Change Log

- 2026-05-21 — Story 5.3 created (`backlog` → `ready-for-dev`). Test-only story: extends `tests/integration/test_throttle_lifecycle.py` with a roster-reader helper + 3 new tests (parallel acquire/drive/release, keep-alive task lifecycle via `asyncio.all_tasks()` inspection, partial-acquire failure releases siblings). Layout-agnostic via raw `httpx` roster fetch (precedent in 5 existing integration tests; public `Layout.roster` API is Growth-deferred). Module docstring updated to document simulator/hardware split + cross-reference to Story 6.5's `CONTRIBUTING.md` release checklist (forward-reference; Story 6.5 currently backlog). NO changes to `src/pyjmri/`. Carry-forward patterns from Story 5.2 review: `excinfo.value.context["dcc_address"]` discipline (P4), markdownlint self-scan (polish discipline). FR23–FR28 exercised in composition; FR42 cross-referenced via Story 6.5.
- 2026-05-22 — Story 5.3 implemented (`ready-for-dev` → `in-progress` → `review`). Added `_fetch_test_dcc_addresses` helper and three new integration tests (`test_multi_throttle_parallel_acquire_drive_release`, `test_multi_throttle_keepalive_tasks_cancel_on_release`, `test_multi_throttle_partial_acquire_failure_releases_siblings`); expanded module docstring with explicit simulator/hardware split and Story 6.5 cross-reference. All 7 throttle-lifecycle integration tests pass against the live `My_NCE_Simulator.jmri` profile (basement roster). Quality gates clean: `ruff format` / `ruff check` / `mypy --strict` pass; unit suite holds at 411 passed; integration `not slow` rises from 15 to 18 passed with 2 skips unchanged. One mid-implementation fix: post-release keep-alive assertions now read from saved local refs because `_release_impl` clears `Throttle._keepalive_task` (same pattern as Story 5.1's `test_throttle_aexit_releases_cleanly`).
