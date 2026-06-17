---
title: "Product Brief Distillate: pyjmri Roster (Read-Only)"
type: llm-distillate
source: "product-brief-roster.md"
created: "2026-06-16"
purpose: "Token-efficient context for downstream PRD / epic+story creation"
---

# Roster (Read-Only) — Detail Pack for PRD/Epic Creation

Dense context captured during the product-brief session. Each bullet stands alone. This feature is a v1.1-class addition to **pyjmri** (Python client for JMRI over its JSON/HTTP+WS web API, lives in `python_code/`). v1.0.0 shipped 2026-05-26.

## Core decisions (locked by user)

- **Roster folds into `Layout`**, NOT a standalone subsystem. Rationale: operator wants roster info *while* operating layout functions, so it belongs on the live `Layout`. This intentionally diverges from Epic 8 Operations (standalone `discover_operations()`); user explicitly accepts two patterns because Operations is a separate planning concern. Resolved, not an open question.
- **Fetched in parallel inside `Client.discover()`** (the existing method — note: `Client.discover()`, there is no `Layout.discover()`). Honors original Epic 2 ACs and PRD Journey 3 (`len(layout.roster)`).
- **Access by DCC address is the PRIMARY key**, because the operator may not know a loco's roster name. Provide `layout.roster.by_address(N)` plus name lookup. JMRI's own primary key is the roster ID/name string, NOT the address — so the address→entry index must be built client-side over the entries.
- **Unknown address must raise a clear, named error** (e.g. "no roster entry for DCC address 5327"), both via `by_address` and `throttle_for_entry`. Catches mistyped addresses; do NOT silently acquire an unknown loco.
- **`layout.throttle_for_entry(address | name | RosterEntry)`** convenience resolving a `Throttle`; derives long/short from the matched entry.
- **Read-only only.** No roster mutation (no create/edit entries, function labels, CVs). Editing stays in DecoderPro.
- **Roster groups: OUT of scope** this pass (user explicitly dropped them). JSON exposes groups via separate endpoints.
- **Ship BOTH examples:** `roster_catalog.py` (fleet reference doc + decoder rollup) and a capability-aware-startup script.

## Use cases (the "why")

- **UC1 — Fleet catalog / reference document:** enumerate all ~44 locos with road number, model, decoder, owner, comment, address. Maps to PRD Journey 3 and Mike's habit of writing short report scripts.
- **UC2 — Capability-aware throttle startup:** when creating a Throttle for a selected engine, pull its roster entry and adapt the startup sequence to that decoder's capability (sound vs motor-only, function mappings). Novel — not an existing PRD journey. Needs RosterEntry to expose enough to branch on capability.
- **UC3 (emergent, strong adoption lever):** pick-a-loco-by-name/address makes every demo/README/doc legible (`throttle_for_entry(5327)` vs opaque `throttle(5327)`). Treat as a headline DX win, not just convenience.

## Capability classification — CRITICAL correctness note

- **`decoderFamily` strings are decoder-DEFINITION-FILE names, NOT capability tags.** Real fleet values include "Jan 2012", "Sep 2018", "Series 3 with FX3, silent, readback", "ESU LokSound 5", "Tsunami Steam Genesis OEM", "E-Z Command decoders". Heterogeneous and date-stamped. DO NOT branch sound-vs-motor on family string alone.
- **Reliable signal = function LABELS.** A function labeled "Startup"/"Shutdown"/"Sound"/"Horn"/"Bell" implies sound capability. Family/model = weak secondary hint only.
- **Labels are user-entered in DecoderPro and frequently blank/default.** Classification MUST fall back to a minimal motor-only startup when labels are blank/unrecognized. Several roster.xml entries have empty `<functionlabels/>`.
- Classification should be a **documented, testable decision function** (which fields, which fallback), not a black box. This is the riskiest/largest part hiding behind a "20-line example" — flag for adequate story sizing.

## JMRI JSON wire format (confirmed from JMRI master source)

- Collection: `GET /json/v5/roster` → JSON array of `{"type":"rosterEntry","data":{...}}` envelopes. Optional group-name resource segment filters by group.
- Single: `GET /json/v5/rosterEntry/{id}` where `{id}` = the entry name/roster ID (URL-encoded), NOT the DCC address. 404/ERROR_NOT_FOUND if unknown.
- Groups: `GET /json/v5/rosterGroups` and `/rosterGroup/{name}` return only `{name, length}` — no member lists. (Out of scope anyway.)
- **`rosterEntry.data` keys:** `name` (entry ID / primary key), `address` (DCC address as STRING), `isLongAddress` (bool), `road`, `number`, `mfg`, `decoderModel`, `decoderFamily`, `model`, `comment`, `maxSpeedPct` (int percent — note exact casing, bind to literal string not the Java constant `MAX_SPD_PCT`), `image` (relative URL or null), `icon` (relative URL or null), `shuntingFunction`, `owner`, `dateModified` (ISO or null), `functionKeys` (array), `attributes` (array of {name,value}).
- **`functionKeys`** = array, one obj per F0..F28: `name` ("F0".."F28"), `label` (string, may be null/empty), `lockable` (bool; true=toggle/latching e.g. lights, false=momentary e.g. horn/bell), `icon` (rel URL or null), `selectedIcon` (rel URL or null). Iterate the array; length can vary by build.
- **Group membership is NOT embedded in the entry object** (per current master). Don't model per-entry groups.
- Media `image`/`icon`/function icons are RELATIVE URLs needing resolution against web-server base + URL-encoded entry ID — not filesystem paths.
- Envelope type for entries is `"rosterEntry"` (singular), even from the `/roster` collection URL.
- Protocol: JSON v5, version "5.4.0"; project targets JMRI 5.14+. Roster shares the same service logic over HTTP (one-shot) and WebSocket (push).
- **Roster IS WebSocket-subscribable** (JsonRosterSocketService listens on Roster + groups + every entry). We deliberately use one-shot HTTP snapshot; live subscription deferred. Prefer HTTP to avoid attaching listeners to every entry.

## RosterEntry proposed fields (in scope)

`dcc_address:int`, `long_address:bool`, `road_name`, `road_number`, `model`, `mfg`, `owner`, `comment`, `image_path`, `max_speed_pct`, `decoder_family`, `decoder_model`, `function_labels` (tuple/map of {num:int, label:str, lockable:bool}). `name` = roster ID (e.g. "1029 NW2 Switcher"); user_name likely None (id is the user-facing label) — entry resembles Operations cars/engines (system name only).

## Existing code assets (reuse, don't rebuild)

- **`_parsing.py` already has `parse_roster_entry` + `_ParsedRosterEntry`** (from Epic 2 scaffolding, currently unused). Reads `name/address/isLongAddress/road/number/model/comment`. Validates address is decimal, isLongAddress is bool, raises `JMRIProtocolError` on malformed. Must be EXTENDED for `owner/comment/image_path/max_speed_pct/decoder_family/decoder_model/function_labels`.
- **`roster.py` is an empty stub** (`__all__=[]`) — reserved home for `RosterEntry`/`Roster`, already named in architecture directory tree.
- **Epic 8 Operations is the near-exact template:** frozen `@dataclass(frozen=True, kw_only=True, slots=True)` entities; parsers return the PUBLIC entity directly (no `_Parsed*` intermediate, no handle/build step — APPLY THIS to roster, replacing the Epic-2-style `_ParsedRosterEntry` intermediate); `EntityCollection[T]` dual-name `Mapping`; `_NamedEntity` Protocol (`.name`, `.user_name`); container defaults each collection to empty so empty snapshot is valid.
- **`EntityCollection`** lives in `layout.py`; reuse as-is, extend roster usage with address index.
- **discover() integration:** mirror `discover_operations()` parallel `asyncio.TaskGroup` + `_fetch_collection` over `GET /json/v5/{type}` + shared cached version gate (`self._version_checked`, >=5.14). CAUTION: `discover()` is a shared TaskGroup — a raising roster task CANCELS sibling fetches (turnouts/sensors). Roster fetch MUST be failure-isolated (wrap so failure → empty roster + warning, never cancels Epics 1-6 discovery). Also must NOT mutate `self._entities` (the WS-dispatch index); roster is a non-subscribed snapshot like Operations.
- **Throttle:** `Throttle(handle, *, dcc_address:int, long:bool)`; `set_speed(value 0..1, *, forward)`; `set_function(n, on)` with **0<=n<=28** (F29+ deferred — affects sound locos with maxFnNum=31). `throttle()`/`throttle_acquire()` currently take raw `dcc_address:int` + `long:bool`.

## Graceful degradation (must specify precisely)

- The existing parser is STRICT (throws on bad address/missing isLongAddress). For roster, **per-entry skip-and-continue**: a malformed entry is skipped (logged), good entries still load. One bad entry must NOT fail the whole roster or `discover()`.
- "Empty roster" is a valid state (not an exception) — mirror Operations FR50.
- Test cases required: empty, partial, **malformed-entry**, failure-isolation (injected roster fetch failure leaves rest of discover() intact), boundary (no mutating methods), address-not-found error.

## Testing & quality (mirror Epic 8 stories)

- All commands via `uv run --no-sync`: `ruff check`, `ruff format --check`, `mypy --strict src/pyjmri`, `mypy --strict examples/`, `pytest -m "not integration"`. Both ruff check AND ruff format --check are CI gates.
- New public types exported ALPHABETICALLY in `__init__.py` `__all__`; must pass mypy --strict.
- **Pin fixtures to a CAPTURED live `/json/v5/roster` payload** from the layout machine (localhost:12080 / basement 192.168.1.159:12080) — do not author the function_labels model from source alone (verify how `visible`/icon fields actually appear).
- Integration tests: `@pytest.mark.integration` + `jmri_available` fixture; pin entities by attribute filter (`next(...)`), never positional `[0]`; layout-specific (the 44-loco basement roster); NFR2-style timing (warm version check via discover() first, then time roster fetch). Roster discovery is fully simulator-testable (pure metadata, no NCE open-loop blind spot).
- Unit baseline post-Epic-8: ~441 passed / 25 deselected (CONTRIBUTING.md may cite older numbers).
- **Capability-startup success criterion is split:** (a) simulator — assert which function COMMANDS the decision function issues given fixture roster data (plumbing-verifiable); (b) hardware — physical "visibly correct startup" is manual, hardware-only (NCE sim has no virtual loco). Don't make (b) a CI gate.
- Release pattern (Epic 8): bump `pyproject.toml` version (no `__version__` in src), `uv lock`, add RELEASES.md section, `uv build` + `twine check dist/*`, all Phase-A gates green, then STOP before `uv publish`/git tag/GitHub release (Mikey's manual Phase-B). Epic 8 targeted v1.1.0.

## Requirements hints / numbering

- Operations took FR45–FR50; a roster epic's FRs likely start at **FR51+**. Epic 8 = Operations; roster would be **Epic 9** (Epic 7 was a test-fix maintenance epic).
- PRD already names `roster`/`rosterEntry` as JSON API surface (read locomotive metadata); FR12 lists roster entries as a min discoverable type. Architecture directory tree pre-reserves `roster.py # Roster, RosterEntry (read-only metadata)` and a `roster.json` test fixture path. Epic 2 Story 2.3/2.5 ACs already anticipated `roster: Roster` as a Layout attribute and `roster` among parallel discover() GETs — this work realizes that.

## Rejected / deferred (don't re-propose)

- **Roster mutation** — rejected, read-only only.
- **Roster groups** — deferred (user dropped this pass).
- **WebSocket roster subscription** — deferred; one-shot snapshot serves both use cases.
- **Deep decoder capability tree (CV/feature defs)** — out; only family/model strings + function labels exposed.
- **`max_speed_pct` auto-clamping in throttle_for_entry** — field exposed, auto-scaling deferred to follow-up (strong candidate).
- **Markdown/HTML photo-bearing fleet sheet** — deferred fast-follow; text catalog ships.
- **F29+ functions** — out (existing v1 throttle limitation).
- **roster↔Operations Engine join (by road+number)** — vision/future, not this pass.

## Adjacent value worth noting in PRD (data already in wire format)

- `comment` field holds real maintenance notes + purchase prices in this fleet (27 of 44 entries) → catalog doubles as maintenance log + value inventory.
- `owner` = provenance (useful for club layouts).
- Decoder-family rollup (counts per family/model) = free decoder inventory / address-collision spotting.
- `max_speed_pct` (per-loco, e.g. 49 vs 100) → future per-loco speed clamp for safety/realism.

## Environment / constraints

- `roster.xml` and `roster/` are READ-ONLY shared JMRI assets; only `python_code/` is writable. Library reads JMRI JSON wire format, never the XML/profile files directly.
- Layout machine (basement) at `192.168.1.159:12080`; office dev machine separate (proxy needs `192.168/16` bypass). All 44 locos in this fleet are `dcc_long`/`longaddress=yes` — but model must carry `long_address:bool` generically.
- Open question (story-level): DCC address collision handling for `by_address` if two entries ever share an address (unique in this fleet today).
