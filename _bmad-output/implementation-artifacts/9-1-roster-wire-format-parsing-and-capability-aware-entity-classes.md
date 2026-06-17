# Story 9.1: Roster wire-format parsing + capability-aware read-only entity classes

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a library user,
I want JMRI's roster JSON parsed into typed read-only `RosterEntry` objects carrying each loco's identity, metadata, decoder identifiers, and per-function labels,
so that I can read a locomotive's capabilities (labeled sound, lighting, momentary functions) and reference data as proper typed attributes rather than raw JSON.

## Acceptance Criteria

1. **`RosterEntry` and `FunctionLabel` are frozen read-only entity classes** in `src/pyjmri/roster.py` (today an empty stub). Both are `@dataclass(frozen=True, kw_only=True, slots=True)`. Neither exposes a setter, command, or wait method — read-only is structural, not convention (FR56). `RosterEntry` carries (FR52): `name: str` (the roster ID / primary key), `user_name: str | None`, `dcc_address: int`, `long_address: bool`, `road_name: str | None`, `road_number: str | None`, `model: str | None`, `mfg: str | None`, `owner: str | None`, `comment: str | None`, `image_path: str | None`, `max_speed_pct: int | None`, `decoder_family: str | None`, `decoder_model: str | None`, and `function_labels: tuple[FunctionLabel, ...]` (FR53). `FunctionLabel` carries `num: int`, `label: str | None`, `lockable: bool`.
2. **`user_name` is `None`.** Roster entries have no JMRI `userName` field — the roster ID *is* the user-facing label (e.g. `"1029 NW2 Switcher"`). Set `user_name=None` (do not fabricate one), mirroring how `Car`/`Engine` are keyed by `name` only. This satisfies the `_NamedEntity` protocol (`name`, `user_name`) so Story 9.2's `Roster` collection can hold these unchanged.
3. **`parse_roster_entry` is extended and returns the public `RosterEntry` directly.** The existing `_ParsedRosterEntry` intermediate is **removed** — roster entries carry no mutable handle, so they follow the Operations direct-public-entity pattern (parser builds the public frozen class, no `_Parsed*` step). The parser populates every field in AC #1 from the `rosterEntry.data` object. (FR51/FR52/FR53 data foundation.)
4. **Function labels parse from `functionKeys` (FR53).** Each element of `data["functionKeys"]` becomes a `FunctionLabel`: `num` parsed from the `"name"` string (`"F0".."F31"` → `0..31`), `label` from `"label"` (JSON `null` **or** empty string `""` → `None`; never fabricated), `lockable` from `"lockable"` (bool). An entry whose `functionKeys` is absent or `[]` yields an empty `function_labels` tuple (valid — many real entries have no labels). **Parse all keys JMRI sends, including F29–F31; do not cap at F28** — the F0–F28 limit is a *throttle-command* constraint (Story 9.3 / FR26), not a roster-*data* constraint.
5. **Address parsing preserves the existing strict validation.** `dcc_address` is parsed from the JSON `address` **string** with the existing `.isdecimal()` guard; a non-decimal `address`, or a missing/non-boolean `isLongAddress`, raises `JMRIProtocolError` (with `entity_type="rosterEntry"`, `field=…`, `name=…`). This is the per-entry strictness the Story 9.2 collection-level skip-and-continue will wrap (FR58) — do **not** soften it here.
6. **`RosterEntry` is a distinct type from `Engine` (Operations).** Its docstring states it models the full DecoderPro catalog (everything the user ever programmed), vs `Engine` which is the operationally-active subset on the layout. The two are not aliased or conflated.
7. **Unit-tested against the captured live fixture.** `tests/unit/fixtures/roster.json` already exists — a real 44-entry capture from the basement layout (`localhost:12080`) with full fields (`mfg`, `decoderFamily`, `decoderModel`, `maxSpeedPct`, `image`, `owner`, `functionKeys`, …). A new `tests/unit/test_roster_parsing.py` round-trips every envelope and asserts the cases in **Testing Requirements** below. No live JMRI required for this story.
8. **`__init__.py` exports** `FunctionLabel` and `RosterEntry` with matching `__all__` entries, inserted alphabetically. (Do **not** export `Roster` — the container is Story 9.2.)
9. **Quality gates green.** All new public types resolve under `mypy --strict src/pyjmri`; `ruff check`, `ruff format --check`, and `pytest -m "not integration"` all pass.

> **Scope fence — this story is parsing + entity classes ONLY.** Do **not** add in this story: the `Roster` container, `by_address`, the address index, any `discover()`/`client.py` change, any `Layout.roster` attribute, `throttle_for_entry`, or the capability-classification decision function. Those are Stories 9.2 (container + standalone `discover_roster()` + lookup) and 9.3 (throttle + classification). `roster.py` here contains only `FunctionLabel` + `RosterEntry`; `_parsing.py` and `__init__.py` are updated; **`client.py`, `layout.py`, `_codes.py`, `throttle.py` are NOT touched.** `discover()` does not reference roster today (confirmed — see Dev Notes), so changing `parse_roster_entry`'s return type breaks nothing.

## Tasks / Subtasks

- [x] **Task 1 — Verify the existing fixture covers every parser path** (AC: #7) — confirmed `tests/unit/fixtures/roster.json` is a live 44-entry capture containing: sound entries with real labels ("Bell", "Horn 1", "Shutdown and Startup"); all-null-label motor-only entries ("1029 NW2 Switcher"); heterogeneous `decoderFamily` ("Jan 2012", "Sep 2018", "ESU LokSound 5", "E-Z Command decoders", …); and `functionKeys` extending to **F29–F31**. No re-capture needed.
  - [x] `maxSpeedPct` is present on the sampled entries but parsed via `_optional_int` (returns `None` if ever absent) — safest given the heterogeneous fleet.
- [x] **Task 2 — Define `FunctionLabel` and `RosterEntry` in `roster.py`** (AC: #1, #2, #6) — replaced the stub. Both frozen `@dataclass(frozen=True, kw_only=True, slots=True)`; `name`/`user_name` first (satisfy `_NamedEntity`). `RosterEntry` docstring documents the read-only boundary, the `user_name is None` rule, and the RosterEntry-vs-`Engine` distinction; `FunctionLabel` docstring notes `lockable` semantics and that labels (not family strings) signal capability.
- [x] **Task 3 — Extend `parse_roster_entry` in `_parsing.py`** (AC: #3, #4, #5) — returns public `RosterEntry`; deleted `_ParsedRosterEntry`. Added `_parse_function_labels(data)` (parses every `functionKeys` element, num from `"Fnn"`, `null`/`""` label → `None`, missing `lockable` → `False`, non-list → `()`) and `_optional_int`. Reused `_data`/`_required_str`/`_optional_str`. Kept the `.isdecimal()` address guard and `isLongAddress` bool guard exactly. Updated the module docstring to list `parse_roster_entry` among the handle-free direct-public-entity parsers.
- [x] **Task 4 — Export public types** (AC: #8) — added `FunctionLabel` (after `EntityCollection`) and `RosterEntry` (before `Route`) to `__init__.py` imports and `__all__`; `ruff check` confirms import-sort.
- [x] **Task 5 — Write `tests/unit/test_roster_parsing.py`** (AC: #7) — 17 tests covering all cases below; migrated the 6 roster tests out of `test_parsing.py` (removed its now-unused `parse_roster_entry` import + roster docstring mention) so roster parsing lives in one suite.
- [x] **Task 6 — Run all gates** (AC: #9) — `ruff check` (passed), `ruff format --check` (69 files formatted), `mypy --strict src/pyjmri` (Success, 22 files), `pytest -m "not integration"` (621 passed / 25 deselected). All green.

## Dev Notes

### What this story is, in one sentence

Turn the dead Epic-2 roster scaffolding (`_ParsedRosterEntry` + a thin `parse_roster_entry`, both currently unused) into a real capability-aware read-only `RosterEntry` (+ `FunctionLabel`), mirroring **exactly** the Story 8.1 Operations pattern — frozen dataclasses + a parser that returns the public entity directly. No container, no discovery, no I/O.

### Critical: the roster scaffolding is currently DEAD CODE — changing it is safe

`client.py` has **zero** roster references; `discover()` does not fetch, parse, or expose the roster today (the `Layout` class has no `roster` attribute). The existing `parse_roster_entry` → `_ParsedRosterEntry` (`_parsing.py:312`, `:102`) is **never called anywhere in `src/`**. Therefore removing `_ParsedRosterEntry` and changing `parse_roster_entry`'s return type to the public `RosterEntry` **cannot break any existing behavior or test** (Epics 1–8 are byte-for-byte unaffected). [Source: src/pyjmri/client.py (no roster refs); src/pyjmri/layout.py (no roster attr); src/pyjmri/_parsing.py:312]

### Exact JMRI JSON shape (from the real captured fixture — not invented)

A real entry from `tests/unit/fixtures/roster.json` (collection URL `/json/v5/roster`; each envelope's `type` is `"rosterEntry"`, singular):

```json
{"type":"rosterEntry","data":{
  "name":"1029 NW2 Switcher", "address":"1029", "isLongAddress":true,
  "road":"Union Pacific", "number":"1029", "mfg":"Kato",
  "decoderModel":"DN123K3", "decoderFamily":"Series 3 with FX3, silent, readback",
  "model":"176-4374", "comment":"$92 plus decoder", "maxSpeedPct":100,
  "image":null, "icon":null, "shuntingFunction":"", "owner":"Mike Dean",
  "dateModified":"2015-08-15T14:58:45.000+00:00",
  "functionKeys":[
    {"name":"F0","label":null,"lockable":true,"icon":null,"selectedIcon":null},
    {"name":"F1","label":null,"lockable":true,"icon":null,"selectedIcon":null}, ...]
}}
```

→ `RosterEntry(name="1029 NW2 Switcher", user_name=None, dcc_address=1029, long_address=True, road_name="Union Pacific", road_number="1029", model="176-4374", mfg="Kato", owner="Mike Dean", comment="$92 plus decoder", image_path=None, max_speed_pct=100, decoder_family="Series 3 with FX3, silent, readback", decoder_model="DN123K3", function_labels=(FunctionLabel(num=0, label=None, lockable=True), FunctionLabel(num=1, label=None, lockable=True), ...))`.

A **sound** entry in the same fixture has real labels (`"Headlights"`, `"Bell"`, `"Horn 1"`, `"Shutdown and Startup"`, …) and `functionKeys` running up to **F31**. The decoder-family strings are heterogeneous and date-stamped (`"Jan 2012"`, `"Sep 2018"`, `"ESU LokSound 5"`, `"E-Z Command decoders"`) — confirming the architecture/brief rule that **capability must be read from function labels, not the family string** (that classification work is Story 9.3, not here; here you just preserve the labels faithfully).

### Field mapping (JMRI camelCase → snake_case)

| JMRI `data` key | `RosterEntry` field | Helper | Notes |
|---|---|---|---|
| `name` | `name` | `_required_str` | roster ID / primary key |
| (none) | `user_name` | — | always `None` (AC #2) |
| `address` (string) | `dcc_address: int` | existing `.isdecimal()` guard then `int(...)` | keep strict |
| `isLongAddress` | `long_address: bool` | existing bool guard | keep strict |
| `road` | `road_name` | `_optional_str` | |
| `number` | `road_number` | `_optional_str` | |
| `model` | `model` | `_optional_str` | |
| `mfg` | `mfg` | `_optional_str` | |
| `owner` | `owner` | `_optional_str` | |
| `comment` | `comment` | `_optional_str` | holds maintenance notes + prices in this fleet |
| `image` | `image_path` | `_optional_str` | relative URL or `null`; **not** a filesystem path. (`icon` not surfaced this story.) |
| `maxSpeedPct` | `max_speed_pct: int \| None` | `_optional_int` (add) or `_required_int` — Task 1 decides | bind the literal string `"maxSpeedPct"` |
| `decoderFamily` | `decoder_family` | `_optional_str` | definition-file name, NOT a capability tag |
| `decoderModel` | `decoder_model` | `_optional_str` | |
| `functionKeys[]` | `function_labels: tuple[FunctionLabel,...]` | `_parse_function_labels` (add) | parse all; `label` `null`/`""` → `None` |

`shuntingFunction`, `icon`, `dateModified`, `selectedIcon`, per-key `icon` — not surfaced in v1.2 (unknown JSON keys are ignored by design).

### `_parse_function_labels` shape (new helper)

Build from `data.get("functionKeys")`: if not a list → `()`. For each element that is a dict, parse `num` by stripping the leading `"F"` from `element["name"]` and `int(...)` the rest; `label = _optional_str(element, "label")` (this already maps `null`→`None`; also map `""`→`None`); `lockable = bool(element.get("lockable"))`. Return a `tuple[FunctionLabel, ...]`. Mirror the Operations `_parse_route_stop` / list-comprehension-into-tuple idiom (`_parsing.py:393`, `:460`). Use `tuple`, never `list`, on the frozen dataclass.

### Type/None rules (mirror Story 8.1)

- `null` JSON → `None` (`_optional_str` already does this).
- Empty string `""` for `label` (and any free-text field) → `None`.
- Absent/empty `functionKeys` array → empty tuple `()`.
- `maxSpeedPct` is a JSON integer → `int`; route it through an int helper, never `_required_state` (that's enum-only). `bool` must be rejected as an int (the existing `_required_int` already does `isinstance(value, int) and not isinstance(value, bool)`).

### Established patterns to FOLLOW (read these; do not reinvent)

- **`src/pyjmri/_parsing.py`** — the module you extend. The Operations parsers (`parse_location`/`parse_car`/`parse_engine`/`parse_train`, lines 357–493) are your exact template: they return public frozen entities directly, with shared `_*_from_data` / `_parse_*` helpers and list-into-tuple comprehensions. `parse_roster_entry` (line 312) is what you transform. Reuse `_data`, `_required_str`, `_optional_str`, `_required_bool`, `_required_int`; add `_optional_int` and `_parse_function_labels` in the same `JMRIProtocolError(..., entity_type=, field=, name=)` style. [Source: src/pyjmri/_parsing.py]
- **`src/pyjmri/operations.py`** — the structural template for `roster.py`: frozen `@dataclass(frozen=True, kw_only=True, slots=True)`, `name`/`user_name` first, value objects (`Track`/`RouteStop`) for nested data — `FunctionLabel` is your analog of `RouteStop`. Read its docstring tone. [Source: src/pyjmri/operations.py]
- **`src/pyjmri/layout.py` → `_NamedEntity` Protocol (lines 27–37)** — Story 9.2's `Roster` collection will require `name: str` + `user_name: str | None`. `RosterEntry` MUST expose both (with `user_name=None`). [Source: src/pyjmri/layout.py:27]
- **`src/pyjmri/roster.py`** — the stub you replace. Currently `__all__: list[str] = []` with a stale "Story 2.3 will add the RosterEntry class" docstring. [Source: src/pyjmri/roster.py]
- **`src/pyjmri/_codes.py` stays untouched** — roster entries carry no integer state enums (`maxSpeedPct` is a plain percent int, not an enum). [Source: src/pyjmri/_codes.py]

### Project Structure Notes

New/changed files (all under `python_code/`, the only writable tree — `.jmri` profiles and shared JMRI assets are read-only):

- `src/pyjmri/roster.py` — **UPDATE** (stub → real): `FunctionLabel`, `RosterEntry`. [arch path: src/pyjmri/roster.py — pre-reserved in the architecture directory tree]
- `src/pyjmri/_parsing.py` — **UPDATE**: extend `parse_roster_entry` to return `RosterEntry`; delete `_ParsedRosterEntry`; add `_parse_function_labels` (+ `_optional_int` if needed); import from `roster.py`.
- `src/pyjmri/__init__.py` — **UPDATE**: export `FunctionLabel`, `RosterEntry` + `__all__`, alphabetically.
- `tests/unit/test_roster_parsing.py` — **NEW**.
- `tests/unit/fixtures/roster.json` — **EXISTS** (live 44-entry capture); reuse as-is unless Task 1 finds a gap.

`_parsing.py` imports from `roster.py`; `roster.py` imports nothing from `_parsing.py` (one-directional, no cycle — same as `operations.py`). `client.py`, `layout.py`, `_codes.py`, `throttle.py` are intentionally **not** touched (scope fence; Epics 1–8 unchanged).

### Testing Requirements

- Framework `pytest`; new file `tests/unit/test_roster_parsing.py`; mirror `tests/unit/test_parsing.py` (the `load_fixture` session fixture in `tests/unit/conftest.py` interpolates `fixtures/<name>.json`, so `load_fixture("roster")` works — no conftest change). [Source: tests/unit/test_parsing.py, tests/unit/conftest.py]
- Required cases:
  1. **Round-trip happy path** — every one of the 44 envelopes in `roster.json` parses to a `RosterEntry` without error; collection is non-empty.
  2. **Full metadata populated** — for a known entry (e.g. `"1029 NW2 Switcher"`): `dcc_address == 1029`, `long_address is True`, `road_name == "Union Pacific"`, `mfg == "Kato"`, `owner == "Mike Dean"`, `decoder_family`/`decoder_model`/`max_speed_pct` populated, `comment` present.
  3. **`user_name` is `None`** on every parsed entry.
  4. **Sound entry → real labels** — an entry with labeled functions yields `function_labels` containing `FunctionLabel`s whose `label` includes the expected strings (e.g. a `"Bell"` or `"Horn 1"`); assert at least one `label is not None`.
  5. **Motor-only / null labels** — a `null`-label entry (`"1029 NW2 Switcher"`) yields `function_labels` whose elements have `label is None` (the keys are **present** with `None` labels, not dropped).
  6. **Function-number parsing past F28** — confirm an entry with F29–F31 keys parses those into `FunctionLabel(num=29..31, ...)` (no cap, no crash).
  7. **Empty/absent functionKeys** — an entry (or a synthetic envelope) with `functionKeys: []` or the key absent → `function_labels == ()`.
  8. **Frozen / read-only (supports FR56)** — `with pytest.raises(dataclasses.FrozenInstanceError): entry.dcc_address = 1` (cheap early guard; the exhaustive no-mutating-method surface test is Story 9.4).
  9. **Malformed entry raises (per-entry strictness; FR58 wrap is 9.2)** — `parse_roster_entry` on a synthetic envelope with a non-decimal `address` raises `JMRIProtocolError`; likewise a missing/non-bool `isLongAddress`; likewise `parse_roster_entry({})` (missing `data`).
- Run before declaring done (always `uv run --no-sync`, never bare):
  - `uv run --no-sync ruff check`
  - `uv run --no-sync ruff format --check`  ← separate CI gate from `ruff check`; run both.
  - `uv run --no-sync mypy --strict src/pyjmri`  (canonical CONTRIBUTING gate; `tests` excluded project-wide due to the known duplicate-`conftest` mypy limitation — not anything in this story)
  - `uv run --no-sync pytest -m "not integration"`  (baseline at story start: **610 passed / 25 deselected**; expect it to rise with the new tests)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 9.1] — story statement + acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics.md — Roster FR block FR51–FR59] — functional requirements; note **FR55 was amended 2026-06-16** (unknown address warns-and-drives, not an error — but that's Stories 9.2/9.3, not 9.1)
- [Source: _bmad-output/planning-artifacts/epics.md — "Roster increment (v1.2) — additional technical requirements"] — standalone `discover_roster()`, graceful-degrade, label-based classification, reuse-existing-assets, wire format
- [Source: _bmad-output/planning-artifacts/prd.md#Roster (Read-Only, Capability-Aware)] — FR52/FR53 field + capability semantics; Journey 6
- [Source: _bmad-output/planning-artifacts/product-brief-roster-distillate.md] — JMRI wire format (confirmed from JMRI master), RosterEntry field list, "decoderFamily is a definition-file name not a capability tag", reuse `parse_roster_entry`+`roster.py`, capture live fixture
- [Source: src/pyjmri/_parsing.py:312] — `parse_roster_entry` + `_ParsedRosterEntry` to transform; Operations parsers (357–493) as the direct-public-entity template
- [Source: src/pyjmri/operations.py] — frozen-dataclass structural template for `roster.py`
- [Source: src/pyjmri/layout.py:27] — `_NamedEntity` protocol the entity must satisfy for Story 9.2
- [Source: _bmad-output/implementation-artifacts/8-1-operations-wire-format-parsing-and-read-only-entity-classes.md] — the near-exact sibling story (pattern, test style, gate commands)

### Git / recent-work intelligence

No recent commit touches the roster path — recent `python_code/` work is notebook/example tinkering (`b5351fc`, `9cd8548`, `1f63c66`) plus `cec8beb` (throttle `set_speed` `forward` now defaults forward — relevant to Story 9.3, not here). The Epic-8 P2 refactor collapsed `discover()` into an `_ENTITY_SPECS` registry in `client.py`; Story 9.2 (not this one) will add a standalone `discover_roster()` method (NOT extending that registry — the roster is a separate read-only snapshot like Operations). Your entity class should be constructible from a parsed object, but you do **not** wire it up here. [Source: git log -- python_code/]

### Project context reference

- `python_code/` is a modern Python 3.11+ async JMRI client (external, over the web server), targeting only `Basement_Revised_2024.jmri`. v1.0.x shipped to PyPI; Epic 8 (Operations) is v1.1; this Epic 9 (Roster) is the v1.2 track. [Source: memory project_python_code, project_pyjmri_status, project_roster_feature]
- Only `python_code/` and `_bmad-output/` are writable; all `.jmri` dirs and shared JMRI assets (incl. `roster.xml`, `roster/`) are read-only — the library reads JMRI's JSON wire format over HTTP, never the profile XML. [Source: memory feedback_writable_paths]
- Always drive Python tooling through `uv run --no-sync <tool>`. [Source: memory feedback_use_uv]
- Both `ruff check` and `ruff format --check` are CI gates; keep this story file markdownlint-clean too. [Source: memory feedback_ruff_format_gate, feedback_polish_matters]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (1M context)

### Debug Log References

- Gates (all `uv run --no-sync`): `ruff check` → All checks passed; `ruff format --check` → 69 files already formatted; `mypy --strict src/pyjmri` → Success, no issues in 22 source files; `pytest -m "not integration"` → 621 passed / 25 deselected (baseline at story start was 610/25; +17 new roster tests, −6 migrated out of `test_parsing.py`).
- Fixture confirmed live-captured with sound labels, null-label entries, heterogeneous decoder families, and F29–F31 keys: `grep -c '"type": "rosterEntry"'` → 44.

### Completion Notes List

- Implemented `FunctionLabel` and `RosterEntry` as frozen `@dataclass(frozen=True, kw_only=True, slots=True)` in `roster.py` (was an empty stub) — read-only is structural (FR56). `RosterEntry.user_name` is always `None` (the roster ID is the label; mirrors Operations cars/engines), satisfying the `_NamedEntity` protocol for Story 9.2's collection.
- Rewrote `parse_roster_entry` to return the public `RosterEntry` directly and **removed** the dead `_ParsedRosterEntry` intermediate — safe because the roster scaffolding was unused (no `discover()`/`client.py` reference; verified). Extended it with `mfg`/`owner`/`image_path`/`max_speed_pct`/`decoder_family`/`decoder_model`/`function_labels`.
- Added `_parse_function_labels`: parses **all** `functionKeys` (num from `"Fnn"`), `null`/`""` label → `None`, missing `lockable` → `False`, non-list/absent → `()`. F29–F31 are captured as data — the F0–F28 limit is a throttle-command constraint (Story 9.3), not a roster-data one. Added a bool-rejecting `_optional_int` for `maxSpeedPct`.
- Kept the existing strict per-entry validation (`.isdecimal()` address guard, `isLongAddress` bool guard) unchanged — the FR58 collection-level skip-and-continue wrap is Story 9.2.
- Migrated the 6 pre-existing roster tests out of `test_parsing.py` into the new `test_roster_parsing.py` (17 tests total) so roster parsing has a single suite, matching how Operations got `test_operations_parsing.py`. The `ignores_extra_jmri_fields` test was inverted into `surfaces_decoder_and_owner_fields` (those fields are now surfaced, not ignored).
- Scope respected: no `Roster` container, no `by_address`, no `discover()`/`Layout`/`throttle` change. `client.py`, `layout.py`, `_codes.py`, `throttle.py` untouched. Epics 1–8 behavior unchanged (621 passing includes the full existing suite).
- `mypy` run on `src/pyjmri` (canonical CONTRIBUTING gate); `tests` excluded project-wide per the pre-existing duplicate-`conftest` limitation. Unit baseline moved 610 → 621; CONTRIBUTING's cited count is housekeeping for a later story.

### File List

- `python_code/src/pyjmri/roster.py` — UPDATED (stub → real): `FunctionLabel`, `RosterEntry`.
- `python_code/src/pyjmri/_parsing.py` — UPDATED: removed `_ParsedRosterEntry`; added `_optional_int` + `_parse_function_labels`; rewrote `parse_roster_entry` to return `RosterEntry`; import from `roster.py`; module docstring updated.
- `python_code/src/pyjmri/__init__.py` — UPDATED: re-export `FunctionLabel`, `RosterEntry` + `__all__`.
- `python_code/tests/unit/test_roster_parsing.py` — NEW: 17 unit tests against the live `roster.json` fixture + synthetic envelopes.
- `python_code/tests/unit/test_parsing.py` — UPDATED: removed the 6 migrated roster tests, the `parse_roster_entry` import, and the roster docstring mention.

## Change Log

| Date | Change |
|------|--------|
| 2026-06-16 | Story 9.1 drafted (create-story): capability-aware `RosterEntry` + `FunctionLabel` + extended `parse_roster_entry` (drops `_ParsedRosterEntry`, returns public entity) + unit tests vs the live 44-entry `roster.json` fixture. Scope fenced to parsing + entity classes; container/discover/throttle deferred to 9.2/9.3. Status → ready-for-dev. |
| 2026-06-16 | Story 9.1 implemented: `roster.py` stub → `FunctionLabel`/`RosterEntry` frozen classes; `parse_roster_entry` returns public entity (F-labels incl. F29+, full metadata); roster tests migrated into `test_roster_parsing.py` (17 tests); all gates green (621 passed / 25 deselected). Status → review. |
| 2026-06-17 | Forward-reference polish for the Epic 9 correct-course (roster now standalone `discover_roster()`, not folded into `Layout`); deliverables unchanged. **Code review** (with 9.2): all 9.1 ACs confirmed satisfied. One shared-`_parsing.py` robustness patch from that review touched this story's `_parsing._data` (raise `JMRIProtocolError` on a non-dict envelope) + added `test_raises_on_non_dict_envelope`. All gates green (636 passed / 26 deselected). Status → done. |
