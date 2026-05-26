# Story 7.1: Fix integration-test inter-test interference on shared first-entity

Status: ready-for-dev

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

- [ ] **Task 1 — Audit and enumerate** (AC: 1)
  - [ ] Run `grep -nE "(sensors|turnouts|lights|blocks|routes|signal_heads|signal_masts)\\[0\\]|next\\(iter\\(layout" tests/integration/*.py`
  - [ ] Open each match and record: file, test name, entity collection, mutating vs read-only, timeout
  - [ ] Add the enumeration to this story's "Notes" section under a new "## Enumeration" heading

- [ ] **Task 2 — Pick non-overlapping entity targets per test** (AC: 2)
  - [ ] For sensors: use `IS1` (already used by NFR1 test) for one test; pick a different *internal* sensor (`IS2`, `IS3`, etc., or whichever is available on the basement layout) for any other sensor-mutating test
  - [ ] For turnouts: pick from the NCE-provided turnouts (`NT100`, `NT102`, `NT104`, etc.); never pick a turnout that's also used by a route the layout depends on
  - [ ] For lights/blocks/signals: only relevant if the layout has them (basement layout has 0 lights, 93 blocks, 12 signal heads/masts) — most current tests skip these anyway; document the pinned choice if a test uses them
  - [ ] Replace every `layout.X[0]` / `next(iter(layout.X))` with `layout.X.by_system_name("...")` calls
  - [ ] Add `pytest.skip(...)` fallback if the named entity is missing (preserves FR43 layout-agnosticism)

- [ ] **Task 3 — Force known starting state in each affected test** (AC: 3)
  - [ ] Each test that mutates an entity begins with a raw-httpx POST to set the entity to a known starting state (use the `_post_sensor_state` / equivalent pattern from `test_wait_primitives_latency.py`)
  - [ ] Each test asserts the starting state is correct (via `await entity.wait_state(starting, timeout=3.0)`) before proceeding to measurement
  - [ ] After the test's assertions, optionally reset the entity to a documented "default" state (e.g., sensor INACTIVE, turnout CLOSED) — improves the *next* test's clean-start probability but is not required if AC2's non-overlap holds

- [ ] **Task 4 — Calibrate timeouts against suite-load reality** (AC: 4)
  - [ ] Bump `test_sensor_wait_change_median_latency_under_100ms` per-trial `wait_change(timeout=...)` from `2.0` to `5.0`; keep NFR1's median assertion at 100 ms
  - [ ] Bump `test_turnout_wait_for_jmri_state_round_trip` `asyncio.timeout(5.0)` to `asyncio.timeout(10.0)`
  - [ ] Add inline comments justifying each timeout value with the calibration rationale (NFR budget, AC reference, or empirical P99 observation)
  - [ ] Survey remaining integration tests for any other `timeout` value under 10 s that lacks a justification comment; add one or widen the timeout as appropriate

- [ ] **Task 5 — Verify on simulator** (AC: 5)
  - [ ] From `python_code/`, run `uv run --no-sync pytest -m "integration and not slow"` twice consecutively
  - [ ] From `python_code/`, run `uv run --with pytest-cov pytest -m "not slow" --cov=pyjmri --cov-report=term` once
  - [ ] All three runs must report `0 failed`
  - [ ] Paste the summary lines (passes / skips / runtime) into this story's Completion Notes

- [ ] **Task 6 — Update memory** (AC: 6)
  - [ ] Write or update a memory entry capturing the "pin by system name + force starting state" discipline for future integration test work
  - [ ] Link from `MEMORY.md` if a new file is created

- [ ] **Task 7 — Quality gates pass** (release-checklist Step 1)
  - [ ] `uv run --no-sync ruff check` clean
  - [ ] `uv run --no-sync ruff format --check` clean (do NOT skip per `feedback_ruff_format_gate.md`)
  - [ ] `uv run --no-sync mypy --strict src/pyjmri` clean
  - [ ] `uv run --no-sync pytest -m "not integration"` clean (unit suite unchanged)

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

## Change Log

| Date | Note |
|---|---|
| 2026-05-26 | Story created from Epic 6 retro action item C3; first story of v1.0.x maintenance epic (Epic 7) |
