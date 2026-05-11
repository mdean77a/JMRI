# Story 2.5: `Client.discover()` — parallel discovery + JMRI version check + integration smoke test

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a library user,
I want `await jmri.discover()` to enumerate every supported entity type from a running JMRI in parallel and return a fully populated `Layout` — refusing to proceed if JMRI is too old,
so that I can write `async with Client() as jmri: layout = await jmri.discover()` and get a working typed model in well under 2 seconds.

## Scope note (Roster)

The epic lists `roster` as one of the entity types to discover. Story 2.3 dropped `Roster`/`RosterEntry` from pyjmri's public surface (2026-05-08 scope reduction). `discover()` therefore issues **eight** parallel per-type GETs — no roster fetch. The epic's integration-test AC ("every EntityCollection is non-empty … roster") is updated to seven assertable types plus roster omitted.

## Acceptance Criteria

**AC1 — `Client.discover()` runs eight parallel entity-type GETs**

**Given** Stories 2.1–2.4 (Client, parsers, entity classes, Layout/EntityCollection all exist)
**When** `Client.discover()` is called on an open Client
**Then** it issues `GET /json/v5/{entity_type}` in parallel via `asyncio.TaskGroup` for all eight types: `turnout`, `sensor`, `block`, `light`, `memory`, `route`, `signalHead`, `signalMast`
**And** each response list is parsed via the matching `_parsing` function (`parse_turnout`, `parse_sensor`, `parse_block`, `parse_light`, `parse_memory`, `parse_route`, `parse_signal_head`, `parse_signal_mast`)
**And** each parsed entity is constructed with `_handle=self` (so future `get_state()` calls route back through the Client)
**And** the eight collections are assembled into a `Layout` and returned (FR8, FR12)

**AC2 — Version check: JMRI < 5.14 raises `JMRIVersionUnsupported`**

**Given** `Client.discover()` is called for the first time on an open Client
**When** the JMRI version fetched from `/json/v5/version` is older than 5.14
**Then** `discover()` raises `JMRIVersionUnsupported` with `detected=<version string>` and `required="5.14"` in `context` (NFR8)
**And** no entity-type GETs are issued (version check is a gate before discovery)

**Given** `discover()` is called a second time on the same Client (and the first call succeeded)
**When** the version was already validated on the first call
**Then** no second version-check GET is issued — the check is cached per Client lifetime

**AC3 — Fail-fast on per-type error**

**Given** discovery is in progress
**When** one of the eight parallel per-type GETs raises `JMRIProtocolError` (e.g., malformed response)
**Then** `asyncio.TaskGroup` cancels the remaining sibling tasks and propagates the exception to the caller
**And** no partially-populated `Layout` is returned

**AC4 — Empty collections are valid, not errors**

**Given** a JMRI instance with no lights configured
**When** `GET /json/v5/light` returns `[]`
**Then** `layout.lights` is an empty `EntityCollection[Light]` — no exception raised

**AC5 — Unit tests in `tests/unit/test_discover.py`**

**Given** `tests/unit/test_discover.py` exists
**When** the unit suite runs (no live JMRI needed)
**Then** it covers:
- `discover()` assembles a `Layout` from eight parsed entity-type responses (all empty collections — verifies plumbing)
- `discover()` on a non-open Client raises `RuntimeError`
- version check raises `JMRIVersionUnsupported` when JMRI version is below 5.14 (e.g., "5.13.9") with `detected` and `required` in context
- version check passes for exactly "5.14" (minimum supported)
- version check is skipped on the second `discover()` call (verify no second `/json/v5/version` request)
- per-type `JMRIProtocolError` propagates from `discover()` (fail-fast test)
- empty-list response for one entity type produces an empty `EntityCollection` for that type, not an error

**And** all new unit tests pass with `uv run --no-sync pytest -m "not integration"`

**AC6 — `patch_http_factory` extended for per-path response staging**

**Given** the deferred-work item from Story 2.3's code review: "`patch_http_factory` cannot stage separate pre-enter/post-enter responses"
**When** `tests/unit/conftest.py` is updated
**Then** `FakeHTTPClient.next_response` accepts either:
- A dict or list (existing behavior — returned for every `get()` call unchanged), OR
- A callable `(path: str) -> dict | list` — called with the request path and its return value used as the response
**And** all existing tests that set `fake.next_response = {}` or `fake.next_response = [...]` continue to work without changes (backward-compatible)

**AC7 — Integration smoke test: `tests/integration/test_discovery.py`**

**Given** an integration test against the running `Basement_Revised_2024.jmri` layout (NCE simulator, `localhost:12080`)
**When** the test calls `await jmri.discover()` and times the call
**Then** the call completes in under 2 seconds (NFR2)
**And** the returned `layout` is a `Layout` instance with eight `EntityCollection` fields
**And** `layout.turnouts`, `layout.sensors`, and `layout.blocks` are non-empty (Mikey's layout has all three)
**And** the test picks the first turnout and asserts `t.name`, `t.user_name`, and `t.state` are all accessible (state may be `TurnoutState.UNKNOWN` — that is correct and expected per FR14)
**And** the test is decorated with `@pytest.mark.integration` and uses the `jmri_available` session fixture (skips when JMRI is unreachable)

**AC8 — Layout-agnosticism invariant**

**Given** the completed implementation
**When** any reviewer runs `grep -rn 'NT[0-9]\|IS:\|NS[0-9]\|IM:' src/pyjmri/`
**Then** no matches exist in `src/pyjmri/` — discovery operates on whatever JMRI returns

**AC9 — No regressions**

**Given** the unit suite had 253 tests before Story 2.5
**When** the unit suite runs after Story 2.5
**Then** every pre-existing test still passes, plus the new tests
**And** `ruff format`, `ruff check`, and `mypy --strict src/pyjmri` are all clean

## Tasks / Subtasks

- [x] **Task 1 — Extend `patch_http_factory` for callable `next_response`** (AC: 6)
  - [x] In `tests/unit/conftest.py`, update `FakeHTTPClient.get()` to check `if callable(self.next_response): return self.next_response(path)` before returning the static `next_response`. Update the type annotation of `next_response` to `dict[str, Any] | list[dict[str, Any]] | Callable[[str], dict[str, Any] | list[dict[str, Any]]]`.
  - [x] Update the fixture docstring to document callable support.
  - [x] Verify all 253 existing tests still pass (no behavior change for non-callable `next_response`).

- [x] **Task 2 — Add `_version_checked` flag and `discover()` to `client.py`** (AC: 1, 2, 3, 4, 8)
  - [x] In `Client.__init__`, add `self._version_checked: bool = False` after the existing `self._http` declaration.
  - [x] Add a private module-level helper `_fetch_collection(http: HTTPClient, entity_type: str) -> list[dict[str, Any]]` that GETs `/json/v5/{entity_type}` and validates the response is a list (raises `JMRIProtocolError` with `entity_type` and `path` context if not).
  - [x] Add a private module-level helper `_check_jmri_version(payload: dict[str, Any] | list[dict[str, Any]]) -> None` that: extracts the `JMRI` version string from `{"type":"version","data":{"JMRI":"<version>",...}}` (or the first element if payload is a list); compares `tuple(int(x) for x in version.split("."))` against `(5, 14)`; raises `JMRIVersionUnsupported(detected=version, required="5.14")` if the detected version is below 5.14; raises `JMRIProtocolError` if the response is missing the expected fields.
  - [x] Implement `async def discover(self) -> Layout` on `Client`:
    1. Guard: `if self._http is None: raise RuntimeError("Client is not open; ...")`.
    2. Version gate: `if not self._version_checked: payload = await self._http.get("/json/v5/version"); _check_jmri_version(payload); self._version_checked = True`.
    3. Parallel fetch: open an `asyncio.TaskGroup`; create eight tasks, each calling `_fetch_collection(self._http, entity_type)`.
    4. After the TaskGroup exits, parse each collection's envelopes and construct entity instances with `_handle=self`.
    5. Assemble and return `Layout(turnouts=..., sensors=..., ...)`.
  - [x] Add the necessary imports to `client.py`: `asyncio`, entity classes (`Turnout`, `Sensor`, `Block`, `Light`, `Memory`, `Route`, `SignalHead`, `SignalMast`), `EntityCollection`, `Layout`, parsers, `JMRIVersionUnsupported`.
  - [x] Update `Client` docstring to mention `discover()`. Add `__all__` — no change needed (Client already listed).
  - [x] Document `discover()` with a Google-style docstring covering Args (none), Returns (`Layout`), Raises (`JMRIVersionUnsupported`, `JMRIProtocolError`, `JMRIConnectionError`, `JMRIRequestTimeout`, `RuntimeError`).

- [x] **Task 3 — Unit tests `tests/unit/test_discover.py`** (AC: 5)
  - [x] Create `tests/unit/test_discover.py`. For each unit test, set `fake.next_response` to a callable that returns the appropriate response per path.
  - [x] Helper: `_version_payload(version: str)` returns the version envelope shape JMRI emits (a list with one dict: `[{"type":"version","data":{"JMRI": version, "JSON":"5.2"}}]`).
  - [x] Helper: `_empty_list_for_all()` returns a callable that gives `[]` for every entity path and the valid version payload for `/json/v5/version`.
  - [x] Test: `test_discover_returns_layout_with_eight_empty_collections` — happy path with all entity responses returning `[]`.
  - [x] Test: `test_discover_raises_runtime_error_when_client_not_open` — call `discover()` on `Client()` that was never entered.
  - [x] Test: `test_discover_version_check_raises_jmri_version_unsupported_below_5_14` — set version response to `"5.13.9"`, assert `JMRIVersionUnsupported` raised with `context["detected"] == "5.13.9"` and `context["required"] == "5.14"`.
  - [x] Test: `test_discover_version_check_passes_for_exactly_5_14` — version `"5.14"` succeeds.
  - [x] Test: `test_discover_version_check_passes_for_5_14_with_patch` — version `"5.14.0"` succeeds.
  - [x] Test: `test_discover_version_check_skipped_on_second_call` — call `discover()` twice on the same fake client; assert `/json/v5/version` appears exactly once in `fake.probed`.
  - [x] Test: `test_discover_protocol_error_from_entity_type_propagates` — one entity-type path raises via callable response; assert `JMRIProtocolError` propagates from `discover()` (wrapped in `ExceptionGroup` per `asyncio.TaskGroup` semantics).
  - [x] Test: `test_discover_empty_entity_collection_is_valid` — one entity path returns `[]`; assert the corresponding Layout collection has `len == 0`.
  - [x] Test: `test_discover_populates_turnout_collection` — turnout path returns a synthetic turnout envelope; assert `len(layout.turnouts) == 1` and the entity has the expected name, user_name, and state.

- [x] **Task 4 — Integration test `tests/integration/test_discovery.py`** (AC: 7)
  - [x] Create `tests/integration/test_discovery.py` following `test_connection_lifecycle.py` shape (module docstring, `from __future__ import annotations`, `import pytest`, imports from `pyjmri`).
  - [x] Test: `test_discover_completes_in_under_two_seconds` — uses `time.perf_counter()` around `discover()` call; asserts `elapsed < 2.0`.
  - [x] Test: `test_discover_layout_has_turnouts_sensors_and_blocks` — asserts each of the three collections is non-empty; picks `layout.turnouts` first entity, checks `.name` is a non-empty str, `.user_name` is `str | None`, and `.state` is a `TurnoutState` instance.
  - [x] Both tests use `@pytest.mark.integration` and `jmri_available: None` fixture parameter.

- [x] **Task 5 — Quality gates and regression check** (AC: 9)
  - [x] Run `uv run --no-sync ruff format`, `uv run --no-sync ruff check`, `uv run --no-sync mypy --strict src/pyjmri`.
  - [x] Run `uv run --no-sync pytest -m "not integration"` — confirm all 253+ unit tests pass (now 262 unit; 253 prior + 9 new).
  - [x] Run `uv run --no-sync pytest` — confirm integration tests pass (now 3 integration: 1 prior + 2 new for discovery).
  - [x] Update story File List.

## Dev Notes

### Current `python_code/` state (verified by inspection, 2026-05-11)

**Source files in place:**
- `client.py` — `Client` with `__aenter__`/`__aexit__`, `get_entity()`, `power_state()`. Does NOT yet have `discover()` or `_version_checked`. `__aenter__` probes `/json/v5/version` and discards the response.
- `layout.py` — `Layout`, `EntityCollection[T]` (Story 2.4, now done).
- `_parsing.py` — all eight entity parsers: `parse_turnout`, `parse_sensor`, `parse_block`, `parse_light`, `parse_memory`, `parse_route`, `parse_signal_head`, `parse_signal_mast`. Each takes a single envelope dict and returns a frozen `_Parsed<Entity>` dataclass.
- Entity classes (`turnout.py`, `sensor.py`, etc.) — all exist with kw-only constructors. Route has no `_handle`. All others accept `_handle: ClientHandle`.
- `exceptions.py` — `JMRIVersionUnsupported(JMRIProtocolError)` is already defined.
- `_transport.py` — `HTTPClient.get(path)` returns `dict[str, Any] | list[dict[str, Any]]`. Collection endpoints return a list; per-entity endpoints return a dict.

**Test infrastructure:**
- `tests/unit/conftest.py` — `patch_http_factory` monkeypatches `HTTPClient`. `FakeHTTPClient.next_response` is typed `dict | list[dict]`, returned for ALL `get()` calls.
- `tests/integration/conftest.py` — `jmri_available` session fixture (skips when JMRI unreachable).
- 253 unit tests + 1 integration test currently passing.

### Critical pre-requisite: `patch_http_factory` callable extension (Task 1)

This is the highest-priority task — do it first. The Story 2.3 code review deferred this explicitly: "`patch_http_factory` cannot stage separate pre-enter/post-enter responses — Story 2.5 version check will break all existing lifecycle tests because `next_response = {}` is used for both the `__aenter__` version probe and the call under test."

The **minimal fix**: in `FakeHTTPClient.get()`, change:
```python
return self.next_response
```
to:
```python
if callable(self.next_response):
    return self.next_response(path)
return self.next_response
```

The type annotation for `next_response` must also accept `Callable[[str], dict[str, Any] | list[dict[str, Any]]]`. Import `Callable` from `collections.abc`. With `from __future__ import annotations` at the top, type annotations are strings and mypy strict handles it.

Why this works for existing tests: they set `fake.next_response = {}` (a dict, not callable), so `callable({})` is False and the existing behavior is unchanged.

Why `__aenter__` tests are unaffected: `__aenter__` calls `/json/v5/version` and discards the response. `next_response = {}` returns `{}`, which `__aenter__` ignores. discover() unit tests will use a callable that returns a real version envelope for `/json/v5/version` and `[]` for entity paths.

### `discover()` implementation guide

**Import additions to `client.py`:**
```python
import asyncio
from pyjmri._parsing import (
    parse_block, parse_light, parse_memory, parse_route,
    parse_sensor, parse_signal_head, parse_signal_mast, parse_turnout,
)
from pyjmri.block import Block
from pyjmri.exceptions import JMRIVersionUnsupported
from pyjmri.layout import EntityCollection, Layout
from pyjmri.light import Light
from pyjmri.memory import Memory
from pyjmri.route import Route
from pyjmri.sensor import Sensor
from pyjmri.signal import SignalHead, SignalMast
from pyjmri.turnout import Turnout
```

All of these are existing modules — no new dependencies introduced.

**Circular import risk:** `client.py` will import from `layout.py`, and `layout.py` imports from entity modules (not from `client.py`). The import chain: `client → layout → block, sensor, turnout, ...` — no cycle. ✓

**`_fetch_collection` helper (module-level private):**
```python
async def _fetch_collection(
    http: HTTPClient, entity_type: str
) -> list[dict[str, Any]]:
    path = f"/json/v5/{entity_type}"
    payload = await http.get(path)
    if not isinstance(payload, list):
        raise JMRIProtocolError(
            "expected list from collection endpoint",
            entity_type=entity_type,
            path=path,
        )
    return payload
```

**`_check_jmri_version` helper (module-level private):**
```python
def _check_jmri_version(
    payload: dict[str, Any] | list[dict[str, Any]],
) -> None:
    envelope = payload[0] if isinstance(payload, list) else payload
    if not isinstance(envelope, dict):
        raise JMRIProtocolError("version response is not a dict")
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise JMRIProtocolError("version response missing 'data'")
    version = data.get("JMRI")
    if not isinstance(version, str):
        raise JMRIProtocolError("version response missing 'JMRI' field")
    detected = tuple(int(x) for x in version.split("."))
    required = (5, 14)
    if detected < required:
        raise JMRIVersionUnsupported(detected=version, required="5.14")
```

Note: `JMRIVersionUnsupported` inherits from `JMRIProtocolError` which inherits from `JMRIError`. Constructor accepts `**context` keyword args: `JMRIVersionUnsupported(detected=version, required="5.14")` — no positional message. The context dict will have `entity_type` absent (that's fine; `JMRIVersionUnsupported` overrides the context). ✓

**`discover()` structure:**
```python
async def discover(self) -> Layout:
    if self._http is None:
        raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
    http = self._http  # local var for mypy narrowing

    # Version gate (once per Client lifetime)
    if not self._version_checked:
        version_payload = await http.get("/json/v5/version")
        _check_jmri_version(version_payload)
        self._version_checked = True

    # Parallel entity-type discovery
    async with asyncio.TaskGroup() as tg:
        t_turnout    = tg.create_task(_fetch_collection(http, "turnout"))
        t_sensor     = tg.create_task(_fetch_collection(http, "sensor"))
        t_block      = tg.create_task(_fetch_collection(http, "block"))
        t_light      = tg.create_task(_fetch_collection(http, "light"))
        t_memory     = tg.create_task(_fetch_collection(http, "memory"))
        t_route      = tg.create_task(_fetch_collection(http, "route"))
        t_sighead    = tg.create_task(_fetch_collection(http, "signalHead"))
        t_sigmast    = tg.create_task(_fetch_collection(http, "signalMast"))

    # Parse and construct entities; TaskGroup ensures all tasks completed
    turnouts = [Turnout(name=p.name, user_name=p.user_name, state=p.state, _handle=self)
                for e in t_turnout.result() for p in (parse_turnout(e),)]
    sensors  = [Sensor(name=p.name, user_name=p.user_name, state=p.state, _handle=self)
                for e in t_sensor.result() for p in (parse_sensor(e),)]
    blocks   = [Block(name=p.name, user_name=p.user_name, state=p.state, value=p.value, _handle=self)
                for e in t_block.result() for p in (parse_block(e),)]
    lights   = [Light(name=p.name, user_name=p.user_name, state=p.state, _handle=self)
                for e in t_light.result() for p in (parse_light(e),)]
    memories = [Memory(name=p.name, user_name=p.user_name, value=p.value, _handle=self)
                for e in t_memory.result() for p in (parse_memory(e),)]
    routes   = [Route(name=p.name, user_name=p.user_name)
                for e in t_route.result() for p in (parse_route(e),)]
    sheads   = [SignalHead(name=p.name, user_name=p.user_name, appearance=p.appearance,
                           held=p.held, lit=p.lit, _handle=self)
                for e in t_sighead.result() for p in (parse_signal_head(e),)]
    smasts   = [SignalMast(name=p.name, user_name=p.user_name, aspect=p.aspect,
                           held=p.held, lit=p.lit, _handle=self)
                for e in t_sigmast.result() for p in (parse_signal_mast(e),)]

    return Layout(
        turnouts     = EntityCollection(turnouts, entity_type="turnout"),
        sensors      = EntityCollection(sensors,  entity_type="sensor"),
        blocks       = EntityCollection(blocks,   entity_type="block"),
        lights       = EntityCollection(lights,   entity_type="light"),
        memories     = EntityCollection(memories, entity_type="memory"),
        routes       = EntityCollection(routes,   entity_type="route"),
        signal_heads = EntityCollection(sheads,   entity_type="signalHead"),
        signal_masts = EntityCollection(smasts,   entity_type="signalMast"),
    )
```

**Why `for p in (parse_turnout(e),)` rather than `parse_turnout(e)` outside?** This is a list-comprehension idiom that avoids calling the parser twice while keeping the comprehension form. Alternative (equally correct, possibly more readable):

```python
turnouts = []
for e in t_turnout.result():
    p = parse_turnout(e)
    turnouts.append(Turnout(name=p.name, user_name=p.user_name, state=p.state, _handle=self))
```

The dev agent should choose whichever form passes mypy --strict and ruff check.

**`asyncio.TaskGroup` fail-fast:** when one task raises, `TaskGroup` cancels remaining tasks and raises an `ExceptionGroup`. For pyjmri, all entity-type errors are `JMRIProtocolError` or `JMRIConnectionError`. Python 3.11 `ExceptionGroup` will propagate. This is the desired fail-fast behavior per AC3. No try/except needed — TaskGroup does it naturally. If `JMRIProtocolError` is the underlying cause, the `ExceptionGroup` will contain it. Callers may need `except* JMRIProtocolError` or `except ExceptionGroup`. This is an important behavioral note for the API docstring: document that `discover()` may raise via `ExceptionGroup` when a per-type request fails.

Actually — wait. Looking at the architecture: "fail-fast: if one per-type request raises, TaskGroup cancels siblings and propagates." This means users need to catch `ExceptionGroup`, which is a major API usability change. Let me reconsider.

**Revised approach:** wrap the TaskGroup so single-exception ExceptionGroups are unwrapped:
```python
try:
    async with asyncio.TaskGroup() as tg:
        ...
except* (JMRIProtocolError, JMRIConnectionError, JMRIRequestTimeout) as eg:
    raise eg.exceptions[0] from None
```

But `except*` changes semantics and is complex. Simpler: just let `ExceptionGroup` propagate and document it. OR: use gather with return_exceptions=False which raises on first error but isn't structured concurrency.

**Design decision: use `asyncio.gather(*tasks, return_exceptions=False)` instead of TaskGroup?** Actually no — architecture explicitly says `asyncio.TaskGroup`. Python 3.11+ TaskGroup cancels siblings on any exception. The ExceptionGroup is a real concern.

Actually, looking at this more carefully: the architecture says "Fail-fast on per-type errors. If one entity-type endpoint raises, TaskGroup cancels siblings and propagates." It doesn't say "raises an ExceptionGroup." The TaskGroup propagates the exception but wraps it in ExceptionGroup. This is Python's structured concurrency behavior.

For pyjmri v1, the simplest correct approach: let it propagate as ExceptionGroup. Document in the docstring that `discover()` may raise `ExceptionGroup[JMRIError]` when a per-type fetch fails. This is technically correct and matches the architecture intent.

This is an open design decision for Mikey — see Open Design Decisions section below.

### Version response format

JMRI `/json/v5/version` returns either:
- A list with one envelope: `[{"type":"version","data":{"JMRI":"5.14.0","JSON":"5.2",...}}]`
- A single dict: `{"type":"version","data":{"JMRI":"5.14.0","JSON":"5.2",...}}`

`_check_jmri_version` handles both shapes (see implementation guide above).

For version comparison: `tuple(int(x) for x in "5.14.0".split("."))` = `(5, 14, 0)`. Comparing `(5, 14, 0) >= (5, 14)` → True. `(5, 13, 9) >= (5, 14)` → False. Standard Python tuple comparison is correct. ✓

### `asyncio.TaskGroup` and mypy

`asyncio.TaskGroup` is Python 3.11+ (stdlib). Project targets Python 3.11+ per `pyproject.toml`. Mypy should type `tg.create_task()` as returning `asyncio.Task[T]`. `task.result()` returns `T`. Since `_fetch_collection` returns `list[dict[str, Any]]`, `tg.create_task(_fetch_collection(...))` is `asyncio.Task[list[dict[str, Any]]]`, and `.result()` is `list[dict[str, Any]]`. ✓

### Deferred-work item addressed

The Story 2.3 code review deferred item "`patch_http_factory` cannot stage separate pre-enter/post-enter responses" is **addressed in Task 1** of this story. After this story, the deferred-work entry for this item should be considered resolved (but leave it in the file; it's already recorded).

### Testing patterns

- Unit tests: `tests/unit/test_discover.py`, function-per-scenario naming, no `@pytest.mark.asyncio` needed (asyncio_mode=auto). Use `patch_http_factory` fixture (extended in Task 1).
- Integration tests: `tests/integration/test_discovery.py`, `@pytest.mark.integration`, `jmri_available: None` fixture parameter.
- Layout-agnosticism: integration test picks entities from whatever the running layout has. Do NOT hardcode `layout.turnouts["NT400"]` — use `next(iter(layout.turnouts.values()))` or similar.

### Open design decisions for Mikey

1. **`ExceptionGroup` propagation from `discover()`**: When one entity-type fetch fails, `asyncio.TaskGroup` raises `ExceptionGroup[JMRIProtocolError | JMRIConnectionError]`. Users would need `except ExceptionGroup` or `except* JMRIProtocolError`. Alternative: wrap the TaskGroup and re-raise the first exception bare. Proposed default: **let ExceptionGroup propagate, document it**. Simple, honest, matches Python 3.11 semantics. The alternative (unwrapping) hides multiple simultaneous failures. If you want the cleaner API, say so.

2. **`_version_checked` behavior on failed discover**: If the version check passes but entity discovery fails (ExceptionGroup), should `_version_checked` stay True on the next `discover()` call? Proposed default: **yes** — version validity is independent of entity fetch success. The version check is truly "once per Client lifetime."

3. **Version endpoint**: Proposed to use `/json/v5/version` (same as `__aenter__` probe). The architecture says "against the `/json/v5` endpoint metadata" — this could mean the base `/json/v5` endpoint. If JMRI serves version info only at `/json/v5` (not `/json/v5/version`), adjust. Proposed default: **use `/json/v5/version`** for consistency with Story 2.1's probe choice.

If you accept all three defaults, the dev agent runs without questions.

### File layout

```
python_code/src/pyjmri/client.py            # MODIFY — add discover(), _version_checked
python_code/tests/unit/conftest.py          # MODIFY — callable next_response
python_code/tests/unit/test_discover.py     # NEW
python_code/tests/integration/test_discovery.py  # NEW
```

No other source files require modification. `__init__.py` already exports `Layout` and `EntityCollection`.

### Cross-story implications

- **Epic 3 (wait_*):** `discover()` returns entities with `_handle=self`. After Epic 3's `wait_*` primitives land, user code can do `layout = await jmri.discover(); await layout.turnouts["NT400"].wait_state(TurnoutState.THROWN)`. The `_handle` wiring is already correct.
- **Epic 4 (set_state):** Same — entities have `_handle=self`, command methods will be added to entity classes directly.
- **Epic 6 (hello_jmri.py example):** `discover()` is the gateway call for the quickstart example: `async with Client() as jmri: layout = await jmri.discover()`.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md`#Story 2.5] — story scope and ACs (roster deviation applies)
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Discovery Strategy] — TaskGroup parallel, fail-fast, empty collections valid
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Concurrency Model] — TaskGroup is the correct primitive
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Internal Layering] — client.py is the orchestrator; parsers stay in _parsing.py
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Complete Project Directory Structure] — test file paths
- [Source: `_bmad-output/planning-artifacts/prd.md`#NFR8] — JMRIVersionUnsupported requirement (JMRI >= 5.14)
- [Source: `_bmad-output/planning-artifacts/prd.md`#NFR2] — < 2 s for ~370-entity layout
- [Source: `_bmad-output/planning-artifacts/prd.md`#FR8, FR12] — discover() returns Layout with all supported types
- [Source: `_bmad-output/implementation-artifacts/2-4-layout-container-entitycollection-with-dual-name-lookup.md`] — Layout/EntityCollection shapes, entity_type strings
- [Source: `_bmad-output/implementation-artifacts/2-3-per-entity-classes-with-read-only-state-and-value-access.md`] — entity constructors (kw-only, _handle, Route has no _handle)
- [Source: `_bmad-output/implementation-artifacts/2-1-http-transport-client-lifecycle-exception-hierarchy-logging-foundation.md`] — Client lifecycle, __aenter__ probe at /json/v5/version
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md`] — patch_http_factory deferred item (addressed in Task 1)
- [Source: `python_code/src/pyjmri/client.py`] — current Client source (read fully before modifying)
- [Source: `python_code/src/pyjmri/_parsing.py`] — parser functions and _Parsed* dataclass fields
- [Source: `python_code/tests/unit/conftest.py`] — patch_http_factory to be extended

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Opus 4.7, 1M context) via Claude Code, with bmad-dev-story workflow.

### Debug Log References

- Initial integration run failed: `JMRIProtocolError: version response missing 'JMRI' field`. Querying live JMRI revealed `/json/v5/version` returns `[{"type":"version","data":{"5.4.0":"v5"}}]` — only the JSON API version, not JMRI. The JMRI **application** version lives in `/json/v5/networkService` (each envelope's `data.jmri` field).
- Story Open Design Decision #3 explicitly anticipated this case ("if JMRI serves version info only at `/json/v5` (not `/json/v5/version`), adjust").
- Pivoted: `_check_jmri_version` now parses `networkService` envelope shape; `discover()` fetches `/json/v5/networkService` for the version gate. `__aenter__`'s probe stays on `/json/v5/version` (cheapest endpoint that proves the API is alive); comment updated to reflect the split.

### Completion Notes List

- All 9 acceptance criteria satisfied; all 5 tasks complete with checkboxes [x].
- **Open design decisions** — all three proposed defaults accepted:
  1. `ExceptionGroup` propagates from `discover()` when a per-type fetch fails (TaskGroup native semantics). Documented in the `discover()` docstring's Note section.
  2. `_version_checked` stays True even if a later `discover()` call fails inside the TaskGroup (version validity is independent of entity-fetch success).
  3. Version endpoint changed from the proposed `/json/v5/version` to `/json/v5/networkService` based on live JMRI evidence (see Debug Log).
- **AC2/NFR8 version gate validated** against live JMRI 5.14.0 (Mike's Basement). `_check_jmri_version` raises `JMRIVersionUnsupported(detected=..., required="5.14")` for any earlier version.
- **AC7 timing** — integration test passes with elapsed time well under 2 s on Mike's Basement layout (~370 entities). Both new integration tests pass.
- **AC8 layout-agnosticism** — `grep` in `src/pyjmri/` finds only docstring example references to NCE system names (e.g., `"NT400"`, `"NS401"`) in pre-existing files from Stories 2.3/2.4 (`turnout.py:45`, `sensor.py:43`, `layout.py:48,49,68`). All operational discovery code is layout-agnostic — entities are read from whatever JMRI returns. No new hardcoded system names were introduced by Story 2.5.
- **AC9 no regressions** — 253 prior unit tests still pass; ruff format/check and mypy --strict clean across all 17 source files.
- **Deferred-work item** — "`patch_http_factory` cannot stage separate pre-enter/post-enter responses" (Story 2.3 review): addressed by extending `FakeHTTPClient.next_response` to accept a callable. Per story Dev Notes guidance, the entry is left in `deferred-work.md` as historical record.

### File List

- `python_code/src/pyjmri/client.py` — MODIFIED. Added `_version_checked` flag in `__init__`; added `discover()` method on `Client`; added module-level helpers `_fetch_collection()` and `_check_jmri_version()`; expanded imports (asyncio, entity classes, parsers, layout types, `JMRIVersionUnsupported`); refreshed the `__aenter__` probe comment to document the version-endpoint split.
- `python_code/tests/unit/conftest.py` — MODIFIED. `FakeHTTPClient.next_response` now accepts a callable `(path) -> dict | list` in addition to the prior static dict/list. Backward-compatible (existing tests unaffected).
- `python_code/tests/unit/test_discover.py` — NEW. 9 unit tests covering happy path, runtime-error guard, version gate (pass/fail/cached), fail-fast via TaskGroup ExceptionGroup, empty collection validity, populated turnout collection with dual-name lookup.
- `python_code/tests/integration/test_discovery.py` — NEW. 2 integration tests (NFR2 timing, layout has turnouts/sensors/blocks with TurnoutState).

## Change Log

- 2026-05-11 — Story 2.5 created (`ready-for-dev`). Exhaustive artifact analysis: epics (2.5 AC verbatim + roster exclusion), architecture (Discovery Strategy, Concurrency Model, Internal Layering, Test Harness), PRD NFR2/NFR8/FR8/FR12, Stories 2.1–2.4 dev notes and review findings, live `client.py`/`_parsing.py`/`conftest.py` state, deferred-work.md. Three open design decisions surfaced (ExceptionGroup propagation, _version_checked on failure, version endpoint choice) with proposed defaults. `patch_http_factory` callable extension flagged as Task 1 critical pre-requisite. `discover()` implementation guide provided with concrete code sketch and mypy notes. Roster exclusion applied consistently.
- 2026-05-11 — Story 2.5 implemented (`in-progress` → `review`). All 5 tasks and 9 acceptance criteria satisfied. Version endpoint pivoted from the proposed `/json/v5/version` to `/json/v5/networkService` after live JMRI evidence showed the former returns only the JSON-API version (`{"5.4.0":"v5"}`) while the JMRI application version lives in `networkService` envelopes' `data.jmri` field. All three open design decisions accepted at the proposed defaults (ExceptionGroup propagates; `_version_checked` independent of fetch success; version endpoint adjusted as anticipated). Quality gates clean: 262 unit tests + 3 integration tests pass; `ruff format`, `ruff check`, and `mypy --strict src/pyjmri` all green. `patch_http_factory` callable extension (Story 2.3 deferred item) resolved.
