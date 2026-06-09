# Story 7.1: Fix integration-test inter-test interference on shared first-entity

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a pyjmri maintainer running the integration suite before a release,
I want the full integration suite (`pytest -m "integration and not slow"`) to pass cleanly on two consecutive runs without retries — even when pytest-cov is instrumenting the code path,
So that release-checklist Step 4 doesn't depend on luck-of-the-draw timing, and so that a flaky-looking test result during release work is a *real* signal of regression rather than known-flake noise.

## Origin

This story comes from Epic 6 retrospective (`epic-6-retro-2026-05-26.md`), action item **C3**. Two flake events observed during Story 6.6 Phase B and the post-ship coverage run:

1. **2026-05-26 Phase B Step 4 (first integration run):** `test_sensor_wait_change_median_latency_under_100ms` (NFR1) timed out on `IS1` from `INACTIVE`. Isolated re-run passed cleanly (median 15.5 ms). Second full-suite run also clean (median 37.9 ms).
2. **2026-05-26 post-ship coverage run (`uv run --with pytest-cov pytest --cov=pyjmri`):** `test_turnout_wait_for_jmri_state_round_trip` timed out from `set_state(..., wait_for_jmri_state=True)` after 5.0 s. Same pattern under coverage instrumentation overhead.

Both tests share two structural traits:

- They pick the **first** entity from `discover()` (`sensors[0]`, `turnouts[0]`) — meaning they all target the *same* JMRI entity (`IS1` for sensors, the first turnout for turnouts), so earlier tests' state leakage and JMRI's per-entity rate limits hit them all.
- They have **tight wall-clock timeouts** (2.0 s for the NFR1 latency test, 5.0 s for the round-trip) — timeouts calibrated against a quiet, just-restarted JMRI, not against JMRI under suite load.

Coverage of integration tests that follow this pattern (from `grep -l "sensors\[0\]\|turnouts\[0\]\|iter(layout" tests/integration/*.py`): `test_command_round_trip.py`, `test_command_latency.py`, `test_command_wait_reconnect.py`, `test_long_run.py`, `test_discovery.py`. Likely also relevant: `test_wait_primitives_latency.py` (uses `sensors[0]` explicitly).

## Scope notes

- **Not a behavior change in the production library.** All v1.0.0 functional and non-functional requirements are unchanged. This story improves *test discipline*; the library itself ships v1.0.0 unmodified through this work.
- **Two release-time symptoms, one root cause.** Solving the shared-first-entity pattern fixes both observed flakes and any latent flakes on other entities (lights, blocks, signal heads) that follow the same pattern.
- **Not a new test framework.** Reuse the existing `jmri_available` fixture and the raw-httpx state-force pattern from `test_wait_primitives_latency.py`. Don't introduce a new test helper module unless three or more tests would share it.
- **The goal is "two consecutive full-suite runs pass" — not 100 consecutive runs.** Eliminating the *systematic* inter-test interference is the gate; eliminating every conceivable transient flake is out of scope.

## Acceptance Criteria

**AC1 — Identify all integration tests that pick a shared first-entity**

**Given** the current state of `python_code/tests/integration/`
**When** Story 7.1 begins
**Then** every test that obtains its target entity via `layout.X[0]`, `next(iter(layout.X))`, or any other "pick the first one" pattern is enumerated in this story's File List
**And** for each, the story records: (a) which entity collection it taps, (b) whether it mutates state on that entity, (c) the test's timeout budget

**AC2 — Each shared-first-entity test gets an explicit, non-overlapping entity target**

**Given** AC1's enumeration
**When** the story lands
**Then** no two integration tests share the same JMRI entity (sensor, turnout, light, block, route) as their command/wait target during a single suite run
**And** the chosen entities are documented in each test's docstring with system name (e.g., `IS1`) and rationale (e.g., "isolated internal sensor — no other test uses it")
**And** entity selection is **system-name-pinned**, not positional — tests should look up entities by explicit name (`layout.sensors.by_system_name("IS1")`), not by `sensors[0]` (FR43: layout-agnostic remains via skip-if-missing, not by picking whatever happens to be first)
**And** if a test's target entity is not present on the discovered layout, the test skips cleanly with a clear message naming the missing entity (`pytest.skip(f"sensor 'IS1' not on this layout — required for NFR1 latency test")`)

**AC3 — State-reset discipline between tests on the same entity**

**Given** AC2 holds for *most* tests, but the integration suite may legitimately have multiple tests touching the same entity (e.g., a "set to A" test and a "set to B" test that share a turnout for valid reasons)
**When** two or more tests target the same entity by system name
**Then** each test ensures a known starting state for its entity at the start of the test — via raw `httpx` POST (the existing pattern from `test_wait_primitives_latency.py`) — and asserts the post-state matches expectation before measuring
**And** the test does NOT assume the entity's state was set correctly by a previous test; it always forces a starting state explicitly

**AC4 — Timeouts calibrated against suite-load reality, not quiet-JMRI ideal**

**Given** the observed flakes were both tight-timeout cases under load (NFR1's 2 s, AC10's 5 s)
**When** Story 7.1 reviews timeouts on shared-first-entity tests
**Then** any wall-clock timeout under 10 s is justified in a comment with the calibration rationale (NFR budget, AC requirement, or "observed P99 under suite-load is N ms")
**And** for the NFR1 sensor-latency test specifically, the **median assertion stays at 100 ms** (NFR1 is the spec; we don't relax it), but the per-trial `wait_change(timeout=...)` budget rises from 2.0 s to **5.0 s** to absorb suite-load variance without changing the assertion floor
**And** for the AC10 turnout round-trip test, the `asyncio.timeout(5.0)` budget rises to **10.0 s** with a comment noting "AC10 budget; tight enough to catch regressions, loose enough to survive coverage instrumentation"
**And** any test that still trips a tightened timeout under coverage is investigated as a real bug, not silently widened

**AC5 — Full suite passes twice in a row without retries**

**Given** AC1–AC4 are in place
**When** the maintainer runs `uv run --no-sync pytest -m "integration and not slow"` twice consecutively from a clean state
**Then** both runs report `0 failed`
**And** the maintainer also runs once with `uv run --with pytest-cov pytest -m "not slow" --cov=pyjmri` and the failure count is `0`
**And** all three runs are recorded in this story's Completion Notes (run timestamps, exit codes, brief metric summaries from the NFR1 line and the long-run summary if it ran)

**AC6 — Memory update**

**Given** the story completes
**When** the memory entry `feedback_writable_paths.md` or a sibling memory is reviewed
**Then** a new memory entry (or update to an existing one) captures the discipline: **"integration tests must pin entities by system name and force a known starting state; never rely on positional `[0]` indexing into discovered collections"** — so future story dev agents follow the same pattern without re-deriving it from this story

## Tasks / Subtasks

- [x] **Task 1 — Audit and enumerate** (AC: 1)
  - [x] Run `grep -nE "(sensors|turnouts|lights|blocks|routes|signal_heads|signal_masts)\\[0\\]|next\\(iter\\(layout" tests/integration/*.py`
  - [x] Open each match and record: file, test name, entity collection, mutating vs read-only, timeout
  - [x] Add the enumeration to this story's "Notes" section under a new "## Enumeration" heading

- [x] **Task 2 — Pick non-overlapping entity targets per test** (AC: 2)
  - [x] For sensors: use `IS1` (already used by NFR1 test) for one test; pick a different *internal* sensor (`IS2`, `IS3`, etc., or whichever is available on the basement layout) for any other sensor-mutating test
  - [x] For turnouts: pick from the NCE-provided turnouts (`NT100`, `NT102`, `NT104`, etc.); never pick a turnout that's also used by a route the layout depends on
  - [x] For lights/blocks/signals: only relevant if the layout has them (basement layout has 0 lights, 93 blocks, 12 signal heads/masts) — most current tests skip these anyway; document the pinned choice if a test uses them
  - [x] Replace every `layout.X[0]` / `next(iter(layout.X))` with `layout.X.by_system_name("...")` calls
  - [x] Add `pytest.skip(...)` fallback if the named entity is missing (preserves FR43 layout-agnosticism)

- [x] **Task 3 — Force known starting state in each affected test** (AC: 3)
  - [x] Each test that mutates an entity begins with a raw-httpx POST to set the entity to a known starting state (shared `force_sensor_state` / `force_turnout_state` helpers in `tests/integration/_entity_state.py`, extracted per the "3+ tests share it" rule)
  - [x] Each test asserts the starting state is correct (turnouts via authoritative HTTP `get_state()`; sensor via `wait_state(...)`) before proceeding to measurement
  - [x] After the test's assertions, reset the entity to a documented "default" state (sensor INACTIVE, turnout CLOSED) in teardown

- [x] **Task 4 — Calibrate timeouts against suite-load reality** (AC: 4)
  - [x] Bump `test_sensor_wait_change_median_latency_under_100ms` per-trial `wait_change(timeout=...)` from `2.0` to `5.0`; keep NFR1's median assertion at 100 ms
  - [x] Bump `test_turnout_wait_for_jmri_state_round_trip` `asyncio.wait_for(..., timeout=5.0)` to `10.0`
  - [x] Add inline comments justifying each timeout value with the calibration rationale (NFR budget, AC reference, or empirical P99 observation)
  - [x] Survey remaining integration tests for any other `timeout` value under 10 s that lacks a justification comment; add one or widen the timeout as appropriate

- [x] **Task 5 — Verify on simulator** (AC: 5)
  - [x] From `python_code/`, run `uv run --no-sync pytest -m "integration and not slow"` twice consecutively
  - [x] From `python_code/`, run `uv run --with pytest-cov pytest -m "not slow" --cov=pyjmri --cov-report=term` once
  - [x] All three runs must report `0 failed`
  - [x] Paste the summary lines (passes / skips / runtime) into this story's Completion Notes

- [x] **Task 6 — Update memory** (AC: 6)
  - [x] Write or update a memory entry capturing the "pin by system name + force starting state" discipline for future integration test work
  - [x] Link from `MEMORY.md` if a new file is created

- [x] **Task 7 — Quality gates pass** (release-checklist Step 1)
  - [x] `uv run --no-sync ruff check` clean
  - [x] `uv run --no-sync ruff format --check` clean (do NOT skip per `feedback_ruff_format_gate.md`)
  - [x] `uv run --no-sync mypy --strict src/pyjmri` clean
  - [x] `uv run --no-sync pytest -m "not integration"` clean (unit suite unchanged)

### Review Findings

- [x] \[Review\]\[Decision\] **AC2 doc gap: entity pins live in module-level comments, not per-function docstrings** — Accepted: module-level comment table satisfies AC2's intent. No per-function docstrings required.
- [x] \[Review\]\[Decision\] **AC3 gap: light tests don't force a known starting state** — Accepted: light tests always skip (0 lights on this layout); AC3 exemption for skip-only entities documented. No force_light_state needed.
- [x] \[Review\]\[Patch\] **`_entity_state.py`: force helpers silently map unsupported states** `_entity_state.py:49,63` — Fixed: both helpers now raise `ValueError` for any state other than the two supported values.
- [x] \[Review\]\[Patch\] **`test_command_wait_reconnect.py`: `raw_http` opened outside `try` — resource leak + aclose not suppressed** `test_command_wait_reconnect.py:73-134` — Fixed: restructured to use `async with httpx.AsyncClient(...) as raw_http:` matching all other test files; explicit `aclose()` call removed.
- [x] \[Review\]\[Patch\] **`test_wait_primitives_latency.py`: inner and outer timeouts use the same value** `test_wait_primitives_latency.py:82-88` — Fixed: added `_STARTING_STATE_INNER_TIMEOUT_S = 4.5` s; outer remains 5.0 s.
- [x] \[Review\]\[Defer\] **`JMRI_BASE_URL` hardcodes `localhost`** `_entity_state.py:30` — pre-existing; all test files previously hardcoded `http://localhost:12080`. Out of scope for this maintenance story.
- [x] \[Review\]\[Defer\] **`max_ms < _WAIT_CHANGE_TIMEOUT_S * 1000.0` vacuously true** `test_wait_primitives_latency.py:144` — a trial that exceeded the per-trial timeout would have already cancelled the waiter, not contributed to `samples_ms`. Pre-existing; original assertion `max_ms < 2000.0` had the same property.
- [x] \[Review\]\[Defer\] **`statistics.median` on empty list in `test_command_latency.py`** — pre-existing structural gap; not introduced by this diff.
- [x] \[Review\]\[Defer\] **Negative overhead values possible in latency test** — pre-existing; overhead is computed as `call_total - jmri_http_baseline_ms` which can go negative if the HTTP baseline was measured faster than individual calls. Out of scope.

## Dev Notes

- **No production source change.** Every file touched is under `tests/integration/`. The wheel content of v1.0.0 stays untouched; this story does not bump `pyproject.toml [project].version`.
- **No `dist/` rebuild.** Same reason — `src/pyjmri/**` is not modified.
- **Layout dependency:** the basement simulator layout has `IS1`, `IS2`, `IS3`, ... (internal sensors), plus NCE sensors `NS*`. Confirm the chosen test-pinned names exist by running `discover()` and listing `layout.sensors` and `layout.turnouts` before pinning.
- **Polish discipline (`feedback_polish_matters.md`):** markdownlint self-scan this story file before declaring done. No `**Why X?**` bold-as-heading lines; every fenced code block has a language tag; heading levels increment cleanly.
- **uv discipline (`feedback_use_uv.md`):** every tool invocation goes through `uv run --no-sync` (or `uv run --with X` when `X` is one-shot).
- **Ruff format discipline (`feedback_ruff_format_gate.md`):** run BOTH `ruff check` AND `ruff format --check` before committing changed test files.

## Out of scope

- **Reorganizing test fixtures into a shared `conftest.py` helper module.** If three or more tests would share the same "force entity to known state" helper, then extract it — but two or fewer means keep it inline (premature abstraction is its own bug).
- **Headless-JMRI CI infrastructure.** Growth-deferred per architecture; integration tests remain local-only for v1.x.
- **Reworking the long-run test (`test_long_run.py`).** Out of scope for this story; the long-run uses its own entity-selection strategy and ran cleanly during Phase B Step 5.
- **Adding new behavioral test coverage** (e.g., signal heads, blocks). Coverage gaps documented in the post-ship coverage report (`htmlcov/`) are tracked separately, not addressed here.
- **Replacing the simulator with mocks.** Architecture invariant: integration tests use live JMRI. This story stays inside that invariant.

## References

- `_bmad-output/implementation-artifacts/epic-6-retro-2026-05-26.md` — Action item C3 (origin)
- `python_code/tests/integration/test_wait_primitives_latency.py` — NFR1 sensor latency test; observed flake on `IS1`; pattern source for raw-httpx state-force
- `python_code/tests/integration/test_command_round_trip.py:151-185` — AC10 turnout round-trip test; observed flake under coverage instrumentation
- `python_code/htmlcov/index.html` — coverage snapshot showing the gaps (block/light/signal) that are *separate* from this story's scope
- Memory: `feedback_ruff_format_gate.md` — both ruff gates must pass
- Memory: `feedback_use_uv.md` — uv run --no-sync discipline
- Memory: `feedback_polish_matters.md` — markdownlint self-scan before done

## Enumeration

AC1: every integration test that obtained its target entity positionally
(`collection[0]` or `next(iter(layout.X))`). Markers determine whether a
test runs in the AC5 verification runs (`integration and not slow`) — the
two `slow` tests do not.

| File | Test | Marker | Collection | Original access | Mutates? | Original timeout | Resolution |
|---|---|---|---|---|---|---|---|
| `test_wait_primitives_latency.py` | `test_sensor_wait_change_median_latency_under_100ms` | integration | sensors | `sensors[0]` | yes | `wait_change` 2.0 s | pin `IS1`; force INACTIVE; 2.0→5.0 s |
| `test_command_round_trip.py` | `test_turnout_round_trip` | integration | turnouts | `turnouts[0]` | yes | none (optimistic) | pin `NT100`; force CLOSED |
| `test_command_round_trip.py` | `test_light_round_trip` | integration | lights | `lights[0]` | yes (skips: 0 lights) | none | pin `IL1`; skip-if-missing |
| `test_command_round_trip.py` | `test_memory_round_trip` | integration | memories | `memories[0]` | yes | none | pin `IM:AUTO:0001` (deterministic) |
| `test_command_round_trip.py` | `test_route_activate_round_trip` | integration | routes | `routes[0]` | trigger | none | pin `IO:AUTO:0001` (no state) |
| `test_command_round_trip.py` | `test_turnout_wait_for_jmri_state_round_trip` | integration | turnouts | `turnouts[0]` | yes | `wait_for` 5.0 s | pin `NT102`; force CLOSED; 5.0→10.0 s |
| `test_command_round_trip.py` | `test_light_wait_for_jmri_state_round_trip` | integration | lights | `lights[0]` | yes (skips: 0 lights) | `wait_for` 5.0 s | pin `IL1`; skip; 5.0 s justified |
| `test_command_wait_reconnect.py` | `test_wait_for_jmri_state_resolves_after_ws_reconnect` | integration | turnouts | `turnouts[0]` | yes | `wait_for` 15.0 s | pin `NT104`; force CLOSED |
| `test_reconnect_resilience.py` | `test_in_flight_wait_survives_forced_disconnect` | integration | sensors + turnouts | `sensors[0]`, `turnouts[0]` | yes | `_COMMAND_TIMEOUT_S` 5.0 s | pin `IS2` + `NT106`; force states; 5.0 s justified |
| `test_discovery.py` | `test_discover_layout_has_turnouts_sensors_and_blocks` | integration | turnouts | `next(iter(...))` | no (read-only) | n/a | pin `NT100` (read-only probe) |
| `test_command_latency.py` | `test_turnout_command_overhead_median_under_20ms` | integration, **slow** | turnouts | `turnouts[0]` | yes | n/a (perf budget) | pin `NT108`; force CLOSED |
| `test_long_run.py` | `test_long_run_stability` | integration, **slow** | sensors | `sensors[0]` | yes | own strategy | **out of scope** (story §Out of scope) — left as-is |

`test_ws_connect.py`, `test_connection_lifecycle.py`, and
`test_throttle_lifecycle.py` were checked and do **not** select layout
entities positionally (throttle uses DCC addresses from the roster), so
they are not shared-first-entity tests.

## Dev Agent Record

### Completion Notes

Root cause confirmed and fixed: the two v1.0.0 release flakes were both
on the **first entity** of a discovered collection (`IS1`, first turnout)
under suite/coverage load. Every mutating integration test now (a) pins
its target by **system name** via `by_system_name(...)` with a clean
skip-if-missing fallback (FR43), (b) targets a **distinct** entity so no
two tests contend for one JMRI object in a run, and (c) **forces a known
starting state** via raw `httpx` before measuring. Shared force-state
helpers were extracted to `tests/integration/_entity_state.py` (5 tests
share the turnout helper — above the "3+ → extract" threshold).

**Real bug found (not in the original task list):** forcing a turnout to
a known starting state surfaced a long-latent **inverted turnout state
code** copied from `test_reconnect_resilience.py` (`THROWN=2, CLOSED=4`).
JMRI's actual codes are `CLOSED=2, THROWN=4` (see
`pyjmri._codes.TURNOUT_STATE_OUTBOUND`). The inversion never failed
before because the reconnect test's turnout path always skipped on the
NCE simulator (no WS echo). The shared helper now uses the correct codes.
This is exactly the AC4 "investigate as a real bug, not silently widen"
case.

**AC5 verification (2026-06-09):**

- Run 1 — `uv run --no-sync pytest -m "integration and not slow"`: **18 passed, 2 skipped, 415 deselected in 3.76s**, exit 0. NFR1 median 44.9 ms (p95 157.9 ms).
- Run 2 (consecutive) — same command: **18 passed, 2 skipped, 415 deselected in 3.41s**, exit 0. NFR1 median 40.9 ms (p95 51.2 ms).
- Coverage — `uv run --with pytest-cov pytest -m "not slow" --cov=pyjmri --cov-report=term`: **431 passed, 2 skipped, 2 deselected in 4.63s**, exit 0. TOTAL coverage 92%.

The 2 skips each run are the two light tests (basement layout has 0
lights — clean skip-by-name). No production source (`src/pyjmri/**`) was
modified; v1.0.0 ships unchanged. Quality gates (Task 7): `ruff check`
clean, `ruff format --check` clean (60 files), `mypy --strict src/pyjmri`
clean, unit suite **413 passed** (baseline unchanged).

### File List

- `python_code/tests/integration/_entity_state.py` — **new**; shared raw-httpx force-state helpers + JMRI state codes
- `python_code/tests/integration/test_wait_primitives_latency.py` — pin `IS1`, force INACTIVE, timeout 2.0→5.0 s, use shared helper
- `python_code/tests/integration/test_command_round_trip.py` — pin `NT100`/`NT102`/`IL1`/`IM:AUTO:0001`/`IO:AUTO:0001`, force states, AC10 timeout 5.0→10.0 s
- `python_code/tests/integration/test_command_wait_reconnect.py` — pin `NT104`, force CLOSED, use shared helper
- `python_code/tests/integration/test_reconnect_resilience.py` — pin `IS2`+`NT106`, drop duplicate helpers for shared module
- `python_code/tests/integration/test_command_latency.py` — pin `NT108`, force CLOSED, use shared helper
- `python_code/tests/integration/test_discovery.py` — pin `NT100` read-only probe by name
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — story 7.1 status transitions
- `~/.claude/.../memory/feedback_integration_test_entity_pinning.md` — **new** memory + `MEMORY.md` pointer (AC6)

## Change Log

| Date | Note |
|---|---|
| 2026-05-26 | Story created from Epic 6 retro action item C3; first story of v1.0.x maintenance epic (Epic 7) |
| 2026-06-09 | Implemented AC1–AC6: pinned all shared-first-entity tests by system name, added force-starting-state discipline (shared `_entity_state.py` helpers), calibrated timeouts, fixed a latent inverted turnout-code bug. AC5 verified (2 consecutive clean runs + coverage). Status → review. |
