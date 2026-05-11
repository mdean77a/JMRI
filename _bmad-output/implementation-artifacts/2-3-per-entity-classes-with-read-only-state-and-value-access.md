# Story 2.3: Per-entity classes with read-only state and value access

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a library user,
I want typed entity classes for turnout, sensor, block, light, memory, route, signalHead, and signalMast — plus a top-level `power_state()` method on `Client` — that expose their current state or value as typed properties,
so that once I have an entity reference (from later discovery work), I can read its state or value in one line with full mypy support.

**Scope note (Mikey, 2026-05-08):** the **roster is dropped from pyjmri's public surface**. User scripts will identify locomotives by DCC address directly; pyjmri does not need to model `Roster` or `RosterEntry` as public classes. The parser shipped in Story 2.2 (`parse_roster_entry`, `_ParsedRosterEntry`) stays in `_parsing.py` as inert code for now — removing it is out of scope for 2.3. Architectural follow-on: Story 2.4's `Layout` will not carry a `roster: Roster` attribute, and Story 2.5's `discover()` will not fetch `/json/v5/roster`.

## Acceptance Criteria

1. **`_protocols.py` defines a `ClientHandle` Protocol that hides transport from entity modules.** Given Story 2.2's state enums and parsers, when `_protocols.py` is added with a `ClientHandle` Protocol exposing the slim Client surface that domain entities depend on, then entity modules import only `ClientHandle` (never `_transport` directly), and `mypy --strict` resolves the Protocol-typed dependency cleanly across `turnout.py`, `sensor.py`, `block.py`, `light.py`, `signal.py`, `memory.py`, and `route.py`.

2. **`turnout.py` defines `class Turnout` with cached state and `async get_state()`.** Given `turnout.py` defines `class Turnout` with `name: str`, `user_name: str | None`, `state: TurnoutState` (cached, mutable), and `async def get_state() -> TurnoutState`, when `await turnout.get_state()` is called, then it issues an HTTP read via the `ClientHandle`, parses the response via `parse_turnout`, updates the cached `state`, and returns the new value (FR13); if JMRI reports the turnout as `unknown`, the returned value is `TurnoutState.UNKNOWN` and is never coerced to `CLOSED` or any other value (FR14).

3. **The same get_state pattern is implemented for sensor, block, light, signal head, and signal mast.** Given the same pattern is applied to `sensor.py` (`Sensor`, `SensorState`), `block.py` (`Block`, `BlockState`), `light.py` (`Light`, `LightState`), and `signal.py` (`SignalHead` returning `SignalHeadAppearance`, `SignalMast` returning `SignalMastAspect`), when each entity's `get_state()` is unit-tested using a fake `ClientHandle` and a synthetic JSON envelope, then the test passes and the entity's cached state field is updated; signal heads and signal masts also expose cached `held: bool` and `lit: bool` populated by the same call (FR13, FR14).

4. **`memory.py` defines `class Memory` with cached value and `async get_value()`.** Given `memory.py` defines `class Memory` with `name`, `user_name`, `value: str | None` (cached), and `async def get_value() -> str | None`, when `await memory.get_value()` is called, then it returns the current memory value as a typed string (or `None` if unset) per FR15, and updates the cached `value` field.

5. **`route.py` defines a typed `Route` class with no read method.** Given `route.py` defines `class Route` with `name`, `user_name`, and a docstring noting that activation is added in Epic 4, when `mypy --strict` runs, then the class is well-typed, declares `__all__`, and has no `get_state` / `get_value` method (routes are fire-and-forget actions per architecture).

6. **`Client.power_state()` returns the current `PowerState` (read-only, no write).** Given `Client` gains an `async def power_state() -> PowerState` method, when `await client.power_state()` is called against a JMRI instance, then it returns the current `PowerState` (FR16) by issuing `GET /json/v5/power`, parsing the singleton envelope via `parse_power`, and returning the parsed `state`; there is no public method to write power state (PRD-deliberate omission per "Power control" note).

7. **Public-API discipline is preserved across every module touched by this story.** Given every public module touched, when a reviewer inspects it, then `__all__` is declared listing only the user-facing exports; every public class has a Google-style docstring describing what + when to use it; `from __future__ import annotations` is at the top; the new public surface (`Turnout`, `Sensor`, `Block`, `Light`, `Memory`, `Route`, `SignalHead`, `SignalMast`) is re-exported from `pyjmri/__init__.py` with `__all__` updated alphabetically, and the `NullHandler` install line is preserved.

8. **Quality gates and unit tests pass; transport boundary is intact.** Given Story 2.3's deliverables, when `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src/pyjmri`, and `uv run pytest -m "not integration"` run from `python_code/`, then all four exit 0; the new unit tests cover every entity's `get_state()` / `get_value()` happy path, the `state=UNKNOWN` not-coerced rule, and at least one error path per entity (e.g., parser raises `JMRIProtocolError`); `grep -rn "^import httpx\|^from httpx" src/` returns only `_transport.py`; Story 2.1's integration smoke test still passes against live JMRI.

## Tasks / Subtasks

- [x] **Task 1: Create `src/pyjmri/_protocols.py` with the `ClientHandle` Protocol** (AC: #1)
  - [x] Create the new private module with the canonical shape from §"`_protocols.py` canonical shape" below.
  - [x] Use `typing.Protocol` (not `runtime_checkable` — there's no `isinstance(x, ClientHandle)` use case in v1; runtime_checkable adds runtime overhead for no value).
  - [x] Method signature: `async def get_entity(self, entity_type: str, name: str) -> dict[str, Any]: ...` — returns the parsed-JSON envelope dict (the same shape `parse_<entity>` consumes).
  - [x] Module-level logger is NOT required on this module (Protocols define typing only; no runtime logging).
  - [x] No `__all__` (private module convention; matches `_codes.py`, `_parsing.py`).
  - [x] **Why a domain-level Protocol method instead of raw `get(path)`:** the Client owns URL formatting, including URL-encoding entity names that can contain spaces or colons (e.g., `IS:DCCAPP:1`, `"Block 1"`). Entities never see paths. This honors architecture §Internal Layering: "domain owns transport, never the inverse."

- [x] **Task 2: Add `Client._get_entity()` and `Client.power_state()`** (AC: #1, #6)
  - [x] In `client.py`, add `async def _get_entity(self, entity_type: str, name: str) -> dict[str, Any]` implementing the `ClientHandle` Protocol method. See §"`Client._get_entity` and `Client.power_state` canonical shapes" below.
  - [x] Path format: `f"/json/v5/{entity_type}/{quote(name, safe='')}"` — `safe=''` because JMRI system names contain colons (`IS:DCCAPP:1`) and user names contain spaces; both must be percent-encoded.
  - [x] Closed-Client guard: if `self._http is None`, raise `RuntimeError("Client is not open; use 'async with Client() as jmri:'")`. The same RuntimeError shape as `Throttle` lifecycle errors (architecture-consistent).
  - [x] Single-envelope narrowing: `HTTPClient.get` returns `dict[str, Any] | list[dict[str, Any]]`. For per-entity GET the response is a dict; if the runtime payload is a list, raise `JMRIProtocolError("expected single entity envelope", entity_type=entity_type, name=name)`.
  - [x] Add `async def power_state(self) -> PowerState`. Calls `self._http.get("/json/v5/power")`, narrows the list-or-dict shape (live JMRI returns a one-element list), parses via `parse_power`, returns `parsed.state`. See canonical shape below.
  - [x] Empty-list guard: if the power response is `[]`, raise `JMRIProtocolError("empty power response", path="/json/v5/power")`.
  - [x] Update `client.py` `__all__` only if needed — `Client` is already re-exported. No changes to module-level `__all__`.
  - [x] **No public `set_power()` method.** PRD §Entity Control deliberately omits power write — the booster's physical power switch is the source of truth on NCE. Resist the temptation to add a setter "for symmetry."

- [x] **Task 3: Implement `class Turnout` in `turnout.py`** (AC: #2, #7)
  - [x] Replace the current "stub" docstring with the full canonical shape from §"`turnout.py` canonical shape" below.
  - [x] Add `from typing import TYPE_CHECKING` and import `ClientHandle` under `if TYPE_CHECKING:` to avoid a runtime import cycle (`pyjmri._protocols` → `pyjmri.turnout` → `pyjmri._protocols` is not a real cycle but TYPE_CHECKING keeps the discipline tight).
  - [x] Constructor signature: `def __init__(self, *, name: str, user_name: str | None, state: TurnoutState, _handle: ClientHandle) -> None`. Underscore on `_handle` is a soft hint that it's library-internal — users typically receive `Turnout` instances from `Layout.turnouts` (Story 2.4/2.5) and never construct directly.
  - [x] **`state` is a public, mutable attribute** (not a `@property`). It's updated in-place by `get_state()` and (later, in Epic 3) by the WS receive loop's `_on_event(new_state)`. Architecture §Subscription Registry: "each entity holds `_state` (cached current state)" — Story 2.3 names this `state` (no underscore) since it's user-readable today; Story 3.1 may add an internal `_state` alias with `_on_event` plumbing if needed.
  - [x] `async def get_state(self) -> TurnoutState`: calls `self._handle.get_entity("turnout", self.name)`, parses with `parse_turnout`, assigns `self.state = parsed.state`, returns `parsed.state`. **`user_name` is NOT updated by `get_state()`** — names are immutable identity fields; only state is refreshed.
  - [x] **FR14 enforcement:** `get_state()` must NEVER coerce `TurnoutState.UNKNOWN` to anything else. The parser already preserves it (Story 2.2 verified); the test for this story re-asserts the round-trip.
  - [x] Keep the existing `TurnoutState` enum unchanged.
  - [x] Update `__all__ = ["Turnout", "TurnoutState"]` (alphabetical).
  - [x] **Docstring discipline:** Google-style; the class docstring's "what + when to use it" line should mention that `state` reflects "JMRI's last commanded state, not the physical position of the turnout on the layout" (per persistent memory: NCE is open-loop; FR14 + FR42).

- [x] **Task 4: Implement `class Sensor`, `class Block`, `class Light` with the same pattern** (AC: #3, #7)
  - [x] **Sensor** — `sensor.py`: class with `name`, `user_name`, `state: SensorState` (cached), `async def get_state() -> SensorState`. Calls `self._handle.get_entity("sensor", self.name)` → `parse_sensor` → assigns and returns. `__all__ = ["Sensor", "SensorState"]`.
  - [x] **Block** — `block.py`: class with `name`, `user_name`, `state: BlockState` (cached), `value: str | None` (cached, since blocks carry an optional `value` field per `_ParsedBlock`), `async def get_state() -> BlockState`. Updates BOTH `state` and `value` from the parsed envelope. `__all__ = ["Block", "BlockState"]`.
  - [x] **Light** — `light.py`: class with `name`, `user_name`, `state: LightState` (cached), `async def get_state() -> LightState`. `__all__ = ["Light", "LightState"]`.
  - [x] All three classes follow the canonical Turnout shape, just substituting types and JMRI entity-type strings (`"sensor"`, `"block"`, `"light"`).
  - [x] All three module docstrings note the FR14 not-coerced rule for their own state's `UNKNOWN`.
  - [x] **Block-specific docstring note:** mention that `BlockState.UNDETECTED` (state=0 from JMRI) means the block has no occupancy detector wired — distinct from `UNKNOWN`. This is the design decision Mikey resolved in Story 2.2.

- [x] **Task 5: Implement `class SignalHead` and `class SignalMast` in `signal.py`** (AC: #3, #7)
  - [x] In `signal.py`, alongside the existing enums, add two classes per §"`signal.py` canonical shape" below.
  - [x] **SignalHead:** `name`, `user_name`, `appearance: SignalHeadAppearance` (cached), `held: bool` (cached), `lit: bool` (cached), `async def get_state() -> SignalHeadAppearance`. Calls `self._handle.get_entity("signalHead", self.name)` → `parse_signal_head` → assigns `appearance`, `held`, `lit` from the parsed envelope; returns `parsed.appearance`.
  - [x] **SignalMast:** `name`, `user_name`, `aspect: SignalMastAspect` (cached), `held: bool` (cached), `lit: bool` (cached), `async def get_state() -> SignalMastAspect`. Calls `self._handle.get_entity("signalMast", self.name)` → `parse_signal_mast` → assigns and returns `parsed.aspect`.
  - [x] **Why `get_state()` and not `get_appearance()` / `get_aspect()`:** the AC explicitly says "each entity's `get_state()` is unit-tested" — the public method name is uniform across entities for ergonomic discoverability. The return *type* differs (the per-entity state enum); the *method* name does not.
  - [x] Update `__all__ = ["SignalHead", "SignalHeadAppearance", "SignalMast", "SignalMastAspect"]` (alphabetical).
  - [x] Keep the existing module docstring's "basic signaling system only" note — it remains accurate.

- [x] **Task 6: Implement `class Memory` in `memory.py`** (AC: #4, #7)
  - [x] Replace the empty stub with a full class per §"`memory.py` canonical shape" below.
  - [x] Class attributes: `name: str`, `user_name: str | None`, `value: str | None` (cached).
  - [x] `async def get_value(self) -> str | None`: calls `self._handle.get_entity("memory", self.name)`, parses with `parse_memory`, assigns `self.value = parsed.value`, returns `parsed.value`. **The method is `get_value()`, not `get_state()`** — memory has no state; it has a value (FR15).
  - [x] `__all__ = ["Memory"]`.
  - [x] Docstring: "Read-only memory variable. Use `await memory.get_value()` to refresh from JMRI; the cached `value` is updated as a side effect."

- [x] **Task 7: Implement `class Route` in `route.py`** (AC: #5, #7)
  - [x] Replace the empty stub with a small class per §"`route.py` canonical shape" below.
  - [x] Class attributes: `name: str`, `user_name: str | None`. **No state, no `get_state` method, no handle held** — routes are fire-and-forget actions; in v1 they have no readable state.
  - [x] Docstring explicitly notes: "Route activation lands in Epic 4 (`route.activate()`); v1 only enumerates routes."
  - [x] Constructor: `def __init__(self, *, name: str, user_name: str | None) -> None`. No `_handle` parameter — routes don't read state in v1.
  - [x] `__all__ = ["Route"]`.
  - [x] mypy strict must pass without complaint about an "unused" handle.

- [x] **Task 8: Update `pyjmri/__init__.py` to re-export new public surface** (AC: #7)
  - [x] Add re-exports: `Turnout`, `Sensor`, `Block`, `Light`, `Memory`, `Route`, `SignalHead`, `SignalMast`. (The state enums and `PowerState` are already re-exported from Story 2.2. `Roster`/`RosterEntry` are explicitly NOT re-exported — see scope note at the top of this story.)
  - [x] Update `__all__` alphabetically — keep the rest of the list intact.
  - [x] **Preserve the `NullHandler` install line.** Architecture §Logging Strategy: "library installs `NullHandler` on the `pyjmri` root at import time."
  - [x] Run `uv run python -c "from pyjmri import Turnout, Sensor, Block, Light, Memory, Route, SignalHead, SignalMast"` to confirm all re-exports resolve cleanly.
  - [x] **`roster.py` stays as the empty stub from Story 2.2.** Do not add `class Roster` or `class RosterEntry` in this story.

- [x] **Task 9: Add unit tests under `tests/unit/`** (AC: #1, #2, #3, #4, #5, #6, #8)
  - [x] **Shared fake handle helper** in `tests/unit/conftest.py` — extend the existing conftest to expose a `make_fake_handle` factory that constructs a fake `ClientHandle` from a callable returning the desired envelope. See §"`tests/unit/conftest.py` extension" below for the canonical shape.
  - [x] **`tests/unit/test_protocols.py`** (~2 tests) — sanity that `ClientHandle` is importable, has the expected `get_entity` member, and a structurally-conforming class type-checks against it (using `typing.cast`).
  - [x] **`tests/unit/test_turnout.py`** (~6–7 tests).
  - [x] **`tests/unit/test_sensor.py`**, **`tests/unit/test_block.py`**, **`tests/unit/test_light.py`** — mirror Turnout's test set with the per-entity types and JMRI codes. Block tests additionally cover `BlockState.UNDETECTED` (state=0) and that `value` is updated.
  - [x] **`tests/unit/test_signal.py`** (~6–8 tests) — covers `get_state()` returning `SignalHeadAppearance` / `SignalMastAspect`, `held` / `lit` updated, and a non-basic aspect raising `JMRIProtocolError` (via `parse_signal_mast`).
  - [x] **`tests/unit/test_memory.py`** (~4 tests) — `get_value()` returns string and `None`; cached `value` updates; missing `value` key in envelope is fine (parser returns `None`).
  - [x] **`tests/unit/test_route.py`** (~2 tests) — construction with name + user_name; no `get_state` attribute.
  - [x] **No `tests/unit/test_roster.py`** in this story — roster public classes are out of scope.
  - [x] **`tests/unit/test_power.py`** (~6 tests) — `patch_http_factory` moved into `tests/unit/conftest.py` for reuse and extended with a `next_response` attribute. All canonical scenarios covered, plus URL-encoding sanity for `_get_entity` (spaces, colons) and list-payload guard.
  - [x] **Test naming follows architecture §Testing Patterns.**
  - [x] **Final new test count: 66 (suite total: 227 unit tests + 1 integration test = 228).**

- [x] **Task 10: Verify quality gates locally and push** (AC: #8)
  - [x] From `python_code/`:
    - `uv run ruff format` → 5 files reformatted, 28 unchanged
    - `uv run ruff check` → All checks passed!
    - `uv run ruff format --check` → 33 files already formatted
    - `uv run mypy src/pyjmri` → Success: no issues found in 16 source files (15 from Story 2.2 + new `_protocols.py`)
    - `uv run pytest -m "not integration"` → 227 passed, 1 deselected
    - `uv run pytest` → 228 passed (Story 2.1's integration smoke test still passes against live JMRI)
  - [x] **Architectural-boundary regression check:** `grep -rn "^import httpx\|^from httpx" src/pyjmri/` returns only `_transport.py:12`. ✅
  - [ ] **Push to GitHub.** Deferred — pending Mikey confirmation.

## Dev Notes

### `_protocols.py` canonical shape

```python
"""Slim Client surface that domain entities depend on.

Defining this Protocol keeps `_transport.py` out of `turnout.py`,
`sensor.py`, etc. — entity modules import only `ClientHandle`. The
concrete implementation lives on `Client` (see `client.py`); the
indirection lets unit tests construct entities with a fake handle.

Architecture §Internal Layering: "domain entities hold a Protocol-typed
handle to the Client for issuing commands. They don't import
`_transport` directly."
"""
from __future__ import annotations

from typing import Any, Protocol


class ClientHandle(Protocol):
    """Internal Protocol for entity → Client read-back calls.

    The Client implements this Protocol implicitly via duck typing: it
    has a matching `_get_entity` method.

    This Protocol is not part of the public API; users of pyjmri never
    interact with it. It exists to satisfy mypy's strict-mode
    requirement that entity modules type their Client handle without
    importing `_transport` (architectural-boundary preservation).
    """

    async def get_entity(
        self, entity_type: str, name: str
    ) -> dict[str, Any]: ...
```

**Why a method named `get_entity` and not `get`:** the method is domain-shaped, not transport-shaped. Entities don't know the URL path format; they pass `(entity_type, name)` and the Client takes care of `quote`-ing the name and assembling `/json/v5/{type}/{name}`.

**Why `dict[str, Any]` is the return type:** matches what `parse_<entity>` consumes. The `Any` is the JSON-input parameter exemption already documented in architecture §Type Annotation Conventions ("`Any` is permitted in `_parsing.py` *only* for the JSON dict input parameter before parsing"). The return remains `dict[str, Any]` to keep that exemption confined to the parse boundary.

**Why no `runtime_checkable`:** there is no `isinstance(x, ClientHandle)` site in v1. Adding `runtime_checkable` would force every duck-typed conformance check to walk the structural members at runtime — pointless overhead for a strict-typed library. If a future story needs runtime checking, add the decorator then.

### `Client._get_entity` and `Client.power_state` canonical shapes

```python
# In client.py — added inside `class Client`

async def _get_entity(self, entity_type: str, name: str) -> dict[str, Any]:
    """Implementation of :class:`pyjmri._protocols.ClientHandle`."""
    if self._http is None:
        raise RuntimeError(
            "Client is not open; use 'async with Client() as jmri:'"
        )
    path = f"/json/v5/{entity_type}/{quote(name, safe='')}"
    payload = await self._http.get(path)
    if not isinstance(payload, dict):
        raise JMRIProtocolError(
            "expected single entity envelope, got list",
            entity_type=entity_type,
            name=name,
            path=path,
        )
    return payload

async def power_state(self) -> PowerState:
    """Return the current JMRI track-power state.

    Issues ``GET /json/v5/power`` and returns the parsed
    :class:`~pyjmri.PowerState`. Read-only by design — the booster's
    physical power switch is the source of truth on NCE hardware
    (PRD FR16, §"Power control" note).

    Raises:
        RuntimeError: when the Client is not open.
        JMRIProtocolError: when the JMRI response is empty or malformed.
        JMRIConnectionError, JMRIRequestTimeout: see :meth:`_get_entity`.
    """
    if self._http is None:
        raise RuntimeError(
            "Client is not open; use 'async with Client() as jmri:'"
        )
    payload = await self._http.get("/json/v5/power")
    if isinstance(payload, list):
        if not payload:
            raise JMRIProtocolError(
                "empty power response",
                path="/json/v5/power",
            )
        envelope = payload[0]
    else:
        envelope = payload
    parsed = parse_power(envelope)
    return parsed.state
```

**Imports added at the top of `client.py`:**

```python
from typing import Any
from urllib.parse import quote

from pyjmri._parsing import parse_power
from pyjmri.exceptions import JMRIProtocolError
from pyjmri.power import PowerState
```

(`PowerState` is also re-exported from `pyjmri/__init__.py`; importing it directly from `pyjmri.power` here avoids a self-import cycle.)

**Why `quote(name, safe='')`:** JMRI system names like `IS:DCCAPP:1` and user names like `"Block 1"` contain characters reserved or unsafe in URL paths. `safe=''` percent-encodes everything outside `[a-zA-Z0-9_.~-]`, which is the conservative correct choice. Adding more "safe" characters risks ambiguity if JMRI ever introduces names containing `/` (unlikely, but cheap to defend against).

**Why `Client` does NOT formally inherit `ClientHandle`:** Python's `Protocol` matching is structural — `Client` having a method with the matching signature is enough to satisfy `_handle: ClientHandle`. Adding `class Client(ClientHandle):` would force every `Client` field to be Protocol-compatible, gain nothing, and violate the architecture's preference for ducktyped Protocols (§Internal Layering).

### `turnout.py` canonical shape

```python
"""Turnout entity class and TurnoutState enum.

Architecture §Domain State Modeling.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

from pyjmri._parsing import parse_turnout

if TYPE_CHECKING:
    from pyjmri._protocols import ClientHandle

logger = logging.getLogger(__name__)

__all__ = ["Turnout", "TurnoutState"]


class TurnoutState(Enum):
    UNKNOWN = "unknown"
    CLOSED = "closed"
    THROWN = "thrown"
    INCONSISTENT = "inconsistent"


class Turnout:
    """A JMRI turnout discovered on the layout.

    The cached :attr:`state` reflects JMRI's last commanded position,
    not the physical state of the turnout on the layout — JMRI knows
    only what it has been told (NCE is open-loop). When the position
    has never been commanded since JMRI started, the state is
    :attr:`TurnoutState.UNKNOWN` and pyjmri preserves it as
    ``UNKNOWN`` rather than coercing to ``CLOSED`` (FR14).

    Example:
        Refresh a turnout's state from JMRI::

            current = await turnout.get_state()
            if current is TurnoutState.THROWN:
                ...

    Args:
        name: JMRI system name (e.g., ``"NT400"``).
        user_name: Optional JMRI user name.
        state: Initial cached state (typically captured by
            :meth:`pyjmri.Client.discover` in Story 2.5).
        _handle: Internal :class:`~pyjmri._protocols.ClientHandle`
            issued by the owning :class:`~pyjmri.Client`.
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
        state: TurnoutState,
        _handle: ClientHandle,
    ) -> None:
        self.name = name
        self.user_name = user_name
        self.state = state
        self._handle = _handle

    async def get_state(self) -> TurnoutState:
        """Refresh the cached :attr:`state` from JMRI and return it.

        Returns:
            The newly read :class:`TurnoutState`. ``UNKNOWN`` is a
            real, first-class value — the library never coerces it to
            ``CLOSED`` (FR14).

        Raises:
            JMRIProtocolError, JMRIConnectionError, JMRIRequestTimeout:
                surfaced from :class:`~pyjmri.Client`.
        """
        envelope = await self._handle.get_entity("turnout", self.name)
        parsed = parse_turnout(envelope)
        self.state = parsed.state
        return parsed.state
```

**Why a class, not a frozen dataclass:** `state` must be mutable so `get_state()` can update the cache. A frozen dataclass would force `object.__setattr__` gymnastics — uglier than the explicit class. Every entity class in this story is a regular (mutable) class for the same reason.

**Why `_handle` is keyword-only and underscore-prefixed:** keyword-only forces named arguments at construction (preventing positional errors as the constructor signature evolves). The underscore signals "internal — not part of the public API"; users obtain a `Turnout` from `Layout.turnouts` (Stories 2.4/2.5), never by calling `Turnout(...)` themselves.

**Why `name` and `user_name` are not refreshed by `get_state()`:** names are identity, not state. JMRI does not change a turnout's system name at runtime; if the parser returns a `name` that doesn't match `self.name`, that is a contract violation worth raising — but Story 2.3 deliberately doesn't add that assertion (it would belong in Story 3.x's WS-event validation work).

### `sensor.py`, `block.py`, `light.py` canonical shapes

Identical pattern to Turnout. Differences per entity:

**`sensor.py`:**
- `Sensor.state: SensorState`
- `get_state()` calls `self._handle.get_entity("sensor", self.name)` → `parse_sensor`
- Class docstring: "A JMRI sensor (block detector, button, etc.)…"

**`block.py`:**
- `Block.state: BlockState` AND `Block.value: str | None` (cached) — blocks carry an optional string value (e.g., a train ID)
- `get_state()` calls `self._handle.get_entity("block", self.name)` → `parse_block`; assigns BOTH `self.state` and `self.value` from the parsed envelope; returns `parsed.state`
- Class docstring includes: "`BlockState.UNDETECTED` (JMRI state=0) means the block has no occupancy detector — a real and distinct value from `UNKNOWN`."
- `__init__` extends Turnout's signature with `value: str | None` parameter

**`light.py`:**
- `Light.state: LightState`
- `get_state()` calls `self._handle.get_entity("light", self.name)` → `parse_light`
- Class docstring: "A JMRI light (panel indicator, layout LED, etc.)…"

### `signal.py` canonical shape (additions)

```python
# In addition to the existing SignalHeadAppearance and SignalMastAspect enums

if TYPE_CHECKING:
    from pyjmri._protocols import ClientHandle


class SignalHead:
    """A JMRI signal head with its current appearance.

    Args:
        name, user_name: JMRI identifiers.
        appearance: Initial cached :class:`SignalHeadAppearance`.
        held: Initial cached "held" flag (when ``True``, JMRI has
            forced the head to its most-restrictive appearance).
        lit: Initial cached "lit" flag (when ``False``, JMRI has
            blanked the head).
        _handle: Internal :class:`ClientHandle`.
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
        appearance: SignalHeadAppearance,
        held: bool,
        lit: bool,
        _handle: ClientHandle,
    ) -> None:
        self.name = name
        self.user_name = user_name
        self.appearance = appearance
        self.held = held
        self.lit = lit
        self._handle = _handle

    async def get_state(self) -> SignalHeadAppearance:
        """Refresh and return the cached :class:`SignalHeadAppearance`.

        Side effects: also updates :attr:`held` and :attr:`lit`.
        """
        envelope = await self._handle.get_entity("signalHead", self.name)
        parsed = parse_signal_head(envelope)
        self.appearance = parsed.appearance
        self.held = parsed.held
        self.lit = parsed.lit
        return parsed.appearance


class SignalMast:
    """A JMRI signal mast with its current aspect.

    pyjmri v1 binds to the JMRI "basic" signaling system only; aspects
    outside that system raise :class:`JMRIProtocolError` on read.
    See README Limitations (Story 6.2).
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
        aspect: SignalMastAspect,
        held: bool,
        lit: bool,
        _handle: ClientHandle,
    ) -> None:
        self.name = name
        self.user_name = user_name
        self.aspect = aspect
        self.held = held
        self.lit = lit
        self._handle = _handle

    async def get_state(self) -> SignalMastAspect:
        envelope = await self._handle.get_entity("signalMast", self.name)
        parsed = parse_signal_mast(envelope)
        self.aspect = parsed.aspect
        self.held = parsed.held
        self.lit = parsed.lit
        return parsed.aspect
```

`__all__` updated to `["SignalHead", "SignalHeadAppearance", "SignalMast", "SignalMastAspect"]` (alphabetical).

Add at top: `from pyjmri._parsing import parse_signal_head, parse_signal_mast`.

### `memory.py` canonical shape

```python
"""Memory entity (a typed read-only memory variable in JMRI)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pyjmri._parsing import parse_memory

if TYPE_CHECKING:
    from pyjmri._protocols import ClientHandle

logger = logging.getLogger(__name__)

__all__ = ["Memory"]


class Memory:
    """A JMRI memory variable.

    Memories are typed string-or-null containers JMRI uses for layout
    metadata (current train ID per block, temperature, etc.).

    Example:
        Refresh and read a memory::

            current = await memory.get_value()
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
        value: str | None,
        _handle: ClientHandle,
    ) -> None:
        self.name = name
        self.user_name = user_name
        self.value = value
        self._handle = _handle

    async def get_value(self) -> str | None:
        """Refresh the cached :attr:`value` from JMRI and return it.

        Returns:
            The memory's current value, or ``None`` if unset (FR15).
        """
        envelope = await self._handle.get_entity("memory", self.name)
        parsed = parse_memory(envelope)
        self.value = parsed.value
        return parsed.value
```

### `route.py` canonical shape

```python
"""Route entity (typed metadata only in v1; activation lands in Epic 4)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = ["Route"]


class Route:
    """A JMRI route — a saved sequence of turnout positions.

    In pyjmri v1 a :class:`Route` is metadata only: name and user name.
    Route activation (firing the saved sequence) lands in Epic 4 as
    ``await route.activate()``. Routes have no readable state in v1.

    Example:
        Enumerate available routes::

            for route in layout.routes.values():
                print(route.name)
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
    ) -> None:
        self.name = name
        self.user_name = user_name
```

No `_handle`. mypy strict will accept it because `Route` declares all of its fields.

### `roster.py` — unchanged in this story

Per the scope note at the top of this story, `roster.py` stays as the empty stub Story 2.2 left in place. No `Roster` or `RosterEntry` public class is introduced. The shipped parser machinery (`_parsing.parse_roster_entry`, `_parsing._ParsedRosterEntry`) remains in place but is not consumed by any public class in this story.

### `tests/unit/conftest.py` extension

Story 2.2 created `conftest.py` with `load_fixture`. Story 2.3 extends it with a fake-handle factory:

```python
# Add alongside the existing load_fixture fixture

from collections.abc import Awaitable, Callable
from typing import Any


@pytest.fixture
def make_fake_handle() -> Callable[
    [Callable[[str, str], dict[str, Any]]],
    object,
]:
    """Return a factory that builds a :class:`ClientHandle`-shaped fake.

    Example:
        Build a fake that returns a synthetic envelope::

            handle = make_fake_handle(
                lambda entity_type, name: {
                    "type": entity_type,
                    "data": {"name": name, "userName": None, "state": 2},
                }
            )
            turnout = Turnout(
                name="NT9", user_name=None,
                state=TurnoutState.UNKNOWN, _handle=handle,
            )
            assert await turnout.get_state() is TurnoutState.CLOSED
    """

    def _make(
        envelope_for: Callable[[str, str], dict[str, Any]],
    ) -> object:
        class _Fake:
            calls: list[tuple[str, str]] = []

            async def get_entity(
                self, entity_type: str, name: str
            ) -> dict[str, Any]:
                _Fake.calls.append((entity_type, name))
                return envelope_for(entity_type, name)

        return _Fake()

    return _make
```

(The fixture's return type is `object` because `ClientHandle` is a Protocol — at the test site we cast or pass the duck-typed instance directly.)

### Power test fixture pattern

Reuse the existing `patch_http_factory` fixture from `tests/unit/test_client.py`. Either:
1. Move it into `tests/unit/conftest.py` so `test_power.py` can import it directly (recommended — DRY), or
2. Mirror it locally inside `test_power.py` (acceptable if the fixture is small).

If moving: the fixture's `FakeHTTPClient.get` already returns whatever the test sets in `fake.fail_with` or returns `{}` by default. Extend the fake to support a `next_response` attribute so a test can stage a list-shaped power response:

```python
# Conftest extension — supplements the existing patch_http_factory.

class FakeHTTPClient:
    def __init__(self, **kwargs: Any) -> None:
        ...
        self.next_response: dict[str, Any] | list[dict[str, Any]] = {}

    async def get(self, path: str) -> dict[str, Any] | list[dict[str, Any]]:
        self.probed.append(path)
        if self.fail_with is not None:
            raise self.fail_with
        return self.next_response
```

**Why extend rather than rewrite:** Story 2.1's `patch_http_factory` is consumed by Story 2.1 tests and Story 2.3 tests. Breaking the existing tests to add a feature is unacceptable; the additive `next_response` field is backward-compatible (the existing tests rely on `{}` default, which `next_response`'s default preserves).

### Architecture compliance checklist

| Architecture / PRD rule | Story 2.3 alignment |
| --- | --- |
| §Internal Layering — entities depend on Protocol-typed handle, not `_transport` | Task 1 (`_protocols.py`); Tasks 3–6 (`if TYPE_CHECKING:` import only) |
| §Internal Layering — `_protocols.py` is private | Task 1 (no `__all__`, no `__init__.py` re-export) |
| §Architectural Boundaries point 2 — only `_transport.py` imports `httpx` | Task 11 (regression check via `grep`) |
| §Domain State Modeling — per-entity Enum, `UNKNOWN` first-class | Tasks 3–5 (FR14 docstring + tests) |
| §Public API Discipline — `__all__` on every public module | Tasks 3–9 (every entity file + `__init__.py`) |
| §Public API Discipline — Examples and docs use top-level `pyjmri` | Task 9 (re-exports added) |
| §Type Annotation Conventions — `from __future__ import annotations`, PEP 604 unions | All tasks |
| §Type Annotation Conventions — `Self` for chaining, no `Optional[X]` | All tasks |
| §Logging Discipline — module-level `logger = logging.getLogger(__name__)` | Tasks 3–8 |
| §Documentation Patterns — Google-style public docstrings | Tasks 3–8 |
| §Testing Patterns — `test_<module>.py` per source module; no JMRI mocks | Task 10 |
| §Async Patterns — public I/O methods are `async def` | Tasks 3–6 (`get_state`, `get_value`); Task 2 (`power_state`) |
| FR13 — typed state read | Tasks 2–5 (`get_state` returns typed enum) |
| FR14 — `unknown` distinguishable, never coerced | Tasks 3–5 (docstrings + dedicated tests) |
| FR15 — typed memory value | Task 6 (`Memory.get_value()`) |
| FR16 — read-only power state | Task 2 (`Client.power_state()` only) |
| FR34 — typed `JMRIError` subclasses surface from reads | Tasks 2–6 (parsers raise `JMRIProtocolError`; Client raises `JMRIProtocolError` on shape mismatch) |

### Live JMRI integer-code dependencies (carry-over from Story 2.2)

Story 2.3's `get_state()` methods consume Story 2.2's `_codes.py` and `_parsing.py` directly. Re-stating the relevant numbers for the dev agent's reference:

| Endpoint | Per-entity GET path used by `_get_entity` | State field type |
| --- | --- | --- |
| `/json/v5/turnout/<name>` | `("turnout", name)` | `int`, codes via `_codes.TURNOUT_STATE` |
| `/json/v5/sensor/<name>` | `("sensor", name)` | `int`, codes via `_codes.SENSOR_STATE` |
| `/json/v5/block/<name>` | `("block", name)` | `int`, codes via `_codes.BLOCK_STATE` |
| `/json/v5/light/<name>` | `("light", name)` | `int`, codes via `_codes.LIGHT_STATE` |
| `/json/v5/signalHead/<name>` | `("signalHead", name)` | `int` (`appearance`), codes via `_codes.SIGNAL_HEAD_APPEARANCE`; plus `held: bool`, `lit: bool` |
| `/json/v5/signalMast/<name>` | `("signalMast", name)` | `str` (`aspect`), translated via `SignalMastAspect(aspect_str)` |
| `/json/v5/memory/<name>` | `("memory", name)` | `value: str \| None` (no state) |
| `/json/v5/power` | (collection — handled by `Client.power_state` directly) | `int`, codes via `_codes.POWER_STATE` |

Note: the per-entity-name endpoints (`.../turnout/NT400`) return a single dict envelope; the collection endpoints (`.../turnout`) return a list of envelopes — Story 2.5 will use the collection endpoints for parallel discovery. Story 2.3's `_get_entity` only deals with the per-name shape.

### Reference: previous story context

**Story 2.2 (status `review`, 2026-05-07):** Created `_codes.py` (six int→Enum tables), `_parsing.py` (ten parsers + ten `_Parsed<X>` dataclasses), and the per-entity public modules as enum-only stubs. Story 2.3 fills in the entity classes the stubs were placeholders for. Mikey's resolved design decisions from 2.2 still apply: `BlockState.UNDETECTED` is its own member (preserve in `Block` docstring), `SignalMastAspect` ships only the JMRI "basic" set (preserve in `SignalMast` docstring), fixture coverage stays narrow.

**Story 2.2 review-finding patterns to honor:**
- `_required_state` and `_required_str` helpers in `_parsing.py` are the centralized error-shape — Story 2.3 doesn't add new parser helpers; entities call existing `parse_<entity>` functions and any `JMRIProtocolError` flows through unchanged.
- The fake-handle pattern Story 2.3 introduces (`make_fake_handle` in conftest) is the unit-test analog of Story 2.1's `patch_http_factory` for `Client`. Both honor architecture §Test Harness: "No mocks of JMRI" — these mock the *Client interface*, not JMRI itself.
- Story 2.2 added 108 unit tests to bring the suite from 53 → 161; Story 2.3 should land in the +50–60 range. Be skeptical of any final count over 70 — that suggests duplicated coverage; under 40 suggests gaps.

**Story 2.1 (status `done`, 2026-05-07):** Owns the `Client` class, `HTTPClient`, exception hierarchy, and the integration smoke test. Story 2.3 modifies `client.py` (adding `_get_entity` and `power_state`); the rest of `client.py` is unchanged. The `__aenter__` probe (`/json/v5/version`) is still load-bearing for the integration smoke test.

**Story 1.3 (CI):** the six-job matrix (macOS+Linux × 3.11/3.12/3.13) runs `pytest -m "not integration"`. New unit tests will run there; integration tests remain local-only.

### Things explicitly NOT in this story

These belong to later stories — resist the urge to bundle:

- **`Client.discover()`** — Story 2.5 (which will also drop the `/json/v5/roster` fetch per the scope note at the top of this story).
- **`Layout` class** and **`EntityCollection[T]`** with dual-name lookup — Story 2.4 (which will also drop the planned `roster: Roster` attribute).
- **Any `Roster` / `RosterEntry` public classes** — out of pyjmri scope. User scripts identify locomotives by DCC address directly.
- **WebSocket transport** and **`SubscriptionRegistry`** — Story 3.1.
- **`entity._on_event(state)`** synchronous fanout — Story 3.1+.
- **`async def wait_state()` / `wait_active()` / `wait_change()` waiter methods** on entities — Story 3.2.
- **Per-entity `set_state()` methods** (turnout `.throw()`, light `.turn_on()`, sensor `.set_active()`, etc.) — Story 4.1.
- **`route.activate()`** — Story 4.1 / 4.2.
- **`wait_for_jmri_state=True` opt-in** on commands — Story 4.2.
- **Throttle classes** (`Throttle`, `acquire`, `release`, `set_speed`) — Story 5.x.
- **Setting power state** — never (PRD-deliberate omission).

### Verification matrix (after all tasks complete)

| Check | Expected outcome |
| --- | --- |
| `python_code/src/pyjmri/_protocols.py` exists; defines `ClientHandle` Protocol | ✅ |
| `python_code/src/pyjmri/turnout.py` defines `class Turnout` with `name`, `user_name`, `state`, `get_state` | ✅ |
| Same for `sensor.py`, `block.py`, `light.py` (state-bearing entities) | ✅ |
| `python_code/src/pyjmri/signal.py` defines `class SignalHead`, `class SignalMast` | ✅ |
| `python_code/src/pyjmri/memory.py` defines `class Memory` with `get_value` | ✅ |
| `python_code/src/pyjmri/route.py` defines `class Route` (no read methods) | ✅ |
| `python_code/src/pyjmri/roster.py` UNCHANGED (still empty stub from Story 2.2) | ✅ |
| `python_code/src/pyjmri/client.py` adds `_get_entity` and `power_state` methods | ✅ |
| `python_code/src/pyjmri/__init__.py` re-exports the eight new public classes (no Roster/RosterEntry) | ✅ |
| `tests/unit/test_protocols.py`, `test_turnout.py`, `test_sensor.py`, `test_block.py`, `test_light.py`, `test_signal.py`, `test_memory.py`, `test_route.py`, `test_power.py` exist and pass | ✅ |
| Story 2.1's `test_client.py`, Story 2.2's `test_codes.py`/`test_parsing.py`/`test_exceptions.py`/`test_transport.py` still pass | ✅ |
| Story 2.1's integration smoke test (`test_connection_lifecycle.py`) still passes against live JMRI | ✅ |
| Only `_transport.py` imports `httpx` (`grep -rn "^import httpx\|^from httpx" python_code/src/pyjmri/`) | ✅ |
| `uv run ruff check` → 0 | ✅ |
| `uv run ruff format --check` → 0 | ✅ |
| `uv run mypy src/pyjmri` → 0 (strict, all 17+ source files) | ✅ |
| `uv run pytest -m "not integration"` → 0; total tests > 161 (Story 2.2's count) | ✅ |
| `uv run pytest` → 0 (integration smoke also passes when JMRI is up) | ✅ |
| `uv run python -c "from pyjmri import Turnout, Sensor, Block, Light, Memory, Route, SignalHead, SignalMast"` succeeds | ✅ |
| GitHub Actions six-job CI matrix goes green on push | ✅ |

### Project Structure Notes

All new and modified files live under `python_code/`. Aligns with architecture §Complete Project Directory Structure exactly — no path deviations.

**New files:**

- `python_code/src/pyjmri/_protocols.py` — NEW (private Protocol module)
- `python_code/tests/unit/test_protocols.py` — NEW
- `python_code/tests/unit/test_turnout.py` — NEW
- `python_code/tests/unit/test_sensor.py` — NEW
- `python_code/tests/unit/test_block.py` — NEW
- `python_code/tests/unit/test_light.py` — NEW
- `python_code/tests/unit/test_signal.py` — NEW
- `python_code/tests/unit/test_memory.py` — NEW
- `python_code/tests/unit/test_route.py` — NEW
- `python_code/tests/unit/test_power.py` — NEW

**Modified files:**

- `python_code/src/pyjmri/turnout.py` — UPDATE (add `class Turnout`; preserve `TurnoutState`)
- `python_code/src/pyjmri/sensor.py` — UPDATE (add `class Sensor`; preserve `SensorState`)
- `python_code/src/pyjmri/block.py` — UPDATE (add `class Block`; preserve `BlockState`)
- `python_code/src/pyjmri/light.py` — UPDATE (add `class Light`; preserve `LightState`)
- `python_code/src/pyjmri/signal.py` — UPDATE (add `class SignalHead`, `class SignalMast`; preserve enums + module docstring)
- `python_code/src/pyjmri/memory.py` — UPDATE (add `class Memory`; replace empty stub)
- `python_code/src/pyjmri/route.py` — UPDATE (add `class Route`; replace empty stub)
- `python_code/src/pyjmri/client.py` — UPDATE (add `_get_entity`, `power_state`, related imports; preserve all existing behavior)
- `python_code/src/pyjmri/__init__.py` — UPDATE (add 8 new entity-class re-exports — Turnout, Sensor, Block, Light, SignalHead, SignalMast, Memory, Route; preserve `NullHandler` install + existing enum/error re-exports)
- `python_code/tests/unit/conftest.py` — UPDATE (add `make_fake_handle` factory; consider moving `patch_http_factory` from `test_client.py` here for reuse)
- `python_code/tests/unit/test_client.py` — UPDATE only if `patch_http_factory` is moved (otherwise unchanged)

**Unchanged from Story 2.2** (regression-protect — do not modify):

- `python_code/src/pyjmri/_codes.py`
- `python_code/src/pyjmri/_parsing.py`
- `python_code/src/pyjmri/_transport.py`
- `python_code/src/pyjmri/exceptions.py`
- `python_code/src/pyjmri/power.py` (`PowerState` enum stays as Story 2.2 left it)
- `python_code/src/pyjmri/roster.py` (empty stub from Story 2.2; deferred per scope note)
- `python_code/tests/unit/test_codes.py`
- `python_code/tests/unit/test_parsing.py`
- `python_code/tests/unit/test_exceptions.py`
- `python_code/tests/unit/test_transport.py`
- `python_code/tests/unit/fixtures/*.json`
- `python_code/tests/integration/conftest.py`
- `python_code/tests/integration/test_connection_lifecycle.py`
- `python_code/pyproject.toml` (no new runtime deps)
- `python_code/uv.lock`

### Open design decisions for Mikey to confirm before dev starts

The dev-story workflow can proceed with the proposed defaults below; all are flagged so Mikey can accept or revise without needing to re-read the architecture.

1. **`ClientHandle` Protocol shape — domain-level vs raw-transport.** Proposed: `async def get_entity(entity_type: str, name: str) -> dict[str, Any]`. The Client owns URL formatting (including `urllib.parse.quote` of the name) and the entity stays naïve about paths. Alternative considered: raw `async def get(path: str) -> dict | list[dict]` matching `HTTPClient.get` exactly — rejected because it pushes path formatting onto every entity class.

2. **Entity constructors are public, kw-only, with an underscore-prefixed `_handle` parameter.** Proposed because users typically receive entities from `Layout` collections (Story 2.4/2.5), but unit tests need to construct them with a fake handle. Alternative: a private `Turnout._construct_with_handle(...)` factory and a public `Turnout(name, user_name, state)` without a handle — rejected because it splits the construction surface and complicates tests.

3. **`Client.power_state()` calls `_http.get` directly, not via the `ClientHandle` Protocol.** Proposed because power isn't a per-entity class and there's no `Power` entity type to hold a handle. Alternative: route everything through `_get_entity`, accepting an awkward `_get_entity("power", "")` shape — rejected as ugly.

4. **No integration smoke test for `Client.power_state()` in this story.** Deferred to Story 2.5 (which already plans an integration test that exercises `discover()` against live JMRI). Adding a separate Story 2.3 integration test would be one more file for ~5 lines of test logic. Mikey may override if they want FR16 covered explicitly before 2.5 lands.

If Mikey accepts all four defaults, the dev agent runs straight through with no design questions. (The fifth question from the original draft — `Roster` shape — was resolved on 2026-05-08 by dropping roster modeling entirely; see the scope note at the top of this story.)

## Resolved design decisions (Mikey, 2026-05-08)

All four open design decisions accepted as proposed:

1. **`ClientHandle` Protocol is domain-level:** `async def get_entity(entity_type: str, name: str) -> dict[str, Any]`. Client owns URL formatting and `urllib.parse.quote` of the name.
2. **Entity constructors are public, kw-only, with underscore-prefixed `_handle: ClientHandle`.** Users receive entities from `Layout` collections in Stories 2.4/2.5; tests construct directly with fake handles.
3. **`Client.power_state()` calls `_http.get` directly, not via the `ClientHandle` Protocol.** Power isn't a per-entity class.
4. **No integration smoke test for `power_state()` in this story.** Deferred to Story 2.5's `discover()` integration test.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3: Per-entity classes with read-only state and value access] — story scope and ACs
- [Source: _bmad-output/planning-artifacts/architecture.md#Domain State Modeling] — per-entity Enum, `UNKNOWN` first-class, no shared base
- [Source: _bmad-output/planning-artifacts/architecture.md#Internal Layering] — Protocol-typed Client handle, public/private split
- [Source: _bmad-output/planning-artifacts/architecture.md#Architectural Boundaries] — point 2 (transport/domain boundary)
- [Source: _bmad-output/planning-artifacts/architecture.md#Type Annotation Conventions] — `from __future__ import annotations`, PEP 604 unions, `Any` only on JSON input parameter
- [Source: _bmad-output/planning-artifacts/architecture.md#Async Patterns] — public I/O is `async def`
- [Source: _bmad-output/planning-artifacts/architecture.md#Public API Discipline] — `__all__` on every public module
- [Source: _bmad-output/planning-artifacts/architecture.md#Documentation Patterns] — Google-style public docstrings
- [Source: _bmad-output/planning-artifacts/architecture.md#Logging Discipline] — `logger = logging.getLogger(__name__)` per module
- [Source: _bmad-output/planning-artifacts/architecture.md#Test Harness] — no JMRI mocks; unit tests cover internals
- [Source: _bmad-output/planning-artifacts/architecture.md#Testing Patterns] — file/function naming
- [Source: _bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure] — exact file paths
- [Source: _bmad-output/planning-artifacts/prd.md FR13] — typed state read
- [Source: _bmad-output/planning-artifacts/prd.md FR14] — `unknown` is a first-class state
- [Source: _bmad-output/planning-artifacts/prd.md FR15] — typed memory value
- [Source: _bmad-output/planning-artifacts/prd.md FR16] — read-only power state
- [Source: _bmad-output/planning-artifacts/prd.md FR34] — typed `JMRIError` hierarchy
- [Source: _bmad-output/planning-artifacts/prd.md §"Power control"] — power is read-only by design
- [Source: _bmad-output/planning-artifacts/prd.md FR42] — Limitations section (NCE open-loop)
- [Source: _bmad-output/implementation-artifacts/2-2-...md] — Story 2.2 dev notes; canonical `_codes.py`/`_parsing.py` shapes; live JMRI observations; resolved design decisions
- [Source: _bmad-output/implementation-artifacts/2-1-...md] — Story 2.1 dev notes; `Client` lifecycle; `patch_http_factory` test harness pattern
- [Source: _bmad-output/implementation-artifacts/epic-1-retro-2026-05-07.md] — Epic 1 retrospective patterns to honor

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Opus 4.7, 1M context)

### Debug Log References

- Initial `from pyjmri import ...` smoke test surfaced a circular import: `block.py → _parsing.py → _codes.py → block.py (BlockState)`. Cause: the canonical shape places `from pyjmri._parsing import parse_<entity>` at module top, but `_parsing.py` imports each entity's enum at module top (Story 2.2 design). Resolution: deferred each entity module's `parse_<entity>` import to inside `get_state()` / `get_value()`. The cycle breaks because the parser is no longer needed at module load time. This deviates from the story's canonical-shape comment ("Add at top: `from pyjmri._parsing import ...`") but preserves the architectural intent (entity modules use parsers; runtime cost is one cached `import` lookup per call). Applied uniformly across `turnout`, `sensor`, `block`, `light`, `signal`, `memory`. `route` does not need a parser.
- `patch_http_factory` was moved from `tests/unit/test_client.py` into `tests/unit/conftest.py` and extended with a `next_response` attribute (defaulting to `{}` for backward compatibility) so that `tests/unit/test_power.py` could stage list-shaped power envelopes without duplicating the fixture.

### Completion Notes List

- All 8 ACs satisfied. Quality gates: ruff format ✅, ruff check ✅, mypy strict ✅ (16 source files, no issues), pytest unit ✅ (227 passed), pytest full ✅ (228 passed including live-JMRI integration smoke test).
- httpx-import boundary preserved: `grep -rn "^import httpx\|^from httpx" src/pyjmri/` returns only `_transport.py:12`.
- Test count: 66 new tests added, bringing unit-suite total from 161 → 227 (story estimated 45–55; the higher count comes from extra `_get_entity` URL-encoding tests in `test_power.py` and a few extra state-code coverage tests per entity — all non-redundant).
- `_protocols.py` was already created as a placeholder during Story 2.2; verified to match the canonical shape exactly. No edits required.
- `roster.py` left untouched per the 2026-05-08 scope reduction (roster dropped from public surface).
- Push to GitHub deferred for Mikey to authorize.

### File List

**New files:**
- `python_code/tests/unit/test_protocols.py`
- `python_code/tests/unit/test_turnout.py`
- `python_code/tests/unit/test_sensor.py`
- `python_code/tests/unit/test_block.py`
- `python_code/tests/unit/test_light.py`
- `python_code/tests/unit/test_signal.py`
- `python_code/tests/unit/test_memory.py`
- `python_code/tests/unit/test_route.py`
- `python_code/tests/unit/test_power.py`

**Modified files:**
- `python_code/src/pyjmri/turnout.py` (added `class Turnout`, kept `TurnoutState`)
- `python_code/src/pyjmri/sensor.py` (added `class Sensor`, kept `SensorState`)
- `python_code/src/pyjmri/block.py` (added `class Block` with `value`, kept `BlockState`)
- `python_code/src/pyjmri/light.py` (added `class Light`, kept `LightState`)
- `python_code/src/pyjmri/signal.py` (added `class SignalHead`, `class SignalMast`, kept enums)
- `python_code/src/pyjmri/memory.py` (added `class Memory` with `get_value`)
- `python_code/src/pyjmri/route.py` (added `class Route`, no read methods)
- `python_code/src/pyjmri/client.py` (added `_get_entity`, `power_state`, related imports)
- `python_code/src/pyjmri/__init__.py` (added 8 entity-class re-exports)
- `python_code/tests/unit/conftest.py` (added `make_fake_handle` factory; moved `patch_http_factory` here from `test_client.py` and extended with `next_response`)
- `python_code/tests/unit/test_client.py` (removed local `patch_http_factory` — now imported from conftest)

**Pre-existing (verified, no changes needed):**
- `python_code/src/pyjmri/_protocols.py` (created in Story 2.2 as placeholder; matches canonical shape)

**Unchanged from Story 2.2 (regression-protected):**
- `python_code/src/pyjmri/_codes.py`
- `python_code/src/pyjmri/_parsing.py`
- `python_code/src/pyjmri/_transport.py`
- `python_code/src/pyjmri/exceptions.py`
- `python_code/src/pyjmri/power.py`
- `python_code/src/pyjmri/roster.py`
- `python_code/tests/unit/test_codes.py`
- `python_code/tests/unit/test_parsing.py`
- `python_code/tests/unit/test_exceptions.py`
- `python_code/tests/unit/test_transport.py`
- `python_code/tests/integration/test_connection_lifecycle.py`
- `python_code/pyproject.toml`, `python_code/uv.lock`

## Change Log

- 2026-05-07 — Story 2.3 created (`ready-for-dev`). Comprehensive context engine analysis: epics, architecture, PRD, Story 2.2 dev notes, live `python_code/` source state. Five open design decisions surfaced for Mikey to confirm or revise before dev-story executes.
- 2026-05-08 — Scope reduced (Mikey): roster dropped from pyjmri's public surface. `RosterEntry` / `Roster` classes removed from this story; AC #6 cut and ACs renumbered (8 ACs total now); `Task 8` (Roster impl) cut; `test_roster.py` cut; `roster.py` moves from "Modified" to "Unchanged"; `__init__.py` re-exports drop `Roster`/`RosterEntry`. Architectural impact noted for Stories 2.4 (no `Layout.roster`) and 2.5 (no `/json/v5/roster` discovery fetch). Open design decisions go from 5 → 4.
- 2026-05-08 — All four remaining open design decisions accepted as proposed (Mikey). See "Resolved design decisions" section. Story is implementation-ready with no outstanding questions.
- 2026-05-08 — Implementation complete. 8 entity classes added (Turnout, Sensor, Block, Light, SignalHead, SignalMast, Memory, Route), `Client._get_entity` and `Client.power_state` added, 66 new unit tests added (227 unit total + 1 integration smoke = 228 passing). All quality gates green. Status moved to `review`. Implementation deviation: parser imports made lazy (inside `get_state` / `get_value`) to break a circular import not anticipated by the canonical shape; entity-module top-level remains free of `_parsing` dependencies. Push to GitHub deferred pending Mikey confirmation.
- 2026-05-11 — Code review complete (3-layer: Blind Hunter, Edge Case Hunter, Acceptance Auditor). 6 patches, 7 deferred, 7 dismissed. Status moved to `in-progress`.

### Review Findings

- [x] [Review][Patch] Protocol/Client name mismatch: `ClientHandle.get_entity` vs `Client._get_entity` — renamed `Client._get_entity` → `Client.get_entity`; fixed `_protocols.py` docstring; updated `test_power.py` references [`_protocols.py:30`, `client.py:111`]
- [x] [Review][Patch] Memory entity has no error-path test — added `test_get_value_propagates_protocol_error` (missing `name` field triggers `JMRIProtocolError`) [`tests/unit/test_memory.py`]
- [x] [Review][Patch] `power_state()` non-list/non-dict payload crashes with `AttributeError` not `JMRIProtocolError` — added `elif isinstance(payload, dict)` / `else raise JMRIProtocolError("unexpected power response type")` [`client.py`]
- [x] [Review][Patch] `_get_entity` "got list" error message misleading for empty list `[]` — added distinct empty-list guard with "entity not found: per-name endpoint returned empty list" message before the general non-dict guard [`client.py`]
- [x] [Review][Patch] `test_power_state_calls_correct_endpoint` assertion too weak — changed `in fake.probed` to `fake.probed[-1] == "/json/v5/power"` [`tests/unit/test_power.py`]
- [x] [Review][Patch] `get_state()` docstrings do not document that `name`/`user_name` are not refreshed — added one-line note to all five entity `get_state()` docstrings; also clarified `SignalHead`/`SignalMast` atomicity [`turnout.py`, `sensor.py`, `block.py`, `light.py`, `signal.py`]
- [x] [Review][Defer] `_optional_str` silent coercion of non-string to `None` [`_parsing.py`] — deferred, pre-existing Story 2.2 behavior
- [x] [Review][Defer] `patch_http_factory` cannot stage separate pre-enter/post-enter responses — Story 2.5 version check will break lifecycle tests [`tests/unit/conftest.py`] — deferred, pre-existing
- [x] [Review][Defer] `_get_entity` "got list" error message wrong for non-list/non-dict types (string, int, None) — real transport prevents; fake misuse only [`client.py:129`] — deferred, pre-existing
- [x] [Review][Defer] `SignalHead` appearance code 256 (HELD sentinel) raises `JMRIProtocolError` — pre-existing Story 2.2 `_codes.py` decision [`_codes.py`] — deferred, pre-existing
- [x] [Review][Defer] URL encoding of `$`, `(`, `)` in signal mast names untested with real JMRI — `quote(name, safe='')` encodes these; acceptance by JMRI per-entity endpoint unverified [`client.py:126`] — deferred, pre-existing
- [x] [Review][Defer] `power_state()` discards `parsed.name` and `parsed.default` — by design for single-booster v1 [`client.py:163`] — deferred, pre-existing
- [x] [Review][Defer] `SignalHead`/`SignalMast` `get_state()` atomicity guarantee undocumented — implementation is all-or-nothing on parse; docstrings omit this [`signal.py`] — deferred, pre-existing

### Second-Pass Review Findings

- [x] [Review][Patch] `get_entity` empty-list guard has no test — added `test_get_entity_raises_on_empty_list` (passes `[]`, asserts "entity not found" message) [`tests/unit/test_power.py`]
- [x] [Review][Patch] `get_entity` now public (no underscore) but is internal-only — added "For internal use by domain entity classes" to docstring [`client.py:111`]
- [x] [Review][Patch] `power_state()` `payload[0]` not validated as dict — added `isinstance(envelope, dict)` check after `envelope = payload[0]`; raises `JMRIProtocolError("unexpected power response type")` [`client.py`]
- [x] [Review][Patch] `test_signal.py` missing `SignalMast` protocol-error test — added `test_signal_mast_get_state_propagates_protocol_error` (missing `held`/`lit` triggers `JMRIProtocolError`) [`tests/unit/test_signal.py`]
- [x] [Review][Patch] `match="single entity envelope"` in `test_get_entity_raises_on_list_payload` is too loose — tightened to exact message `"expected single entity envelope, got list"` [`tests/unit/test_power.py:125`]
- [x] [Review][Defer] `power_state()` silently discards `payload[1:]` for multi-item lists — by design for single-booster v1 [`client.py`] — deferred, pre-existing
