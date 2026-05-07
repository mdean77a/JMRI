# Story 2.2: Wire-format translation — `_codes`, `_parsing`, per-entity state enums

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a library developer,
I want a private `_codes.py` mapping JMRI integer state codes to per-entity Enum members and a private `_parsing.py` translating JMRI's camelCase JSON into typed Python values,
so that integer codes never cross the public API and the JSON-translation boundary is the single place where wire-format details live.

## Acceptance Criteria

1. **Per-entity state enums shipped in their target public modules.** Given Story 2.1's transport boundary, when `turnout.py`, `sensor.py`, `block.py`, `light.py`, `power.py`, and `signal.py` are added with state/aspect enums only (no entity class yet), then every state enum is a plain `enum.Enum` (not `IntEnum`, not `StrEnum`); `UNKNOWN` is a member of every state enum that has an unknown wire condition (FR14); each enum's literal member set matches §"Per-entity enum membership" below; integer JMRI codes are kept private — the enums expose no integer values to user code; `signal.py` exports both `SignalHeadAppearance` (from JMRI integer codes) and `SignalMastAspect` (from JMRI string aspects in the **basic** signaling system).
2. **`_codes.py` contains one int-→-EnumMember table per state-bearing entity type.** Given `_codes.py` is added, when unit tests inspect it, then it exports `TURNOUT_STATE: Mapping[int, TurnoutState]`, `SENSOR_STATE`, `BLOCK_STATE`, `LIGHT_STATE`, `POWER_STATE`, `SIGNAL_HEAD_APPEARANCE` covering every JMRI-documented integer code AND every observed live-layout integer (notably `state=0`, see §"Live JMRI integer-code observations" below); `test_codes.py` asserts the full code-set per entity is mapped, and that `UNKNOWN` is reachable from at least one integer in every table.
3. **`_parsing.py` exposes a pure parse function per entity type returning a typed dataclass.** Given `_parsing.py` is added with `parse_turnout`, `parse_sensor`, `parse_block`, `parse_light`, `parse_memory`, `parse_route`, `parse_signal_head`, `parse_signal_mast`, `parse_roster_entry`, and `parse_power`, when each is called with the JMRI envelope `{"type": "<kind>", "data": {...}}` (the shape returned by `HTTPClient.get`), then it returns a frozen `_Parsed<Kind>` dataclass with snake_case fields and Enum-typed state values; `Any` appears only on the JSON-input parameter (`payload: dict[str, Any]`) and never in any return type; unknown JSON keys in `data` are silently ignored (forward-compat per architecture §JSON ↔ Python Translation); missing expected keys raise `JMRIProtocolError` with `entity_type`, `field`, and (where available) `name` populated in `context`.
4. **Wire-format translation rules are uniform across parsers.** Given any parser, when it processes a JMRI envelope, then `userName` translates to `user_name`, `systemName` (where present) to `system_name`, `name` (already snake-shaped) is read as-is and used for the `name` field; `userName: null` translates to `None` (not the string `"null"`); integer state codes are translated through `_codes.py` only — no parser does its own int-to-enum mapping; an integer present in the JSON but absent from the relevant `_codes.py` table raises `JMRIProtocolError` (contract drift, fail-fast); `signalMast` aspect strings are translated to `SignalMastAspect` enum members via Python's value-based enum lookup (`SignalMastAspect(jmri_string)`); an aspect string outside the basic-signaling-system enum raises `JMRIProtocolError` with an actionable message — see §"SignalMast aspect handling" below.
5. **`tests/unit/fixtures/` ships synthetic JSON sampled from live JMRI for every entity type.** Given the live JMRI used during 2.1 implementation, when fixtures are added, then `tests/unit/fixtures/` contains one `.json` file per entity type listed in §"Fixture files and their canonical paths"; each file holds a JSON array of envelope objects (the exact shape `HTTPClient.get` returns for collection endpoints); fixtures are captured directly from the live basement layout — narrow code coverage is acceptable (per Mikey's design call, see §"Live JMRI integer-code observations"); `tests/unit/conftest.py` exposes a `load_fixture(name)` helper that returns the parsed JSON list.
6. **Per-parser unit tests verify the round-trip from fixture → typed dataclass.** Given the fixtures and parsers, when `tests/unit/test_parsing.py` runs, then for every entity type it loads the fixture and parses each envelope, asserting that snake_case fields are populated and enum members are correct; when it constructs malformed envelopes inline (missing `data`, missing `name`, integer state outside the codes table, signalMast aspect outside the basic system), it asserts `JMRIProtocolError` with the appropriate `context` keys. **Note:** documented-but-unobserved enum values (e.g., `TurnoutState.INCONSISTENT`) are exercised via inline-constructed test envelopes in this same file — the fixture coverage is narrow on purpose, but the rare-code paths still get test coverage.
7. **Public re-exports surface every state enum.** Given `__init__.py`, when it is imported, then `TurnoutState`, `SensorState`, `BlockState`, `LightState`, `PowerState`, `SignalHeadAppearance`, and `SignalMastAspect` are importable as `from pyjmri import …`; `__all__` includes them; the module-level `NullHandler` install is preserved.
8. **All four local quality gates remain green and the CI matrix passes.** Given Story 2.2's deliverables, when the four gates run from `python_code/`, then `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src/pyjmri`, and `uv run pytest -m "not integration"` all exit 0 with the new test count visible; the GitHub Actions six-job CI matrix goes green on push.

## Tasks / Subtasks

- [x] **Task 1: Create `src/pyjmri/_codes.py` with per-entity int-→-Enum tables** (AC: #2, #4)
  - [x] Create `_codes.py`. Module-only — no classes, no functions, no `raise` statements. See §"`_codes.py` canonical shape" for the exact table shape and contents.
  - [x] **Source of truth** for documented integer constants is JMRI's published Java interfaces (`Turnout`, `Sensor`, `Block`, `Light`, `SignalHead`, `Power`). The integers below are not invented — they come from JMRI's public API. The dev agent should not paraphrase or "round" them.
  - [x] **Live-layout robustness:** the tables MUST include the `state=0` mappings noted in §"Live JMRI integer-code observations." Skipping these will cause the discovery tests in Story 2.5 to crash on the basement layout the moment they parse an idle turnout or a block without an occupancy sensor.
  - [x] Tables are typed as `Mapping[int, <EnumType>]` (use `types.MappingProxyType` over a literal dict to make them immutable at module load — see §"Why MappingProxyType").
  - [x] **No `__all__`** in `_codes.py`. Private modules don't declare `__all__` (architecture §Public API Discipline applies to public modules; `_codes.py` is internal-only and should not be part of any public surface).
  - [x] Module-level logger: `logger = logging.getLogger(__name__)` → `pyjmri._codes`. (Even though there are no log calls in 2.2; the logger declaration matches every other module per architecture §Logging Discipline.)

- [x] **Task 2: Seed per-entity public modules with their state enums** (AC: #1, #4, #7)
  - [x] Create six new public modules: `turnout.py`, `sensor.py`, `block.py`, `light.py`, `power.py`, `signal.py`. Each one contains *only* its enum(s), `__all__`, and a module-level logger. **No entity classes** — those are Story 2.3.
  - [x] Also create `memory.py`, `route.py`, and `roster.py` as **module stubs** with just `from __future__ import annotations`, `__all__ = []`, and a module-level logger. They have no enums to define in 2.2; Story 2.3 will fill them in. Creating them now keeps imports stable across the boundary and prevents Story 2.3 from doing distracting boilerplate work.
  - [x] **Enum classes use `enum.Enum`, not `enum.IntEnum` and not `enum.StrEnum`.** Architecture §Domain State Modeling: "JMRI integer codes kept private." If any user could write `if turnout.state == 2:`, the encapsulation is broken. The Enum members carry no integer value; their `.value` is conventionally a lowercase string for `repr()` and for `str()` ergonomics, but it is NOT the JMRI wire code.
  - [x] **Member values:** use lowercase string names matching the enum member (e.g., `TurnoutState.CLOSED.value == "closed"`). This makes `print(turnout.state)` produce `TurnoutState.CLOSED` and `str(turnout.state.value)` produce `"closed"` — both readable in user code and log lines without leaking integers.
  - [x] See §"Per-entity enum membership" for the exact member set for each enum. Note that **`BlockState` includes `UNDETECTED`** (0 → UNDETECTED): live JMRI emits state=0 for blocks without occupancy sensors, and a separate enum member preserves the distinction between "unknown to user" and "block has no detector." This is a deliberate expansion of the architecture's example enum membership (Mikey-confirmed 2026-05-07).
  - [x] **`signal.py` ships two enums:** `SignalHeadAppearance` (integer-coded, see §"Per-entity enum membership") and `SignalMastAspect` (string-valued, seeded with the basic-signaling-system aspects per §"SignalMast aspect handling"). Both enums live in the same module because architecture's project structure colocates them in `signal.py`.
  - [x] **README warning is not in scope for Story 2.2.** When Story 6.2 (README Limitations section) is implemented, it MUST include a note that pyjmri v1 supports only JMRI's "basic" signaling-system aspect set; layouts using AAR-1946, NORAC, or custom signaling will see `JMRIProtocolError` on signal-mast read. Capture this as a follow-up for Story 6.2; do not author the README content here.

- [x] **Task 3: Create `src/pyjmri/_parsing.py`** (AC: #3, #4)
  - [x] Create `_parsing.py` with one `parse_<entity>` function per entity type. See §"`_parsing.py` canonical shape" for the exact pattern and per-entity field mappings.
  - [x] **Each parser receives a JMRI envelope.** `HTTPClient.get` returns either a single envelope `{"type": "...", "data": {...}}` (named-entity GET) or a list of envelopes (collection GET). Parsers operate on a single envelope. The discovery code in Story 2.5 will iterate the list and call the parser per element — that's not 2.2's job.
  - [x] **Each parser returns a private frozen dataclass `_Parsed<Kind>`** defined in `_parsing.py` itself. These dataclasses are the typed shape used to construct entity classes in Story 2.3; their fields match the entity's eventual public attributes (see §"Parsed dataclass shapes per entity"). The leading underscore in `_Parsed<Kind>` marks them as internal.
  - [x] **Translation rules — applied uniformly:**
    - `userName` → `user_name`. If JSON has `userName: null` (or the key is absent), the field is `None`. Architecture §JSON ↔ Python Translation: missing optional keys map to `None`; missing required keys raise.
    - `systemName` → `system_name`. (JMRI's envelope uses `name` for system name in most entity types, but some payloads include `systemName` separately. Treat `name` as the system name.)
    - Integer `state` codes → enum member via the matching `_codes.py` table. Use `<table>.get(int_code)`; if `None`, raise `JMRIProtocolError(entity_type=..., field="state", state_code=int_code, name=<system_name>)`.
    - Unknown keys in `data` are silently ignored. Iterate only the keys the parser knows about.
    - Missing required keys raise `JMRIProtocolError(entity_type=..., field=<key_name>)`.
  - [x] **`signalMast` is special.** JMRI returns `aspect: "Clear"` (string), not an integer. The parser translates the string to a `SignalMastAspect` enum member via Python's value-based lookup (`SignalMastAspect(aspect_str)`). On `ValueError` (aspect string not in the basic-system enum), the parser raises `JMRIProtocolError` with an actionable message naming the offending aspect. There is no `SIGNAL_MAST_ASPECT` table in `_codes.py` — string-to-enum translation lives entirely in the enum definition. See §"SignalMast aspect handling" for the canonical pattern.
  - [x] **`roster` envelope quirk.** The collection URL is `/json/v5/roster` but each envelope's `type` field is `"rosterEntry"` (not `"roster"`). The parser is `parse_roster_entry` accordingly. Document this in the function's docstring so a future developer hunting "why is the URL different from the type" finds the answer.
  - [x] **`power` envelope.** Singleton, not a collection. The envelope is `{"type": "power", "data": {"name": "<connection>", "state": <int>, "default": <bool>}}`. The parser returns `_ParsedPower(name=..., state=PowerState, default=bool)`.
  - [x] **No `__all__`** in `_parsing.py` (private module). Module-level logger: `logger = logging.getLogger(__name__)` → `pyjmri._parsing`.
  - [x] **No imports of `httpx`, `Client`, or `_transport`.** Architecture §Architectural Boundaries: parsing is the wire-translation layer above transport but below domain. It imports only stdlib + `enum` + the per-entity public modules (for the enums) + `_codes` (for the tables) + `pyjmri.exceptions`.

- [x] **Task 4: Capture synthetic JSON fixtures from live JMRI** (AC: #5)
  - [x] Create `tests/unit/fixtures/` (new directory) and one JSON file per entity type. See §"Fixture files and their canonical paths" for the exact list.
  - [x] **Capture procedure** (run with JMRI live on `localhost:12080`, the same JMRI that Story 2.1 verified against):

    ```bash
    cd python_code
    mkdir -p tests/unit/fixtures
    for ep in turnout sensor block light memory route signalHead signalMast roster power; do
      curl -s "http://localhost:12080/json/v5/$ep" \
        | python3 -m json.tool > "tests/unit/fixtures/${ep}.json"
    done
    ```

    Then **rename** `signalHead.json` → `signal_heads.json`, `signalMast.json` → `signal_masts.json`, `roster.json` → `roster.json`, and pluralize the rest (`turnouts.json`, `sensors.json`, etc.) per the architecture's project-structure spec.
  - [x] **Narrow-coverage policy** (Mikey-confirmed 2026-05-07). Fixtures are captured **as-is** from the idle live layout. We are **not** fabricating extra envelopes to exercise documented-but-unobserved enum values. The rationale: pyjmri's unit tests verify the parser machinery, not JMRI's full state space. Coverage of rare codes (`TurnoutState.INCONSISTENT`, `SignalHeadAppearance.FLASHRED`, etc.) is achieved via inline-constructed test envelopes in `test_parsing.py` — see Task 8. No `_README.md` needed; no synthetic envelopes in fixture files.
  - [x] **Privacy / size considerations.** The basement layout is a personal project; the fixtures will commit to a public GitHub repo. Names like "South Turnout 100" are fine to commit (already public in roster.csv). DCC addresses in `roster.json` are also already public. No redaction required.
  - [x] **`light.json` will be an empty array** (live layout has zero lights). That is fine — `parse_light` is exercised via inline-constructed envelopes in `test_parsing.py`, not via the fixture. The empty `lights.json` is still committed for shape-consistency with the rest of the fixtures directory.

- [x] **Task 5: Add `tests/unit/conftest.py` fixture loader** (AC: #5)
  - [x] Replace the currently-empty `tests/unit/conftest.py` with a `load_fixture(name: str) -> list[dict[str, Any]]` helper that reads `tests/unit/fixtures/<name>.json` and returns the parsed JSON list. See §"`tests/unit/conftest.py` canonical shape."
  - [x] **Pytest-fixture vs. helper-function design choice:** prefer a plain function exposed via a session-scoped pytest fixture: `@pytest.fixture(scope="session") def load_fixture() -> Callable[[str], list[dict[str, Any]]]`. Tests then call `load_fixture("turnouts")` directly. Keeps test bodies short.
  - [x] Use `Path(__file__).parent / "fixtures"` to resolve the fixtures directory; avoid hard-coded absolute paths.

- [x] **Task 6: Update `src/pyjmri/__init__.py` to re-export state enums** (AC: #7)
  - [x] Add re-exports for `TurnoutState`, `SensorState`, `BlockState`, `LightState`, `PowerState`, `SignalHeadAppearance`, `SignalMastAspect`. Add each name to `__all__` (alphabetically).
  - [x] **Do NOT re-export the parser functions or `_Parsed<X>` dataclasses.** They are private (`_parsing.py`). Architecture §Public API Discipline: "Private modules (`_*.py`) are import-internal only."
  - [x] **Do NOT re-export `_codes.py`.** Same reason.
  - [x] **Preserve the `NullHandler` install line** verbatim. AC #5 of Story 2.1 still applies and is regression-checked.

- [x] **Task 7: Add unit tests for `_codes.py`** (AC: #2)
  - [x] Create `tests/unit/test_codes.py` (no marker — unit tests are unmarked).
  - [x] Cover, parametrized where it shortens the test:
    - **Total coverage:** `test_<entity>_codes_cover_all_documented_integers` — for each table, assert the full integer key set matches the documented constants from §"JMRI documented integer constants per entity."
    - **`UNKNOWN` reachable:** `test_<entity>_codes_include_unknown` — every table maps at least one integer to its enum's `UNKNOWN` member.
    - **Live-layout robustness:** `test_turnout_codes_map_zero_to_unknown`, `test_block_codes_map_zero_to_undetected`, `test_sensor_codes_map_zero_to_unknown` — these guard the live-emit edge cases.
    - **No int leakage:** `test_turnout_state_is_not_int_enum` — `assert not issubclass(TurnoutState, int)`. Repeat for every state enum. This is a regression guard against a future contributor "simplifying" with `IntEnum`.
  - [x] Test naming follows architecture §Testing Patterns: `test_<scenario_in_snake_case>`.

- [x] **Task 8: Add unit tests for `_parsing.py`** (AC: #3, #4, #6)
  - [x] Create `tests/unit/test_parsing.py`. No marker.
  - [x] **Cover the happy path per entity:** for each parser, parametrize over the fixture file's envelopes and assert each one parses to a `_Parsed<Kind>` with non-None `name` and the expected enum/value. Use `load_fixture` from conftest. (For the empty `lights.json`, this loop is a no-op — covered by inline envelopes below.)
  - [x] **Cover documented-but-unobserved enum values inline.** For each state enum member that the basement-layout fixture does not exercise (e.g., `TurnoutState.INCONSISTENT`, `SignalHeadAppearance.FLASHRED`, `SensorState.UNKNOWN`), build a one-envelope test inline:

    ```python
    def test_parse_turnout_inconsistent_state() -> None:
        envelope = {"type": "turnout", "data": {"name": "NT9001", "userName": None, "state": 8}}
        parsed = parse_turnout(envelope)
        assert parsed.state is TurnoutState.INCONSISTENT
    ```

    One such test per (entity, enum-member) pair that the live fixture misses. Keeps coverage of the codes tables complete without fabricating fixture entries.
  - [x] **Cover translation rules:**
    - `test_parser_translates_user_name_camel_to_snake` — pass `{"data": {"name": "X", "userName": "Foo", "state": 2}}` through `parse_turnout`; assert `result.user_name == "Foo"`.
    - `test_parser_treats_user_name_null_as_none` — `userName: None` (or absent) → `result.user_name is None`.
    - `test_parser_ignores_unknown_keys` — extra `{"futureField": 42}` does not crash and is not surfaced.
    - `test_parser_raises_on_missing_required_field` — envelope without `data` raises `JMRIProtocolError(entity_type="turnout", field="data")`. Same for `data.name` missing, `data.state` missing on state-bearing entities.
    - `test_parser_raises_on_unknown_state_code` — `state=99` for a turnout raises `JMRIProtocolError(entity_type="turnout", field="state", state_code=99, name="X")`. Use `pytest.raises(JMRIProtocolError) as exc_info` and assert `exc_info.value.context["state_code"] == 99`.
  - [x] **Per-entity peculiarities to cover:**
    - `test_parse_block_zero_state_maps_to_undetected` (live-layout case)
    - `test_parse_turnout_zero_state_maps_to_unknown` (live-layout case)
    - `test_parse_signal_mast_translates_basic_aspect` — pass `{"data": {"name": "X", "aspect": "Clear", "lit": true, "held": false}}`; assert `result.aspect is SignalMastAspect.CLEAR`.
    - `test_parse_signal_mast_unknown_aspect_raises` — pass `{"data": {"name": "X", "aspect": "Manchester Cab Signal", "lit": true, "held": false}}`; assert `JMRIProtocolError` with `context["aspect"] == "Manchester Cab Signal"` and message naming the basic-system limitation.
    - `test_parse_roster_entry_extracts_dcc_address` — assert `int(result.dcc_address) == 1029` and `result.long_address is True` for an `isLongAddress: true` envelope. Roster has many fields; the parser surfaces `dcc_address`, `long_address`, `road_number`, `road_name`, `model`, `name`, plus the optional `comment`.
    - `test_parse_power_envelope` — envelope `{"type": "power", "data": {"name": "NCE", "state": 0, "default": true}}` parses to `_ParsedPower(name="NCE", state=PowerState.UNKNOWN, default=True)`.
    - `test_parse_memory_value_can_be_string_or_none` — fixture has at least one memory with `value: null`; parser returns `value=None`.
  - [x] **Total expected new test count: ~50–70.** Story 2.1 added 53 unit tests; 2.2 should roughly double that. CI logs will show the new test count after push.

- [x] **Task 9: Verify quality gates locally and push** (AC: #8)
  - [x] From `python_code/`:
    - `uv run ruff check` → 0
    - `uv run ruff format --check` → 0 (run `uv run ruff format` first to fix)
    - `uv run mypy src/pyjmri` → 0 (strict-mode clean)
    - `uv run pytest -m "not integration"` → 0; test count > Story 2.1's 53
    - `uv run pytest` → 0; the existing 2.1 integration smoke test still passes against live JMRI
  - [x] **Likely mypy friction points** to anticipate:
    - `_codes.py` `MappingProxyType` typing — `Mapping[int, TurnoutState]` is the right surface type; if mypy complains about the `MappingProxyType` literal, declare the dict-literal first then wrap.
    - Frozen dataclass fields with `Optional` (use `X | None` per architecture §Type Annotation Conventions; never `Optional[X]`).
    - Parser narrowing of `payload["data"]` from `Any` to `dict[str, Any]` — use `if not isinstance(payload.get("data"), dict): raise JMRIProtocolError(...)` at the top of each parser to satisfy mypy and AC #3.
  - [x] **Push to GitHub.** Same flow as Stories 1.2/1.3/1.4/2.1: local-clean before push, CI as backstop. Cache from previous pushes will warm-start the runs.

### Review Findings

- [x] [Review][Decision] `_optional_str` silently drops non-string `value` — resolved: keep `None` (current behavior) — intentional, matches `str | None` contract
- [x] [Review][Patch] `isdigit()` allows Unicode digits; `int()` raises raw `ValueError` instead of `JMRIProtocolError` [`_parsing.py:461`]
- [x] [Review][Patch] 6 of 15 `SignalMastAspect` members untested inline (APPROACH_SLOW, SLOW_APPROACH, MEDIUM_APPROACH, PERMISSIVE, SLOW, MEDIUM) [`test_parsing.py`]
- [x] [Review][Patch] Immutability tests only for 2 of 6 `_codes.py` tables (SENSOR_STATE, LIGHT_STATE, POWER_STATE, SIGNAL_HEAD_APPEARANCE untested) [`test_codes.py`]
- [x] [Review][Defer] DCC address `"0"` (broadcast) accepted without range check [`_parsing.py`] — deferred, pre-existing
- [x] [Review][Defer] No cross-validation of `isLongAddress` vs. `dcc_address` numeric range [`_parsing.py`] — deferred, pre-existing

## Dev Notes

### `_codes.py` canonical shape

```python
"""JMRI integer code ↔ Enum tables.

Single source of truth for wire-format state-code translation. Each
table is keyed by the integer JMRI emits in the JSON ``state`` (or
``appearance``) field; the value is the matching Enum member from the
public per-entity module.

Architecture §Domain State Modeling and §JSON ↔ Python Translation.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from types import MappingProxyType

from pyjmri.block import BlockState
from pyjmri.light import LightState
from pyjmri.power import PowerState
from pyjmri.sensor import SensorState
from pyjmri.signal import SignalHeadAppearance
from pyjmri.turnout import TurnoutState

logger = logging.getLogger(__name__)


# JMRI Turnout: UNKNOWN=1, CLOSED=2, THROWN=4, INCONSISTENT=8.
# Live observation: idle/never-commanded turnouts emit state=0 — map to UNKNOWN.
TURNOUT_STATE: Mapping[int, TurnoutState] = MappingProxyType({
    0: TurnoutState.UNKNOWN,
    1: TurnoutState.UNKNOWN,
    2: TurnoutState.CLOSED,
    4: TurnoutState.THROWN,
    8: TurnoutState.INCONSISTENT,
})

# JMRI Sensor: UNKNOWN=1, ACTIVE=2, INACTIVE=4, INCONSISTENT=8.
# Live observation: state=0 also seen on never-commanded sensors — map to UNKNOWN.
SENSOR_STATE: Mapping[int, SensorState] = MappingProxyType({
    0: SensorState.UNKNOWN,
    1: SensorState.UNKNOWN,
    2: SensorState.ACTIVE,
    4: SensorState.INACTIVE,
    8: SensorState.INCONSISTENT,
})

# JMRI Block: UNDETECTED=0, UNKNOWN=1, OCCUPIED=2, UNOCCUPIED=4, INCONSISTENT=8.
# UNDETECTED is preserved as a distinct enum member — see §"Per-entity enum membership."
BLOCK_STATE: Mapping[int, BlockState] = MappingProxyType({
    0: BlockState.UNDETECTED,
    1: BlockState.UNKNOWN,
    2: BlockState.OCCUPIED,
    4: BlockState.UNOCCUPIED,
    8: BlockState.INCONSISTENT,
})

# JMRI Light: UNKNOWN=1, ON=2, OFF=4, INCONSISTENT=8.
LIGHT_STATE: Mapping[int, LightState] = MappingProxyType({
    0: LightState.UNKNOWN,
    1: LightState.UNKNOWN,
    2: LightState.ON,
    4: LightState.OFF,
    8: LightState.INCONSISTENT,
})

# JMRI Power: UNKNOWN=0, ON=2, OFF=4. (Power has no INCONSISTENT.)
POWER_STATE: Mapping[int, PowerState] = MappingProxyType({
    0: PowerState.UNKNOWN,
    1: PowerState.UNKNOWN,
    2: PowerState.ON,
    4: PowerState.OFF,
})

# JMRI SignalHead appearances:
# DARK=0, RED=1, FLASHRED=2, YELLOW=4, FLASHYELLOW=8,
# GREEN=16, FLASHGREEN=32, LUNAR=64, FLASHLUNAR=128.
# (HELD=256 is exposed via the separate ``held`` boolean field, NOT via ``appearance``.)
SIGNAL_HEAD_APPEARANCE: Mapping[int, SignalHeadAppearance] = MappingProxyType({
    0: SignalHeadAppearance.DARK,
    1: SignalHeadAppearance.RED,
    2: SignalHeadAppearance.FLASHRED,
    4: SignalHeadAppearance.YELLOW,
    8: SignalHeadAppearance.FLASHYELLOW,
    16: SignalHeadAppearance.GREEN,
    32: SignalHeadAppearance.FLASHGREEN,
    64: SignalHeadAppearance.LUNAR,
    128: SignalHeadAppearance.FLASHLUNAR,
})
```

**Why `MappingProxyType`:** the dict is module-level state. A misbehaving caller could otherwise assign into it; `MappingProxyType` makes the read-only intent explicit and enforced at runtime. mypy sees the declared `Mapping[int, X]` type, so callers cannot mutate even at type-check time.

**Why two integers map to `UNKNOWN` for turnout/sensor/light/power (0 and 1):** JMRI's `NamedBean` defines `UNKNOWN = 1`, but uninitialized entities — those that have never been polled or commanded since JMRI started — emit `state = 0` over the wire. Treating both as `UNKNOWN` is the conservative behavior and matches PRD FR14 ("the user can distinguish unknown state from every other state"). The library never has to decide *which kind* of unknown — both are unknown to the user.

**Why `BlockState.UNDETECTED` is its own enum member:** for blocks, state=0 has a stable physical meaning — the block has no occupancy detector wired up. Collapsing it into UNKNOWN would lose information that a layout author cares about. This is a deliberate expansion of the architecture's example enum and is flagged for Mikey's review at story end.

### Per-entity enum membership

Each enum is plain `enum.Enum`. Member values are lowercase strings — they exist only to give `str()` and `repr()` reasonable output, never to expose JMRI integers.

```python
# turnout.py
class TurnoutState(Enum):
    UNKNOWN = "unknown"
    CLOSED = "closed"
    THROWN = "thrown"
    INCONSISTENT = "inconsistent"

# sensor.py
class SensorState(Enum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    INACTIVE = "inactive"
    INCONSISTENT = "inconsistent"

# block.py
class BlockState(Enum):
    UNKNOWN = "unknown"
    OCCUPIED = "occupied"
    UNOCCUPIED = "unoccupied"
    UNDETECTED = "undetected"      # JMRI state=0; block has no detector wired
    INCONSISTENT = "inconsistent"

# light.py
class LightState(Enum):
    UNKNOWN = "unknown"
    ON = "on"
    OFF = "off"
    INCONSISTENT = "inconsistent"

# power.py
class PowerState(Enum):
    UNKNOWN = "unknown"
    ON = "on"
    OFF = "off"

# signal.py
class SignalHeadAppearance(Enum):
    DARK = "dark"
    RED = "red"
    FLASHRED = "flashred"
    YELLOW = "yellow"
    FLASHYELLOW = "flashyellow"
    GREEN = "green"
    FLASHGREEN = "flashgreen"
    LUNAR = "lunar"
    FLASHLUNAR = "flashlunar"


class SignalMastAspect(Enum):
    """JMRI 'basic' signaling-system aspects.

    pyjmri v1 binds to the basic signaling system only. Layouts using
    AAR-1946, NORAC, or custom signaling will see ``JMRIProtocolError``
    when ``parse_signal_mast`` encounters an aspect string outside this
    enum. Document this limitation in the README (Story 6.2).

    Member values are the exact JMRI aspect strings — Python's
    value-based enum lookup (``SignalMastAspect("Clear")``) is the
    translation primitive, so the strings MUST match JMRI verbatim
    (case, spaces, and all).
    """

    CLEAR = "Clear"
    APPROACH = "Approach"
    APPROACH_MEDIUM = "Approach Medium"
    ADVANCE_APPROACH = "Advance Approach"
    APPROACH_SLOW = "Approach Slow"
    SLOW_APPROACH = "Slow Approach"
    MEDIUM_APPROACH = "Medium Approach"
    RESTRICTING = "Restricting"
    PERMISSIVE = "Permissive"
    SLOW = "Slow"
    MEDIUM = "Medium"
    STOP = "Stop"
    DARK = "Dark"
    HELD = "Held"
    UNKNOWN = "Unknown"
```

**SignalMastAspect membership source.** The members above are drawn from JMRI's `xml/signals/basic/aspects.xml` file. The dev agent should open that file (or the equivalent in the JMRI distribution shipped with `Basement_Revised_2024.jmri`) and confirm the member set matches every `<Name>` element under `<AspectTable>` for the basic system. If JMRI defines additional basic aspects not enumerated above, add them — values must be byte-identical to JMRI's strings or `SignalMastAspect(jmri_string)` will raise `ValueError`. The list above is a strong starting point but treat JMRI's `aspects.xml` as authoritative.

**Per-module structure** (turnout.py shown; all others identical pattern):

```python
"""Turnout state enum. Story 2.3 will add the Turnout entity class."""
from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)

__all__ = ["TurnoutState"]


class TurnoutState(Enum):
    UNKNOWN = "unknown"
    CLOSED = "closed"
    THROWN = "thrown"
    INCONSISTENT = "inconsistent"
```

**`memory.py`, `route.py`, `roster.py` stubs** (just enough to be importable):

```python
"""Memory entity. Story 2.3 will add the Memory class and its read methods."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__: list[str] = []
```

**No `signal_head.py` / `signal_mast.py` split.** Architecture project structure has both signalHead and signalMast types living in `signal.py`. Story 2.2 places `SignalHeadAppearance` there; signalMast aspect handling is string-typed (no enum) per §"SignalMast aspect handling."

### `_parsing.py` canonical shape

```python
"""JMRI JSON v5 → typed Python value translation.

Each parser receives the JMRI envelope shape (``{"type": "...",
"data": {...}}``) and returns a frozen ``_Parsed<Kind>`` dataclass.
Architecture §JSON ↔ Python Translation: integer codes are
translated through ``_codes.py`` only; unknown JSON keys are silently
ignored; missing required keys raise ``JMRIProtocolError``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pyjmri import _codes
from pyjmri.block import BlockState
from pyjmri.exceptions import JMRIProtocolError
from pyjmri.light import LightState
from pyjmri.power import PowerState
from pyjmri.sensor import SensorState
from pyjmri.signal import SignalHeadAppearance
from pyjmri.turnout import TurnoutState

logger = logging.getLogger(__name__)


# ────── Frozen parsed-shape dataclasses ──────

@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedTurnout:
    name: str
    user_name: str | None
    state: TurnoutState

@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedSensor:
    name: str
    user_name: str | None
    state: SensorState

@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedBlock:
    name: str
    user_name: str | None
    state: BlockState
    value: str | None

@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedLight:
    name: str
    user_name: str | None
    state: LightState

@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedMemory:
    name: str
    user_name: str | None
    value: str | None

@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedRoute:
    name: str
    user_name: str | None

@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedSignalHead:
    name: str
    user_name: str | None
    appearance: SignalHeadAppearance
    held: bool
    lit: bool

@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedSignalMast:
    name: str
    user_name: str | None
    aspect: SignalMastAspect   # value translated from JMRI's basic-system aspect string
    held: bool
    lit: bool

@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedRosterEntry:
    name: str
    dcc_address: int
    long_address: bool
    road_name: str | None
    road_number: str | None
    model: str | None
    comment: str | None

@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedPower:
    name: str
    state: PowerState
    default: bool


# ────── Parsers ──────

def _data(payload: dict[str, Any], entity_type: str) -> dict[str, Any]:
    """Return ``payload['data']`` or raise JMRIProtocolError."""
    data = payload.get("data")
    if not isinstance(data, dict):
        raise JMRIProtocolError(
            "envelope is missing 'data' object",
            entity_type=entity_type,
            field="data",
        )
    return data


def _required_str(data: dict[str, Any], key: str, *, entity_type: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise JMRIProtocolError(
            f"missing or non-string field {key!r}",
            entity_type=entity_type,
            field=key,
            name=data.get("name"),
        )
    return value


def _required_state(
    data: dict[str, Any],
    table: Mapping[int, EnumT],
    *,
    entity_type: str,
) -> EnumT:
    code = data.get("state")
    if not isinstance(code, int):
        raise JMRIProtocolError(
            "missing or non-integer 'state' field",
            entity_type=entity_type,
            field="state",
            name=data.get("name"),
        )
    member = table.get(code)
    if member is None:
        raise JMRIProtocolError(
            "unknown state code",
            entity_type=entity_type,
            field="state",
            state_code=code,
            name=data.get("name"),
        )
    return member


def parse_turnout(payload: dict[str, Any]) -> _ParsedTurnout:
    data = _data(payload, "turnout")
    return _ParsedTurnout(
        name=_required_str(data, "name", entity_type="turnout"),
        user_name=data.get("userName"),
        state=_required_state(data, _codes.TURNOUT_STATE, entity_type="turnout"),
    )


# parse_sensor / parse_block / parse_light / parse_signal_head pattern is identical;
# parse_memory / parse_route omit the state field;
# parse_signal_mast uses 'aspect' (str) directly;
# parse_roster_entry pulls multiple fields per the dataclass shape;
# parse_power reads the singleton envelope.
```

**Why the helpers (`_data`, `_required_str`, `_required_state`):** they de-duplicate the field-validation boilerplate across ten parsers. Each parser otherwise repeats six lines of "look up key, check type, raise on miss" per field, which mypy-strict makes verbose. The helpers are private (`_`-prefixed). They also centralize the `JMRIProtocolError` `context` shape so all parsers populate `entity_type`, `field`, `name` consistently — Story 2.1's review finding pattern.

**Why `dataclass(frozen=True, kw_only=True, slots=True)`:**
- `frozen=True` — parsed values are immutable snapshots; entity classes in Story 2.3 will hold them and cache mutable state separately.
- `kw_only=True` — call sites read better (`_ParsedTurnout(name=..., user_name=..., state=...)`) and resist accidental positional-argument bugs.
- `slots=True` — small memory win on a layout-discovery payload that creates ~370 of these in 2 seconds. Doesn't matter for correctness; it's cheap to add.

**Why `EnumT`** in the helper signature: the helper is generic over enum types. Declare a `TypeVar` near the top: `EnumT = TypeVar("EnumT", bound=Enum)`. The `Mapping[int, EnumT]` parameter and the matching return type then resolve cleanly under mypy-strict. Don't import `Enum` from `enum` for this — import the per-module enums and let mypy infer the bound from the call site.

### Parsed dataclass shapes per entity

| Entity | Parser | Dataclass fields |
| --- | --- | --- |
| turnout | `parse_turnout` | `name`, `user_name`, `state: TurnoutState` |
| sensor | `parse_sensor` | `name`, `user_name`, `state: SensorState` |
| block | `parse_block` | `name`, `user_name`, `state: BlockState`, `value: str \| None` |
| light | `parse_light` | `name`, `user_name`, `state: LightState` |
| memory | `parse_memory` | `name`, `user_name`, `value: str \| None` |
| route | `parse_route` | `name`, `user_name` |
| signalHead | `parse_signal_head` | `name`, `user_name`, `appearance: SignalHeadAppearance`, `held: bool`, `lit: bool` |
| signalMast | `parse_signal_mast` | `name`, `user_name`, `aspect: SignalMastAspect`, `held: bool`, `lit: bool` |
| rosterEntry | `parse_roster_entry` | `name`, `dcc_address: int`, `long_address: bool`, `road_name: str \| None`, `road_number: str \| None`, `model: str \| None`, `comment: str \| None` |
| power | `parse_power` | `name`, `state: PowerState`, `default: bool` |

**Notes on individual parsers:**

- **`parse_block`** also surfaces `value: str | None` because JMRI blocks can carry an arbitrary user-set value (string), which Story 2.3's Block class will expose as a property. Future parsers may surface more fields; for v1, `name`, `user_name`, `state`, `value` is sufficient for what Story 2.3 needs.
- **`parse_memory`** has no state — JMRI memories hold a freeform string value. The parser surfaces `value` as `str | None` (JMRI sends `null` for unset memories).
- **`parse_route`** has only identity fields. Routes are fire-and-forget; `state` exists in the envelope but is meaningless for read in this version (always 0 = "not active"). Don't surface it. If Story 4.x decides to expose route state, the parser grows then.
- **`parse_roster_entry`** maps the camelCase JMRI fields:
  - `address` (string) → `dcc_address: int` (parser does `int(value)` after validating the string is digit-only; raises `JMRIProtocolError` otherwise).
  - `isLongAddress` (bool) → `long_address: bool`.
  - `road` → `road_name`.
  - `number` → `road_number`.
  - `model` → `model`.
  - `comment` → `comment`.
  - The `name` field in roster JSON is the entry's display name (e.g., `"1029 NW2 Switcher"`), not a system name.
- **`parse_signal_head`** ignores `state` (which JMRI duplicates from `appearance`) and ignores `appearanceName` (which is the human-readable label that pyjmri's enum already encodes). Forward-compat note: if a future JMRI version diverges `state` from `appearance`, the parser will need to grow. For v1, `appearance` is the source of truth.
- **`parse_signal_mast`** translates `aspect` (JMRI string) to `SignalMastAspect` via `SignalMastAspect(value)`. On `ValueError`, raises `JMRIProtocolError`. See §"SignalMast aspect handling" for the canonical pattern and the basic-system-only contract.
- **`parse_power`** is the only singleton (no collection endpoint that returns it as an array element). The envelope shape is the same as the others (`{"type": "power", "data": {...}}`).

### SignalMast aspect handling

JMRI signal-mast aspects are layout-dependent strings drawn from the user-loaded signaling-system XML. **pyjmri v1 binds to the JMRI "basic" signaling system only** (Mikey-confirmed 2026-05-07). Layouts using AAR-1946, NORAC, or custom signaling are out of scope for v1; the README "Limitations" section in Story 6.2 must call this out explicitly.

**Translation pattern:**

```python
def parse_signal_mast(payload: dict[str, Any]) -> _ParsedSignalMast:
    data = _data(payload, "signalMast")
    name = _required_str(data, "name", entity_type="signalMast")
    aspect_str = _required_str(data, "aspect", entity_type="signalMast")
    try:
        aspect = SignalMastAspect(aspect_str)
    except ValueError as e:
        raise JMRIProtocolError(
            "unknown signal-mast aspect "
            "(pyjmri v1 supports the JMRI 'basic' signaling system only)",
            entity_type="signalMast",
            field="aspect",
            aspect=aspect_str,
            name=name,
            signaling_system_hint="basic",
        ) from e
    return _ParsedSignalMast(
        name=name,
        user_name=data.get("userName"),
        aspect=aspect,
        held=bool(data.get("held", False)),
        lit=bool(data.get("lit", True)),
    )
```

**Why use Python's value-based enum lookup** rather than a `_codes.py` `Mapping[str, SignalMastAspect]`:

- Enums already provide value-keyed lookup natively (`SignalMastAspect("Clear")`).
- A separate string→enum table in `_codes.py` would duplicate state — the enum's value list and the table would have to stay in sync. One source of truth is better.
- `_codes.py` is conceptually about **integer wire codes**; signal masts have no integer codes. Keeping `_codes.py` integer-only preserves a clean mental model.

**Forward-compat:** when a future story adds AAR-1946 or NORAC support, the right shape is probably a per-system enum plus a runtime selector (`Client(config=ClientConfig(signaling_system="aar-1946"))`). Not v1's problem.

**Note on the `state` field in JMRI's signalMast envelope.** Live JMRI emits both `aspect: "Clear"` AND `state: "Clear"` (the same string, duplicated). The parser reads `aspect`, ignores `state`. If a future JMRI version desyncs them, the parser stays correct because `aspect` is the documented authoritative field.

### Live JMRI integer-code observations

Captured 2026-05-07 against `Basement_Revised_2024.jmri` on the simulator (JMRI 5.4.0):

| Endpoint | Distinct state codes seen | Documented JMRI codes for this entity |
| --- | --- | --- |
| `/json/v5/turnout` | 0, 2, 4 | 1=UNKNOWN, 2=CLOSED, 4=THROWN, 8=INCONSISTENT |
| `/json/v5/sensor` | 2, 4 | 1=UNKNOWN, 2=ACTIVE, 4=INACTIVE, 8=INCONSISTENT |
| `/json/v5/block` | 0, 4 | 0=UNDETECTED, 1=UNKNOWN, 2=OCCUPIED, 4=UNOCCUPIED, 8=INCONSISTENT |
| `/json/v5/light` | (empty list) | 1=UNKNOWN, 2=ON, 4=OFF, 8=INCONSISTENT |
| `/json/v5/route` | 0 | (state semantics N/A for read in v1) |
| `/json/v5/signalHead` | 16 (all heads = GREEN) | 0=DARK, 1=RED, 2=FLASHRED, 4=YELLOW, 8=FLASHYELLOW, 16=GREEN, 32=FLASHGREEN, 64=LUNAR, 128=FLASHLUNAR |
| `/json/v5/signalMast` | "Clear" (string, not int) | (string aspects, layout-dependent) |
| `/json/v5/power` | 0 | 0=UNKNOWN, 2=ON, 4=OFF |

**Critical implication:** the codes tables MUST cover every documented integer (right column), not just every observed integer (left column). The tests in `test_codes.py` enforce this. Skipping documented codes would silently regress when a user's layout exercises them — e.g., a turnout fault during operations sends INCONSISTENT=8, which the basement's idle simulator never produces but a real layout under a derailment will.

**Narrow fixture coverage is intentional** (Mikey-confirmed 2026-05-07). Fixtures capture the live basement layout as-is — no fabricated envelopes. Coverage of unobserved enum values comes from inline-constructed test envelopes in `test_parsing.py` (see Task 8). Unit tests verify pyjmri's parser machinery, not JMRI's full state space.

### JMRI documented integer constants per entity

These are the integer constants the codes tables are tested against. Source: JMRI's published Java interfaces (`jmri.Turnout`, `jmri.Sensor`, etc.) — not invented for this story.

```text
Turnout:       UNKNOWN=1, CLOSED=2, THROWN=4, INCONSISTENT=8
               (plus runtime-emitted 0 for never-commanded turnouts)
Sensor:        UNKNOWN=1, ACTIVE=2, INACTIVE=4, INCONSISTENT=8
               (plus runtime-emitted 0 for never-commanded sensors)
Block:         UNDETECTED=0, UNKNOWN=1, OCCUPIED=2, UNOCCUPIED=4, INCONSISTENT=8
Light:         UNKNOWN=1, ON=2, OFF=4, INCONSISTENT=8
               (plus runtime-emitted 0 for never-commanded lights)
Power:         UNKNOWN=0, ON=2, OFF=4
SignalHead:    DARK=0, RED=1, FLASHRED=2, YELLOW=4, FLASHYELLOW=8,
               GREEN=16, FLASHGREEN=32, LUNAR=64, FLASHLUNAR=128
               (HELD=256 is exposed via separate ``held`` boolean — NOT in this table)
SignalMast:    (string aspects, no integer codes)
```

### Fixture files and their canonical paths

```text
python_code/tests/unit/fixtures/
├── turnouts.json         # /json/v5/turnout collection (captured as-is)
├── sensors.json          # /json/v5/sensor collection (captured as-is)
├── blocks.json           # /json/v5/block collection (captured as-is)
├── lights.json           # /json/v5/light — empty array on this layout
├── memories.json         # /json/v5/memory collection (captured as-is)
├── routes.json           # /json/v5/route collection (captured as-is)
├── signal_heads.json     # /json/v5/signalHead collection (captured as-is)
├── signal_masts.json     # /json/v5/signalMast collection (captured as-is)
├── roster.json           # /json/v5/roster collection (captured as-is)
└── power.json            # /json/v5/power singleton — wrap in a single-element list for consistency
```

**Why power.json is wrapped in a list** even though the endpoint returns a single envelope: the `load_fixture(name)` helper returns `list[dict[str, Any]]` consistently. Wrapping the singleton in `[envelope]` keeps the helper signature uniform; `parse_power` is then called with `fixture[0]`. The cost is one bracket pair in the fixture file.

**No `_README.md` is needed** in `tests/unit/fixtures/`: every file is a verbatim capture from live JMRI, no fabricated envelopes mixed in. If a future story changes that, add the README then.

### `tests/unit/conftest.py` canonical shape

```python
"""Unit-test bootstrap: synthetic-fixture loader."""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def load_fixture() -> Callable[[str], list[dict[str, Any]]]:
    """Return a function that loads ``tests/unit/fixtures/<name>.json``.

    Example:
        envelopes = load_fixture("turnouts")
    """

    def _load(name: str) -> list[dict[str, Any]]:
        path = _FIXTURES_DIR / f"{name}.json"
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, list):
            raise TypeError(f"fixture {name!r} must be a JSON array, got {type(payload).__name__}")
        return payload

    return _load
```

### Architecture compliance checklist

| Architecture / PRD rule | Story 2.2 alignment |
| --- | --- |
| §Domain State Modeling — per-entity `enum.Enum` (not IntEnum/StrEnum) | Task 2 (every enum is plain `Enum`) |
| §Domain State Modeling — `UNKNOWN` member required on every state enum | Task 2; AC #1 |
| §Domain State Modeling — `_codes.py` private translation tables | Task 1 |
| §JSON ↔ Python Translation — translation in `_parsing.py` only | Task 3 |
| §JSON ↔ Python Translation — camelCase → snake_case | Task 3; AC #4 |
| §JSON ↔ Python Translation — unknown JSON keys ignored | Task 3; AC #3 |
| §JSON ↔ Python Translation — missing required keys raise `JMRIProtocolError` | Task 3; AC #3 |
| §JSON ↔ Python Translation — int codes never on public API | Task 1, 2 (enums opaque); Task 6 (re-exports surface enums only) |
| Epic 2.2 AC — "plus signal-head/mast aspect enums" | Task 2 (`SignalHeadAppearance` from int codes; `SignalMastAspect` from JMRI basic-system strings) |
| §Type Annotation Conventions — `from __future__ import annotations`, PEP 604, no `Any` on public surface | All tasks |
| §Type Annotation Conventions — `Any` permitted only on JSON-input parameter | Task 3 (parsers) |
| §Public API Discipline — `__all__` on every public module | Task 2 (per-entity); Task 6 (`__init__.py`) |
| §Public API Discipline — `_codes.py`, `_parsing.py` are private | Tasks 1, 3 (no `__all__`, no `__init__.py` re-export) |
| §Architectural Boundaries point 2 — only `_transport.py` imports httpx | Tasks 1, 3 (zero httpx imports added) |
| §Logging Discipline — module-level `logger = logging.getLogger(__name__)` | Tasks 1, 2, 3 |
| §Test Harness — synthetic JSON fixtures in `tests/unit/fixtures/` | Tasks 4, 5 |
| §Testing Patterns — file naming `test_<module>.py`; no JMRI mocks | Tasks 7, 8 |
| FR12 — discovered layout includes turnouts, sensors, blocks, lights, memories, routes, signal heads, signal masts, roster | Tasks 2, 3 (per-entity parsers ready for Story 2.5 to consume) |
| FR13 — typed state read | Task 2 (enums); Task 3 (parsers) |
| FR14 — `unknown` distinguishable | Task 2 (enums); Task 1 (codes table maps to UNKNOWN) |
| FR16 — power state read | Task 1 (POWER_STATE table); Task 3 (parse_power) |
| FR34 — typed `JMRIError` subclasses | Task 3 (parsers raise `JMRIProtocolError`) |

### Reference: previous story context

**Story 2.1 (status `done`, 2026-05-07):** Established the transport boundary, exception hierarchy, Client lifecycle, and integration-test scaffolding. Story 2.2 builds *above* Story 2.1's transport — `HTTPClient.get` is the eventual call site for the parsers, but Story 2.2 itself never calls it. The integration smoke test from 2.1 (`test_connection_lifecycle.py`) is the only integration test in the suite; Story 2.2 adds none. The probe endpoint `/json/v5/version` is unchanged.

**Story 2.1 review finding patterns to honor:**
- Diagnostic context populated on every `JMRIError` raise: `entity_type`, `field`, `name`, `state_code` per the parser's `_required_*` helpers. Don't raise `JMRIProtocolError("bad state")` without context — the dev agent's `_required_state` helper centralizes the right shape.
- `__all__` declared in every public module; preserve `_codes.py` and `_parsing.py` *without* `__all__` (private convention).
- Logger names per `getLogger(__name__)` discipline. Story 2.1's `_transport.py` deviated and used `logging.getLogger("pyjmri.transport")` explicitly to match the architecture's documented hierarchy; for 2.2's modules, `__name__` is the right call (yields `pyjmri.turnout`, `pyjmri._codes`, `pyjmri._parsing`, etc.). Match the existing pattern in `client.py` (which uses `__name__`), not the override in `_transport.py`.

**Story 1.3 (CI):** the six-job matrix (macOS+Linux × 3.11/3.12/3.13) runs `pytest -m "not integration"`. New unit tests will run there; integration tests are excluded. Story 2.1's path-scoped workflow filter (`python_code/**`) means this story will trigger CI on push.

### Things explicitly NOT in this story

These belong to later stories — resist the urge to bundle:

- **Per-entity classes** (`class Turnout`, `class Sensor`, ...) → Story 2.3.
- **`_protocols.py` `ClientHandle` Protocol** → Story 2.3.
- **`async def get_state()` methods on entities** → Story 2.3.
- **`Layout` and `EntityCollection`** → Story 2.4.
- **`Client.discover()`** → Story 2.5.
- **JMRI version check** (raising `JMRIVersionUnsupported`) → Story 2.5.
- **WebSocket-driven state-change events** (entities calling parsers from WS messages) → Story 3.1+.
- **Integer code ↔ enum mapping for SignalMast** → either deferred to Growth or never, per §"SignalMast aspect handling."
- **Encoder direction (`Enum → JMRI integer`)** for `set_state` calls → Story 4.1 (when commands first need to encode a target state to a JMRI int).
- **A shared `Enum` base class** — architecture explicitly rejects this; per-entity enums are independent types.

### Verification matrix (after all tasks complete)

| Check | Expected outcome |
| --- | --- |
| `python_code/src/pyjmri/_codes.py` exists; six tables populated | ✅ |
| `python_code/src/pyjmri/_parsing.py` exists; ten parsers + ten `_Parsed<X>` dataclasses | ✅ |
| `python_code/src/pyjmri/turnout.py` etc. exist with state enums (no entity classes) | ✅ |
| `python_code/src/pyjmri/__init__.py` re-exports seven enums; preserves `NullHandler` | ✅ |
| `tests/unit/fixtures/*.json` present for all ten entity types | ✅ |
| `tests/unit/conftest.py` exposes `load_fixture` session fixture | ✅ |
| `tests/unit/test_codes.py` passes; covers full code-set per entity, no IntEnum | ✅ |
| `tests/unit/test_parsing.py` passes; covers fixture round-trip + translation rules + error paths | ✅ |
| Story 2.1's integration smoke test still passes against live JMRI | ✅ |
| Only `_transport.py` imports `httpx` (regression check via `grep -r "^import httpx\|^from httpx" src/`) | ✅ |
| `uv run ruff check` → 0 | ✅ |
| `uv run ruff format --check` → 0 | ✅ |
| `uv run mypy src/pyjmri` → 0 (strict) | ✅ |
| `uv run pytest -m "not integration"` → 0; total tests > 53 | ✅ |
| `uv run pytest` → 0 (integration smoke also passes) | ✅ |
| GitHub Actions six-job CI matrix goes green on push | ✅ |

### Project Structure Notes

All new files live under `python_code/`. Aligns with architecture §Complete Project Directory Structure exactly — no path deviations:

**New files:**

- `src/pyjmri/_codes.py` — NEW (private)
- `src/pyjmri/_parsing.py` — NEW (private)
- `src/pyjmri/turnout.py` — NEW (public, enum-only stub)
- `src/pyjmri/sensor.py` — NEW (public, enum-only stub)
- `src/pyjmri/block.py` — NEW (public, enum-only stub)
- `src/pyjmri/light.py` — NEW (public, enum-only stub)
- `src/pyjmri/power.py` — NEW (public, enum-only stub)
- `src/pyjmri/signal.py` — NEW (public, enum-only stub; both `SignalHeadAppearance` and `SignalMastAspect`)
- `src/pyjmri/memory.py` — NEW (public, empty stub for Story 2.3)
- `src/pyjmri/route.py` — NEW (public, empty stub for Story 2.3)
- `src/pyjmri/roster.py` — NEW (public, empty stub for Story 2.3)
- `tests/unit/fixtures/turnouts.json` — NEW (captured from live JMRI)
- `tests/unit/fixtures/sensors.json` — NEW (captured from live JMRI)
- `tests/unit/fixtures/blocks.json` — NEW (captured from live JMRI)
- `tests/unit/fixtures/lights.json` — NEW (empty array; live layout has zero lights)
- `tests/unit/fixtures/memories.json` — NEW (captured from live JMRI)
- `tests/unit/fixtures/routes.json` — NEW (captured from live JMRI)
- `tests/unit/fixtures/signal_heads.json` — NEW (captured from live JMRI)
- `tests/unit/fixtures/signal_masts.json` — NEW (captured from live JMRI)
- `tests/unit/fixtures/roster.json` — NEW (captured from live JMRI)
- `tests/unit/fixtures/power.json` — NEW (singleton envelope wrapped in single-element list)
- `tests/unit/test_codes.py` — NEW
- `tests/unit/test_parsing.py` — NEW

**Modified files:**

- `src/pyjmri/__init__.py` — UPDATE (add six enum re-exports + `__all__` entries; preserve `NullHandler` line)
- `tests/unit/conftest.py` — UPDATE (currently empty; add `load_fixture` fixture)

**Unchanged from Story 2.1** (regression-protect):

- `src/pyjmri/_transport.py`
- `src/pyjmri/exceptions.py`
- `src/pyjmri/client.py`
- `tests/unit/test_exceptions.py`
- `tests/unit/test_transport.py`
- `tests/unit/test_client.py`
- `tests/integration/conftest.py`
- `tests/integration/test_connection_lifecycle.py`
- `pyproject.toml` (no new runtime deps; nothing added beyond existing httpx)
- `uv.lock`

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.2: Wire-format translation — `_codes`, `_parsing`, per-entity state enums] — story scope and ACs
- [Source: _bmad-output/planning-artifacts/architecture.md#Domain State Modeling] — per-entity Enum, no IntEnum/StrEnum, `_codes.py` placement
- [Source: _bmad-output/planning-artifacts/architecture.md#JSON ↔ Python Translation] — camelCase→snake_case, unknown keys ignored, missing keys raise, int codes private
- [Source: _bmad-output/planning-artifacts/architecture.md#Internal Layering] — public/private split; `_codes.py` and `_parsing.py` are private
- [Source: _bmad-output/planning-artifacts/architecture.md#Architectural Boundaries] — point 2 (transport/domain) and point 3 (JMRI JSON v5 integration boundary)
- [Source: _bmad-output/planning-artifacts/architecture.md#Type Annotation Conventions] — `from __future__ import annotations`, PEP 604 unions, `Any` only on JSON input
- [Source: _bmad-output/planning-artifacts/architecture.md#Public API Discipline] — `__all__` on public modules; private modules have none
- [Source: _bmad-output/planning-artifacts/architecture.md#Logging Discipline] — `logger = logging.getLogger(__name__)` per module
- [Source: _bmad-output/planning-artifacts/architecture.md#Test Harness] — synthetic JSON fixtures in `tests/unit/fixtures/`
- [Source: _bmad-output/planning-artifacts/architecture.md#Testing Patterns] — file/function naming, no JMRI mocks
- [Source: _bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure] — exact file paths
- [Source: _bmad-output/planning-artifacts/prd.md FR12] — discovered layout entity types
- [Source: _bmad-output/planning-artifacts/prd.md FR13] — typed state read
- [Source: _bmad-output/planning-artifacts/prd.md FR14] — `unknown` is a first-class state
- [Source: _bmad-output/planning-artifacts/prd.md FR15] — typed memory value
- [Source: _bmad-output/planning-artifacts/prd.md FR16] — read-only power state
- [Source: _bmad-output/planning-artifacts/prd.md FR34] — typed `JMRIError` hierarchy
- [Source: _bmad-output/planning-artifacts/prd.md "Assumed JMRI JSON Contract"] — entity-type endpoint surface (the contract Story 2.2 binds against)
- [Source: _bmad-output/implementation-artifacts/2-1-...md] — Story 2.1 dev notes; transport boundary; integration test pattern
- [Source: _bmad-output/implementation-artifacts/epic-1-retro-2026-05-07.md] — Epic 1 retrospective patterns to honor

## Resolved design decisions (Mikey, 2026-05-07)

1. **`BlockState.UNDETECTED` is added as an explicit enum member.** Confirmed: state=0 from idle JMRI maps to `UNDETECTED`, distinct from `UNKNOWN`. Architecture deviation accepted.
2. **`SignalMastAspect` enum is shipped, seeded with the JMRI "basic" signaling-system aspect set.** Other signaling systems (AAR-1946, NORAC, custom) are out of scope for v1 and will produce `JMRIProtocolError` on read. Story 6.2 (README Limitations) must surface this constraint to users.
3. **Fixture coverage stays narrow.** Live basement-layout captures are taken as-is, no synthetic augmentation. Documented-but-unobserved enum values are exercised via inline-constructed test envelopes in `test_parsing.py`. The unit tests verify pyjmri's parser machinery, not JMRI's full state space.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Opus 4.7, 1M context)

### Debug Log References

None — implementation proceeded cleanly without HALT conditions.

### Completion Notes List

- All 8 acceptance criteria satisfied. 108 new unit tests added (30 in `test_codes.py`, 78 in `test_parsing.py`); total unit tests now 161 (up from 53 in Story 2.1).
- Strict-mode mypy passes against `src/pyjmri` with zero issues across all 15 source files.
- Architectural boundary preserved: `grep -rn "^import httpx\|^from httpx" src/` returns only `_transport.py:12`.
- Story 2.1's integration smoke test against live JMRI still passes.
- Implementation note: `_required_state` helper accepts a `field` keyword (default `"state"`) so `parse_signal_head` can read JMRI's `appearance` integer without a separate helper. `bool` is excluded explicitly from int-state parsing because `isinstance(True, int)` is `True` in Python — a subtle gotcha worth a regression-guard comment if needed later.
- `_optional_str` helper added (not in story spec) to centralize `userName` / `value` / `road` / `comment` null-handling. Returns `None` for absent, null, or non-string values; rejected silently per architecture's "unknown keys ignored" rule. This avoids ten near-identical inline conditions across parsers.
- `power.json` was returned by JMRI's v5 endpoint as a single-element list, not a singleton object — the planned wrap-in-list step was unnecessary. The `load_fixture` helper signature stays uniform.
- `tests/unit/fixtures/lights.json` is committed as `[]` per the narrow-coverage policy (live layout has zero lights).
- Two ruff findings auto-fixed: import ordering in `test_codes.py` and an unused `_ParsedLight` import in `test_parsing.py` (parser is exercised via inline envelopes only).
- Re-export check: `from pyjmri import TurnoutState, SensorState, BlockState, LightState, PowerState, SignalHeadAppearance, SignalMastAspect` succeeds; `__all__` updated alphabetically; the `NullHandler` install line at module scope is preserved.

### File List

**New files:**

- `python_code/src/pyjmri/_codes.py`
- `python_code/src/pyjmri/_parsing.py`
- `python_code/src/pyjmri/turnout.py`
- `python_code/src/pyjmri/sensor.py`
- `python_code/src/pyjmri/block.py`
- `python_code/src/pyjmri/light.py`
- `python_code/src/pyjmri/power.py`
- `python_code/src/pyjmri/signal.py`
- `python_code/src/pyjmri/memory.py`
- `python_code/src/pyjmri/route.py`
- `python_code/src/pyjmri/roster.py`
- `python_code/tests/unit/test_codes.py`
- `python_code/tests/unit/test_parsing.py`
- `python_code/tests/unit/fixtures/turnouts.json`
- `python_code/tests/unit/fixtures/sensors.json`
- `python_code/tests/unit/fixtures/blocks.json`
- `python_code/tests/unit/fixtures/lights.json`
- `python_code/tests/unit/fixtures/memories.json`
- `python_code/tests/unit/fixtures/routes.json`
- `python_code/tests/unit/fixtures/signal_heads.json`
- `python_code/tests/unit/fixtures/signal_masts.json`
- `python_code/tests/unit/fixtures/roster.json`
- `python_code/tests/unit/fixtures/power.json`

**Modified files:**

- `python_code/src/pyjmri/__init__.py` — added 7 enum re-exports (alphabetical), preserved `NullHandler` install
- `python_code/tests/unit/conftest.py` — replaced empty file with `load_fixture` session-scoped pytest fixture
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — story key transitioned ready-for-dev → in-progress → review

## Change Log

- 2026-05-07 — Story 2.2 created (`ready-for-dev`). Comprehensive context engine analysis: epics, architecture, PRD, Story 2.1 dev notes, live JMRI 5.4.0 wire-format observations against `Basement_Revised_2024.jmri`.
- 2026-05-07 — Story 2.2 design decisions resolved with Mikey: (1) `BlockState.UNDETECTED` confirmed as a distinct enum member; (2) `SignalMastAspect` enum shipped with JMRI basic-signaling-system aspects (other systems raise `JMRIProtocolError`; README Limitations note in Story 6.2 must call this out); (3) fixture coverage stays narrow — live captures only, rare-code coverage moves into inline-constructed envelopes in `test_parsing.py`.
- 2026-05-07 — Story 2.2 implementation complete. `_codes.py` (six int→Enum tables) and `_parsing.py` (ten parsers + ten `_Parsed<Kind>` dataclasses) added; nine new public modules (`turnout.py`, `sensor.py`, `block.py`, `light.py`, `power.py`, `signal.py`, plus stubs `memory.py`, `route.py`, `roster.py`); ten fixture files captured from live JMRI; 108 new unit tests; all four local quality gates green; status → `review`.
