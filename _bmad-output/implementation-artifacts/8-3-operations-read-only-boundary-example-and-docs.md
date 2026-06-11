# Story 8.3: Read-only boundary test + Operations example + docs + v1.1 release

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a JMRI layout owner,
I want a worked example and documentation showing how to inspect my Operations session from Python, plus a test that nails down the read-only boundary,
so that I can write my own "where is every car" reports (PRD Journey 5), understand that Operations is read-only in this increment, and install it from PyPI as pyjmri v1.1.

## Acceptance Criteria

1. **Read-only boundary test (FR49).** A unit test asserts that the `Operations` container **and** each of its entity classes (`Location`, `Train`, `Car`, `Engine`, plus the nested value objects `Track`, `Placement`, `RouteStop`) expose **no** mutating/command method — specifically none of `build`, `move`, `assign`, `manifest`, `set_state`, `set_value`, and no command/wait/throttle method. The test mirrors the existing absence-of-method pattern (`assert hasattr(obj, "<name>") is False`). It is a unit test (unmarked, runs under `pytest -m "not integration"`).

2. **Read-only boundary stated in docs.** The documentation states that Operations discovery is read-only in v1.1, with a forward pointer to the Vision command increment (build train / move-assign car / generate manifest are deliberately deferred).

3. **`operations_report.py` example realizes PRD Journey 5.** A new `examples/operations_report.py` connects, calls `discover_operations()`, and prints: every location; each train with its current location; and each car with its location and train assignment. It runs against `Basement_Revised_2024.jmri` (Operations data loaded) **without modification**.

4. **The example degrades gracefully.** When no Operations data is configured, the example prints an explanatory message — **not** a traceback, and **not** empty sections. This covers two distinct cases: (a) FR50 — JMRI returns empty Operations collections (a valid `Operations`, not an exception) → detect the all-empty state and print a clear message; (b) JMRI unreachable / protocol failure → catch the relevant exceptions and print a friendly message. The example passes `mypy --strict examples/`.

5. **Docs Operations section.** Documentation explains the **roster-vs-Operations distinction** (the roster catalogs every engine programmed in DecoderPro; Operations is the operationally-active subset actually deployed) and states that **Operations read-only discovery is fully simulator-testable** (a pure data subsystem, not subject to the throttle/sensor open-loop blind spot).

6. **CONTRIBUTING records the Operations test-data setup.** `CONTRIBUTING.md` records the Operations data setup needed to run the Operations integration tests (the basement profile's Operations data — the suite is **not** layout-agnostic). The unit-test baseline figure in `CONTRIBUTING.md` is updated to the current count.

7. **v1.1.0 release prepared.** The version is bumped `1.0.1 → 1.1.0`, `uv.lock` regenerated, `RELEASES.md` gains a `## v1.1.0` entry, a clean `uv build` + `twine check dist/*` pass, and all Phase-A quality gates are green (`ruff check`, `ruff format --check`, `mypy --strict src/pyjmri`, `mypy --strict examples/`, `pytest -m "not integration"`). **The production `uv publish` + git tag is Mikey's manual Phase-B step (PyPI credentials) and is NOT performed by the dev agent** — no throttle-hardware validation is required (Operations is read-only data).

> **Scope fence:** Tests + example + docs + version bump + build + RELEASES.md draft only. Do **NOT** modify any Epic 1–6 behavior, the Story 8.1 entity classes/parsers (`operations.py` entity defs, `_parsing.py`, `_codes.py`), `layout.py` `EntityCollection`, or `Client.discover` / `discover_operations` logic. Do **NOT** add any command/mutating surface to Operations (that is Vision, not this story). Do **NOT** run the production `uv publish`, create the git tag, or publish a GitHub release — those are Mikey's manual Phase-B steps.

## Tasks / Subtasks

- [x] **Task 1 — Read-only boundary test** (AC: #1)
  - [x] Create `tests/unit/test_operations_boundary.py` (unit test, unmarked — `asyncio_mode = "auto"`, no `integration` marker).
  - [x] Mirror the absence-of-method pattern from `tests/unit/test_route.py:22-27` (`assert hasattr(obj, "<name>") is False`). Build real instances of each Operations type (use `load_fixture` to parse real `Car`/`Engine`/`Location`/`Train` from `tests/unit/fixtures/operations/*`, and construct nested `Track`/`Placement`/`RouteStop` directly or pull them from the parsed entities), plus an `Operations()` container.
  - [x] For every Operations class assert the absence of: `build`, `move`, `assign`, `manifest`, `set_state`, `set_value`, `set_speed`, `throttle`, `command`, `wait`, `get_state`, `get_value`. For the `Operations` container also assert no `discover`, `throttle`, or `set_*` surface — only `locations`/`trains`/`cars`/`engines` attributes.
  - [x] Do NOT duplicate the frozen-immutability checks already in `tests/unit/test_operations_parsing.py:244-257` (`test_entities_are_frozen` / `test_nested_value_objects_are_frozen`) — this test covers method *absence*, which those do not.

- [x] **Task 2 — `examples/operations_report.py`** (AC: #3, #4)
  - [x] Copy the structure and the `_fmt` / `_fmt_placement` helpers and the `print_operations` rendering body from `examples/show_discovery.py` (it is a near-complete prototype). Use the standard `--url` argparse flag + `async def main` + `asyncio.run(main(_parse_args()))` skeleton shared by all examples.
  - [x] Open the module docstring with a "PRD Journey 5" line. Foreground the "where is every car" report and the roster-vs-Operations contrast (≈45 engines in the roster vs the handful deployed).
  - [x] Per Journey 5, call `await jmri.discover()` then `await jmri.discover_operations()` inside the `async with`. The report focus is Operations; you may omit the full layout dump (`print_layout`) — it is not part of Journey 5.
  - [x] **Graceful degradation (a) — empty data (FR50):** after discovery, if all four collections are empty (`len(ops.locations) == 0 and ... engines == 0`), print an explanatory message (e.g. "No Operations data is configured in this JMRI profile — nothing to report.") and return, instead of printing empty sections. `discover_operations()` returns a valid empty `Operations` here; it does **not** raise.
  - [x] **Graceful degradation (b) — unreachable/malformed:** wrap connect+discovery in error handling that prints a friendly one-line message (not a traceback). Catch `JMRIConnectionError`, `JMRIRequestTimeout`, `JMRIVersionUnsupported`, and `JMRIProtocolError`. **CRITICAL:** `discover_operations()` runs its four fetches in an `asyncio.TaskGroup`, so a per-type failure propagates wrapped in an `ExceptionGroup` (unlike `discover()`, this path is not unwrapped — see Dev Notes). Use `except*` (Python 3.11+) for the grouped types, or catch `ExceptionGroup` alongside the bare connection types. Verify by reading `client.py:826-829`.
  - [x] Handle `None` everywhere in output: `Car.location`/`destination`/`Engine.location`/`destination` are `Placement | None`; `.train` is `str | None`; `Train.current_location`/`route`/`lead_engine` are `str | None`; most `user_name` are `str | None`. The `_fmt`/`_fmt_placement` helpers already cover these — reuse them.
  - [x] Ensure `mypy --strict examples/` passes for the new file (the existing examples are already strict-clean).

- [x] **Task 3 — Docs: README Operations section** (AC: #2, #5)
  - [x] Add a new `## Operations` (or `## Inspecting an Operations session`) H2 to `README.md`, placed after `## Limitations` (after line 106) and before/after `## Migrating from Jython`. Operations is NOT mentioned anywhere in README yet.
  - [x] Cover: (1) roster-vs-Operations distinction — paraphrase the FR48 framing already written in `operations.py:124-133` (Engine docstring); (2) "Operations read-only discovery is fully simulator-testable"; (3) the read-only boundary in v1.1 with a forward pointer to the Vision command increment (no build/move/manifest surface yet). Point readers at `examples/operations_report.py`.
  - [x] Optionally add Operations rows to the Jython→pyjmri migration table (`README.md:114-127`) mapping JMRI Operations idioms to `discover_operations()`.

- [x] **Task 4 — Docs: CONTRIBUTING + baseline** (AC: #6)
  - [x] In `CONTRIBUTING.md` `## Running integration tests locally` pre-conditions (line ~64-70, esp. line 67 "Most integration tests are layout-agnostic..."), add an Operations note: the Operations integration tests are **not** layout-agnostic — they need the `Basement_Revised_2024.jmri` Operations data (3 locations / 4 engines / 3 cars / 1 train / 1 route). The NCE simulator profile without Operations data exercises only the empty path.
  - [x] Also note this at release-checklist step 4 (line ~126, "or the simulator") — the simulator alone is insufficient for the Operations suite.
  - [x] Update the unit-test baseline figure (currently `411 passed, 22 deselected` at `CONTRIBUTING.md:43`, `:51`, `:124`) to the verified current count. Current `pytest -m "not integration"` = **441 passed / 25 deselected** before this story; re-run after Task 1 adds the boundary test and use that exact number in all three places.

- [x] **Task 5 — v1.1.0 release prep (Phase A only)** (AC: #7)
  - [x] Bump `pyproject.toml:3` `version = "1.0.1"` → `version = "1.1.0"`. This is the ONLY code/config version edit — there is no `__version__` in `src/`. Then run `uv lock` so `uv.lock`'s pyjmri version matches.
  - [x] Do NOT touch historical version strings (`CONTRIBUTING.md:158` "0.1.0", `RELEASES.md` prior entries, `release-check/INSTRUCTIONS.md`, integration-test comments) — they document history, not the live version.
  - [x] Add a `## v1.1.0` section to `RELEASES.md` above the `## v1.0.1` line (line 3), following the v1.0.1 template: prose summary of the Operations read-only additions (Epic 8: `discover_operations()`, `Operations` container, four read-only entity classes, example, docs), "JMRI version tested against" (5.14.0), and — per the v1.0.1 precedent (`RELEASES.md:17-21`) — a note that the 1-hour long-run and throttle-hardware validation are **reused/waived** because Operations adds only read paths (no transport/reconnect/throttle changes). Leave the `(Published YYYY-MM-DD)` footer as a placeholder for Mikey to fill at publish time.
  - [x] Phase-A build + verify (no credentials): `rm -rf dist/ && uv build`; confirm `py.typed` in the wheel and METADATA has `Requires-Python: >=3.11` + MIT + `Description-Content-Type: text/markdown`; `twine check dist/*` → PASSED.
  - [x] Phase-A gates (all green): `uv run --no-sync ruff check`, `ruff format --check`, `mypy --strict src/pyjmri`, `mypy --strict examples/`, `pytest -m "not integration"`.
  - [x] **STOP at the publish boundary.** Do NOT run production `uv publish`, do NOT `git tag`, do NOT create a GitHub release. Leave the story for Mikey's manual Phase-B publish (and code-review). Record in Completion Notes exactly what Phase-B steps remain.

- [x] **Task 6 — Final verification**
  - [x] Run `examples/operations_report.py` against the live basement JMRI (`localhost:12080`, Operations data loaded) and confirm it prints the Journey-5 report without modification (AC #3).
  - [x] Confirm all Phase-A gates green and the boundary test passes. Record the final unit-test count.

## Dev Notes

### What this story is, in one sentence

Epic 8's capstone: prove the read-only boundary with a test, ship the Journey-5 example and the Operations docs, and prepare (not publish) pyjmri v1.1.0 — all additive, no behavior changes to existing code.

### Established patterns to FOLLOW (read these first; do not reinvent)

- **Boundary test pattern** — `tests/unit/test_route.py:22-27` (`test_route_has_no_get_state`): constructs a real instance, then `assert hasattr(instance, "<method>") is False`, one assertion per forbidden name (explicit denylist, NOT a `dir()` allowlist). This is the exact shape to mirror. Epics.md:765-768 describes the analogous v1 read-only contract for Block/SignalHead/SignalMast but only frames it as reviewer inspection — `test_route.py` is the one codified runnable example.
- **Frozen-already-covered** — `tests/unit/test_operations_parsing.py:244-257` already asserts the entities are `frozen` (attribute immutability). Your new test covers a different axis (method *absence*); do not duplicate the frozen checks.
- **Example skeleton** — all of `examples/{hello_jmri,back_and_forth,multi_train_session,show_discovery}.py` share: `from __future__ import annotations`; Google-style module docstring opening with a PRD-Journey line; `--url` argparse flag (`default=None`; `Client(url) if url is not None else Client()`); `async def main(args) -> None`; `if __name__ == "__main__": asyncio.run(main(_parse_args()))`.
- **`show_discovery.py` is your prototype** — `examples/show_discovery.py:22-98` already imports the right surface, has `_fmt`/`_fmt_placement` None-safe helpers, and a `print_operations(ops)` that renders locations/trains/cars/engines correctly via `.values()`. Copy it; the deltas for `operations_report.py` are (1) graceful degradation and (2) Journey-5 framing. `show_discovery.py` itself bills itself as distinct from this curated example (`show_discovery.py:7-8`), so keep both.

### Operations API surface (for the example and the test)

- Container `Operations` (`operations.py:184-237`): attrs `.locations`/`.trains`/`.cars`/`.engines`, each an `EntityCollection`. **Iterate with `.values()`** — bare iteration yields system-name strings (`layout.py:115-117`), a trap the PRD snippet falls into. `len(coll)` gives counts.
- `Car.name` is road+number (e.g. `"AA123"`); there is **no** `car.road_number` attribute (the PRD snippet is illustrative, not literal — use `car.name`). `Car`/`Engine` `user_name` is always `None`.
- `None`-bearing fields needing graceful output: `Car/Engine.location`, `.destination` (`Placement | None`), `.train` (`str | None`); `Train.current_location`, `.route`, `.lead_engine` (`str | None`); most `user_name` (`str | None`). FR48: both assigned and unassigned engines occur in practice.
- Full per-class field inventory is in `operations.py` (Location:76-89, Train:147-181, Car:92-113, Engine:116-144, Placement:44-58, Track:32-41, RouteStop:61-73). None of the 8 classes defines any method — they are pure attribute carriers (`frozen=True, slots=True`); `Operations` has only `__init__`.

### `discover_operations()` error-surface — the one real gotcha

`discover_operations()` (`client.py:771-854`) fetches the four types in an `asyncio.TaskGroup`; a per-type failure propagates **wrapped in an `ExceptionGroup`** and is NOT unwrapped (this was reviewed and intentionally left consistent with `discover()` in Story 8.2 — both raise raw groups). So the example's graceful-degradation block must use `except*` (3.11+) or catch `ExceptionGroup` in addition to the bare `JMRIConnectionError`/`JMRIRequestTimeout`/`JMRIVersionUnsupported`/`JMRIProtocolError`. The empty-data case (FR50) is the opposite — it does NOT raise; `discover_operations()` returns an `Operations` with four empty collections, which you must detect by length.

### Release intelligence (Phase A vs Phase B)

- **Current version is `1.0.1`** (not 1.0.0) — both already shipped to PyPI. The bump is `1.0.1 → 1.1.0`.
- **Single version source:** `pyproject.toml:3` + `uv.lock` (via `uv lock`) + a new `RELEASES.md` section. No `__version__` in the package.
- **Phase A (this story / dev agent):** bump, docs, build, twine check, all gates. **Phase B (Mikey, manual):** re-run gates, run Operations integration tests against live JMRI with Operations data, TestPyPI dry-run, `uv publish`, fresh-venv smoke install, `git tag v1.1.0`, GitHub release. The dev agent HALTs before publish (mirrors Story 6.6's design where dev sets the story to `review`, not `done`).
- **Skipped for this release** (read-only data, per AC #7 and the v1.0.1 precedent at `RELEASES.md:17-21`): the 1-hour long-run test (reuse prior evidence — no transport/reconnect changes) and Step 6 hardware-mode throttle validation (no throttle code touched). The relevant Phase-B gate is the **Operations integration test** against live JMRI, which Mikey runs.
- Full step-by-step release procedure: `_bmad-output/implementation-artifacts/6-6-first-pypi-publication-of-pyjmri-v1.md` (Phase A 159-198, Phase B 265-492) and `CONTRIBUTING.md:88-195`.

### Testing Requirements

- New unit test is unmarked (CI runs `pytest -m "not integration"`); `asyncio_mode = "auto"` (`pyproject.toml:69`) — no `@pytest.mark.asyncio` needed (the boundary test is likely synchronous anyway).
- Re-run `uv run --no-sync pytest -m "not integration"` after adding the test and update the three CONTRIBUTING baseline references to match (was 441/25 pre-story).
- Run BOTH `ruff check` AND `ruff format --check` (CI gates both), plus `mypy --strict src/pyjmri` AND `mypy --strict examples/`. Use `uv run --no-sync` for every tool invocation.

### Project Structure Notes

- New files: `tests/unit/test_operations_boundary.py`, `examples/operations_report.py`. Edits: `README.md`, `CONTRIBUTING.md`, `RELEASES.md`, `pyproject.toml`, `uv.lock`.
- There is no `examples/README.md` or example index — no registration needed. There is no `docs/` directory; all docs are top-level Markdown (`README.md`, `CONTRIBUTING.md`, `RELEASES.md`, `SECURITY.md`).
- Writable paths only: `python_code/` and `_bmad-output/`. Do not touch `.jmri` profiles or shared JMRI assets.

### Previous Story Intelligence (8.2)

- 8.2 delivered `Operations` + `discover_operations()` and was reviewed clean (commit `60b93e0`): all 11 ACs met, no scope-fence violations. The 8.2 review confirmed `discover()` and `discover_operations()` both raise raw `ExceptionGroup`s (consistent) — this is why the example must handle the group, not a bare exception.
- 8.2 deferred three low/pre-existing `EntityCollection` items (duplicate-key collapse, user-name shadowing) to `deferred-work.md` — out of scope here; do not address.
- The basement profile has live Operations data (verified this session via `discover_operations()`): 3 locations / 4 engines / 3 cars / 1 train (TestTrainOne on Test_Route, "Partial 3/27 cars"). The example will print exactly this when run against `localhost:12080`.

### Git / recent-work intelligence

- Recent commits (`60b93e0`, `840ab61`, `11bd55c`) are the 8.2 review, the `show_discovery.py` demo, and a docs correction (basement layout is 38 blocks / no sections — relevant if you cite layout counts in docs). Use `examples/show_discovery.py` as the live, tested rendering reference.

### References

- [Source: epics.md#Story 8.3 (lines 1214-1241)] — acceptance criteria
- [Source: epics.md#Epic 8 (1146-1153); FR45-FR50 (99-104)] — read-only scope policy, FR49 boundary
- [Source: architecture.md#Operations Subsystem (Read-Only) (579-642)] — handle-free read-only design; "FR49 enforced by the class surface" (605-611); fully-simulator-testable (629-634)
- [Source: prd.md#Journey 5 (473-518)] — the example's narrative spec (note: code snippet is illustrative; iterate `.values()`, use `car.name`)
- [Source: tests/unit/test_route.py:22-27] — boundary-test pattern to mirror
- [Source: examples/show_discovery.py] — rendering prototype to copy
- [Source: 6-6-first-pypi-publication-of-pyjmri-v1.md; CONTRIBUTING.md:88-195] — Phase A/B release pattern
- [Source: RELEASES.md:3-28] — v1.0.1 entry = template for the v1.1.0 entry (non-hardware release)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (1M context) — `claude-opus-4-8[1m]`

### Debug Log References

- Boundary test: 169 cases pass (8 Operations types × 21 forbidden method names + 1 container allowlist test).
- Example verified three ways against live JMRI (`localhost:12080`, basement Operations data): populated Journey-5 report (3 loc / 1 train / 3 cars / 4 engines); empty-data path via `print_report(Operations())` → explanatory message; unreachable path via `--url localhost:12099` → friendly one-liner, no traceback.
- Operations integration suite re-run against live JMRI: 3 passed.
- Phase-A gates all green: `ruff check` (All checks passed), `ruff format --check` (67 files), `mypy --strict src/pyjmri` (22 files), `mypy --strict examples/` (5 files), `pytest -m "not integration"` → **610 passed / 25 deselected** (up from 441/25).
- Build: `uv build` → `pyjmri-1.1.0.tar.gz` + `pyjmri-1.1.0-py3-none-any.whl`; `twine check dist/*` PASSED; wheel carries `py.typed`; METADATA `Version: 1.1.0`, `Requires-Python: >=3.11`.

### Completion Notes List

- **AC1 (boundary test):** `tests/unit/test_operations_boundary.py` mirrors the `test_route.py` `hasattr(...) is False` denylist across all 8 Operations types, plus a `dir()`-based allowlist asserting `Operations` exposes exactly `{locations, trains, cars, engines}` and no methods/handle. Did not duplicate the existing frozen-immutability checks (different axis).
- **AC2 / AC5 (docs):** new `## Operations (read-only)` README section covers the roster-vs-Operations distinction, "fully simulator-testable," and the read-only boundary with a forward pointer to the future command increment. Added two Operations rows + note (e) to the Jython migration table.
- **AC3 / AC4 (example):** `examples/operations_report.py` realizes Journey 5 (locations; trains + current location; cars + location + train assignment), runs unmodified against the basement profile, and degrades gracefully on both the empty-data (FR50) and unreachable/malformed paths. The `except* JMRIError` block handles the `ExceptionGroup` wrapping from `discover_operations()`'s TaskGroup (confirmed against `client.py:826-829`) as well as bare connection errors. Passes `mypy --strict examples/`.
- **AC6 (CONTRIBUTING):** updated the unit-test baseline (610/25) in all three places and recorded the Operations integration-test data requirement (not layout-agnostic; basement profile or simulator-with-Operations-data) in both the pre-conditions and release step 4.
- **AC7 (release prep — Phase A only):** bumped `pyproject.toml` 1.0.1 → 1.1.0, regenerated `uv.lock`, added the `## v1.1.0` RELEASES.md entry (long-run reused, hardware validation waived — read-only data), clean build + twine check + all gates green. **STOPPED at the publish boundary** per the scope fence.
- **Remaining Phase-B steps for Mikey (manual, not done here):** re-run gates + Operations integration tests against live JMRI; TestPyPI dry-run; `uv publish` to production PyPI; fresh-venv smoke install; `git tag v1.1.0` + push; GitHub release; fill the `(Published YYYY-MM-DD)` date in RELEASES.md. No throttle-hardware validation required.
- **Scope fence honored:** no Epic 1–6 behavior, Story 8.1 entity classes/parsers, `_codes.py`, `EntityCollection`, or `discover`/`discover_operations` logic was modified. No mutating surface added.

### File List

- `python_code/tests/unit/test_operations_boundary.py` (new) — read-only boundary test
- `python_code/examples/operations_report.py` (new) — Journey-5 example
- `python_code/README.md` (modified) — Operations section + migration rows
- `python_code/CONTRIBUTING.md` (modified) — Operations test-data setup + baseline 610/25
- `python_code/RELEASES.md` (modified) — v1.1.0 entry
- `python_code/pyproject.toml` (modified) — version 1.0.1 → 1.1.0
- `python_code/uv.lock` (modified) — pyjmri 1.1.0

## Change Log

| Date | Change |
| --- | --- |
| 2026-06-11 | Story 8.3 implemented: read-only boundary test, `operations_report.py` example, README Operations docs, CONTRIBUTING test-data + baseline update, v1.1.0 release prep (Phase A). All Phase-A gates green (610 passed / 25 deselected). Status → review. Phase-B publish remains a manual maintainer step. |
