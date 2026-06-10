# Story 8.1: Operations wire-format parsing + read-only entity classes

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a library user,
I want JMRI's Operations JSON for locations, trains, cars, and engines parsed into typed read-only Python objects,
so that I can read operational state (where a car is, what train it's on, where a train is) as proper typed attributes rather than raw JSON.

## Acceptance Criteria

1. **Parsing functions exist and cover the envelope.** `_parsing.py` gains `parse_location`, `parse_train`, `parse_car`, `parse_engine`. Each consumes one JMRI `{"type", "data"}` envelope and returns a typed object. The same per-envelope function serves both the list response form (`GET /json/v5/car` → array of envelopes, parse each) and the single-entity form (`GET /json/v5/car/AA123` → one envelope) — the envelope shape is identical, so no second code path is needed. (FR45–FR48)
2. **Parsing is unit-tested against captured fixtures, no live JMRI required.** New fixtures `tests/unit/fixtures/operations/{locations,trains,cars,engines}.json` are captured from a live JMRI instance with Operations data loaded; `tests/unit/test_operations_parsing.py` round-trips every envelope in each fixture through its parser.
3. **Four read-only entity classes are defined:** `Location`, `Train`, `Car`, `Engine` in `src/pyjmri/operations.py`. Each carries its system `name` and `user_name` and a typed read-only view of the operational state JMRI exposes — at minimum `Car.location` / `Car.train` / `Car.destination`; `Train.route` / `Train.current_location`; `Engine` road+number plus deployment (location) and optional `train`. (FR45–FR47)
4. **Read-only is enforced by the class surface (FR49).** None of the four entity classes (nor the nested value objects) exposes a setter, command, or wait method. Implement them as **frozen** dataclasses (`@dataclass(frozen=True, kw_only=True, slots=True)`) so immutability is structural, not just convention.
5. **`Engine` is a distinct type from any roster entry (FR48).** `Engine` is its own class, not an alias of (the future) `RosterEntry`. Its docstring states it models the operationally-active subset deployed on the layout, vs the full DecoderPro catalog. The two are not conflated in the type model.
6. **Absence is a valid operational state, parsed without crashing (FR48).** When JMRI reports `null` (e.g. a car/engine not assigned to a train: `trainName: null`, `destination: null`) or an empty string for a reference field (e.g. an un-built train's `location: ""`), the corresponding attribute resolves to `None` (or an empty tuple for list fields) rather than raising.
7. **`train.status` is a raw string** (e.g. `"Partial 3/27 cars"`). No status enum in v1.1.
8. **Cars and engines have no user name.** They are keyed by `name` = road+number (e.g. `"AA123"`, `"UP2570"`); their `user_name` attribute is `None` (do not fabricate one). Locations and trains carry both `user_name` and a system `name`.
9. **`__init__.py` exports** `Location`, `Train`, `Car`, `Engine` (and any public nested value object) with matching `__all__` entries, alphabetically sorted to match the existing list.
10. **Quality gates green.** All new public types resolve under `mypy --strict`; `ruff check`, `ruff format --check`, and unit `pytest -m "not integration"` all pass.

> **Scope fence:** This story is parsing + entity classes **only**. The `Operations` container class and `Client.discover_operations()` are **Story 8.2** — do **not** add them here. `operations.py` in this story contains the value objects and the four entity classes, nothing that does I/O. `client.py`, `_codes.py`, and `layout.py` are **not modified** by this story.

## Tasks / Subtasks

- [x] **Task 1 — Capture live JSON fixtures** (AC: #2) — JMRI confirmed running on `localhost:12080` with the Operations test data loaded. Created `tests/unit/fixtures/operations/` and saved the four list-form responses:
  - [x] `locations.json` (3 envelopes), `trains.json` (1), `cars.json` (3), `engines.json` (4) captured via `curl … | python3 -m json.tool`.
  - [x] Verified each file is a JSON **array** of `{"type","data"}` envelopes (the `load_fixture` helper requires a top-level array).
  - [x] Confirmed the fixture set exercises every parser path: `cars.json` has 3 cars placed + assigned (nested `location→track`, `destination→track`, `trainName="TestTrainOne"`); `engines.json` has **both** the assigned engine (UP8997 via train consist) and **unassigned** engines (UP2570/5488/8096, `trainName: null`, `destination: null`); `trains.json` has the nested consist (`engines[]` + `cars[]`) and ordered route stops (`locations[]`).
- [x] **Task 2 — Define nested value objects in `operations.py`** (AC: #3, #4, #6) — frozen dataclasses, no behavior:
  - [x] `Track` — `name`, `user_name`.
  - [x] `Placement` — `name`, `user_name`, `track: Track | None`. (JMRI's `route` field intentionally not surfaced — it is `null` for unassigned stock and adds no value to the read-only snapshot.)
  - [x] `RouteStop` — `name`, `user_name`, `sequence_id: int`, `train_direction: str`.
- [x] **Task 3 — Define the four entity classes in `operations.py`** (AC: #3, #4, #5, #7, #8) — frozen dataclasses with `name` + `user_name` first (satisfy the `_NamedEntity` protocol Story 8.2's `EntityCollection` requires):
  - [x] `Location` — `name`, `user_name`, `length: int`, `comment: str | None`, `tracks: tuple[Track, ...]`.
  - [x] `Train` — `name`, `user_name`, `route: str | None`, `current_location: str | None`, `status: str`, `status_code: int`, `lead_engine: str | None`, `route_stops`, `engines`, `cars` tuples.
  - [x] `Car` — `name`, `user_name=None`, `road`, `number`, `car_type`, `length`, `location: Placement | None`, `train: str | None`, `destination: Placement | None`.
  - [x] `Engine` — `name`, `user_name=None`, `road`, `number`, `model: str | None`, `engine_type`, `length`, `location`, `train`, `destination`. Docstring documents the roster-vs-Operations distinction (FR48).
- [x] **Task 4 — Add parsers to `_parsing.py`** (AC: #1, #6, #7) — `parse_location`, `parse_train`, `parse_car`, `parse_engine`. Reused `_data`, `_required_str`, `_optional_str`:
  - [x] Added a `_required_int` helper (bool-rejecting) for `length`, `sequenceId`, `statusCode`. (`_optional_int` not needed — all int fields are required and present.)
  - [x] `_parse_track` / `_parse_placement` return `None` for `null`/empty objects; `"" or None` collapses empty reference strings (`route`/`current_location`/`leadEngine`/`model`/`trainName`/`comment`) to `None`.
  - [x] `parse_train` builds `route_stops` from `data["locations"]` and the consist via shared `_car_from_data` / `_engine_from_data` on `data["cars"]` / `data["engines"]` — confirmed those are bare data objects (no `{type,data}` wrapper; inner `type` is the car/engine type e.g. `"Boxcar"`/`"Diesel"`), so no double-unwrap.
  - [x] Parsers return public frozen entity classes directly — no `_Parsed*` intermediate. `_parsing.py` imports from `operations.py`; `operations.py` imports nothing from `_parsing.py` (one-directional, no cycle).
- [x] **Task 5 — Export public types** (AC: #9) — added `Car`, `Engine`, `Location`, `Placement`, `RouteStop`, `Track`, `Train` to `__init__.py` imports and `__all__`, alphabetically.
- [x] **Task 6 — Write `tests/unit/test_operations_parsing.py`** (AC: #2, #5, #6) — 19 tests covering all cases below.
- [x] **Task 7 — Run all gates** (AC: #10) — `ruff check`, `ruff format --check`, `mypy --strict src/pyjmri` (canonical invocation per CONTRIBUTING — `tests` excluded due to the known duplicate-conftest mypy limitation), `pytest -m "not integration"` all green.

## Dev Notes

### What this story is, in one sentence

Add four pure-data read-only entity types and their JSON parsers, mirroring the Epic 2 parsing pattern (`_parsing.py` + per-entity class), but **handle-free and immutable** because Operations is a read-only snapshot subsystem. No I/O, no container, no client method here.

### Live capture — JMRI is running right now

JMRI **is confirmed live on `localhost:12080`** (verified during story creation, 2026-06-10) serving the basement Operations test data: 3 locations, 4 engines, 3 cars, 1 train (`TestTrainOne`, status `"Partial 3/27 cars"`), 1 route. This is the exact fixture source. Capture with the Task 1 `curl` commands. The library parses this **JSON**, never the profile's `Operations*Roster.xml` storage files. [Source: memory project_operations_json_contract; project_operations_test_data]

> Endpoint note: both `/json/v5/locations` (plural) and `/json/v5/location` (singular, no name) return the full collection as a JSON array; `/json/v5/location/<name>` returns a single envelope dict. Story 8.2 will use the same `/json/v5/{entity_type}` collection path that `discover()` already uses, with `entity_type` ∈ `{"location","train","car","engine"}`. For this story you only need the captured fixtures.

### Exact JMRI JSON shapes (captured live — these are real, not invented)

**Location** (`type: "location"`) — has BOTH `userName` and system `name`:
```json
{"type":"location","data":{
  "userName":"NW_Staging_Yard", "name":"2", "length":4000, "comment":"", "reporter":"",
  "carType":["Baggage","Boxcar", "..."],
  "track":[{"userName":"NW_Track_3","name":"2s3","comment":"","length":1000,
            "location":"2","reporter":"","type":"Staging","carType":["..."]}]
}}
```
→ `Location(name="2", user_name="NW_Staging_Yard", length=4000, comment=None, tracks=(Track(name="2s3", user_name="NW_Track_3"), ...))`. (`comment:""` → `None`. The `carType` allow-list is not modeled in v1.1 — skip it.)

**Car** (`type: "car"`) — keyed by `name` = road+number, **no `userName`**:
```json
{"type":"car","data":{
  "name":"AA123","number":"123","road":"AA","type":"Boxcar","length":40,"color":"Black",
  "location":{"userName":"NW_Staging_Yard","name":"2","route":"1r2",
              "track":{"userName":"NW_Track_1","name":"2s1"}},
  "trainId":"1","trainName":"TestTrainOne",
  "destination":{"userName":"South Interchange","name":"3","route":"1r3",
                 "track":{"userName":"Arrival_Departure","name":"3s1"}},
  "load":"E","outOfService":false, "...":"(many more flags)"
}}
```
→ `Car(name="AA123", user_name=None, road="AA", number="123", car_type="Boxcar", length=40, location=Placement(name="2", user_name="NW_Staging_Yard", track=Track(name="2s1", user_name="NW_Track_1")), train="TestTrainOne", destination=Placement(name="3", user_name="South Interchange", track=Track(name="3s1", user_name="Arrival_Departure")))`.

**Engine** (`type: "engine"`) — keyed by `name` = road+number, **no `userName`**. Unassigned example (UP2570) shows the null path:
```json
{"type":"engine","data":{
  "name":"UP2570","number":"2570","road":"UP","type":"Diesel","length":70,"model":"ES44AC",
  "location":{"userName":"NW_Staging_Yard","name":"2","route":null,
              "track":{"userName":"NW_Track_6","name":"2s4"}},
  "trainId":null, "trainName":null, "destination":null, "hp":"", "consist":""
}}
```
→ `Engine(name="UP2570", user_name=None, road="UP", number="2570", model="ES44AC", engine_type="Diesel", length=70, location=Placement(name="2", user_name="NW_Staging_Yard", track=Track(name="2s4", user_name="NW_Track_6")), train=None, destination=None)`. **This is the FR48 absence path: `trainName`/`destination` are `null` → `None`.** (Note `location.route` is also `null` here → `Placement.route` or whatever you surface must tolerate it; the recommended `Placement` model above does not surface `route`, which sidesteps it entirely — surface it only if you want it.)

**Train** (`type: "train"`) — has BOTH `userName` and system `name`; carries a nested consist:
```json
{"type":"train","data":{
  "userName":"TestTrainOne","name":"1","route":"Test_Route","routeId":"1",
  "location":"NW_Staging_Yard","locationId":"1r2",
  "status":"Partial 3/27 cars","statusCode":20,"length":206,"weight":...,
  "leadEngine":"UP 8997","caboose":...,
  "locations":[{"name":"1r2","userName":"NW_Staging_Yard","trainDirection":"East",
                "sequenceId":1,"expectedArrivalTime":"00:00","expectedDepartureTime":"00:00",
                "location":{"userName":"NW_Staging_Yard","name":"2"}}, ...],
  "engines":[ <bare engine data object>, ... ],
  "cars":[ <bare car data object>, ... ]
}}
```
→ `Train(name="1", user_name="TestTrainOne", route="Test_Route", current_location="NW_Staging_Yard", status="Partial 3/27 cars", status_code=20, route_stops=(RouteStop(name="1r2", user_name="NW_Staging_Yard", sequence_id=1, train_direction="East"), ...), engines=(...), cars=(...), lead_engine="UP 8997")`.

**CRITICAL — train consist elements are bare data objects, not envelopes.** Each element of `train.engines[]` / `train.cars[]` is the inner `data` object directly (it has `name`/`road`/`number`/... at the top level, **no** `{"type","data"}` wrapper). The top-level `/json/v5/cars` list, by contrast, IS a list of full envelopes. So:
- `parse_car(envelope)` expects `{"type":"car","data":{...}}` (uses the existing `_data()` unwrap).
- For consist elements, either (a) call a small inner `_car_from_data(data)` that both `parse_car` and `parse_train` share, or (b) re-wrap: `parse_car({"type":"car","data":elem})`. Pick one and be consistent. Option (a) is cleaner. Verify against the captured `trains.json` — do **not** assume; confirm the consist element shape after capture.

`current_location`: JMRI's top-level `train.location` is the **userName string** of the train's current location (`"NW_Staging_Yard"`), or `""` when the train hasn't departed — map empty string → `None`. (`locationId` is the route-stop id; surface it only if useful.)

### Type/None rules (FR48 — absence is valid)

- `null` JSON → `None`. (`_optional_str` already does this for strings.)
- Empty string `""` for **reference/identity** fields that represent absence (e.g. `train.location` current-location) → `None`. For genuinely-free-text fields (`comment`), `""` → `None` is also reasonable and matches the existing `_optional_str(... )` convention used for `comment` in `parse_roster_entry`.
- Nested object that is `null` or `{}` → `None` (Placement/Track).
- Array that is absent/empty → empty tuple `()`. Use `tuple[...]` (immutable) on frozen dataclasses, not `list`.
- `length`, `sequenceId`, `statusCode` are JSON integers → `int`. Add an int helper; do not route them through `_required_state` (that's enum-only).

### Established patterns to FOLLOW (read these files; do not reinvent)

- **`src/pyjmri/_parsing.py`** — the parsing module you extend. Note: frozen `@dataclass(frozen=True, kw_only=True, slots=True)` shapes; `_data()` unwraps the envelope and raises `JMRIProtocolError` on a missing `data` object; `_required_str` / `_optional_str` helpers; `parse_roster_entry` is the closest analog (string identity, optional fields, no integer state enum). Reuse these helpers; add `_optional_int`/`_required_int` alongside them following the same `JMRIProtocolError(..., entity_type=, field=, name=)` error style. [Source: src/pyjmri/_parsing.py]
- **`src/pyjmri/block.py`** — read it for the read-only entity docstring tone and the "Read-only in pyjmri v1" framing. **But do NOT copy its structure**: `Block` is a *mutable* class holding a `_handle` + `WaiterList` for refresh/wait. Operations entities have **none of that** — no `_handle`, no `WaiterList`, no `get_state`, no `wait_*`, no `_on_event`. They are frozen dataclasses. [Source: src/pyjmri/block.py]
- **`src/pyjmri/layout.py` → `_NamedEntity` Protocol (lines 27–32)** — Story 8.2's `EntityCollection[T]` requires every element to expose `name: str` and `user_name: str | None`. Your four entity classes MUST have both attributes (cars/engines: `user_name=None`) so 8.2 can drop them into an `EntityCollection` unchanged. [Source: src/pyjmri/layout.py:27]
- **`src/pyjmri/_codes.py` is untouched** — Operations entities carry no integer state enums (the one int-coded field, `train.statusCode`, is surfaced as a plain `int`, not an enum). [Source: architecture.md#Operations Subsystem (Read-Only)]
- **`RosterEntry` is NOT a public class** — `src/pyjmri/roster.py` is a stub (Story 2.3 deferred it; an unused `_ParsedRosterEntry`/`parse_roster_entry` exists in `_parsing.py` but no public `RosterEntry`). So FR48's "distinct from `RosterEntry`" is satisfied trivially: make `Engine` a standalone class and document the distinction. Do not alias or import anything roster-related. [Source: src/pyjmri/roster.py, src/pyjmri/_parsing.py:289]

### Project Structure Notes

New/changed files (all under `python_code/`, the only writable tree — `.jmri` profiles and shared JMRI assets are read-only):
- `src/pyjmri/operations.py` — **NEW**: value objects (`Track`, `Placement`, `RouteStop`) + `Location`, `Train`, `Car`, `Engine`. [arch path: src/pyjmri/operations.py]
- `src/pyjmri/_parsing.py` — **UPDATE**: add `parse_location/train/car/engine` + int helpers; import entity classes from `operations.py`.
- `src/pyjmri/__init__.py` — **UPDATE**: export the four entity classes (and public value objects) + `__all__`.
- `tests/unit/fixtures/operations/{locations,trains,cars,engines}.json` — **NEW**: captured live.
- `tests/unit/test_operations_parsing.py` — **NEW**.

No conflicts with the unified structure — these paths are exactly the architecture's prescribed layout (architecture.md lines 1059, 1093–1097, 1105). `client.py`, `layout.py`, `_codes.py` are intentionally **not** touched (Epic 8 scope policy: Epics 1–6 behavior byte-for-byte unchanged).

### Testing Requirements

- Framework: `pytest`; tests live in `tests/unit/`; new file `tests/unit/test_operations_parsing.py`. Mirror `tests/unit/test_parsing.py` style (the `load_fixture` session fixture, per-fixture round-trip loops). [Source: tests/unit/test_parsing.py, tests/unit/conftest.py]
- The existing `load_fixture` helper (`tests/unit/conftest.py:17`) interpolates the name into `fixtures/<name>.json`, so a subdirectory works directly: `load_fixture("operations/cars")`. **No conftest change needed.**
- Required test cases:
  1. **Round-trip happy path** — for each of `operations/locations|trains|cars|engines`, assert the fixture is non-empty and every envelope parses to the right type without error.
  2. **Dual-name fields** — a parsed `Location` and `Train` carry both `name` and `user_name`; a parsed `Car` and `Engine` carry `user_name is None` and `name` == road+number (e.g. `"AA123"`).
  3. **Absence path (FR48)** — the unassigned engine (`UP2570`) parses with `train is None` and `destination is None` and `location is not None`; assert no exception.
  4. **Assigned path** — `Car("AA123")` parses with `train == "TestTrainOne"`, `location.track.user_name == "NW_Track_1"`, `destination.track.user_name == "Arrival_Departure"`.
  5. **Nested consist** — the parsed `Train` has non-empty `engines` and `cars` tuples (the consist), and `route_stops` ordered by `sequence_id`; `status == "Partial 3/27 cars"`, `status_code == 20`, `route == "Test_Route"`, `current_location == "NW_Staging_Yard"`, `lead_engine == "UP 8997"`.
  6. **Engine is a distinct type** — `Engine is not Car`; a parsed engine is an `Engine` instance (FR48 type-model assertion).
  7. **Frozen / read-only (supports FR49)** — assert mutating an attribute raises `dataclasses.FrozenInstanceError` (e.g. `with pytest.raises(FrozenInstanceError): car.train = "X"`). (The exhaustive "no command method" surface test is Story 8.3; a frozen-mutation assert here is a cheap early guard.)
  8. **Malformed envelope** — `parse_car({})` (missing `data`) raises `JMRIProtocolError`, matching the existing `_data()` contract.
- Run before declaring done (use `uv run --no-sync` per project policy — never invoke tools bare):
  - `uv run --no-sync ruff check`
  - `uv run --no-sync ruff format --check`  ← separate gate from `ruff check`; CI runs both.
  - `uv run --no-sync mypy --strict src tests`  (mypy strict, `python_version = 3.11`)
  - `uv run --no-sync pytest -m "not integration"`  (baseline before this story ≈ 413 passed / 22 deselected; expect it to rise with the new tests)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 8.1] — story statement + acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics.md#FR45–FR50] — functional requirements (lines 99–104)
- [Source: _bmad-output/planning-artifacts/architecture.md#Operations Subsystem (Read-Only)] — design decisions: separate subsystem, snapshot-not-live, frozen value objects, parsing reuse, `_codes.py` untouched, Engine ≠ RosterEntry (lines 579–642)
- [Source: _bmad-output/planning-artifacts/architecture.md#Internal Layering] — file placement (lines 1059, 1093–1097, 1105)
- [Source: src/pyjmri/_parsing.py] — parser helpers + `_Parsed*` pattern to mirror (and where to diverge)
- [Source: src/pyjmri/layout.py:27] — `_NamedEntity` Protocol contract the entity classes must satisfy for 8.2
- [Source: src/pyjmri/block.py] — read-only entity docstring tone (structure deliberately NOT copied)
- [Source: memory project_operations_json_contract] — live envelope shapes + naming nuance
- [Source: memory project_operations_test_data] — exact fixture data set + parser-path coverage

### Git / recent-work intelligence

Most recent code work is Story 7.1 (`ee7fa52`, integration-test pinning) and a P2 refactor (`35e9fe1`) that **collapsed `discover()` into the `_ENTITY_SPECS` registry** in `client.py`. That registry is the pattern Story 8.2 will extend for `discover_operations()` — **not this story**, but worth knowing your entity classes must be registry-friendly (constructible from a parsed object). No code conflicts: the most recent commits touching `python_code/` are unrelated to Operations. The Operations *data* commits (`bb69873`, `5b7c2a8`) populated the profile that JMRI is now serving.

### Project context reference

- python_code is a modern Python 3.11+ async JMRI client (external, over the web server), targeting only `Basement_Revised_2024.jmri`. v1.0.x shipped to PyPI; Epic 8 is the v1.1 feature track. [Source: memory project_python_code, project_pyjmri_status]
- Only `python_code/` and `_bmad-output/` are writable; all `.jmri` dirs and shared JMRI assets are read-only — capture fixtures via the HTTP API, never by reading/copying profile XML. [Source: memory feedback_writable_paths]
- Always drive Python tooling through `uv run --no-sync <tool>`. [Source: memory feedback_use_uv]
- Both `ruff check` and `ruff format --check` are CI gates; markdownlint cleanliness on this story file matters too. [Source: memory feedback_ruff_format_gate, feedback_polish_matters]

### Review Findings (2026-06-10)

- [x] [Review][Patch] `route_stops` not sorted by `sequence_id` in `parse_train` [`_parsing.py:parse_train`] — applied
- [x] [Review][Patch] `_parsing.py` module docstring stale: still says `_Parsed<Kind>` for all parsers [`_parsing.py:4`] — applied
- [x] [Review][Patch] `default_factory=tuple` vs `= ()` inconsistency in `Train` [`operations.py:Train`] — applied
- [x] [Review][Patch] `Train.lead_engine` format undocumented (`"UP 8997"` ≠ `Engine.name` `"UP8997"`) [`operations.py:Train`] — applied
- [x] [Review][Defer] `Track` drops `length`/`type` fields from location tracks [`operations.py:Track`] — deferred, v1.1 scope limit (intentional)
- [x] [Review][Defer] Malformed nested objects (e.g. `track` field is a string) silently yield `None` [`_parsing.py:_parse_track`] — deferred, pre-existing `_optional_str` pattern

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (1M context)

### Debug Log References

- Captured live fixtures: `curl -s http://localhost:12080/json/v5/{locations,trains,cars,engines} | python3 -m json.tool`.
- Gates: `uv run --no-sync pytest -m "not integration"` → 432 passed / 22 deselected; `uv run --no-sync mypy --strict src/pyjmri` → Success, 22 source files; `uv run --no-sync ruff check` → All checks passed; `uv run --no-sync ruff format --check` → 62 files already formatted.

### Completion Notes List

- Implemented four read-only Operations entity classes (`Location`, `Train`, `Car`, `Engine`) plus three nested value objects (`Track`, `Placement`, `RouteStop`) as frozen `@dataclass(frozen=True, kw_only=True, slots=True)` — immutability is structural, satisfying the FR49 read-only boundary at the class surface.
- Added `parse_location`/`parse_train`/`parse_car`/`parse_engine` to `_parsing.py`. They return the public frozen entities directly (no `_Parsed*` intermediate, since Operations entities carry no mutable handle). Shared `_car_from_data`/`_engine_from_data` helpers serve both the top-level collection parse and the train-consist parse.
- **Verified during implementation, not assumed:** train consist elements (`train.engines[]`/`train.cars[]`) are bare inner-`data` objects (no `{type,data}` wrapper); their inner `type` field is the car/engine *type* (`"Boxcar"`/`"Diesel"`), so reading `data["type"]` as `car_type`/`engine_type` is correct and no double-unwrap is needed.
- FR48 absence path covered: `null` `trainName`/`destination` → `None`; empty reference strings (`route`, current `location`, `leadEngine`, `model`, `comment`) collapse to `None` via `_optional_str(...) or None`; null/empty nested objects → `None` Placement/Track.
- Cars/engines carry `user_name=None` and `name`=road+number (FR48 identity); locations/trains carry both names — ready for Story 8.2's dual-name `EntityCollection`.
- `train.status` kept as a raw string (`"Partial 3/27 cars"`) per AC #7; `status_code` surfaced as a plain `int` (`_codes.py` untouched — no new enum tables).
- Scope respected: no `Operations` container, no `discover_operations()`, no I/O — those are Story 8.2. `client.py`, `layout.py`, `_codes.py` unchanged.
- mypy run on `src/pyjmri` (the canonical CONTRIBUTING gate); `tests` is excluded from mypy project-wide due to the pre-existing duplicate-`conftest` limitation, not anything in this story.
- Unit-test baseline moved 413 → 432 (+19 Operations parsing tests). Update CONTRIBUTING's cited count when convenient (separate housekeeping).

### File List

- `python_code/src/pyjmri/operations.py` — NEW: `Track`, `Placement`, `RouteStop`, `Location`, `Car`, `Engine`, `Train`.
- `python_code/src/pyjmri/_parsing.py` — UPDATED: `_required_int` helper + `_parse_track`/`_parse_placement`/`_parse_route_stop`/`_car_from_data`/`_engine_from_data` + `parse_location`/`parse_car`/`parse_engine`/`parse_train`; import of entity classes.
- `python_code/src/pyjmri/__init__.py` — UPDATED: public re-exports + `__all__` for the seven new types.
- `python_code/tests/unit/test_operations_parsing.py` — NEW: 19 unit tests.
- `python_code/tests/unit/fixtures/operations/locations.json` — NEW (captured).
- `python_code/tests/unit/fixtures/operations/trains.json` — NEW (captured).
- `python_code/tests/unit/fixtures/operations/cars.json` — NEW (captured).
- `python_code/tests/unit/fixtures/operations/engines.json` — NEW (captured).

## Change Log

| Date | Change |
|------|--------|
| 2026-06-10 | Story 8.1 implemented: Operations wire-format parsers + four frozen read-only entity classes (`Location`/`Train`/`Car`/`Engine`) + nested value objects; 19 unit tests against live-captured fixtures; all gates green. Status → review. |
