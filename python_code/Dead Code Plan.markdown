# pyjmri v1.0.0 — Dead Code & Refactor Plan

## Context

`python_code/src/pyjmri/` is 4,443 LOC across 20 modules — a tagged v1 client for the JMRI web server. Code is clean and intentional: 31 public exports, no leakage; type hints and docstrings are disciplined throughout. The opportunities are almost entirely **duplication consolidation** and **a small handful of unused-import deletions**. There is essentially no rotten dead code.

This plan lays out the cleanups in dependency order so each PR is small, mechanical, and independently verifiable. Net effect across P1–P5: ~400 LOC removed/consolidated, public API unchanged.

```
                ┌──────────────────────────┐
                │ P1: dead imports (warmup)│
                └────────────┬─────────────┘
                             │ (no deps)
        ┌────────────────────┼─────────────────────┐
        ▼                    ▼                     ▼
  ┌─────────────┐   ┌────────────────────┐   ┌──────────────┐
  │ P2 discover │   │ P3 wait_state /    │   │ P5.1 httpx   │
  │ builder     │   │   wait_change      │   │ exc wrap     │
  │ (client.py) │   │ helper (6 files)   │   │ (_transport) │
  └─────┬───────┘   └────────┬───────────┘   └──────────────┘
        │                    │
        ▼                    ▼
  ┌──────────────┐   ┌────────────────────┐
  │ P5.2 EG      │   │ P4 set_state +     │
  │ unwrap helper│   │   shield helper    │
  │ (client.py)  │   │ (turnout, light)   │
  └──────────────┘   └────────────────────┘
                             │
                             ▼
                  ┌────────────────────┐
                  │ P6 (optional):     │
                  │  extract WS        │
                  │  dispatch          │
                  └────────────────────┘
```

P3 must land before P4: P4's helper reuses the pre-register-wait + cleanup pattern that P3 establishes for the wait-without-command case. P2 and P5 are independent of the wait/command consolidation and can interleave.

---

## Priority 1 — Dead-import cleanup (one PR)

Pure deletion. Zero behavior change. CI-safe warmup.

### 1.1 Remove unused `logger` declarations

Every domain module declares `logger = logging.getLogger(__name__)` and never calls it. Telemetry actually flows through `_transport.py` (`pyjmri.transport`), `_subscriptions.py` (`pyjmri.subscription`), `_waiters.py` (its own logger), and `throttle.py` (`pyjmri.throttle`). The domain-module loggers are dead.

Files to clean (delete both `import logging` and the `logger = …` line; preserve the module docstring above them):

| File | `import logging` line | `logger = ...` line |
|---|---|---|
| `sensor.py` | 9 | 19 |
| `turnout.py` | 9 | 19 |
| `light.py` | 9 | 19 |
| `block.py` | 9 | 19 |
| `signal.py` | 20 | 30 |
| `memory.py` | 5 | 11 |
| `route.py` | 5 | 12 |
| `power.py` | 5 | 8 |
| `roster.py` | 5 | 7 |
| `_codes.py` | 13 | 25 |
| `_parsing.py` | 12 | 27 |
| `layout.py` | 8 | 25 |

That last two — `_parsing.py` and `layout.py` — were missed by the original audit; verified with `grep -c "logger\." module.py` returning 0.

Net: ~24 lines removed across 12 files.

### 1.2 Do NOT touch `_protocols.py`

The original draft flagged `Coroutine` as unused. **It is used** at `_protocols.py:112` (`coro: Coroutine[Any, Any, None]`). Leave the import alone.

### 1.3 Verification

```
cd python_code
uv run --no-sync ruff check .
uv run --no-sync mypy src
uv run --no-sync pytest -q
```

---

## Priority 2 — Consolidate `discover()` entity construction

**File:** `client.py:724–816`

`Client.discover()` contains eight near-identical parse-and-construct blocks, one per entity type. Every block follows:

```python
xs: list[X] = []
for envelope in t_x.result():
    parsed = parse_x(envelope)
    xs.append(X(name=parsed.name, user_name=parsed.user_name, …state fields…, _handle=self))
```

The only variations are (a) which `_handle`-aware constructor to call, and (b) which parsed-state fields to forward. Turnout/Sensor/Light/Route forward `(state,)` or nothing (Route); Block forwards `(state, value)`; SignalHead/SignalMast forward `(appearance|aspect, held, lit)`; Memory forwards `(value,)`.

### Recommended implementation

Replace the eight loops with a small registry-driven loop. The existing `_DISPATCH_PARSERS` table at `client.py:891–908` already maps `entity_type → (parser, primary_attr)` for the six WS-dispatched types; this work expands a sister table to cover all eight `discover()` types with their builder closures.

Sketch (place near `_fetch_collection`):

```python
@dataclass(frozen=True, slots=True)
class _DiscoverSpec(Generic[T]):
    parser: Callable[[dict[str, Any]], Any]
    build: Callable[[Any, ClientHandle], T]
    in_dispatch_index: bool  # False for memory, route
```

Then `discover()` walks a single `dict[str, _DiscoverSpec[Any]]` keyed by entity-type string, fetches and parses each, and appends into per-type lists. The dispatch-index rebuild loop (`client.py:823–836`) collapses to one pass over the same dict, filtering on `spec.in_dispatch_index`.

The `_handle=self` injection lives in one place — if Story 5.x needs to wrap the handle (e.g., to instrument calls), it's now a one-line change.

### Risk

Low. Internal to `discover()`. Covered by `tests/unit/test_discover.py` and the integration suite. Preserve the parallel fetch via `TaskGroup` — the consolidation is over the post-fetch loops only.

---

## Priority 3 — Consolidate `wait_state` / `wait_change`

**Files:** `sensor.py`, `turnout.py`, `light.py`, `block.py`, `signal.py` (×2 classes)

The wait-for-state pattern is byte-for-byte identical across six classes. Read `sensor.py:97–161`, `turnout.py:203–271`, `light.py:166–230`, `block.py:107–171`, `signal.py:140–204` (SignalHead), `signal.py:276–340` (SignalMast). The skeleton is:

```python
# wait_state
if self.<state_attr> == target: return self.<state_attr>
await self._handle.ensure_subscription(<entity_type>, self.name)
if self.<state_attr> == target: return self.<state_attr>
future = self._waiters.register(lambda s: s == target)
try:
    if timeout is None: return await future
    async with asyncio.timeout(timeout): return await future
except TimeoutError as e:
    raise WaitTimeout(entity_type=<entity_type>, name=self.name, target=target.name) from e
finally:
    self._waiters.remove(future)

# wait_change
await self._handle.ensure_subscription(<entity_type>, self.name)
starting = self.<state_attr>
future = self._waiters.register(lambda s: s != starting)
try:
    # same timeout/except/finally as above, but raise WaitTimeout(..., from_state=starting.name)
```

Only three things vary per entity: the `entity_type` string (`"sensor"` / `"signalHead"` / etc.), the state-attribute name (`state` for most; `appearance` for SignalHead; `aspect` for SignalMast), and the enum type. `WaiterList` is already generic on `StateT`.

### Recommended implementation

Add a private helper module `_wait_helpers.py` (sibling of `_waiters.py`) exposing two functions:

```python
async def wait_for_target(
    *,
    entity: Waitable,                      # has .name + ._waiters
    state_attr: str,                       # "state" | "appearance" | "aspect"
    entity_type: str,
    handle: ClientHandle,
    target: StateT,
    timeout: float | None,
) -> StateT: ...

async def wait_for_change(
    *,
    entity: Waitable,
    state_attr: str,
    entity_type: str,
    handle: ClientHandle,
    timeout: float | None,
) -> StateT: ...
```

Each domain class's `wait_state` and `wait_change` becomes a 3-line wrapper that supplies the per-entity strings and attribute name. The convenience wrappers (`Sensor.wait_active`, `Light.on`, `Turnout.throw`, etc.) keep their existing single-line bodies that call `wait_state`/`set_state`.

Type the `state_attr` lookup with `getattr(entity, state_attr)` and keep the predicate construction inside the helper. `WaitTimeout` and `asyncio.timeout` semantics stay byte-identical.

### Risk

Medium — this is on the hot path for user code. Preserve exact cancellation/timeout semantics. The unit suite `tests/unit/test_state_machine.py` exercises wait timeouts, cancellation cleanup, predicate retention, and early-return — keep it green and add one test per entity type that goes through the shared helper (currently `test_state_machine.py` is Turnout-heavy with Sensor convenience-wrapper checks).

---

## Priority 4 — Consolidate `set_state(..., wait_for_jmri_state=...)`

**Files:** `turnout.py:76–156`, `light.py:73–131`

These are the only two entities with a commandable state and a `wait_for_jmri_state` opt-in. The two bodies are structurally identical: validate against the outbound map, build `{"state": <int>}` payload, fire-and-forget OR pre-register-wait + shield + cleanup.

### Recommended implementation

Place `command_then_wait` next to the `wait_for_target` helper from P3 (same module). The helper accepts the outbound-code mapping, the entity, the state, and the entity-type string. It performs:

1. Mapping lookup → `ValueError` if state not commandable (helper raises with the same message format).
2. If `wait_for_jmri_state=False`: delegate to `handle.command(entity_type, name, payload)` and return.
3. Else: `ensure_subscription` → `register` waiter → `asyncio.shield(handle.command(...))` → await waiter → `BaseException` cleanup (the existing `_waiters.remove(future)` rescue).

Each domain method becomes ~5 lines:

```python
async def set_state(self, state, *, wait_for_jmri_state=False):
    from pyjmri._codes import TURNOUT_STATE_OUTBOUND
    await command_then_wait(
        entity=self, entity_type="turnout", handle=self._handle,
        state=state, outbound_map=TURNOUT_STATE_OUTBOUND,
        wait_for_jmri_state=wait_for_jmri_state,
    )
```

The `throw`/`close`/`on`/`off` convenience wrappers are unchanged.

### Risk

Low–medium. Test coverage is solid: `test_turnout.py:133–371` and `test_light.py:108–315` cover invalid-state `ValueError`, optimistic-only cache (FR22 honesty), and shield-on-cancel. Keep them passing.

---

## Priority 5 — Smaller dedupes (one PR, can ride alongside P2)

### 5.1 `httpx` exception wrapping in `_transport.py`

`HTTPClient.get` (lines 99–117) and `HTTPClient.command` (lines 189–205) repeat the same three-branch `httpx.ConnectError` / `httpx.TimeoutException` / `httpx.TransportError` → `JMRIConnectionError`/`JMRIRequestTimeout` block.

Extract:

```python
def _translate_httpx_error(self, e: httpx.HTTPError, *, path: str) -> Exception: ...
```

Returns a fully-built `JMRIError` subclass (with `from e` handled at call site). Use as:

```python
try:
    response = await self._http.get(path)
except (httpx.ConnectError, httpx.TimeoutException, httpx.TransportError) as e:
    raise self._translate_httpx_error(e, path=path) from e
```

This module is the only place in the package allowed to import `httpx` exceptions (architectural rule — see `_transport.py:3–5`), so the helper stays here.

### 5.2 `ExceptionGroup` unwrap helper in `client.py`

Two sites (not three):
- `__aexit__`: `client.py:220–237`
- `_teardown_on_aenter_failure`: `client.py:267–274`

Both filter cancellations out of a `BaseExceptionGroup` and either re-raise the lone non-cancellation exception or propagate the original group. Extract `_unwrap_exception_group(eg, *, body_exc=None)` returning `None | BaseException` (where `None` means "fully consumed, suppress"). Keep both call sites at the existing line offsets — body of helper does the filtering; call sites stay the `raise`/`return` arbiters.

Justification: small, but the two implementations are subtly different (`__aexit__` swallows when the lone non-cancellation IS the original body exc; `_teardown` doesn't have that branch because there's no body exc in flight) — keeping them in lockstep matters for the cancellation-semantics contract documented in `__aenter__:188–207`.

---

## Priority 6 — Optional `client.py` decomposition

`client.py` is 1,007 lines; after P2 it shrinks by ~70 LOC. The only seam that's genuinely clean is WS dispatch:

- `_on_ws_message` (`client.py:286–352`)
- `_dispatch_throttle_envelope` (`client.py:415–438`)
- `_dispatch_error_envelope` (`client.py:440–471`)
- `_DISPATCH_PARSERS` table (`client.py:891–908`)

These ~130 LOC touch only `self._entities`, `self._pending_throttle`, and `self._pending_throttle_error_queue`. They can move to a new `_dispatch.py` module where the methods become free functions taking the relevant state, called from a thin `Client._on_ws_message` shim. Lifecycle (`__aenter__`/`__aexit__`/`_teardown_on_aenter_failure`) stays in `client.py` because it's too entangled with `_tg`/`_http`/`_ws`/`_supervisor_task` to factor cleanly.

**Recommendation:** defer until after P2 lands. If `client.py` reads at ~900 LOC and feels right-sized then, skip P6. The user explicitly asked for a v1 cleanup, not a v1.1 redesign — churn budget is a real cost.

---

## Priority 7 — Hygiene (defer or document, do not change in code)

- **`pyproject.toml` deps** (lines 41–44): `httpx>=0.28.1`, `websockets>=16.0`, no upper bounds. Ecosystem opinion is split; for a tagged v1, capping at next major (`<1.0`, `<17.0`) buys predictability. **One-line patch in a separate PR.**
- **`Memory.get_value()` vs others' `get_state()`**: real API asymmetry, but renaming is breaking. Leave for v1.1 + record in `CONTRIBUTING.md` or `RELEASES.md`. No code change in v1.0.
- **`_force_disconnect()` test hooks** at `_transport.py:403–413` and `client.py:354–368`: keep, but consider extending the existing docstrings with a one-line "integration-test only" header for future readers (already noted in both, so this is optional).
- **`roster.py`** (`__all__ = []` placeholder for v1.1 `RosterEntry`): fine as-is.
- **`throttle_heartbeat` raises `NotImplementedError`**: documented Story 5.3 extension point. Leave.

---

## Items considered and explicitly rejected

- **Memory missing `_on_event`** — documented design decision (`memory.py:59–63`), not dead code.
- **Route missing observable post-state** — correct per FR20.
- **`power.py` / `roster.py` being tiny** — appropriate, not folding candidates.
- **`throttle.py` complexity** — 335 LOC for acquire→keepalive→release with cancellation safety; justified and well-commented.
- **`EntityCollection`** — clean abstraction with no unused methods.
- **15× `Client is not open` guard repetition** (lines 367/381/412/492/534/557/594/636/706/866) — consistent, clear, and a decorator wouldn't save real LOC because each guard is one line. Leave.

---

## Recommended PR sequence

1. **P1** (dead imports) — 1 small PR, ~24 LOC removed across 12 files.
2. **P3** (wait_state/wait_change helper) — biggest LOC win, touches 6 files, single PR with thorough tests.
3. **P4** (set_state-with-wait helper) — natural follow-on; same helper module.
4. **P2** (discover builder) — independent, mechanical.
5. **P5** (transport httpx wrap + EG unwrap) — small, can ride alongside P2 or land on its own.
6. **P6** (optional dispatch extraction) — only if `client.py` still feels heavy after P2.
7. **P7.1** (dep upper bounds) — metadata, separate patch PR.

---

## Verification (every PR)

```
cd python_code
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy src             # strict mode; refactors must hold types
uv run --no-sync pytest -q            # full suite
```

For P3 and P4 specifically:
- Run the integration tests against the simulator (`tests/integration/test_command_wait_reconnect.py`, `test_reconnect_resilience.py`) — these exercise `_force_disconnect` and prove cancellation semantics didn't drift.
- Smoke against the real layout (`192.168.1.159:12080`) — wait/state behavior is what end-users feel; type/unit tests don't catch event-loop timing regressions.

For P2: `tests/unit/test_discover.py` plus `tests/integration/test_discovery.py`.

For P6 (if pursued): re-run `tests/unit/test_client.py` and the full integration suite — moving dispatch to a new module is mechanical but easy to break.