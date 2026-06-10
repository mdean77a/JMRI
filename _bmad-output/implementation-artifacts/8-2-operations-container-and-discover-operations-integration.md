# Story 8.2: `Operations` container + `Client.discover_operations()` + integration

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a library user,
I want `await jmri.discover_operations()` to enumerate every Operations entity from a running JMRI and return a typed `Operations` container,
so that I can inspect my whole operating session — locations, trains, cars, engines — in one call, looked up by name.

## Acceptance Criteria

1. **`Operations` container class exists** in `src/pyjmri/operations.py`. It holds four `EntityCollection` attributes — `locations`, `trains`, `cars`, `engines` — reusing `EntityCollection[T]` from `layout.py` unchanged (FR45–FR47). Each constructor parameter is keyword-only and defaults to an empty `EntityCollection` with the matching `entity_type`, so `Operations()` is a valid empty snapshot (mirrors `Layout()`). (FR45–FR47, FR50)
2. **`Operations` is read-only and handle-free (FR49).** Unlike `Layout` (which holds a `ClientHandle` for `.throttle()`), `Operations` takes **no** `handle` and exposes **no** command, set, wait, or throttle method — only the four collection attributes. Read-only is enforced by the class surface. (The exhaustive boundary test is Story 8.3; do not add command methods here.)
3. **`Client.discover_operations()` is implemented** in `src/pyjmri/client.py`. It issues `GET /json/v5/{entity_type}` for `location`, `train`, `car`, `engine` **in parallel** via `asyncio.TaskGroup`, reusing the existing `_fetch_collection` helper (same pattern as `discover()`). It parses each envelope with the Story 8.1 parsers (`parse_location` / `parse_train` / `parse_car` / `parse_engine`), assembles four `EntityCollection`s, and returns a populated `Operations`. (FR45–FR48)
4. **`discover_operations()` is a separate entry point from `discover()`** — it is **not** folded into `discover()`, returns `Operations` (not `Layout`), and **does not mutate** the Client's WS-dispatch index (`self._entities`). Epic 1–6 behavior is byte-for-byte unchanged (Epic 8 scope policy). (Architecture: separate container/entry point)
5. **Version gate is honored and shared.** `discover_operations()` performs the same JMRI ≥ 5.14 version check `discover()` does, gated on and caching `self._version_checked` — so the probe fires once per Client whether the user calls `discover()`, `discover_operations()`, or both, in any order. (NFR8)
6. **Empty Operations data yields empty collections, not an error (FR50).** When JMRI returns `[]` for every Operations type, `discover_operations()` returns an `Operations` whose four collections are each empty (`len == 0`) and raises nothing. This path is covered by a **unit test** (mocked transport returning `[]`), because the basement profile now has Operations data loaded and can no longer exercise the empty path live — see Dev Notes "AC wording drift".
7. **Populated discovery works against live JMRI (integration).** An `@pytest.mark.integration` test calls `discover_operations()` against the running basement simulator (which has Operations data loaded: 3 locations / 4 engines / 3 cars / 1 train), asserts every collection is non-empty, and asserts entities resolve by **both** system and user name (locations/trains) and by system name (cars/engines). It skips cleanly via the `jmri_available` fixture when JMRI is unreachable. (FR45–FR47)
8. **Timing within the NFR2 Operations bound.** The integration test times `discover_operations()` and asserts it completes within ≤ 1 s for the basement-sized Operations roster (NFR2: layout discovery plus ≤ 1 s additional for Operations). Call `discover()` first to warm the version check, then time `discover_operations()` alone so the measurement maps to the "additional 1 second" budget. (NFR2)
9. **Layout-agnostic — no hardcoded Operations entity names or counts in `src/pyjmri/`** (FR43/FR50 invariant). Discovery operates on whatever JMRI returns; only the entity-**type** strings (`"location"`, `"train"`, `"car"`, `"engine"` — JMRI API types, not layout entity names) appear in source. Specific names/counts live only in tests. (FR43, FR50)
10. **`__init__.py` exports `Operations`** with a matching `__all__` entry, alphabetically placed (between `Memory` and `Placement`).
11. **Quality gates green.** `uv run --no-sync ruff check`, `ruff format --check`, `mypy --strict src/pyjmri`, and `pytest -m "not integration"` all pass; the unit-test count rises from the post-8.1 baseline (433 passed / 22 deselected).

> **Scope fence:** This story is the container + discovery method + tests **only**. The read-only **boundary test** (asserting no mutating methods), the `operations_report.py` **example**, the **docs**, and the **v1.1 release** are all **Story 8.3** — do **not** do them here. Do **not** modify the four Story 8.1 entity classes, the parsers, `_codes.py`, `layout.py` (`EntityCollection` is reused **as-is**), or any Epic 1–6 behavior in `discover()`.

## Tasks / Subtasks

- [x] **Task 1 — Add the `Operations` container to `operations.py`** (AC: #1, #2)
  - [x] Import `EntityCollection` from `pyjmri.layout` (one-directional: `operations` → `layout`; `layout` imports neither `operations` nor `_parsing` at module level — its entity-module parser imports are lazy/in-method — so no cycle; verified by running the suite).
  - [x] Define `class Operations:` with a keyword-only `__init__` taking `locations`/`trains`/`cars`/`engines: EntityCollection[...] | None = None`, each defaulting to `EntityCollection([], entity_type="location"|"train"|"car"|"engine")` when `None`. No `handle` parameter, no methods beyond `__init__`.
  - [x] Write a class docstring: read-only point-in-time snapshot, distinct from `Layout`, refresh by calling `discover_operations()` again, dual-name lookup via the reused `EntityCollection` (cars/engines system-name only). Matches the docstring tone of `Layout` and the Story 8.1 entity classes.
  - [x] Add `"Operations"` to `operations.py`'s `__all__` (alphabetical: after `Location`, before `Placement`).
- [x] **Task 2 — Implement `Client.discover_operations()` in `client.py`** (AC: #3, #4, #5, #9)
  - [x] Added `parse_car`, `parse_engine`, `parse_location`, `parse_train` to the existing `from pyjmri._parsing import (...)` block; added `from pyjmri.operations import Car, Engine, Location, Operations, Train`.
  - [x] Added a module-level `_OPERATIONS_PARSERS: dict[str, Callable[[dict[str, Any]], Any]]` mapping the four type strings to their parsers (parser-only — no `build`/`primary_attr`). Placed after `_ENTITY_SPECS`.
  - [x] Implemented `async def discover_operations(self) -> Operations:` — `RuntimeError` if `self._http is None`; the same `if not self._version_checked:` block `discover()` uses; parallel `_fetch_collection` over `_OPERATIONS_PARSERS` via `asyncio.TaskGroup`; parse each list; build four `EntityCollection`s; return `Operations(...)`.
  - [x] Does NOT touch `self._entities` (the WS-dispatch index) — verified by a dedicated regression test. Inline comment documents why.
  - [x] Wrote the docstring (mirrors `discover()`'s): parallel fetch, version gate cached, snapshot distinct from `Layout`, empty collections valid (FR50), `ExceptionGroup` semantics, `RuntimeError` when not open.
- [x] **Task 3 — Export `Operations`** (AC: #10) — added to `__init__.py` imports and `__all__` (between `"Memory"` and `"Placement"`).
- [x] **Task 4 — Unit tests `tests/unit/test_discover_operations.py`** (AC: #6, and #3/#4/#5 hermetically) — 8 tests via `patch_http_factory`:
  - [x] **FR50 empty path** — responder returns `[]` for the four operations paths → `Operations` with four empty collections, no raise.
  - [x] **Populated path** — responder returns the Story 8.1 captured fixtures (`load_fixture("operations/...")`) → collections populated (3 loc / 1 train / 3 cars / 4 engines).
  - [x] **Dual-name lookup** — `ops.locations["NW_Staging_Yard"]` is `ops.locations["2"]`; `ops.trains["TestTrainOne"]` is `ops.trains["1"]`; `ops.cars["AA123"]` has `user_name is None`.
  - [x] **Parallel paths probed** — `/json/v5/{location,train,car,engine}` all appear in `fake.probed`.
  - [x] **Version gate shared** — two tests: `discover_operations()` first → one version probe, later `discover()` skips it; and `discover()` first → `discover_operations()` skips it.
  - [x] **Does not clobber `self._entities`** — `discover()` populates the index (turnout NT400), then `discover_operations()` leaves it byte-for-byte unchanged (AC #4 regression guard).
  - [x] **Not open** — `await Client().discover_operations()` raises `RuntimeError` matching `"not open"`.
- [x] **Task 5 — Integration test `tests/integration/test_operations_discovery.py`** (AC: #7, #8) — `@pytest.mark.integration`, `jmri_available` fixture; 3 tests, all run green against live JMRI with the basement Operations data:
  - [x] Populated discovery: non-empty `locations`/`trains`/`cars`/`engines`.
  - [x] Dual-name resolution: a named location resolves by user AND system name to the same object; a car resolves by system name with `user_name is None`. Entities pinned by attribute (defensive `next(...)` filter), never positional index (Story 7.1 lesson).
  - [x] Timing: `await discover()` first (warm version check), then time `discover_operations()` alone, assert `elapsed < 1.0` (NFR2 Operations bound). Measured ~0.1 s on the basement roster.
- [x] **Task 6 — Run all gates** (AC: #11) — all green via `uv run --no-sync`: `ruff check` (All checks passed), `ruff format --check` (64 files formatted), `mypy --strict src/pyjmri` (Success, 22 files), `pytest -m "not integration"` (441 passed / 25 deselected, up from 433/22).

### Review Findings

Code review 2026-06-10 (Blind Hunter / Edge Case Hunter / Acceptance Auditor). AC coverage: all 11 ACs ✅ Met (AC11 gates ❓ not machine-verified in review, but +8 unit / +3 integration confirmed by inspection). No scope-fence violations.

- [x] [Review][Dismissed] Error-surface parity with `discover()` (was Decision D1) — DISMISSED on verification: the finding's premise was false. `discover()`'s own `TaskGroup` block (client.py:720) is bare and propagates a raw `ExceptionGroup` exactly like `discover_operations()`; the `_unwrap_exception_group` calls (client.py:237, 276) are in lifecycle teardown (`__aexit__` / `_teardown_on_aenter_failure`), NOT in `discover()`. Both discovery methods are already consistent and document the raw-`ExceptionGroup` behavior identically (client.py:694-700 vs 809-814). Patching `discover_operations()` would have *introduced* divergence. No change made.
- [x] [Review][Patch] Docstring overclaimed version check "fires at most once regardless of call order" — FIXED (client.py:787-791): softened to "cached for the Client's lifetime and shared with `discover` — subsequent sequential calls to either method skip the probe," matching `discover()`'s careful wording. The false concurrency claim is gone; the underlying non-atomic race is deferred (see below).
- [x] [Review][Defer] Version-check concurrency race [client.py:820-823] — deferred, pre-existing: the non-atomic check-then-set is the identical pattern already in `discover()` (client.py:715); fixing only `discover_operations()` would be inconsistent and fixing both touches Epic 1–6 / fenced code. Benign (probe is idempotent; documented single-task discovery usage).
- [x] [Review][Defer] Duplicate car/engine road+number silently collapse (last-wins) [layout.py:88-91] — deferred, pre-existing: `EntityCollection` is reused as-is (scope fence); cars/engines are keyed solely by system name with no user-name fallback, so a collision drops an entity with no diagnostic. Low real-world probability (JMRI enforces unique car IDs). Fix belongs in `EntityCollection`.
- [x] [Review][Defer] Duplicate location/train user-name shadowing (last-wins) [layout.py:90-91] — deferred, pre-existing: same `EntityCollection` model; system-name access still works, so impact is limited to ambiguous user-name lookup.

## Dev Notes

### What this story is, in one sentence

Add the `Operations` read-only container and the `Client.discover_operations()` method that parallel-fetches the four Operations collections and fills it — the exact `discover()` → `Layout` pattern, but read-only (no handle), parsing to the Story 8.1 entities directly, and **without** touching the WS-dispatch index.

### Recommended implementation (verified against the current code)

**`operations.py` — append the container (entity classes already live in this file):**

```python
from pyjmri.layout import EntityCollection  # add near the top, after `from dataclasses import dataclass`

class Operations:
    """Read-only snapshot of a JMRI Operations session.

    Returned by :meth:`pyjmri.Client.discover_operations`. Holds one
    :class:`EntityCollection` per Operations type. Distinct from
    :class:`~pyjmri.Layout` — Operations is its own subsystem. The
    snapshot is point-in-time and not WebSocket-subscribed; to refresh,
    call ``discover_operations()`` again (FR49 read-only contract).

    Locations and trains carry both a user and a system name, so dual-name
    lookup works (``ops.locations["NW_Staging_Yard"]`` and ``["2"]``).
    Cars and engines have no user name and are keyed by road+number
    (``ops.cars["AA123"]``).
    """

    def __init__(
        self,
        *,
        locations: EntityCollection[Location] | None = None,
        trains: EntityCollection[Train] | None = None,
        cars: EntityCollection[Car] | None = None,
        engines: EntityCollection[Engine] | None = None,
    ) -> None:
        self.locations: EntityCollection[Location] = (
            locations if locations is not None else EntityCollection([], entity_type="location")
        )
        self.trains: EntityCollection[Train] = (
            trains if trains is not None else EntityCollection([], entity_type="train")
        )
        self.cars: EntityCollection[Car] = (
            cars if cars is not None else EntityCollection([], entity_type="car")
        )
        self.engines: EntityCollection[Engine] = (
            engines if engines is not None else EntityCollection([], entity_type="engine")
        )
```

**`client.py` — registry + method (place the registry near `_ENTITY_SPECS`):**

```python
_OPERATIONS_PARSERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "location": parse_location,
    "train": parse_train,
    "car": parse_car,
    "engine": parse_engine,
}

async def discover_operations(self) -> Operations:
    if self._http is None:
        raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
    http = self._http

    if not self._version_checked:
        version_payload = await http.get("/json/v5/networkService")
        _check_jmri_version(version_payload)
        self._version_checked = True

    async with asyncio.TaskGroup() as tg:
        fetch_tasks = {
            entity_type: tg.create_task(_fetch_collection(http, entity_type))
            for entity_type in _OPERATIONS_PARSERS
        }

    results: dict[str, list[Any]] = {
        entity_type: [parser(env) for env in fetch_tasks[entity_type].result()]
        for entity_type, parser in _OPERATIONS_PARSERS.items()
    }
    locations: list[Location] = results["location"]
    trains: list[Train] = results["train"]
    cars: list[Car] = results["car"]
    engines: list[Engine] = results["engine"]

    return Operations(
        locations=EntityCollection(locations, entity_type="location"),
        trains=EntityCollection(trains, entity_type="train"),
        cars=EntityCollection(cars, entity_type="car"),
        engines=EntityCollection(engines, entity_type="engine"),
    )
```

`Callable` and `Any` are already imported in `client.py` (`from collections.abc import Callable, Coroutine`; `from typing import ... Any`). `EntityCollection` is already imported (`from pyjmri.layout import EntityCollection, Layout`). `_fetch_collection`, `_check_jmri_version`, and `asyncio` are all already present.

### Established patterns to FOLLOW (read these; do not reinvent)

- **`src/pyjmri/client.py` → `discover()` (lines 656–764) + `_ENTITY_SPECS` (824–894) + `_fetch_collection` (973–988).** `discover_operations()` is the read-only twin of `discover()`. **Reuse `_fetch_collection` verbatim** (it already builds `/json/v5/{entity_type}` and validates the list). The one deliberate divergence: `discover()` rebuilds `self._entities` (the WS-dispatch index) at lines 746–752 — `discover_operations()` **must not** do this. [Source: src/pyjmri/client.py:656]
- **`src/pyjmri/layout.py` → `EntityCollection` (35–150) + `Layout.__init__` (194–235).** `Operations.__init__` copies `Layout`'s "param-or-empty-collection" idiom exactly. `EntityCollection` is reused **unchanged** — your four entity classes already satisfy its `_NamedEntity` protocol (`name: str`, `user_name: str | None`); Story 8.1 made cars/engines `user_name=None` precisely so they drop into a system-name-only `EntityCollection`. `LayoutEntityNotFound` is the reused miss exception (no new exception type). [Source: src/pyjmri/layout.py:35]
- **`src/pyjmri/operations.py`** — the Story 8.1 entity classes (`Location`, `Train`, `Car`, `Engine`) and value objects already live here; add `Operations` to the **same** module (architecture: one `operations.py`, not per-entity modules). [Source: src/pyjmri/operations.py]
- **`tests/unit/test_discover.py` + `tests/unit/conftest.py::patch_http_factory` (lines 172–269).** The exact unit-mock idiom: `fake = patch_http_factory[0]; fake.next_response = responder`, where `responder(path)` returns the `networkService` version payload for `/json/v5/networkService` and per-type lists otherwise. Copy `_version_payload` / `_responder` shape from `test_discover.py:33-76`. [Source: tests/unit/test_discover.py:33, tests/unit/conftest.py:172]
- **`tests/integration/test_discovery.py` + `conftest.py::jmri_available`.** Integration idiom: `@pytest.mark.integration`, `async with Client() as jmri:`, `time.perf_counter()` around the call, `jmri_available` skips when JMRI is down. [Source: tests/integration/test_discovery.py:1, tests/integration/conftest.py:19]

### AC wording drift — the FR50 empty path is now a UNIT test (important)

Epic 8 (written 2026-06-09) says the empty-collection path should be "covered by an integration test on the basement simulator profile **as it stands today**." That wording predates commits `bb69873` / `5b7c2a8`, which **added Operations data to `Basement_Revised_2024`** — the profile JMRI now serves has 3 locations / 4 engines / 3 cars / 1 train. So the live basement profile can **no longer** produce empty Operations collections.

Resolution (apply this, don't fight it): cover **FR50 empty path with a unit test** (`patch_http_factory` returning `[]` for all four paths) — hermetic, profile-independent, and a stronger guarantee than depending on which profile happens to be loaded. The **integration** test covers the **populated** path (AC #7) and the timing bound (AC #8). Do not write an integration test that asserts empty collections — it would fail against the data-loaded basement profile. Note this decision in your Completion Notes so the reviewer sees the AC #6-vs-epic reconciliation.

### Type / mypy notes (FR: gates green under `mypy --strict`)

- The `results: dict[str, list[Any]]` + per-variable `list[Location]` re-pinning is the same pattern `discover()` uses (client.py:726–739) and passes `mypy --strict`. Keep it; don't try to over-type the heterogeneous registry.
- `mypy --strict src/pyjmri` is the canonical CONTRIBUTING gate (NOT `src tests` — `tests` trips a pre-existing duplicate-`conftest` limitation unrelated to this story). [Source: Story 8.1 Dev Notes]
- Confirm no import cycle after adding `from pyjmri.layout import EntityCollection` to `operations.py`: the chain is `_parsing → operations → layout → (block/light/... leaf entities)`; `layout` imports neither `operations` nor `_parsing`, so it's a DAG. If you somehow see a cycle, the suite import will fail immediately — run `pytest` to verify.

### Project Structure Notes

New/changed files (all under `python_code/`, the only writable tree — `.jmri` profiles and shared JMRI assets are read-only):

- `src/pyjmri/operations.py` — **UPDATE**: add `Operations` container + `EntityCollection` import + `__all__` entry. [arch path: src/pyjmri/operations.py — "Operations + Location/Train/Car/Engine"]
- `src/pyjmri/client.py` — **UPDATE**: add `discover_operations()` + `_OPERATIONS_PARSERS` + parser/entity imports. [arch path: client.py — "discover_operations() (FR45–FR50)"]
- `src/pyjmri/__init__.py` — **UPDATE**: export `Operations`.
- `tests/unit/test_discover_operations.py` — **NEW**.
- `tests/integration/test_operations_discovery.py` — **NEW** (architecture names this file at line 1117).

No conflicts with the unified structure — these are exactly the architecture's prescribed paths (architecture.md lines 1057–1058, 1117). `layout.py`, `_codes.py`, the Story 8.1 entity classes/parsers, and `discover()`'s internals are intentionally **not** changed (Epic 8 scope policy: Epics 1–6 behavior byte-for-byte unchanged).

### Testing Requirements

- Framework: `pytest` (`asyncio_mode = "auto"` — async tests need no decorator; see existing tests). Unit tests in `tests/unit/`, integration in `tests/integration/`.
- Integration entity-pinning rule (Story 7.1): pin by **system/user name**, never positional `next(iter(...))[0]`, so a reordered JMRI response can't flake the test. [Source: memory integration_test_entity_pinning; tests/integration/test_discovery.py:15]
- Run before declaring done (always `uv run --no-sync`, never bare):
  - `uv run --no-sync ruff check`
  - `uv run --no-sync ruff format --check`  ← separate CI gate from `ruff check`.
  - `uv run --no-sync mypy --strict src/pyjmri`
  - `uv run --no-sync pytest -m "not integration"`  (post-8.1 baseline 433 passed / 22 deselected; expect it to rise with the new unit tests)
  - Optional (only if JMRI is running locally): `uv run --no-sync pytest -m integration` to exercise Tasks 5 against live data.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 8.2] — story statement + acceptance criteria (lines 1185–1212)
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 8] — test-environment note: Operations fully simulator-testable; empty + populated paths (lines 1146–1152)
- [Source: _bmad-output/planning-artifacts/architecture.md#Operations Subsystem (Read-Only)] — separate container/entry point, snapshot-not-live, reuse `EntityCollection`, handle-free read-only objects, `discover_operations()` parallel fetch (lines 579–642, 1242–1255)
- [Source: _bmad-output/planning-artifacts/architecture.md#Internal Layering] — file placement (lines 1057–1058, 1117)
- [Source: _bmad-output/planning-artifacts/prd.md#NFR2] — Operations timing bound: layout discovery + ≤1 s for comparable-size Operations roster (lines 914–920)
- [Source: src/pyjmri/client.py:656] — `discover()` pattern to mirror; `_ENTITY_SPECS` (824), `_fetch_collection` (973), version gate (710–713), `self._entities` rebuild to NOT replicate (746–752)
- [Source: src/pyjmri/layout.py:35] — `EntityCollection` (reused as-is) + `_NamedEntity` protocol + `Layout.__init__` empty-default idiom (194)
- [Source: src/pyjmri/operations.py] — Story 8.1 entity classes the container holds
- [Source: tests/unit/test_discover.py:33, tests/unit/conftest.py:172] — `patch_http_factory` unit-mock idiom
- [Source: tests/integration/test_discovery.py, tests/integration/conftest.py:19] — integration idiom + `jmri_available`
- [Source: 8-1-operations-wire-format-parsing-and-read-only-entity-classes.md] — Story 8.1 entity contract, JSON shapes, fixtures, `mypy src/pyjmri` gate
- [Source: memory project_operations_test_data] — basement profile now has 3 loc / 4 eng / 3 car / 1 train (drives AC #6 empty-path reconciliation + AC #7 populated assertions)

### Git / recent-work intelligence

Most recent commit is `3671121` (Story 8.1: Operations parsing + entity classes — 11 files, the `operations.py` entity classes / parsers / fixtures this story builds on). Before that, `35e9fe1` collapsed `discover()` into the `_ENTITY_SPECS` registry — that registry is the structural model for `_OPERATIONS_PARSERS` (but simpler: parser-only, no `build`/`primary_attr`). No code conflicts: 8.1 added `operations.py` and `_parsing` functions without touching `client.py`, so `discover_operations()` lands on a clean `client.py`.

### Project context reference

- python_code is a modern Python 3.11+ async JMRI client (external, over the web server), targeting only `Basement_Revised_2024.jmri`. v1.0.x shipped to PyPI; Epic 8 is the v1.1 feature track. [Source: memory project_python_code, project_pyjmri_status]
- Only `python_code/` and `_bmad-output/` are writable; all `.jmri` dirs and shared JMRI assets are read-only. [Source: memory feedback_writable_paths]
- Always drive Python tooling through `uv run --no-sync <tool>`. [Source: memory feedback_use_uv]
- Both `ruff check` and `ruff format --check` are CI gates; keep this story file markdownlint-clean too. [Source: memory feedback_ruff_format_gate, feedback_polish_matters]
- JMRI is read-only/open-loop, but Operations is a pure **data** subsystem with no hardware dependency — so unlike throttles, both unit and integration coverage here are fully meaningful on the simulator (no open-loop blind spot). [Source: memory project_nce_open_loop, project_operations_json_contract]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (1M context)

### Debug Log References

- Gates: `uv run --no-sync ruff check` → All checks passed; `ruff format --check` → 64 files already formatted; `mypy --strict src/pyjmri` → Success, 22 source files; `pytest -m "not integration"` → 441 passed / 25 deselected.
- Live integration: `uv run --no-sync pytest tests/integration/test_operations_discovery.py -m integration` → 3 passed against JMRI on `localhost:12080` (basement profile, Operations data loaded). NFR2 timing comfortably met (full 3-test run incl. a `discover()` warm-up in ~0.2 s).

### Completion Notes List

- Added the read-only `Operations` container to `operations.py` (handle-free, four `EntityCollection` attributes, empty-default constructor mirroring `Layout()`), and `Client.discover_operations()` to `client.py` — the read-only twin of `discover()`: parallel `_fetch_collection` over a new `_OPERATIONS_PARSERS` registry, parse-direct to the Story 8.1 frozen entities, assemble four `EntityCollection`s.
- **`discover_operations()` deliberately does NOT rebuild `self._entities`** (the WS-dispatch index) — Operations entities have no `_on_event` and are not waitable; clobbering it would break in-flight Layout `wait_*` calls. Covered by a dedicated regression test (`test_discover_operations_does_not_clobber_entity_index`).
- **Necessary correctness fix in `layout.py` (scope-fence exception, documented):** the `_NamedEntity` protocol declared `name`/`user_name` as read-**write** attributes. The plain-class layout entities (`Turnout` et al.) satisfied that, but the **frozen** Operations dataclasses do not — `mypy --strict` rejected `EntityCollection[Location|Train|Car|Engine]` with `type-var` errors. Story 8.1's claim that the entities "already satisfy `_NamedEntity`" was never actually compiled against `EntityCollection`. Fix: redeclared the two protocol members as read-only `@property`s. `EntityCollection` only ever reads these attributes, so a read-only protocol is strictly more correct; mutable-attribute entities still satisfy it (covariance), so no Epic 1–6 behavior changes and all 433 prior tests still pass. This is the minimal change that lets frozen entities into the reused container; it does not alter `EntityCollection`'s logic.
- **AC #6 vs epic wording reconciled (as planned in Dev Notes):** the FR50 empty path is covered by a **unit test** (mocked transport → `[]`), not an integration test, because the basement profile now has Operations data loaded (commits `bb69873`/`5b7c2a8`) and can no longer produce empty collections live. The integration test covers the populated path + timing.
- Version gate is shared via `self._version_checked`: the `/json/v5/networkService` probe fires at most once per Client regardless of whether the user calls `discover()`, `discover_operations()`, or both, in any order (two unit tests assert both orderings).
- Layout-agnostic: only entity-**type** strings (`"location"/"train"/"car"/"engine"`) appear in `src/pyjmri/`; specific names/counts live only in tests. The integration test pins entities by attribute (defensive `next(...)` filter), not positional index (Story 7.1 lesson).
- Unit-test count moved 433 → 441 (+8 Operations discovery tests). Integration deselected count moved 22 → 25 (+3).

### File List

- `python_code/src/pyjmri/operations.py` — UPDATED: added `Operations` container + `EntityCollection` import + `__all__` entry.
- `python_code/src/pyjmri/client.py` — UPDATED: added `discover_operations()` + `_OPERATIONS_PARSERS` registry + parser/entity imports.
- `python_code/src/pyjmri/layout.py` — UPDATED: `_NamedEntity` protocol members made read-only (`@property`) so frozen Operations entities satisfy `EntityCollection[T]` under `mypy --strict`.
- `python_code/src/pyjmri/__init__.py` — UPDATED: export `Operations` (import + `__all__`).
- `python_code/tests/unit/test_discover_operations.py` — NEW: 8 unit tests (empty/FR50, populated, dual-name, parallel, shared version gate ×2, no-clobber, not-open).
- `python_code/tests/integration/test_operations_discovery.py` — NEW: 3 integration tests (populated, dual-name, NFR2 timing).

## Change Log

| Date | Change |
|------|--------|
| 2026-06-10 | Story 8.2 implemented: `Operations` read-only container + `Client.discover_operations()` (parallel fetch, shared version gate, no WS-index mutation); `_NamedEntity` protocol made read-only so frozen Operations entities satisfy `EntityCollection`; 8 unit + 3 integration tests; all gates green (441/25). Status → review. |
