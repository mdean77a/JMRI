---
stepsCompleted: ['step-01-init', 'step-02-context', 'step-03-starter', 'step-04-decisions', 'step-05-patterns', 'step-06-structure', 'step-07-validation', 'step-08-complete']
lastStep: 8
status: 'complete'
completedAt: '2026-05-06'
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/prd-validation-report.md'
workflowType: 'architecture'
project_name: 'JMRI'
user_name: 'Mikey'
date: '2026-05-06'
projectClassification:
  projectType: 'developer_tool'
  domain: 'general (iot / process-control flavor)'
  complexity: 'medium'
  projectContext: 'greenfield-code-brownfield-environment'
  releaseMode: 'phased'
  distribution: 'PyPI as `pyjmri`, MIT'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements (44 FRs across 8 categories):**

- *Connection & Session* (FR1–FR7): host:port with default `localhost:12080`,
  async context manager, typed connection errors, transparent
  HTTP+WebSocket coupling behind a single `Client`, automatic WebSocket
  reconnect with bounded backoff, subscription restoration that keeps
  in-flight `wait_*` calls alive across reconnect.
- *Layout Discovery* (FR8–FR12): one-shot discovery returns a typed
  `Layout`; entities indexed by both system name and user name; full
  iteration without re-discovery; typed `LayoutEntityNotFound` on miss;
  minimum entity coverage = turnouts, sensors, blocks, lights, memories,
  routes, signal heads, signal masts, roster entries.
- *Entity Read* (FR13–FR16): typed state read for every entity;
  `unknown` distinguishable from every other state; memory value read;
  power state read (read-only on supported hardware).
- *Entity Control* (FR17–FR22): set turnout/light/memory state, activate
  route by name, optimistic-by-default with opt-in
  `wait_for_jmri_state=True`; library never returns false-positive
  confirmation. Power write and internal-sensor write deliberately
  omitted from MVP.
- *Throttle* (FR23–FR28): acquire by DCC address (long/short); async
  context-manager lifecycle; speed (0..1) + direction in a single call;
  function bits F0..F28; explicit release; documented best-effort
  semantics (acquire ≠ physical presence).
- *Event Subscription & Wait Primitives* (FR29–FR33): subscribe via
  layout model with no manual bookkeeping; `wait_active`,
  `wait_inactive`, `wait_state`, `wait_change` with optional timeouts
  raising typed timeout errors; in-flight `wait_*` calls survive
  WebSocket reconnect.
- *Error Handling & Diagnostics* (FR34–FR37): `JMRIError` hierarchy with
  concrete subclasses; actionable diagnostic context on connection
  errors; structured logging at WARN/INFO/DEBUG without forcing a config;
  no exceptions for undetectable failures (open-loop NCE).
- *Distribution, Documentation & Tooling* (FR38–FR44): PyPI install via
  `uv add` or `pip`; `uv sync` for source contributors; ≤5-min
  getting-started guide; Jython→pyjmri migration table; "Limitations"
  documentation section; three shipped examples runnable against
  `Basement_Revised_2024.jmri` unmodified; `py.typed` marker so
  downstream `mypy --strict` resolves cleanly.

**Non-Functional Requirements (11 NFRs across 4 categories):**

- *Performance* (NFR1–NFR3): sensor-event propagation <100 ms median
  under steady-state; full discovery of ~370 entities <2 s on a current
  laptop against local JMRI; per-command library overhead <20 ms beyond
  JMRI's HTTP cost. Targets measured against
  `Basement_Revised_2024.jmri` with NCE simulator.
- *Reliability* (NFR4–NFR6): one-hour unattended run with no
  leaked memory / file descriptors / asyncio tasks; survive ≥5 forced
  WebSocket disconnects per hour with level-triggered semantics across
  the reconnect boundary; bounded exponential backoff (0.5 s initial,
  doubled, capped at 30 s).
- *Compatibility* (NFR7–NFR9): Python 3.11+ (rejected at install for
  older); JMRI 5.14+ documented + per-release JMRI test version
  recorded; macOS and Linux are first-class CI gates; Windows is
  best-effort with no proactive testing for v1.
- *Security & Network Posture* (NFR10–NFR11): default `localhost:12080`,
  remote requires explicit configuration; library introduces no
  authentication and documents that JMRI's web server is unauthenticated
  by design (trusted-network use).

**Scale & Complexity:**

- Complexity: medium. Code volume is modest; architectural complexity
  is concentrated in async correctness, WebSocket subscription-state
  management, command/event correlation, reconnect semantics, and
  strict-mypy public-surface design.
- Primary domain: developer-tool / Python library. No UI, no DB, no
  service runtime. External-process client of JMRI's HTTP+WebSocket
  web server.
- Estimated architectural components: ~7 distinct concerns —
  transport (HTTP + WebSocket), discovery, layout container, entity
  domain types, throttle lifecycle, exceptions, logging — surfaced
  through ~12–15 modules per the PRD's illustrative layout.

### Technical Constraints & Dependencies

- **JMRI JSON v5 web service is the sole integration surface.** No XML
  parsing, no JVM embedding. JMRI 5.14+ required. Contract drift in a
  future JMRI release surfaces as a clean typed error, not silent
  misbehavior. The "Assumed JMRI JSON Contract" subsection of the PRD
  is the authoritative blast-radius checklist.
- **NCE hardware is open-loop.** No feedback path from any commanded
  accessory or decoder back to JMRI. The library *cannot* observe
  physical-layout state and *must not* pretend to. `unknown` is the
  honest answer when JMRI itself does not know.
- **`uv` is canonical tooling.** `pyproject.toml` + `uv.lock` are the
  source of truth; `pip install` works as an alternative install path
  but `uv` is the project tool.
- **`mypy --strict` and `ruff` clean** are quality gates on every
  release. `py.typed` ships with the package.
- **Python 3.11+** unlocks `asyncio.TaskGroup`, `Self`, and modern
  exception-group semantics — all relevant for the design space.
- **No JMRI mocks.** Integration tests run against a real JMRI
  process loaded with `Basement_Revised_2024.jmri` (NCE simulator on
  the dev machine). Unit tests cover library internals that don't
  touch JMRI: response parsing, state-machine logic, reconnect/backoff
  timing.
- **HTTP and WebSocket client libraries are not pre-decided.** PRD
  flags `httpx` and `websockets` as hints but explicitly leaves
  selection to architecture.
- **Distribution:** single PyPI package `pyjmri`, MIT license.

### Cross-Cutting Concerns Identified

- **Async correctness end-to-end.** Zero blocking I/O on the event
  loop. Affects every module: parsing, logging, file ops (if any),
  exception flows. Verified by strict mypy + integration tests that
  exercise high-concurrency `asyncio.gather` paths.
- **Connection lifecycle entanglement.** `Client`, the WebSocket, the
  subscription registry, throttle leases, and in-flight `wait_*`
  futures all share lifetime. Reconnect logic must coordinate across
  all of them — restore subscriptions, re-arm waiters, keep throttle
  state coherent — without exposing the seams to user scripts.
- **Unified state modeling across entity types.** Eight entity types
  (turnout, sensor, block, light, memory, route, signal head, signal
  mast) all need: typed state with `UNKNOWN`, dual-name lookup, wait
  primitives where applicable. Commonality must be factored without
  costing mypy ergonomics on the typed subclasses.
- **Command/event correlation.** When `wait_for_jmri_state=True`, an
  HTTP command must be matched to the next state-change event from
  the WebSocket on the same entity. The mechanism must work across
  reconnect.
- **Structured logging without forced configuration** (FR36). Library
  emits at WARN/INFO/DEBUG via the standard `logging` module without
  installing handlers; users opt in to their own configuration.
- **Strict-mypy public API.** `py.typed`; no `Any` leakage on the
  user-facing surface. Cross-cutting because every module's public
  exports contribute.
- **Test harness boundary.** Tests split into unit (no JMRI) and
  integration (real JMRI). The split must be enforceable so unit
  tests can run anywhere and integration tests have a clear bootstrap.

## Starter Template Evaluation

### Primary Technology Domain

Python library (developer-tool / SDK) distributed as a PyPI package.
No frontend, no service runtime, no CLI in MVP.

### Foundational Decisions Pre-Locked by the PRD

The following are locked by the PRD before this workflow began and
are therefore not re-deliberated here:

- Language: Python 3.11+ (NFR7)
- Project tool: `uv` (FR38, FR39, Technical Success)
- Build backend / packaging: `pyproject.toml` + `uv.lock`
- Type checker: `mypy --strict` with `py.typed` shipped
  (Technical Success, FR44)
- Linter: `ruff` (Technical Success)
- Test framework: `pytest` (Technical Success)
- License: MIT (Business Success)
- Distribution: single PyPI package `pyjmri` (FR38)
- Public API shape: flat per-entity modules under the package
  root (Developer Tool Specific Requirements §"Public API Surface")

Open questions that the *starter* does NOT settle (handled in
step 4):

- HTTP client library
- WebSocket client library
- Internal layering between transport, parsing, and domain model
- Reconnect / subscription-restoration mechanism
- Command-event correlation mechanism
- Integration-test bootstrap

### Project Directory

The library lives in the existing empty `python_code/` directory
at the JMRI repository root. That directory stays named
`python_code` for repository-layout reasons; the PyPI distribution
name, the importable package name, and the package directory under
`src/` are all `pyjmri`.

### Starter Options Considered

| Option | Outcome |
|---|---|
| `uv init --lib --name pyjmri` (Astral first-party) | **Selected** |
| `uv init` (default application mode) | Rejected — defaults to flat app layout, no `py.typed`, would require manual rework after init |
| `uv init --package` | Rejected — flat library layout; loses the `src/` isolation benefit for tests |
| `jlevy/simple-modern-uv` Copier template | Rejected — opinionated bundling adds audit burden vs. very small DIY config delta |
| `cookiecutter-pypackage` / `hatch new` | Rejected — predates `uv` as canonical tooling, conflicts with PRD lock-in |
| Roll your own from scratch | Rejected — `uv init --lib` produces ~95% of the same scaffold and is the Astral-recommended path |

### Selected Starter: `uv init --lib --name pyjmri`

**Rationale for Selection:**

The PRD nominated `uv` as canonical project tooling (FR38, FR39).
`uv init --lib` is Astral's first-party library scaffold and the
2026 golden path for new PyPI libraries. It produces the
recommended `src/` layout, configures `uv_build` as the build
backend, ships a `py.typed` marker (directly satisfying FR44),
and adds nothing the project would have to remove. It is thin
enough to audit in a single read, which avoids the trap of
inheriting a heavier template's incidental opinions. The
`--name pyjmri` flag decouples the on-disk directory name
(`python_code`) from the package / distribution name (`pyjmri`).

**Initialization Command:**

```bash
cd python_code
uv init --lib --name pyjmri
```

**Architectural Decisions Provided by Starter:**

**Language & Runtime:**

- Python 3.11+ pinned via `.python-version` and `pyproject.toml`
  `requires-python` (matches NFR7)
- `uv`-managed virtual environment, locked via `uv.lock`

**Project Layout:**

- `python_code/pyproject.toml` — `name = "pyjmri"`, single source
  of truth for metadata, deps, and tool configs
- `python_code/src/pyjmri/__init__.py` — public re-exports
- `python_code/src/pyjmri/py.typed` — FR44 marker, shipped in
  the wheel
- `python_code/tests/` — created at scaffold time; will be split
  further into `tests/unit/` and `tests/integration/`

**Build & Packaging:**

- `uv_build` build backend
- `pyproject.toml` `[project]` and `[build-system]` tables
  pre-populated for PyPI distribution

**Development Experience:**

- `uv sync` for environment setup (creates `.venv/` and
  `uv.lock`)
- `uv add` / `uv add --dev` for dependency management
- `uv run` for invoking commands inside the project environment

### Project-Specific Configuration to Layer On

The following are not provided by `uv init --lib` and will be
configured as part of the project-init story:

- **Ruff** rule set in `[tool.ruff]` (E, W, F, I, B, UP, ASYNC,
  RUF at minimum) and formatter config
- **Mypy** strict config in `[tool.mypy]` (`strict = true`, no
  implicit `Any` on the public surface)
- **Pytest** config in `[tool.pytest.ini_options]` plus
  `pytest-asyncio` as a dev dependency (`asyncio_mode = "auto"`)
- **Tests directory split**: `tests/unit/` and `tests/integration/`
  to enforce the unit-vs-integration test-harness boundary
  identified in step 2's cross-cutting concerns
- **GitHub Actions CI** matrix workflow: macOS-latest +
  ubuntu-latest × Python 3.11 / 3.12 / 3.13, running `ruff check`,
  `mypy`, and `pytest tests/unit/` on every push (NFR9 — Windows
  excluded from CI per NFR9)
- **MIT LICENSE** file at `python_code/LICENSE` so the PyPI
  distribution is self-contained (Business Success). The
  surrounding JMRI repository has its own license posture; the
  pyjmri license is scoped to `python_code/`.
- **README.md** seeded with the 5-minute getting-started outline
  (FR40)

**Note:** Project initialization using this command should be the
first implementation story.

**Tool versions are not pinned in this document.** `uv.lock` is the
source of truth for dev-tool versions (`ruff`, `mypy`, `pytest`,
`pytest-asyncio`, etc.). Stories that need a specific tool feature
should reference the feature, not a version range, and let `uv`
resolve the lockfile.

## Core Architectural Decisions

### Architectural Invariant: Layout-Agnosticism

The library carries zero knowledge of any specific JMRI layout. It
connects to a running JMRI, queries what JMRI has loaded, and exposes
whatever entities exist as a typed runtime model. This invariant
applies at every layer:

- **Library code:** no hardcoded entity names, system-name prefixes
  (`NT*`, `IS*`, etc.), DCC addresses, or layout-shape assumptions
  anywhere in the package.
- **Discovery:** works against whatever JMRI returns. Empty collections
  are normal. A layout with three sensors works the same as one with
  three hundred.
- **Tests at both levels:** unit tests use synthetic JSON fixtures;
  integration tests query JMRI for available entities and operate on
  whatever's there ("pick the first turnout, command it, observe the
  state change"). Integration tests skip gracefully when the running
  layout has none of the required entity types.
- **Shipped examples:** may have defaults tuned for the author's basement
  layout for zero-friction first-run, but accept entity names and DCC
  addresses as arguments or environment variables so they run against
  any layout that supplies the corresponding values. FR43's "unmodified
  against `Basement_Revised_2024.jmri`" means "no code changes needed
  when that panel is loaded," not "code is basement-shaped."

The basement layout is the author's test environment, not a target. If
a JMRI server is running at `localhost:12080` with any panel file
loaded, discovery and the library's primitives must work.

### Decision Priority Analysis

**Critical Decisions (block implementation):**

- Transport libraries (HTTP, WebSocket)
- Subscription registry & event-fanout shape
- Reconnect & restoration mechanism
- Command/event correlation pattern
- Concurrency model (TaskGroup ownership)
- Layout container & dual-name lookup
- Domain state-modeling approach
- Exception hierarchy

**Important Decisions (shape the architecture):**

- Internal layering (public/private split)
- Discovery strategy (parallel vs. sequential, partial-failure handling)
- Logging strategy
- Client configuration shape
- Test harness boundary (unit/integration split)

**Deferred Decisions (Growth or post-MVP):**

- Throttle keep-alive interval and refresh strategy beyond v1's basic
  loop (to be tuned against the simulator)
- Headless-JMRI CI for integration tests (treated as a Growth-phase
  spike; unit tests cover CI in v1)
- Higher-level patterns library (`automaton.py`) beyond v1 stubs
- CLI utilities (`pyjmri-status`, etc.) — Growth-deferred per PRD
- Operations / Warrants / LogixNG / Dispatcher integration — Vision-
  deferred per PRD

### Transport Layer

| Concern | Decision | Rationale |
|---|---|---|
| HTTP client | `httpx` (async client only) | Modern, mypy-strict friendly, used by major Python SDKs (OpenAI, Anthropic, FastAPI TestClient); JMRI is HTTP/1.1 so HTTP/2 is irrelevant; performance ceiling is irrelevant for human-paced layout commands |
| WebSocket client | `websockets` (>= 16.0) | Purpose-built for WS, asyncio-first; built-in auto-reconnect via `connect()` async iterator (NFR5). Backoff timing is the library's built-in (NFR6); `process_exception(exc) -> Exception \| None` controls retryable-vs-fatal only (not delays). |
| Rejected: `aiohttp` for both | n/a | WS is secondary in aiohttp; reconnect is roll-your-own; no win over the split design |
| Rejected: `httpx-ws` | n/a | Still in beta on PyPI; one-hour-unattended NFR4 makes beta a risk |

### Domain State Modeling

- **Per-entity `enum.Enum`** classes (e.g.,
  `TurnoutState.{UNKNOWN, CLOSED, THROWN, INCONSISTENT}`), opaque
  values, JMRI integer codes kept private.
- **No shared base class** for state enums — mypy's generic-enum
  support is limited; per-entity types give cleaner method
  signatures.
- **`UNKNOWN`** is a member of every state enum. PRD requires it as a
  first-class state across all entity types.
- **Translation layer** lives in `_codes.py` (private module): JMRI
  integer code ↔ Enum member tables, one per entity type.
- **Rejected:** `IntEnum` (couples public API to wire format; tempts
  users to bypass the enum); `StrEnum` with name strings (loses
  bidirectional mapping; JMRI uses ints in many responses).

### Layout Container & Dual-Name Lookup

- `Layout` exposes per-entity-type collections (`layout.turnouts`,
  `layout.sensors`, ...) of type `EntityCollection[T]`.
- `EntityCollection[T]` implements `Mapping[str, T]`:
  - `__getitem__(key)` tries user name first, then falls back to
    system name. Raises `LayoutEntityNotFound` if neither matches.
  - `by_user_name(name)` and `by_system_name(name)` for explicit
    disambiguation.
  - `__iter__` yields system names. `.values()` and `.keys()` work as
    standard `Mapping`. `len()` and `in` work as expected.
- **Collision rule:** if a string is both a user name on entity X and
  a system name on entity Y, user name wins. Documented in the API
  reference as a known quirk.
- Rationale: matches PRD Journey 1 (`layout.sensors["Block 1"]`, a
  user name) and Journey 3 (`layout.turnouts["NT400"]`, a system
  name) without forcing users to learn which is which.

### Exception Hierarchy

```text
JMRIError                           (base; carries diagnostic context dict)
├── JMRIConnectionError             (cannot reach JMRI; carries host, port, cause)
│   └── JMRIReconnectFailed         (WS reconnect gave up — bounded retry exhausted)
├── JMRIRequestTimeout              (HTTP request exceeded request_timeout)
├── JMRIProtocolError               (unexpected response shape — contract drift)
│   └── JMRIVersionUnsupported      (JMRI < 5.14 detected at handshake)
├── LayoutEntityNotFound            (name not in either index)
├── LayoutEntityNotControllable     (set_state on a read-only entity, e.g., signalMast)
├── ThrottleError                   (throttle base)
│   ├── ThrottleAcquireFailed       (JMRI rejected the acquire)
│   └── ThrottleReleased            (method called after .release())
└── WaitTimeout(JMRIError, TimeoutError)
                                    (await wait_* exceeded timeout;
                                     also catchable as builtin TimeoutError)
```

- `JMRIError` carries `context: dict[str, Any]` for diagnostic fields;
  subclasses populate relevant keys.
- `JMRIConnectionError.__str__` formats actionable text per FR35
  (e.g., "could not connect to localhost:12080 — is JMRI running with
  the web server enabled?").
- The library never raises `JMRIError` itself — only concrete
  subclasses; the base exists for `except JMRIError:` catch-all.
- **Not raised** (per FR37): no `LocomotiveAbsent`, no
  `TurnoutPhysicallyJammed`, no `CommandRejected` for the layout —
  these are undetectable on open-loop NCE.

### Subscription Registry & Event Fanout

- **`SubscriptionRegistry`** holds the authoritative
  `set[(EntityType, str)]` describing what subscriptions should
  exist, decoupled from any particular WS connection's state.
  `registry.ensure(t, n)` is idempotent — adds to the set and sends a
  WS subscribe iff not already subscribed.
- **Per-entity waiter list:** each entity holds `_state` (cached
  current state) and `_waiters: list[(predicate, asyncio.Future)]`.
  The WS receive loop calls `entity._on_event(new_state)`, which:
  1. Updates `_state`.
  2. Synchronously fans out: for each `(predicate, future)` pair, if
     `predicate(new_state)` and the future is not done, set the
     result; keep the rest.
  3. Single event loop = no lock needed.
- **`wait_*` early-return:** if `_state` already matches the
  predicate when `wait_state` is called, return immediately without
  registering a future.
- **Rejected:** `asyncio.Condition` per entity (more machinery for no
  win in single-loop code); single broadcast queue per entity-type
  (overkill, complicates predicates); per-`(entity, target_state)`
  Event (combinatorial, doesn't handle `wait_change()`).

### Reconnect & Restoration Mechanism

- **The library does not write its own reconnect loop.** It consumes
  `websockets.connect()` as an async iterator (which performs
  auto-reconnect) and hooks `on_connect` and `on_message` callbacks.
- **On each reconnect:**
  1. `websockets.connect()` yields a fresh connection.
  2. `SubscriptionRegistry.replay()` fires — re-sends every
     `(type, name)` subscribe.
  3. JMRI replies to each subscribe with current state.
  4. Each reply flows through the normal `on_message` path →
     `entity._on_event(new_state)`.
  5. In-flight `wait_*` futures see the post-reconnect state. If the
     predicate matches, the future resolves (level-triggered
     semantics per NFR5).
- **No event replay attempted.** Events that fired during the
  disconnect window are not delivered as discrete events; they
  surface only as "current state on resubscribe."
- **Backoff policy:** delegated to `websockets`' built-in `backoff()`
  generator (random initial 0–5 s, then 3.1 s growing by factor 1.618,
  capped at 90 s). This satisfies NFR6's "bounded exponential backoff
  with sensible defaults" — the library's defaults are the sensible
  defaults. The library does not expose a per-`connect()` parameter
  for delay tuning; only env vars (`WEBSOCKETS_BACKOFF_INITIAL_DELAY`,
  etc.) can override globally. v1 ships with library defaults and
  exposes no delay-tuning knob on `ReconnectConfig` — the `process_exception`
  hook returns `Exception | None` (retryable vs fatal), not a delay
  value. *(Spec revision 2026-05-12: the original architecture text
  showed a `process_exception` hook returning the next delay as a
  float. That misread the websockets v16 API; corrected during Story
  3.1 dev.)*
- **Give-up:** retry forever by default. Optional
  `max_attempts: int | None = None` config; the `process_exception`
  hook counts consecutive failures and returns a fatal exception
  once `attempt >= max_attempts`, breaking the async-iterator loop.
  `WSConnection.run` re-raises as `JMRIReconnectFailed`.
- **Heartbeat:** JMRI's `hello` envelope advertises a 13.5 s heartbeat.
  pyjmri sets `websockets.connect(..., ping_interval=10)` so the WS
  protocol's ping/pong satisfies JMRI's "any inbound traffic" check
  without a JMRI-specific heartbeat envelope.

### Command / Event Correlation

For `wait_for_jmri_state=True`, use the **pre-register-wait, then
send command** pattern:

```python
async def throw(self, *, wait_for_jmri_state: bool = False) -> None:
    if not wait_for_jmri_state:
        await self._client._http_command("turnout", self.name, "thrown")
        return

    self._client._registry.ensure(EntityType.TURNOUT, self.name)
    wait_task = asyncio.create_task(self.wait_state(TurnoutState.THROWN))
    try:
        await self._client._http_command("turnout", self.name, "thrown")
        await wait_task
    except BaseException:
        wait_task.cancel()
        raise
```

The wait future is registered before the HTTP command goes out so a
fast post-ack state event cannot race ahead of the waiter. Reconnect
during a `wait_for_jmri_state=True` operation preserves the wait
(it's a future on the entity, not on the WS connection); the
subscription replay surfaces current state, and if the predicate
matches, the future resolves.

**Rejected:** "send command, then check state, then wait if needed"
(racy); server-sequence-number correlation (JMRI's JSON v5 doesn't
expose what we'd need).

### Concurrency Model

- **One Client-level `asyncio.TaskGroup`** (Python 3.11+ structured
  concurrency) supervises every long-running coroutine the library
  owns.
- **Supervised tasks (v1):**
  - The WS reconnect-and-receive loop (always).
  - Per-throttle keep-alive coroutine, one per active `Throttle`,
    spawned in `Throttle.__aenter__` and cancelled in `__aexit__`.
    Whether keep-alive is needed is a TBD verified against the
    simulator early in implementation; the architecture supports
    the task whether v1 ships an active loop or a no-op stub.
- **Hard rule:** the library never uses bare `asyncio.create_task`
  outside the supervising TaskGroup. Reconnect bugs leak tasks; the
  TaskGroup boundary makes leaks immediately visible.
- **`wait_*` waiters are futures, not tasks** — no supervision needed
  for them.
- **User-level concurrency** (`asyncio.gather`, user TaskGroups) is
  the user's call; the library doesn't dictate.
- **Open verification item:** confirm whether JMRI's JSON v5 throttle
  endpoint requires keep-alive without testing it. NFR4's one-hour
  unattended-stability run is the authoritative signal.

### Discovery Strategy

- **Parallel via `asyncio.TaskGroup`:** all per-type discovery
  requests fire concurrently; total time ≈ slowest single fetch.
  NFR2 (<2 s for ~370 entities) easily met with headroom.
- **Fail-fast on per-type errors.** If one entity-type endpoint
  raises, TaskGroup cancels siblings and propagates. Surfaces as
  `JMRIConnectionError` or `JMRIProtocolError`. Prefer fast failure
  to a partially-populated `Layout`.
- **Empty collections are normal, not errors.** "Layout has no signal
  masts" returns `[]`; becomes `EntityCollection` with
  `len() == 0`. Only non-200 or schema-broken responses raise.

### Internal Layering

```text
src/pyjmri/
├── __init__.py          # public re-exports
├── client.py            # Client                                   ┐
├── layout.py            # Layout, EntityCollection                 │
├── turnout.py           # Turnout, TurnoutState                    │
├── sensor.py            # Sensor, SensorState                      │
├── block.py             # Block, BlockState                        │
├── light.py             # Light, LightState                        │ public
├── memory.py            # Memory                                   │
├── route.py             # Route                                    │
├── signal.py            # SignalHead, SignalMast, aspect enums     │
├── throttle.py          # Throttle                                 │
├── roster.py            # Roster, RosterEntry                      │
├── power.py             # PowerState (read-only)                   │
├── exceptions.py        # JMRIError tree                           │
├── automaton.py         # patterns library (v1 stub)               ┘
├── _transport.py        # HTTPClient + WSConnection                ┐
├── _parsing.py          # JSON → typed-value functions             │ private
├── _subscriptions.py    # SubscriptionRegistry                     │
├── _codes.py            # JMRI integer-code ↔ enum tables          ┘
└── py.typed
```

**Layering rules:**

- Public modules import from private; private modules do not import
  public domain types. A `Protocol` defines the slim Client surface
  that domain entities depend on; that Protocol lives in
  `_subscriptions.py` or a dedicated `_protocols.py`. Avoids cycles.
- Domain entities (Turnout, Sensor, ...) hold a `Protocol`-typed
  handle to the Client for issuing commands. They don't import
  `_transport` directly. Unit-testing entities does not require
  standing up real transport.
- `_parsing` is a functional module —
  `parse_turnout(json: dict) -> Turnout`, no parser classes. Pure
  functions; easy to unit-test.
- `_codes` is data-only: lookup tables for the integer-code ↔ Enum
  translation referenced by Domain State Modeling above.
- `__all__` discipline in every public module keeps the user-visible
  surface explicit and small.

### Logging Strategy

- **stdlib `logging`**. Hierarchical loggers; library installs
  `NullHandler` on the `pyjmri` root at import time so unconfigured
  users get silence.
- **Logger hierarchy:**
  - `pyjmri.transport` — HTTP + WS request/response (DEBUG: per-message)
  - `pyjmri.subscription` — registry add/remove, replay (INFO: lifecycle, DEBUG: per-entity)
  - `pyjmri.reconnect` — backoff attempts, give-up (WARN: each disconnect, INFO: reconnected)
  - `pyjmri.throttle` — acquire / release / keep-alive (INFO: lifecycle)
- **Level guidance:**
  - WARN — transient failures the library is handling internally.
  - INFO — lifecycle events the user might want at default verbosity.
  - DEBUG — per-message detail.
- **Structured context** via `extra={...}` on every log call:
  relevant identifiers (`entity_type`, `system_name`, `host`,
  `attempt`). Users plugging in JSON formatters or `structlog` get
  usable structured output without library changes.

### Client Configuration Shape

```python
class Client:
    def __init__(
        self,
        url: str = "localhost:12080",
        *,
        config: ClientConfig | None = None,
    ) -> None: ...

@dataclass(frozen=True, kw_only=True)
class ReconnectConfig:
    max_attempts: int | None = None  # None = retry forever; backoff timing
                                     # is delegated to websockets' built-in
                                     # backoff() (NFR6).

@dataclass(frozen=True, kw_only=True)
class ClientConfig:
    request_timeout: float = 10.0
    reconnect: ReconnectConfig = field(default_factory=ReconnectConfig)
    subscription_replay_timeout: float = 30.0
```

- `url` accepts `"host:port"`, `"http://host:port"`, or
  `"ws://host:port/json"`. Missing scheme defaults to plain HTTP/WS.
- `config` is optional; defaults satisfy NFR6.
- Both config dataclasses are frozen and kw-only — immutable after
  construction; mypy-strict friendly.
- Satisfies all four PRD-shown call patterns: `Client()`,
  `Client("localhost:12080")`, `Client(host_port_string)`, and
  `Client(url, config=ClientConfig(...))`.

### Test Harness

```text
tests/
├── unit/                     # no JMRI required; runs in CI
│   ├── test_parsing.py
│   ├── test_subscription_registry.py
│   ├── test_reconnect_backoff.py
│   ├── test_state_machine.py
│   ├── test_codes.py
│   └── ...
└── integration/              # requires real JMRI on localhost:12080
    ├── conftest.py           # session fixture probes JMRI; skips on absence
    ├── test_discovery.py
    ├── test_command_round_trip.py
    ├── test_reconnect_resilience.py
    └── ...
```

- **`pytest.mark.integration`** marker on integration tests; pytest
  config sets `asyncio_mode = "auto"`.
- **Bootstrap:** developer launches JMRI separately with whatever
  panel file they prefer. Integration tests do not manage the JMRI
  process.
- **Layout-agnostic by construction.** Integration tests query JMRI
  for available entities and operate on whatever's there ("pick the
  first turnout, command it, observe the state change"). Tests that
  require a specific entity type skip when the running layout has
  none of that type.
- **Skip-on-absence fixture** probes JMRI at session start; if
  unreachable, skips all integration tests with a clear message.
- **CI gate (NFR9):**
  - **Unit tests** run in CI matrix: macOS-latest + ubuntu-latest ×
    Python 3.11 / 3.12 / 3.13. Every push.
  - **Integration tests** run **locally only** for v1.
    Headless-JMRI CI is a Growth-phase spike, not in scope here.
- **One-hour unattended stability run** (NFR4) is its own pytest
  target, invoked manually before each release.

### Decision Impact Analysis

**Implementation sequence (highest-leverage first):**

1. Project init via `uv init --lib --name pyjmri` (the Step 3 starter
   command), plus the project-specific configuration layered on top
   (ruff, mypy strict, pytest + pytest-asyncio, tests directory
   split, GH Actions CI, MIT LICENSE, README scaffold).
2. `_transport.HTTPClient` (httpx async wrapper) + first round-trip
   smoke test against JMRI.
3. `_codes` integer-code ↔ enum tables + `_parsing` per-type parsers
   + matching unit tests.
4. `_transport.WSConnection` consuming `websockets.connect()`
   iterator + `SubscriptionRegistry`.
5. Domain entities (turnout, sensor first) with the waiter-list
   pattern + `EntityCollection` lookup behavior.
6. Discovery + `Layout` assembly + first end-to-end integration
   test ("connect, discover, print first 5 turnouts" —
   `hello_jmri.py` shape).
7. `Throttle` lifecycle (acquire / release / set_speed /
   set_function) plus the keep-alive task structure (initially as a
   stub, then activated once the simulator answer is known).
8. Reconnect resilience integration test (forced disconnect mid-run).
9. Remaining entity types (block, light, memory, route, signals,
   roster).
10. The three shipped examples and the README quickstart (FR40,
    FR43).

**Cross-component dependencies:**

- The `Protocol`-typed Client handle (Internal Layering) is what
  makes domain entities testable in unit tests without standing up
  real transport — depends only on a stable shape, not on `httpx`
  or `websockets`.
- `_codes` (Domain State Modeling) is consumed by `_parsing`
  (Internal Layering) and by `entity._on_event` (Subscription
  Registry); changes to JMRI integer codes ripple to all three
  sites — the contract is small and centralized.
- `SubscriptionRegistry.replay` (Reconnect) and `Layout` discovery
  (Discovery Strategy) are independent — replay restores
  subscriptions, discovery enumerates the model. Both run on top of
  the same `HTTPClient` + `WSConnection`.
- `JMRIReconnectFailed` (Exception Hierarchy) is the terminal output
  of the Reconnect mechanism's `max_attempts` config knob.
- The TaskGroup ownership model (Concurrency Model) is the one place
  where the WS receive loop, the keep-alive coroutines, and the
  Client lifecycle all meet — `Client.__aexit__` cleanly cancels the
  TaskGroup, which in turn cancels every supervised coroutine, which
  in turn cancels in-flight waiters with `CancelledError`. That is
  the entire shutdown path.

## Implementation Patterns & Consistency Rules

These rules govern decisions that `ruff` + `mypy --strict` do not
already enforce. They exist to prevent diverging choices when multiple
AI agents (or contributors) work on the codebase.

### Type Annotation Conventions

- **`from __future__ import annotations`** at the top of every module
  in `src/pyjmri/`. Forward references work without quoting; lazy
  evaluation; smaller runtime annotation cost.
- **PEP 604 union syntax** everywhere: `X | None`, `X | Y`. Never
  `Optional[X]`, never `Union[X, Y]`.
- **`Self`** (from `typing`, Python 3.11+) for chaining and factory
  methods that return the same class.
- **No `Any` in the public surface.** If a value's shape is genuinely
  unknown, use `object` and narrow at the boundary. `Any` is
  permitted in `_parsing.py` *only* for the JSON dict input parameter
  before parsing — output of every parser is a typed value.
- **Generic type variables:** `T` (invariant), `T_co` (covariant for
  read-only collection types). One TypeVar declaration per module
  near the top.
- **Public type aliases** declared with `TypeAlias` when reused:
  `EntityName: TypeAlias = str` for documentation-driven aliases.

### Async Patterns

- **Library-owned long-running tasks live in the Client's
  `TaskGroup`**, never in a bare `asyncio.create_task` outside a
  `TaskGroup`. Single exception: a method-local `create_task` used
  within a try/finally that guarantees cancellation (the
  pre-register-wait pattern in Command/Event Correlation is the
  canonical example).
- **Timeouts use `asyncio.timeout(...)` context manager**, not
  `asyncio.wait_for(...)`. The block form is more readable and
  handles cancellation more cleanly in 3.11+.
- **Cancellation discipline:** `except asyncio.CancelledError:` is
  used only for cleanup followed by `raise`. Never swallow
  cancellation. A bare `except BaseException:` is forbidden outside
  cleanup blocks that re-raise.
- **No blocking I/O inside `async def`**. No `time.sleep`, no sync
  HTTP, no sync file ops. Where unavoidable (rare), use
  `asyncio.to_thread` and document why.
- **Public I/O methods are always `async def`.** No sync wrappers.
  Users wanting sync invoke `asyncio.run(...)` themselves.

### Error Handling Discipline

- **Library-detected errors raise concrete `JMRIError` subclasses.**
  The base class is never raised directly — it exists only for
  catch-all `except JMRIError` blocks.
- **Wrap third-party exceptions at the transport boundary.**
  `_transport.py` is the only module allowed to catch `httpx.*`
  and `websockets.*` exception types. It re-raises as `JMRIError`
  subclasses with `from e`:

  ```python
  try:
      response = await self._http.get(url)
  except httpx.ConnectError as e:
      raise JMRIConnectionError(host=self._host, port=self._port) from e
  ```
- **Never catch and swallow.** Every `except` either re-raises (with
  `from e` if a new exception is raised) or completes a documented
  cleanup path.
- **Diagnostic context** populated on every raised `JMRIError`
  subclass: `host`, `port`, `entity_name`, `attempt`, etc., as
  applicable. The `__str__` method formats actionable text per FR35.
- **Catch-name convention:** `except JMRIError as e:` — always name
  the variable `e`, never `err`, `ex`, or `exception`.
- **`WaitTimeout` multi-inherits `TimeoutError`** so users can catch
  either; the library raises only `WaitTimeout`, never bare
  `TimeoutError` or `asyncio.TimeoutError`.

### Logging Discipline

- **Module-level logger** at the top of every module:

  ```python
  logger = logging.getLogger(__name__)
  ```
  This yields `pyjmri.transport`, `pyjmri.subscription`, etc.,
  matching the Logging Strategy hierarchy from Core Architectural
  Decisions.
- **Always pass structured context via `extra=`**:

  ```python
  logger.warning(
      "WebSocket disconnected — backing off",
      extra={"host": self._host, "attempt": self._attempt},
  )
  ```
- **No f-strings inside log calls** for variable interpolation —
  pass the message template and use `%`-style formatting OR put
  the values in `extra=`. Reason: lazy evaluation when the log
  level is disabled, and structured-formatter compatibility.
- **No `print()`, no `sys.stderr.write()`** anywhere in the library.
- **Level-to-event mapping** matches the table in Core
  Architectural Decisions; agents use that as the authoritative
  guide.

### Public API Discipline

- **Every public module declares `__all__`** at the top, listing only
  the exports intended for users. Anything not in `__all__` is
  considered internal even if not underscore-prefixed.
- **`pyjmri/__init__.py` re-exports** the user-facing surface:
  `Client`, `Layout`, all entity classes, all state enums, all
  exceptions, all configs. Users should `from pyjmri import Client,
  Turnout, TurnoutState`, not reach into submodules.
- **Examples and documentation use the `pyjmri` top-level only.**
  Never `from pyjmri.turnout import Turnout` in a user-facing
  example — the deeper path is an implementation detail.
- **Private modules (`_*.py`) are import-internal only.** They never
  appear in user code, examples, or documentation.

### JSON ↔ Python Translation

- **Translation happens at the parse boundary** in `_parsing.py`.
  No public-API method ever returns a raw JSON dict. No domain
  entity field ever holds a JSON dict.
- **JMRI uses camelCase JSON (`userName`, `systemName`); Python
  uses snake_case (`user_name`, `system_name`).** Translation is
  one-way at parse time; if a value needs to round-trip back to
  JMRI, the encoder applies the inverse mapping.
- **Unknown JSON fields are ignored**, not error-raising. JMRI may
  add fields in newer versions; the parser accepts them silently
  and surfaces only fields the library models. A *missing* expected
  field is a `JMRIProtocolError`.
- **Integer state codes never cross the public API.** They are
  translated to typed Enum members in `_parsing.py` using tables
  from `_codes.py`.

### Testing Patterns

- **File naming:** `test_<module>.py` for unit tests mirrors
  `_<module>.py` or `<module>.py` source. E.g.,
  `tests/unit/test_parsing.py` covers `src/pyjmri/_parsing.py`.
  Integration tests use functional names: `test_discovery.py`,
  `test_reconnect_resilience.py`.
- **Function naming:** `test_<scenario_described_in_snake_case>`.
  E.g., `test_turnout_state_unknown_does_not_coerce_to_closed`.
  Length is fine; clarity beats brevity for test names.
- **Async tests:** `async def test_*`. Pytest config sets
  `asyncio_mode = "auto"`, so the `@pytest.mark.asyncio` decorator
  is not needed.
- **Marker discipline:** every integration test carries
  `@pytest.mark.integration`. Unit tests carry no marker. CI uses
  the marker to filter; `pytest -m "not integration"` runs unit
  tests only.
- **Fixtures live in `conftest.py`** at the appropriate scope
  (module, package, or session). Synthetic JSON fixtures for
  parsing tests live in `tests/unit/fixtures/` as `.json` files,
  loaded via a conftest helper.
- **No mocks of JMRI.** Per PRD policy. Unit tests cover
  internals (parsing, state-machine logic, reconnect timing) that
  do not touch JMRI; integration tests use the real thing.

### Documentation Patterns

- **Public docstrings are mandatory.** Every public class, public
  method, and public function has a docstring. They are the API
  contract.
- **Docstring style: Google-style** (Args, Returns, Raises). Ruff's
  `D` rules enforce shape; tone is "what + when to use it,"
  not "how it works."
- **Internal code: comments only when the WHY is non-obvious.**
  No comments restating what the code says. Docstrings on
  underscore-prefixed helpers only when the function is non-trivial
  *and* its name doesn't capture the intent.
- **README-first documentation.** The 5-minute getting-started
  (FR40) is the front door. API reference is generated from
  docstrings (Sphinx or MkDocs — Growth-deferred per PRD).
- **"Limitations" section is mandatory README content** (FR42),
  not buried elsewhere.

### Enforcement

**All AI agents working on this codebase MUST:**

- Run `ruff format`, `ruff check`, and `mypy --strict` before
  treating any change as complete. CI is the backstop, not the
  primary gate — local-clean before push.
- Prefer the patterns above over rediscovering them. When a pattern
  feels wrong for a specific case, document the deviation in the PR
  description and propose updating the pattern document — don't
  silently diverge.
- Never reach into a private module from outside its package or
  add a public re-export without updating the relevant `__all__`.
- Treat `JMRIError` discipline as a hard rule: the library never
  leaks `httpx`, `websockets`, or other library exception types
  past `_transport.py`.

**Pattern updates** are themselves PRs that update this document
and any affected code in one change. The architecture document is
the source of truth; CLAUDE.md and `python_code/README.md` link to
it rather than duplicating rules.

## Project Structure & Boundaries

### Complete Project Directory Structure

```text
# Note: .github/workflows/ci.yml lives at the JMRI repository root,
# NOT under python_code/. GitHub Actions only reads .github/ from the
# repository root, so workflow files must be there. The pyjmri-specific
# CI workflow path-scopes itself to python_code/** to avoid running on
# panel-XML / roster / Jython commits. The tree below shows only the
# pyjmri project directory.

python_code/                              # repo-root for pyjmri (named per Step 3)
├── .gitignore                            # uv init default + project additions
├── .python-version                       # Python 3.11 (or later) pin
├── LICENSE                               # MIT (Business Success)
├── README.md                             # 5-min getting-started + Limitations + migration table
├── CONTRIBUTING.md                       # integration-tests-local-only policy, dev setup
├── pyproject.toml                        # project metadata + ruff/mypy/pytest configs
├── uv.lock                               # generated by `uv sync`
├── src/
│   └── pyjmri/
│       ├── __init__.py                   # public re-exports + __all__
│       ├── client.py                     # Client (FR1–FR7)
│       ├── layout.py                     # Layout, EntityCollection (FR8–FR12)
│       ├── turnout.py                    # Turnout, TurnoutState
│       ├── sensor.py                     # Sensor, SensorState
│       ├── block.py                      # Block, BlockState
│       ├── light.py                      # Light, LightState
│       ├── memory.py                     # Memory
│       ├── route.py                      # Route
│       ├── signal.py                     # SignalHead, SignalMast, aspect enums
│       ├── throttle.py                   # Throttle (FR23–FR28)
│       ├── roster.py                     # Roster, RosterEntry
│       ├── power.py                      # PowerState read (FR16)
│       ├── exceptions.py                 # JMRIError hierarchy (FR34–FR35)
│       ├── automaton.py                  # higher-level patterns (v1 stub; Growth)
│       ├── _transport.py                 # HTTPClient, WSConnection (httpx + websockets)
│       ├── _parsing.py                   # JSON → typed value functions
│       ├── _subscriptions.py             # SubscriptionRegistry
│       ├── _codes.py                     # JMRI integer code ↔ Enum tables
│       ├── _protocols.py                 # internal Protocol typing for Client handle
│       └── py.typed                      # FR44 marker (shipped in wheel)
├── tests/
│   ├── unit/
│   │   ├── conftest.py                   # synthetic JSON fixture loader
│   │   ├── fixtures/
│   │   │   ├── turnouts.json
│   │   │   ├── sensors.json
│   │   │   ├── blocks.json
│   │   │   ├── lights.json
│   │   │   ├── memories.json
│   │   │   ├── routes.json
│   │   │   ├── signal_heads.json
│   │   │   ├── signal_masts.json
│   │   │   └── roster.json
│   │   ├── test_parsing.py               # _parsing.py per-entity parsers
│   │   ├── test_codes.py                 # _codes.py integer-↔-enum tables
│   │   ├── test_subscriptions.py         # SubscriptionRegistry
│   │   ├── test_reconnect_backoff.py     # backoff math (jitter, cap, attempts)
│   │   ├── test_state_machine.py         # waiter list, predicate fanout, early-return
│   │   ├── test_layout_collection.py     # dual-name lookup + collision rule
│   │   └── test_exceptions.py            # diagnostic context, chaining, __str__
│   └── integration/
│       ├── conftest.py                   # JMRI-probe session fixture (skip-on-absence)
│       ├── test_discovery.py             # parallel discovery, layout-agnostic
│       ├── test_command_round_trip.py    # set_state + wait_for_jmri_state (FR21)
│       ├── test_subscription_lifecycle.py # subscribe/unsubscribe/replay
│       ├── test_reconnect_resilience.py  # forced disconnect mid-run (NFR5)
│       ├── test_throttle_lifecycle.py    # acquire / release / multi-throttle parallel
│       └── test_long_run.py              # one-hour unattended stability (NFR4)
└── examples/
    ├── hello_jmri.py                     # FR43 #1 — connect, discover, list
    ├── back_and_forth.py                 # FR43 #2 — port of MikeBackAndForth.py
    └── multi_train_session.py            # FR43 #3 — Journey 2 use case
```

(`docs/` for the Sphinx or MkDocs site is **Growth-deferred per PRD**;
not present in v1.)

### Architectural Boundaries

The library is small enough that "boundaries" are not microservice
contracts — they're three discipline lines drawn through the source
tree.

**1. Public / Private surface boundary**

- *Public:* `pyjmri/__init__.py` re-exports + every non-underscore
  module (`client.py`, `layout.py`, all entity modules,
  `exceptions.py`, `automaton.py`).
- *Private:* every `_<name>.py` module. Never imported from user code,
  examples, or documentation.
- *Enforcement:* `__all__` declared in every public module; `ruff`
  configured to flag underscore-prefixed imports from outside the
  package.

**2. Transport / Domain boundary**

- Only `_transport.py` is allowed to import `httpx` or `websockets`.
- Only `_transport.py` is allowed to catch `httpx.*` or `websockets.*`
  exception types. Catches re-raise as `JMRIError` subclasses with
  `from e`.
- Domain modules (entities, layout, client) interact with transport
  through the `Protocol`-typed handle defined in `_protocols.py`.
- *Enforcement:* code review; periodic `ruff` rule audit
  (forbidden-imports rule per file).

**3. JMRI JSON v5 integration boundary**

- The library binds to JMRI's JSON v5 web service surface
  (HTTP endpoints + `/json` WebSocket). Wire-format details
  (camelCase keys, integer state codes, request shapes) live entirely
  in `_transport.py`, `_parsing.py`, and `_codes.py`.
- The "Assumed JMRI JSON Contract" subsection of the PRD is the
  authoritative blast-radius checklist when reviewing JMRI version
  upgrades.
- *Enforcement:* contract drift surfaces as `JMRIProtocolError` —
  specifically called out in test scenarios.

### Requirements to Structure Mapping

**Connection & Session (FR1–FR7) →**

- `client.py` — Client lifecycle, async context manager, default URL
- `_transport.py` — HTTP client wrapper (httpx); WS connection wrapper
  consuming `websockets.connect()` async iterator (auto-reconnect)
- `_subscriptions.py` — SubscriptionRegistry replays on each WS
  reconnect (FR7)
- `exceptions.py` — `JMRIConnectionError`, `JMRIRequestTimeout` (FR4)

**Layout Discovery (FR8–FR12) →**

- `client.py` — `Client.discover()` orchestrates parallel per-type
  HTTP calls
- `layout.py` — `Layout` typed container; `EntityCollection[T]` with
  dual-name `__getitem__`
- `_parsing.py` — per-entity-type `parse_<entity>` functions
- `exceptions.py` — `LayoutEntityNotFound`

**Entity Read & Control (FR13–FR22) →**

- Per-entity modules (`turnout.py`, `sensor.py`, `block.py`,
  `light.py`, `memory.py`, `route.py`, `signal.py`) — each defines
  the entity class, its state enum, its read/set/wait methods, and
  its docstrings
- `power.py` — `PowerState` enum (FR16); access via
  `await client.power_state() -> PowerState` (read-only per PRD's
  deliberate-omission note on power write)
- `_codes.py` — JMRI integer code ↔ Enum tables, one per entity type
- `_transport.py` — HTTP command path for `set_state` calls

**Throttle & Locomotive Control (FR23–FR28) →**

- `throttle.py` — `Throttle` class, async context manager,
  `set_speed`, `set_function`, `release`; spawns keep-alive
  coroutine in Client's TaskGroup
- `roster.py` — `Roster`, `RosterEntry` (read-only metadata)

**Event Subscription & Wait Primitives (FR29–FR33) →**

- Per-entity modules — `wait_active`, `wait_inactive`, `wait_state`,
  `wait_change` methods (synchronous fanout from
  `SubscriptionRegistry`)
- `_subscriptions.py` — registry shape + replay logic
- `client.py` — registers in-flight waiters via the entity's own API
- `exceptions.py` — `WaitTimeout(JMRIError, TimeoutError)`

**Error Handling & Diagnostics (FR34–FR37) →**

- `exceptions.py` — full `JMRIError` hierarchy with diagnostic
  `context` field
- `_transport.py` — wraps third-party exceptions at the boundary
- All modules — `logger = logging.getLogger(__name__)` per
  Logging Discipline
- `__init__.py` — installs `NullHandler` on `pyjmri` root logger at
  import

**Distribution, Docs, Tooling (FR38–FR44) →**

- `pyproject.toml` — `[project]` metadata, dependencies, build
  backend, tool configs
- `README.md` — 5-min getting-started (FR40), Limitations (FR42),
  Jython migration table (FR41)
- `CONTRIBUTING.md` — integration-test-local-only policy
- `examples/hello_jmri.py`, `examples/back_and_forth.py`,
  `examples/multi_train_session.py` — FR43 shipped examples
- `src/pyjmri/py.typed` — FR44 marker
- `<repo-root>/.github/workflows/ci.yml` — macOS+Linux × Python
  3.11/3.12/3.13 matrix (NFR9). Lives at the JMRI repository root,
  not under `python_code/`, because GitHub Actions only reads
  `.github/` from the repo root. Path-scoped to `python_code/**` so
  panel-XML / roster / Jython commits do not trigger CI.

### Cross-Cutting Concerns Mapping

**Async correctness** — affects every module that does I/O.
Verified by `mypy --strict`, `ruff` (`ASYNC` rule set), and unit
tests for state-machine and reconnect-backoff modules.

**Connection-lifecycle entanglement** — concentrated in `client.py`
and `_transport.py`. The Client TaskGroup is the single place that
coordinates WS receive loop + per-throttle keep-alive coroutines.

**Unified state modeling** — `_codes.py` is the single source of
truth for JMRI integer code ↔ Enum mapping; per-entity modules
import their own enum; no shared base class.

**Command/event correlation** — implemented in per-entity modules
using the pre-register-wait pattern; relies on `_subscriptions.py`
+ `client.py` for the ensure-subscription plumbing.

**Structured logging** — module-level loggers everywhere; `extra={}`
context discipline; `NullHandler` installed in `__init__.py`.

**Strict-mypy public API** — `__all__` discipline + `py.typed`;
`_protocols.py` defines the Protocol that domain entities depend on,
keeping the public surface independent of transport implementation.

**Test harness boundary** — physical directory split
(`tests/unit/` vs `tests/integration/`) enforced by
`pytest.mark.integration` marker and CI's
`pytest -m "not integration"` invocation.

### Integration Points

**External integration: JMRI**

- *HTTP endpoint:* `http://<host>:<port>/json/<entity-type>`,
  default `localhost:12080`. Per-entity-type GET for discovery and
  state read; PUT/POST for state set. Surface kept entirely in
  `_transport.HTTPClient`.
- *WebSocket endpoint:* `ws://<host>:<port>/json`, default
  `localhost:12080`. Subscribe / unsubscribe messages outbound;
  state-change events inbound. Surface kept entirely in
  `_transport.WSConnection`.
- *No other external integrations.* No DB, no auth provider, no
  message broker, no observability backend (logging hands off to
  whatever the user configures).

**Internal data flow**

```text
JMRI HTTP/WS
    ↑
    │ (raw JSON)
    │
_transport.py  ←──── catches httpx.*/websockets.* errors,
    │                wraps as JMRIError subclasses
    │ (typed primitives)
    │
_parsing.py    ←──── translates camelCase JSON → snake_case fields,
    │                int state codes → Enum members (via _codes.py)
    │ (typed Python values)
    │
_subscriptions.py / domain entities
    │
    │ (state events)
    ↓
entity._on_event(state) → fans out to waiter list synchronously
    │
    ↓
user-script await sensor.wait_active() resolves
```

### Build & Distribution

- **Source build:** `uv build` (uses `uv_build` backend declared in
  `pyproject.toml`) produces sdist + wheel into `dist/`.
- **PyPI publish:** `uv publish` for v1; or hand off to a GitHub
  Actions release workflow in Growth.
- **Local dev install:** `uv sync` creates `.venv/` with all
  runtime + dev deps; library is installed editable via the `src/`
  layout convention.
- **No runtime configuration files** — all configuration is via
  `Client(url, config=ClientConfig(...))` constructor arguments.
  No env-var reading, no config-file loading. Library is a
  good citizen: it does not surprise the user's environment.

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**

All transport, concurrency, and domain decisions form a coherent
graph. `httpx` (async-only) + `websockets` (>=16) + Python 3.11+
`asyncio.TaskGroup` work together cleanly under `mypy --strict`.
The TaskGroup ownership model meshes with the
`websockets.connect()` async-iterator reconnect pattern and the
`SubscriptionRegistry.replay()` hook on the same timeline. Per-
entity Enums plus the `_codes.py` translation table never let raw
integers cross the public API. The `JMRIError` boundary at
`_transport.py` is the single layer that catches `httpx.*` and
`websockets.*` exceptions; everything above sees only typed
`JMRIError` subclasses. No contradictions found across decisions.

**Pattern Consistency:**

Implementation patterns (Type Annotation Conventions, Async
Patterns, Error Handling Discipline, Logging Discipline, Public
API Discipline, JSON↔Python Translation, Testing Patterns,
Documentation Patterns) align with and reinforce the architectural
decisions. Each pattern is enforceable via `ruff` + `mypy --strict`
configuration plus code review; nothing relies on convention alone.

**Structure Alignment:**

The src-layout tree mirrors the public/private boundary; the
transport/domain boundary is enforced by import discipline (only
`_transport.py` imports `httpx` / `websockets`); the JMRI
integration boundary lives entirely in `_transport.py` +
`_parsing.py` + `_codes.py`. Tests directory split (`unit/` vs
`integration/`) enforces the test-harness boundary. The structure
supports every architectural decision without gaps.

### Requirements Coverage Validation ✅

**Functional Requirements Coverage:**

All 44 FRs across 8 categories are architecturally supported:

- *Connection & Session (FR1–FR7):* `client.py` + `_transport.py`
  + `_subscriptions.py` + `JMRIConnectionError` /
  `JMRIRequestTimeout`.
- *Layout Discovery (FR8–FR12):* `client.py` (parallel TaskGroup
  discovery) + `layout.py` (`EntityCollection` dual-name lookup)
  + `_parsing.py` per-entity parsers + `LayoutEntityNotFound`.
- *Entity Read (FR13–FR16):* per-entity modules (FR13, FR14, FR15)
  + `power.py` (FR16, added during validation; see amendment
  below).
- *Entity Control (FR17–FR22):* per-entity `set_state` methods +
  pre-register-wait pattern for `wait_for_jmri_state=True` + FR22
  honored by exception discipline (no false-positive
  confirmations).
- *Throttle (FR23–FR28):* `throttle.py` (acquire / release /
  set_speed / set_function / async context manager) + per-throttle
  keep-alive coroutine in Client TaskGroup + best-effort
  documentation per FR28.
- *Event Subscription & Wait (FR29–FR33):* per-entity wait
  primitives + `SubscriptionRegistry` + waiter-list fanout +
  `WaitTimeout`.
- *Error Handling (FR34–FR37):* full `JMRIError` hierarchy with
  diagnostic context dict; structured logging; FR37's "no
  exceptions for undetectable failures" enforced by exception
  discipline.
- *Distribution & Docs (FR38–FR44):* `pyproject.toml` + `uv` +
  `README.md` + `examples/` + `py.typed`.

**Non-Functional Requirements Coverage:**

All 11 NFRs are architecturally supported:

- *Performance (NFR1–NFR3):* synchronous fanout from WS receive
  meets <100 ms sensor latency; parallel TaskGroup discovery meets
  <2 s discovery; thin transport layer meets <20 ms per-command
  overhead.
- *Reliability (NFR4–NFR6):* TaskGroup ownership + per-throttle
  task management for one-hour stability; `websockets.connect()`
  iterator + replay for ≥5 disconnects/hr survival;
  `ReconnectConfig` defaults match the 0.5–30 s bounded backoff
  spec.
- *Compatibility (NFR7–NFR9):* `pyproject.toml requires-python =
  ">=3.11"`; JMRI version check in `Client.discover()` raises
  `JMRIVersionUnsupported` for < 5.14; CI matrix gates macOS +
  Linux × 3.11/3.12/3.13.
- *Security & Network Posture (NFR10–NFR11):* `Client` defaults
  to `localhost:12080`; library introduces no auth and documents
  trusted-network use in README.

### Implementation Readiness Validation ✅

**Decision Completeness:**

Every critical decision (transport libraries, concurrency model,
state modeling, exception hierarchy, subscription registry,
reconnect mechanism, command/event correlation) is documented
with rationale, alternatives considered, and rejection notes.
Library versions are specified at the floor (`httpx` async client,
`websockets >= 16.0`, Python 3.11+, JMRI 5.14+).

**Pattern Completeness:**

Conflict points specifically relevant to a Python async library
(type-annotation style, async patterns, error handling, logging,
public API discipline, JSON translation, testing, documentation)
are all covered by enforceable rules. PEP 8 / formatting is
delegated to `ruff format` and `ruff check`.

**Structure Completeness:**

The complete project tree is enumerated file-by-file (with the
`power.py` amendment from validation). Every public module has a
clear purpose; every private module has a single responsibility.
Test-harness layout is concrete down to fixture filenames.

### Gap Analysis Results

**Critical Gaps:** None.

**Important Gaps (resolved during validation):**

- `power.py` module was missing from the structure tree despite
  FR16. Resolved by amendment below; the structure trees and
  Requirements-to-Structure mapping above were updated in place
  to include `power.py`.

**Nice-to-Have Gaps (implementation-detail items, not blocking):**

- *Throttle keep-alive default interval:* set
  `ClientConfig.throttle_keepalive_interval = 15.0` as the v1
  default (matches JMRI WiThrottle convention). The first
  integration test on the simulator confirms whether the loop
  fires or stays a no-op stub.
- *`automaton.py` v1 stub:* ships as an empty module with a
  docstring announcing future patterns; concrete patterns arrive
  in Growth.
- *JMRI version detection site:* version check happens in
  `Client.discover()` against the `/json/v5` endpoint metadata;
  raises `JMRIVersionUnsupported` for any JMRI < 5.14.
- *Throttle behavior on mid-acquire disconnect:* HTTP acquire path
  is independent of WS state; succeeds or raises
  `JMRIConnectionError`. WS subscription is established after
  acquire succeeds. Documented in `throttle.py` docstring.

### Validation Issues Addressed

**Amendment: `power.py` added to public module list.**

Rationale: PRD FR16 requires power-state read; the PRD's "Public
API Surface" subsection describes power as "a top-level property";
no entity-collection mapping fits. A dedicated `power.py` is the
clean home.

`PowerState.{ON, OFF, UNKNOWN}` follows the same pattern as
other state enums (Domain State Modeling). Access is
`await client.power_state() -> PowerState`. No write path
(per the PRD's deliberate-omission note: power is hardware-
governed on the supported environment).

`pyjmri/__init__.py` re-exports `PowerState`. `_codes.py` gains
the JMRI integer-code ↔ `PowerState` table.

The structure trees in *Internal Layering* and *Project
Structure → Complete Project Directory Structure* and the
*Requirements to Structure Mapping* were updated in place to
include `power.py`.

### Architecture Completeness Checklist

**Requirements Analysis**

- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped

**Architectural Decisions**

- [x] Critical decisions documented with versions
- [x] Technology stack fully specified
- [x] Integration patterns defined
- [x] Performance considerations addressed

**Implementation Patterns**

- [x] Naming conventions established
- [x] Structure patterns defined
- [x] Communication patterns specified
- [x] Process patterns documented

**Project Structure**

- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] Requirements to structure mapping complete

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** high

**Key Strengths:**

- Tightly bounded scope: every public surface item traces to a
  specific FR or NFR; nothing is included speculatively.
- Three boundary lines (public/private, transport/domain, JMRI
  integration) are mechanically enforceable, not just stylistic.
- Layout-agnosticism elevated to a first-class invariant means
  the library is community-shippable without basement-specific
  conditional code.
- Reconnect complexity is delegated to a battle-tested upstream
  primitive (`websockets.connect()` async iterator) rather than
  hand-rolled.
- Test-harness boundary is enforceable by directory split + pytest
  marker, and unit tests run in CI without any JMRI bootstrap.

**Areas for Future Enhancement (Growth-deferred per PRD):**

- Headless-JMRI CI for integration tests
- Concrete patterns in `automaton.py`
- CLI utilities (`pyjmri-status`, `pyjmri-discover`,
  `pyjmri-throttle`)
- Hosted documentation site (Sphinx or MkDocs)
- Additional entity coverage (oblock, layoutBlock, reporter, idTag,
  audio, configProfile, time, panel, train, engine, location,
  consist)
- Sensor recording / replay for offline test/simulation
- Multi-JMRI federation

### Implementation Handoff

**AI Agent Guidelines:**

- Follow all architectural decisions exactly as documented in this
  file. The architecture document is the source of truth;
  CLAUDE.md and `python_code/README.md` link to it rather than
  duplicating rules.
- Use implementation patterns consistently across all components.
  Local-clean (`ruff format`, `ruff check`, `mypy --strict`,
  `pytest tests/unit`) before push.
- Respect project structure and the three boundary lines
  (public/private, transport/domain, JMRI integration). Boundary
  violations are PR review blockers.
- Treat layout-agnosticism as a hard invariant. No file in
  `src/pyjmri/` may contain a hardcoded entity name, system-name
  prefix, or DCC address.
- Refer to this document for all architectural questions; propose
  changes to it via PR rather than diverging silently in code.

**First Implementation Priority:**

```bash
cd python_code
uv init --lib --name pyjmri
```

Then layer on the project-specific configuration enumerated in
*Starter Template Evaluation → Project-Specific Configuration to
Layer On*: ruff config, mypy strict config, pytest +
pytest-asyncio, tests directory split, GitHub Actions CI matrix,
MIT LICENSE at `python_code/LICENSE`, README scaffold.

This is Story 1. The Implementation Sequence in *Core
Architectural Decisions → Decision Impact Analysis* is the
authoritative ordering for subsequent stories.
