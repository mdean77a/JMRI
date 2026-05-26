---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
status: 'complete'
completedAt: '2026-05-06'
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/architecture.md'
project_name: 'pyjmri'
user_name: 'Mikey'
date: '2026-05-06'
---

# pyjmri - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for `pyjmri`, decomposing the requirements from the PRD and Architecture decisions into implementable stories. (No UX Design document — `pyjmri` has no GUI.)

## Requirements Inventory

### Functional Requirements

**Connection & Session**

- FR1: A user script can connect to a JMRI instance by specifying host and port.
- FR2: A user script can use default connection settings (`localhost:12080`) without explicit configuration.
- FR3: A user script can manage `Client` lifecycle as an async context manager so that resources are released deterministically on exit.
- FR4: A user script can detect when JMRI is unreachable and receive a typed connection error including diagnostic context (host, port, suggested cause).
- FR5: The library transparently maintains a WebSocket connection alongside the HTTP connection without exposing two separate clients to the user.
- FR6: The library automatically reconnects to JMRI's WebSocket after a transient disconnect, using a bounded backoff strategy, without intervention from the user script.
- FR7: The library restores all entity subscriptions after a WebSocket reconnect such that in-flight `wait_*` calls in user scripts continue to function across the disconnect.

**Layout Discovery**

- FR8: A user script can request a complete layout discovery and receive a typed `Layout` object enumerating all known entities of the supported types.
- FR9: A user script can access enumerated entities by both system name (e.g., `NT400`) and user name (e.g., "Staging NW Turnout 400").
- FR10: A user script can iterate the full collection of any entity type without invoking additional discovery calls.
- FR11: A user script can detect when a requested entity does not exist and receive a typed lookup error rather than `None` or a silent failure.
- FR12: The discovered layout includes, at minimum: turnouts, sensors, blocks, lights, memories, routes, signal heads, signal masts, and roster entries.

**Entity Read**

- FR13: A user script can read the current state of any enumerated entity in a typed form (e.g., `TurnoutState.CLOSED`, `SensorState.ACTIVE`).
- FR14: A user script can distinguish `unknown` state from every other state for any entity where JMRI reports unknown.
- FR15: A user script can read the value of any memory by name and receive a typed value.
- FR16: A user script can read the current power state of the layout (read-only; power write deliberately omitted from MVP).

**Entity Control**

- FR17: A user script can command a turnout to a state (closed or thrown) by name.
- FR18: A user script can set the value of a memory by name.
- FR19: A user script can command a light on or off.
- FR20: A user script can activate a route by name.
- FR21: A user script can choose, per command, to receive only optimistic command-acknowledgement (default) or to wait for JMRI to report the post-command state via WebSocket (opt-in `wait_for_jmri_state=True`).
- FR22: The library never returns a false-positive confirmation for a command outcome it cannot verify (NCE has no feedback path; the library does not pretend otherwise).

**Throttle & Locomotive Control**

- FR23: A user script can acquire a throttle for a DCC address, specifying long or short addressing.
- FR24: A user script can manage throttle lifecycle as an async context manager so that throttles are released deterministically on exit.
- FR25: A user script can set throttle speed (0.0..1.0) and direction in a single call.
- FR26: A user script can set throttle function bits F0..F28 individually. (Higher function bits deferred to Growth.)
- FR27: A user script can release a throttle explicitly to free it for other scripts or operators.
- FR28: A successful throttle acquire is documented as best-effort; the library does not imply a locomotive is physically present at the address.

**Event Subscription & Wait Primitives**

- FR29: A user script can subscribe to state changes on any state-bearing entity via the layout model, without manual subscription bookkeeping.
- FR30: A user script can `await` a sensor becoming active or inactive, with an optional timeout that raises a typed timeout error when exceeded.
- FR31: A user script can `await` an entity reaching a specific state, with an optional timeout.
- FR32: A user script can `await` the next state change of an entity, regardless of which state it transitions to.
- FR33: A user script's in-flight `wait_*` calls survive a WebSocket reconnect and resume waiting against the restored subscription.

**Error Handling & Diagnostics**

- FR34: The library raises typed exceptions from a documented `JMRIError` hierarchy for every error condition the library can detect (connection failure, request timeout, lookup failure).
- FR35: Connection-failure exceptions include actionable diagnostic context (host, port, suggested cause).
- FR36: The library emits structured log events at levels appropriate to severity (WARN for transient/recoverable conditions, INFO for routine state, DEBUG for detail) without forcing any specific logging configuration on the user.
- FR37: The library does not raise exceptions for failure modes it cannot detect (e.g., missing locomotive on the rails, turnout that physically failed to move); such limitations are documented in user-facing materials, not buried.

**Distribution, Documentation & Tooling**

- FR38: A user can install the library from PyPI using `uv add` or `pip install`.
- FR39: A contributor can install the library from source using `uv sync` after cloning the repository.
- FR40: A user can read a getting-started guide that takes them from install to a successful turnout flip in five minutes or less.
- FR41: A user can read a Jython-to-pyjmri migration table that maps common Jython idioms to their pyjmri equivalents.
- FR42: A user can read a "Limitations" section that explains what the library can and cannot detect (NCE open-loop, no DCC feedback path, no power control on this hardware).
- FR43: A user can run three shipped example programs (`hello_jmri.py`, `back_and_forth.py`, `multi_train_session.py`) against `Basement_Revised_2024.jmri` without modification.
- FR44: A developer can use the library against their own user scripts under `mypy --strict` and have all public types resolve cleanly (the library ships a `py.typed` marker).

### NonFunctional Requirements

**Performance**

- NFR1: Sensor state-change events propagate from JMRI's WebSocket message arrival to user-script `wait_*` resolution within 100 ms at the median, under steady-state load (idle layout, fewer than 100 active subscriptions).
- NFR2: Layout discovery against a layout the size of the author's basement (~370 entities across the supported types) completes within 2 seconds on a current macOS or Linux laptop, against a JMRI instance running on the same machine.
- NFR3: Library overhead on a single command round-trip (`await turnout.throw()` → JMRI ack → caller resumes) does not exceed 20 ms beyond what JMRI's HTTP response itself takes.

**Reliability**

- NFR4: A user script subscribed to fewer than 100 entities can run unattended for at least one hour against a stable JMRI instance without leaking memory, file descriptors, or asyncio tasks.
- NFR5: A user script's in-flight `wait_*` calls survive at least five forced WebSocket disconnects per hour without intervention. State-change events that occur *during* the disconnect window are delivered as the post-reconnect state (level-triggered across a reconnect boundary); this is documented.
- NFR6: WebSocket reconnect attempts use bounded exponential backoff with sensible defaults (initial 0.5 s, doubled on each failure, capped at 30 s) so that a long JMRI outage does not produce a tight reconnect loop.

**Compatibility**

- NFR7: The library supports Python 3.11 and later. Older Python versions are rejected at install time via `pyproject.toml` declarations.
- NFR8: The library supports JMRI 5.14 and later. The minimum required JMRI version is documented in the README, and the specific JMRI version used for testing each release is recorded in that release's notes.
- NFR9: The library runs on macOS and Linux as first-class development targets, gated by automated CI on each release. Windows has no CI gate; best-effort with no proactive testing for v1.

**Security & Network Posture**

- NFR10: The library defaults to `localhost:12080`. Connecting to a remote JMRI requires explicit user configuration (host argument).
- NFR11: The library introduces no authentication of its own and does not represent itself as providing security. JMRI's web server is unauthenticated by design and intended for trusted-network use; the library's documentation states this clearly so a user does not assume otherwise.

### Additional Requirements

These are technical/infrastructure requirements derived from the Architecture document that materially shape stories beyond the FR/NFR list:

- **Starter template (Epic 1 Story 1):** Initialize via `uv init --lib --name pyjmri` inside `python_code/`. Astral first-party library scaffold; produces `src/` layout, `uv_build` backend, `.python-version`, `pyproject.toml`, `py.typed` marker. **First implementation story is bounded by this command + the project-specific config layered on top.**
- **Project-specific configuration to layer onto starter:** `[tool.ruff]` rule set (E, W, F, I, B, UP, ASYNC, RUF) + formatter; `[tool.mypy]` `strict = true` with no implicit `Any` on public surface; `[tool.pytest.ini_options]` with `pytest-asyncio` (`asyncio_mode = "auto"`); tests directory split into `tests/unit/` + `tests/integration/`; MIT `LICENSE` at `python_code/LICENSE`; `README.md` seeded with 5-min getting-started outline.
- **CI matrix workflow:** GitHub Actions `.github/workflows/ci.yml` running on macOS-latest + ubuntu-latest × Python 3.11/3.12/3.13 on every push, executing `ruff check`, `mypy`, and `pytest tests/unit/` (`pytest -m "not integration"`). Windows excluded from CI per NFR9. Integration tests run locally only for v1; headless-JMRI CI is Growth-deferred.
- **Transport library selection:** `httpx` (async client only) for HTTP; `websockets` (>=16.0) for WebSocket. Auto-reconnect uses `websockets.connect()` async iterator + `process_exception` hook (no hand-rolled reconnect loop).
- **Internal layering & boundaries:** `src/pyjmri/` split into public modules (`client.py`, `layout.py`, per-entity modules, `exceptions.py`, `automaton.py`, `power.py`) and private modules (`_transport.py`, `_parsing.py`, `_subscriptions.py`, `_codes.py`, `_protocols.py`). Domain entities depend on a `Protocol`-typed Client handle from `_protocols.py` (no transport imports). `__all__` declared in every public module. **Three boundary lines are enforceable:** public/private surface, transport/domain (only `_transport.py` imports `httpx`/`websockets` or catches their exceptions), JMRI JSON v5 integration boundary (wire-format details confined to `_transport.py` + `_parsing.py` + `_codes.py`).
- **Domain state modeling:** Per-entity `enum.Enum` classes (no shared base). `UNKNOWN` is a member of every state enum. JMRI integer codes never cross the public API; translation tables live in private `_codes.py`.
- **Layout container with dual-name lookup:** `Layout` exposes per-entity-type `EntityCollection[T]` (implements `Mapping[str, T]`). `__getitem__` tries user name first, then system name; raises `LayoutEntityNotFound` otherwise. Explicit `by_user_name` / `by_system_name`. Documented collision rule: user name wins.
- **Exception hierarchy (concrete subclasses):** `JMRIError` base + `JMRIConnectionError` → `JMRIReconnectFailed`, `JMRIRequestTimeout`, `JMRIProtocolError` → `JMRIVersionUnsupported`, `LayoutEntityNotFound`, `LayoutEntityNotControllable`, `ThrottleError` → `ThrottleAcquireFailed` / `ThrottleReleased`, `WaitTimeout(JMRIError, TimeoutError)`. Base `JMRIError` carries `context: dict[str, Any]`. Library never raises base `JMRIError` directly. `__str__` formats actionable text (FR35).
- **Subscription registry & event fanout:** `SubscriptionRegistry` holds authoritative `set[(EntityType, str)]` decoupled from any specific WS connection. `registry.ensure(t, n)` is idempotent. Per-entity waiter list (`_waiters: list[(predicate, asyncio.Future)]`) with synchronous fanout from WS receive loop. `wait_*` early-returns if `_state` already matches.
- **Reconnect & restoration mechanism:** On each reconnect, `SubscriptionRegistry.replay()` re-sends every `(type, name)` subscribe; JMRI replies surface as normal state events; in-flight `wait_*` futures see post-reconnect state (level-triggered, no event replay). Backoff: 0.5 s initial, doubled, capped at 30 s, ±25% jitter. Default retries forever; optional `max_attempts` raises `JMRIReconnectFailed`.
- **Command/event correlation:** Pre-register-wait pattern. For `wait_for_jmri_state=True`, register the wait future on the entity *before* sending the HTTP command, so a fast post-ack state event cannot race ahead of the waiter. Reconnect during a `wait_for_jmri_state=True` operation preserves the wait.
- **Concurrency model:** Single Client-level `asyncio.TaskGroup` supervises every long-running coroutine the library owns (WS reconnect-and-receive loop; per-throttle keep-alive coroutine spawned in `Throttle.__aenter__`, cancelled in `__aexit__`). Hard rule: no bare `asyncio.create_task` outside the TaskGroup. `Client.__aexit__` cancels the TaskGroup → cancels supervised coroutines → cancels in-flight waiters with `CancelledError`.
- **Discovery strategy:** Parallel via `asyncio.TaskGroup` — all per-type discovery requests fire concurrently. Fail-fast on per-type errors (TaskGroup cancels siblings, propagates as `JMRIConnectionError` or `JMRIProtocolError`). Empty collections are normal (not errors).
- **Client configuration shape:** `Client(url, *, config: ClientConfig | None = None)`. `url` accepts `"host:port"`, `"http://..."`, or `"ws://..."`. `ClientConfig` and `ReconnectConfig` are frozen, kw-only dataclasses. `ClientConfig.throttle_keepalive_interval = 15.0` default (matches JMRI WiThrottle convention).
- **Power module (`power.py`):** Read-only `PowerState.{ON, OFF, UNKNOWN}`. Access via `await client.power_state() -> PowerState`. No write path (validation amendment that must be reflected in stories).
- **`automaton.py` v1 stub:** Ships as an empty module with a docstring announcing future patterns; concrete patterns Growth-deferred.
- **JMRI version detection:** `Client.discover()` checks `/json/v5` endpoint metadata; raises `JMRIVersionUnsupported` for any JMRI < 5.14.
- **Layout-agnosticism invariant:** No file in `src/pyjmri/` may contain hardcoded entity names, system-name prefixes (`NT*`, `IS*`, etc.), or DCC addresses. Integration tests query JMRI for available entities and operate on whatever is there; they skip gracefully when the running layout has none of a required entity type.
- **Test harness:** Physical directory split (`tests/unit/` vs `tests/integration/`) enforced by `pytest.mark.integration` marker. Integration `conftest.py` probes JMRI at session start; skips on absence with a clear message. No JMRI mocks (PRD policy). One-hour unattended stability run (`tests/integration/test_long_run.py`) is its own pytest target invoked manually before each release.
- **Logging:** Stdlib `logging`. Library installs `NullHandler` on the `pyjmri` root logger at import time. Logger hierarchy: `pyjmri.transport`, `pyjmri.subscription`, `pyjmri.reconnect`, `pyjmri.throttle`. Always use `logger = logging.getLogger(__name__)` and pass structured context via `extra={...}`. No f-strings inside log calls; no `print()` / `sys.stderr.write()`.
- **Implementation patterns enforcement:** Type annotation conventions (`from __future__ import annotations`, PEP 604 unions, `Self`, no `Any` in public surface), async patterns (`asyncio.timeout(...)` over `wait_for`), error handling discipline (third-party exceptions wrapped at `_transport` boundary with `from e`), JSON↔Python translation at parse boundary (camelCase → snake_case; unknown JSON fields ignored, missing expected fields raise `JMRIProtocolError`), public API discipline (`__all__` everywhere, top-level re-exports for users), Google-style docstrings on every public class/method/function.
- **Three shipped examples in `examples/`:** `hello_jmri.py` (connect + enumerate + print first 5 turnouts), `back_and_forth.py` (port of `MikeBackAndForth.py`), `multi_train_session.py` (Journey 2 — `asyncio.gather` of multi-loco coroutines).
- **`CONTRIBUTING.md`:** Documents integration-tests-local-only policy and developer setup.

### UX Design Requirements

(None — `pyjmri` has no GUI; no UX Design document exists.)

### FR Coverage Map

| FR | Epic | Brief |
|---|---|---|
| FR1 | 2 | Connect by host:port |
| FR2 | 2 | Default `localhost:12080` |
| FR3 | 2 | `Client` async context manager |
| FR4 | 2 | Typed connection error with diagnostics |
| FR5 | 3 | Single Client owns HTTP+WS |
| FR6 | 3 | Auto-reconnect with bounded backoff |
| FR7 | 3 | Subscriptions restored across reconnect |
| FR8 | 2 | `discover()` returns typed `Layout` |
| FR9 | 2 | Dual-name (user/system) lookup |
| FR10 | 2 | Iterate full entity collection |
| FR11 | 2 | `LayoutEntityNotFound` typed lookup error |
| FR12 | 2 | Min entity types: turnouts, sensors, blocks, lights, memories, routes, signal heads, signal masts, roster |
| FR13 | 2 | Read state in typed form |
| FR14 | 2 | `unknown` distinguishable |
| FR15 | 2 | Memory value read |
| FR16 | 2 | Power state read (read-only) |
| FR17 | 4 | Command turnout |
| FR18 | 4 | Set memory value |
| FR19 | 4 | Command light on/off |
| FR20 | 4 | Activate route |
| FR21 | 4 | Optimistic vs `wait_for_jmri_state=True` |
| FR22 | 4 | No false-positive confirmations |
| FR23 | 5 | Acquire throttle (long/short) |
| FR24 | 5 | Throttle async context manager |
| FR25 | 5 | Speed + direction in one call |
| FR26 | 5 | Function bits F0..F28 |
| FR27 | 5 | Explicit release |
| FR28 | 5 | Best-effort acquire (no presence implied) |
| FR29 | 3 | Subscribe via layout model |
| FR30 | 3 | `wait_active`/`wait_inactive` with timeout |
| FR31 | 3 | `wait_state(...)` with timeout |
| FR32 | 3 | `wait_change()` with timeout |
| FR33 | 3 | In-flight waits survive reconnect |
| FR34 | 2 | `JMRIError` hierarchy foundation |
| FR35 | 2 | Actionable diagnostic context |
| FR36 | 2 | Structured logging WARN/INFO/DEBUG |
| FR37 | 4 | No exceptions for undetectable failures |
| FR38 | 1 | Install via `uv add` / `pip install` |
| FR39 | 1 | `uv sync` from source |
| FR40 | 6 | 5-min getting-started |
| FR41 | 6 | Jython migration table |
| FR42 | 6 | Limitations section |
| FR43 | 6 | Three shipped examples |
| FR44 | 1 | `py.typed` marker; mypy strict resolves |

## Epic List

### Epic 1: Buildable, Type-checked Library Foundation

A developer can install `pyjmri` (empty stub) from PyPI or source via `uv add` / `pip install` / `uv sync`; `mypy --strict` against user code resolves the package's public types cleanly; `ruff` and `pytest` run; CI gates the project on every push.

**FRs covered:** FR38, FR39, FR44
**NFRs supported:** NFR7, NFR9
**Notes:** Starter is `uv init --lib --name pyjmri` per Architecture. Ships the `py.typed` marker, MIT LICENSE, README scaffold, ruff + mypy strict + pytest + pytest-asyncio config, tests dir split (`tests/unit/` + `tests/integration/`), and CI matrix (macOS + Linux × Python 3.11/3.12/3.13).

### Epic 2: Connect to JMRI and Discover the Layout

A user writes `async with Client() as jmri: layout = await jmri.discover()` and receives a typed `Layout` enumerating all entities. Lookup works by both user name and system name. Current state of every entity (including `unknown`) is readable; memory values readable; power state readable. Connection failures raise typed errors with diagnostic context.

**FRs covered:** FR1, FR2, FR3, FR4, FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15, FR16, FR34, FR35, FR36
**NFRs supported:** NFR2, NFR7, NFR8, NFR10, NFR11
**Notes:** Builds `_transport.HTTPClient`, `_codes`, `_parsing`, all eight entity classes' read paths, `EntityCollection` dual-name lookup, `Layout`, JMRI version check (raises `JMRIVersionUnsupported`), `power.py` read-only module, exception-hierarchy foundation, module-level loggers + `NullHandler`. Read-only operation is a viable end-state.

### Epic 3: Subscribe to State Changes and Wait Asynchronously

A user can `await sensor.wait_active()`, `wait_state(...)`, `wait_change()`, `wait_inactive()` on any state-bearing entity with optional timeouts that raise `WaitTimeout`. The library transparently maintains a WebSocket alongside HTTP, auto-reconnects after disconnects with bounded backoff, and restores subscriptions so in-flight waits survive. Multi-train evening sessions run unattended for an hour through forced disconnects.

**FRs covered:** FR5, FR6, FR7, FR29, FR30, FR31, FR32, FR33
**NFRs supported:** NFR1, NFR4, NFR5, NFR6
**Notes:** Adds `_transport.WSConnection` consuming `websockets.connect()` async iterator, `SubscriptionRegistry`, per-entity waiter list with synchronous fanout, Client `asyncio.TaskGroup`, `JMRIReconnectFailed`. Includes two first-class integration test stories: forced-WS-disconnect resilience + one-hour unattended stability.

### Epic 4: Command Layout Entities

A user can throw turnouts, command lights, set memory values, and activate routes — by name. Optimistic by default; opt-in `wait_for_jmri_state=True` waits for JMRI to report the post-command state via WebSocket. The library never returns a false-positive confirmation.

**FRs covered:** FR17, FR18, FR19, FR20, FR21, FR22, FR37
**NFRs supported:** NFR3
**Notes:** HTTP command path; per-entity command methods; pre-register-wait pattern; `LayoutEntityNotControllable` for read-only entities (e.g., signalMast). Power write and internal-sensor write deliberately omitted from MVP per PRD.

### Epic 5: Drive Locomotives via Throttles

A user can `async with layout.throttle(addr, long=True) as t:` and `t.set_speed(0.4, forward=True)`, set function bits F0–F28, and release deterministically. Multi-loco scripts compose via `asyncio.gather`.

**FRs covered:** FR23, FR24, FR25, FR26, FR27, FR28
**Notes:** `Throttle` async context manager; per-throttle keep-alive coroutine supervised by Client TaskGroup; `ThrottleAcquireFailed` / `ThrottleReleased`. Includes a multi-throttle parallel integration test story.

### Epic 6: Ship to the Community

A new user reads the README, installs via `uv add pyjmri`, follows the 5-minute getting-started, runs three shipped examples against `Basement_Revised_2024.jmri` unmodified, and finds a Jython→pyjmri migration table and a "Limitations" section explaining what the library can and cannot detect.

**FRs covered:** FR40, FR41, FR42, FR43
**Notes:** README quickstart; Limitations section; Jython migration table; `hello_jmri.py`; `back_and_forth.py`; `multi_train_session.py`; `CONTRIBUTING.md` integration-tests-local-only policy; PyPI publish workflow.

## Epic 1: Buildable, Type-checked Library Foundation

A developer can install `pyjmri` (empty stub) from PyPI or source via `uv add` / `pip install` / `uv sync`; `mypy --strict` against user code resolves the package's public types cleanly; `ruff` and `pytest` run; CI gates the project on every push.

### Story 1.1: Initialize package skeleton with `uv init --lib`

As a library developer,
I want the `pyjmri` package scaffolded with the Astral first-party `uv init --lib` template inside `python_code/`,
So that the project has a buildable `src/`-layout PyPI package with `py.typed` and a Python 3.11+ requirement from day one.

**Acceptance Criteria:**

**Given** an empty `python_code/` directory in the repo
**When** the developer runs `uv init --lib --name pyjmri` inside it and commits the output
**Then** `python_code/pyproject.toml` exists with `name = "pyjmri"`, `requires-python = ">=3.11"`, and `uv_build` as the build backend
**And** `python_code/src/pyjmri/__init__.py` exists
**And** `python_code/src/pyjmri/py.typed` exists (FR44)
**And** `python_code/.python-version` pins Python 3.11+
**And** `python_code/uv.lock` is generated and committed

**Given** a fresh checkout of the repo
**When** the developer runs `uv sync` inside `python_code/`
**Then** `.venv/` is created and the package installs in editable mode without errors (FR39)

**Given** the package is installed
**When** `python -c "import pyjmri"` runs
**Then** the import succeeds and emits no log output (the `pyjmri` root logger has `logging.NullHandler` attached at import time)

**Given** `python_code/pyproject.toml` declares `requires-python = ">=3.11"`
**When** an attempt is made to `pip install pyjmri` on Python 3.10 or older
**Then** the install fails with a Python-version mismatch message (NFR7)

### Story 1.2: Configure quality gates (ruff, mypy strict, pytest)

As a library developer,
I want `ruff`, `mypy --strict`, and `pytest` configured in `pyproject.toml` plus a `tests/unit/` and `tests/integration/` directory split,
So that every push runs through the same quality gates locally and in CI, and unit vs. integration tests are physically separable from the start.

**Acceptance Criteria:**

**Given** the package skeleton from Story 1.1
**When** a developer adds `[tool.ruff]` configuration to `python_code/pyproject.toml` enabling rule sets `E, W, F, I, B, UP, ASYNC, RUF` plus the formatter
**Then** `uv run ruff check src/ tests/` exits with status 0 against the empty scaffold
**And** `uv run ruff format --check src/ tests/` exits with status 0

**Given** `[tool.mypy]` is configured with `strict = true` in `pyproject.toml`
**When** `uv run mypy src/pyjmri` runs
**Then** it exits with status 0 (no errors) against the empty package

**Given** `[tool.pytest.ini_options]` is configured with `asyncio_mode = "auto"`
**When** `pytest-asyncio` is added as a dev dependency via `uv add --dev pytest-asyncio`
**Then** `uv run pytest tests/` discovers no tests and exits with the "no tests collected" status without crashing

**Given** `tests/unit/` and `tests/integration/` directories exist with empty `conftest.py` placeholders
**When** a developer registers a custom marker `integration` in `[tool.pytest.ini_options]`
**Then** `uv run pytest -m "not integration"` runs without warnings about unregistered markers

### Story 1.3: Add GitHub Actions CI matrix

As a library developer,
I want a GitHub Actions workflow that runs `ruff check`, `mypy`, and `pytest -m "not integration"` on every push across macOS and Linux × Python 3.11/3.12/3.13, scoped to `python_code/**` changes,
So that regressions are caught before merge and routine commits to JMRI panel XML, roster, or Jython files do not trigger CI churn.

**Acceptance Criteria:**

**Given** the quality gates from Story 1.2
**When** `.github/workflows/ci.yml` is committed at the JMRI repo root with a matrix of `os: [macos-latest, ubuntu-latest]` × `python-version: ['3.11', '3.12', '3.13']`
**Then** every qualifying push triggers six parallel CI jobs

**Given** a CI job is running
**When** the workflow installs `uv`, runs `uv sync` inside `python_code/`, then sequentially runs `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src/pyjmri`, and `uv run pytest -m "not integration"`
**Then** all four steps complete with exit status 0 against the current scaffold

**Given** the workflow definition
**When** a reviewer inspects the matrix
**Then** Windows is not present (NFR9 — Windows excluded from CI for v1)

**Given** the workflow lives at the JMRI repo root but pyjmri sources live only under `python_code/`
**When** the workflow's `on:` triggers are configured
**Then** the workflow runs only on commits that touch `python_code/**` or `.github/workflows/ci.yml` itself
**And** routine commits to JMRI panel XML (`*.jmri/`), `roster.xml`, `roster/`, or `jython/` files do not trigger CI

**Given** a future commit introduces a `mypy --strict` violation in `src/pyjmri/`
**When** CI runs
**Then** the affected jobs fail and the failure is surfaced on the PR

### Story 1.4: Add MIT LICENSE and README scaffold

As a library publisher,
I want a MIT `LICENSE` file at `python_code/LICENSE` and a `README.md` seeded with the placeholder sections required by FR40/FR41/FR42,
So that the wheel built from `python_code/` is self-contained and PyPI-ready, with the documentation surface stubbed for later epics to fill.

**Acceptance Criteria:**

**Given** the package skeleton from Story 1.1
**When** `python_code/LICENSE` is added containing the MIT License text with the author's copyright line
**And** `python_code/pyproject.toml` `[project]` metadata declares `license = "MIT"` and references `LICENSE`
**Then** `uv build` produces an sdist and wheel under `python_code/dist/` whose `METADATA` reflects the MIT license

**Given** `python_code/README.md` exists with placeholder sections titled "Quickstart" (for FR40), "Migrating from Jython" (for FR41), and "Limitations" (for FR42)
**When** `pyproject.toml` `[project]` metadata declares `readme = "README.md"`
**Then** the built wheel's METADATA includes the README content and `twine check dist/*` (or equivalent METADATA inspection) passes

**Given** the README scaffold
**When** a reviewer reads the placeholder sections
**Then** each section is clearly marked as a stub to be filled in Epic 6 (e.g., a `TODO` comment or an explicit "(filled in Epic 6)" note), so no Epic-1 reader mistakes the placeholder for the final content

## Epic 2: Connect to JMRI and Discover the Layout

A user writes `async with Client() as jmri: layout = await jmri.discover()` and receives a typed `Layout` enumerating all entities. Lookup works by both user name and system name. Current state of every entity (including `unknown`) is readable; memory values readable; power state readable. Connection failures raise typed errors with diagnostic context.

### Story 2.1: HTTP transport + Client lifecycle + exception hierarchy + logging foundation

As a library user,
I want `async with Client() as jmri:` to connect to JMRI's HTTP API and either succeed or raise a typed connection error with diagnostic context,
So that failed connections fail fast and informatively, and successful connections release resources deterministically on exit.

**Acceptance Criteria:**

**Given** the package skeleton from Epic 1
**When** `_transport.py` is added with an `HTTPClient` async wrapper around `httpx.AsyncClient`
**Then** only `_transport.py` imports `httpx` (transport/domain boundary enforced)
**And** `_transport.py` is the only module allowed to catch `httpx.*` exception types
**And** any caught `httpx.ConnectError` / `httpx.TimeoutException` is re-raised as `JMRIConnectionError` / `JMRIRequestTimeout` using `from e`

**Given** `exceptions.py` is added with the full `JMRIError` hierarchy from the architecture (base `JMRIError` with `context: dict[str, Any]`, plus `JMRIConnectionError`, `JMRIReconnectFailed`, `JMRIRequestTimeout`, `JMRIProtocolError`, `JMRIVersionUnsupported`, `LayoutEntityNotFound`, `LayoutEntityNotControllable`, `ThrottleError`, `ThrottleAcquireFailed`, `ThrottleReleased`, `WaitTimeout(JMRIError, TimeoutError)`)
**When** a unit test instantiates each subclass with diagnostic context and calls `str(exc)`
**Then** `JMRIConnectionError(host="localhost", port=12080)` formats as actionable text matching FR35 (e.g., "could not connect to localhost:12080 — is JMRI running with the web server enabled?")
**And** `WaitTimeout` instances are catchable as either `JMRIError` or `TimeoutError`
**And** the base `JMRIError` is never raised by library code (only subclasses)

**Given** `client.py` is added with a `Client(url: str = "localhost:12080", *, config: ClientConfig | None = None)` class implementing `__aenter__` / `__aexit__`
**When** the user writes `async with Client() as jmri: ...`
**Then** the Client connects on entry and closes the underlying `httpx.AsyncClient` on exit (FR2, FR3)
**And** `Client("host:port")`, `Client("http://host:port")`, and `Client("ws://host:port/json")` all parse correctly (FR1)
**And** the default URL is `localhost:12080` (NFR10)

**Given** the Client is configured with a non-existent host
**When** `__aenter__` runs
**Then** it raises `JMRIConnectionError` with `host`, `port`, and a suggested-cause string (FR4, FR35)
**And** the original `httpx.ConnectError` is chained via `__cause__`

**Given** the package is imported
**When** `pyjmri/__init__.py` runs
**Then** `logging.getLogger("pyjmri").addHandler(logging.NullHandler())` is called once (FR36 — no forced configuration)
**And** module-level `logger = logging.getLogger(__name__)` exists in `_transport.py` (yields `pyjmri.transport`)

**Given** Story 2.1's deliverables
**When** an integration test runs against a live JMRI on `localhost:12080`
**Then** `async with Client() as jmri: pass` connects and disconnects cleanly without raising
**And** the test is marked `@pytest.mark.integration` and skips when JMRI is not reachable

### Story 2.2: Wire-format translation — `_codes`, `_parsing`, per-entity state enums

As a library developer,
I want a private `_codes.py` mapping JMRI integer state codes to per-entity Enum members and a private `_parsing.py` translating JMRI's camelCase JSON into typed Python values,
So that integer codes never cross the public API and the JSON-translation boundary is the single place where wire-format details live.

**Acceptance Criteria:**

**Given** Story 2.1's transport boundary
**When** per-entity modules are seeded with their state enums only (no entity class yet) — `TurnoutState.{UNKNOWN, CLOSED, THROWN, INCONSISTENT}`, `SensorState.{UNKNOWN, ACTIVE, INACTIVE, INCONSISTENT}`, `BlockState.{UNKNOWN, OCCUPIED, UNOCCUPIED}`, `LightState.{UNKNOWN, ON, OFF}`, `PowerState.{UNKNOWN, ON, OFF}`, plus signal-head/mast aspect enums
**Then** `UNKNOWN` is a member of every state enum (FR14)
**And** every enum is a plain `enum.Enum` (not `IntEnum` or `StrEnum`) so JMRI integer codes are kept private

**Given** `_codes.py` is added
**When** unit tests inspect it
**Then** it contains a one-table-per-entity-type mapping `int → EnumMember` covering every state value JMRI is documented to emit
**And** `test_codes.py` covers each table with assertions that every JMRI documented integer maps to the expected enum member, including the `unknown` sentinel

**Given** `_parsing.py` is added with pure functions like `parse_turnout(json: dict) -> Turnout`-shape values
**When** a parser receives JSON with camelCase keys (`userName`, `systemName`)
**Then** the output uses snake_case Python attributes (`user_name`, `system_name`)
**And** integer state codes are translated to Enum members using `_codes.py` lookups
**And** unknown JSON fields are silently ignored (forward-compat with future JMRI versions)
**And** missing expected fields raise `JMRIProtocolError` with diagnostic context

**Given** `tests/unit/fixtures/` contains synthetic JSON samples for each entity type captured from a real JMRI response
**When** `test_parsing.py` runs each parser against its fixture
**Then** every parser produces the expected typed value
**And** `Any` does not appear in any parser's return type
**And** the only place `Any` is permitted is the input-JSON parameter type before parsing

### Story 2.3: Per-entity classes with read-only state and value access

As a library user,
I want typed entity classes for turnout, sensor, block, light, memory, route, signalHead, signalMast, roster, and rosterEntry — plus a top-level `power_state()` method on Client — that expose their current state or value as typed properties,
So that once I have an entity reference (from later discovery work), I can read its state or value in one line with full mypy support.

**Acceptance Criteria:**

**Given** Story 2.2's state enums and parsers
**When** `_protocols.py` defines a `ClientHandle` Protocol (slim interface for entities to issue HTTP reads via the Client)
**Then** entity modules import only `ClientHandle`, never `_transport` directly (transport/domain boundary)
**And** `mypy --strict` resolves the Protocol-typed dependency cleanly

**Given** `turnout.py` defines `class Turnout` with `name: str`, `user_name: str | None`, `state: TurnoutState` (cached), and `async def get_state() -> TurnoutState`
**When** `await turnout.get_state()` is called
**Then** it issues an HTTP GET via the `ClientHandle`, parses the response via `parse_turnout`, updates the cached `state`, and returns the new value (FR13)
**And** if JMRI reports the turnout as unknown, the returned value is `TurnoutState.UNKNOWN` (FR14 — never coerced)

**Given** the same pattern is applied to `sensor.py` (`Sensor`, `SensorState`), `block.py` (`Block`, `BlockState`), `light.py` (`Light`, `LightState`), `signal.py` (`SignalHead`, `SignalMast`, aspect enums)
**When** each entity's `get_state()` is unit-tested using a Mock `ClientHandle`
**Then** the test passes against a synthetic JSON response and the entity's cached `state` is updated

**Given** `memory.py` defines `class Memory` with `name`, `user_name`, `value: str | None` (cached), and `async def get_value() -> str | None`
**When** `await memory.get_value()` is called
**Then** it returns the current memory value as a typed string (or `None` if unset) per FR15

**Given** `route.py` defines `class Route` with `name`, `user_name`, and a docstring noting that activation is added in Epic 4
**When** `mypy --strict` runs
**Then** the class is well-typed even though it has no read-state method (routes are fire-and-forget actions)

**Given** `roster.py` defines `class RosterEntry` with at minimum `dcc_address: int`, `long_address: bool`, `road_number: str | None`, `road_name: str | None`, `model: str | None`, plus a `class Roster` container (read-only metadata)
**When** parsing a roster JSON sample
**Then** the resulting `RosterEntry` instances have all expected metadata fields populated as typed values

**Given** `power.py` defines `PowerState.{UNKNOWN, ON, OFF}` and `Client` gains an `async def power_state() -> PowerState` method
**When** `await client.power_state()` is called against a JMRI instance
**Then** it returns the current `PowerState` (FR16)
**And** there is no public method to write power state (PRD-deliberate omission)

**Given** every public module
**When** a reviewer inspects it
**Then** `__all__` is declared listing only the user-facing exports
**And** every public class has a Google-style docstring describing what + when to use it
**And** `from __future__ import annotations` is at the top

### Story 2.4: `Layout` container + `EntityCollection` with dual-name lookup

As a library user,
I want a `Layout` object exposing per-entity-type collections (`layout.turnouts`, `layout.sensors`, …) where I can look up entities by either user name or system name,
So that `layout.sensors["Block 1"]` (user name) and `layout.turnouts["NT400"]` (system name) both work without me having to know which is which.

**Acceptance Criteria:**

**Given** Story 2.3's entity classes
**When** `layout.py` defines a generic `EntityCollection[T](Mapping[str, T])` type
**Then** `__getitem__(key)` tries user-name lookup first, falls back to system-name lookup, and raises `LayoutEntityNotFound` (with `entity_type` and `key` in `context`) if neither matches (FR11)
**And** `by_user_name(name)` and `by_system_name(name)` methods exist for explicit disambiguation
**And** `__iter__` yields system names; `len()`, `in`, `.values()`, `.keys()`, `.items()` all behave per `Mapping` protocol (FR10)

**Given** an `EntityCollection` populated with two entities — entity X with user name "Foo" and entity Y with system name "Foo"
**When** `collection["Foo"]` is called
**Then** entity X is returned (user name wins per the documented collision rule)
**And** the public docstring explicitly notes this collision behavior

**Given** `layout.py` defines `class Layout` with `turnouts: EntityCollection[Turnout]`, `sensors: EntityCollection[Sensor]`, `blocks: EntityCollection[Block]`, `lights: EntityCollection[Light]`, `memories: EntityCollection[Memory]`, `routes: EntityCollection[Route]`, `signal_heads: EntityCollection[SignalHead]`, `signal_masts: EntityCollection[SignalMast]`, `roster: Roster`
**When** an empty `Layout()` is constructed and `len(layout.turnouts)` is checked
**Then** it returns `0` and iteration yields nothing (empty collections are valid; FR12 is about minimum types, not minimum counts)

**Given** `tests/unit/test_layout_collection.py`
**When** the test suite runs
**Then** it covers: dual-name lookup happy path, collision rule (user name wins), missing-key raises `LayoutEntityNotFound`, iteration yields system names, `len()` matches population, `in` checks both name spaces

**Given** `mypy --strict` runs over `layout.py`
**Then** the generic `EntityCollection[T]` resolves cleanly for every concrete entity type without `Any` leakage

### Story 2.5: `Client.discover()` parallel discovery + JMRI version check + integration smoke test

As a library user,
I want `await jmri.discover()` to enumerate every supported entity type from a running JMRI in parallel and return a fully populated `Layout` — refusing to proceed if JMRI is too old,
So that I can write `async with Client() as jmri: layout = await jmri.discover()` and get a working typed model in well under 2 seconds.

**Acceptance Criteria:**

**Given** Stories 2.1–2.4
**When** `Client.discover()` is implemented
**Then** it issues per-entity-type HTTP GETs in parallel using `asyncio.TaskGroup` (`turnout`, `sensor`, `block`, `light`, `memory`, `route`, `signalHead`, `signalMast`, `roster`)
**And** it parses each response via the matching `_parsing` function
**And** assembles the results into per-type `EntityCollection`s on a `Layout` instance (FR8, FR12)
**And** returns the populated `Layout`

**Given** `Client.discover()` runs
**When** the JMRI version is older than 5.14
**Then** discover() raises `JMRIVersionUnsupported` with the detected and required version in `context` (NFR8)
**And** the version check is performed once per `Client` lifetime against the `/json/v5` endpoint metadata

**Given** discovery is in progress and one per-type request raises `JMRIProtocolError`
**When** the TaskGroup catches the exception
**Then** it cancels the sibling tasks (fail-fast) and propagates the exception to the caller
**And** no partially-populated `Layout` is returned

**Given** an integration test against `Basement_Revised_2024.jmri` (NCE simulator)
**When** the test calls `discover()` and times the call
**Then** the call completes in under 2 seconds against the ~370-entity layout (NFR2)
**And** every `EntityCollection` is non-empty (turnouts, sensors, blocks, lights, memories, routes, signal heads, signal masts, roster)
**And** the test is marked `@pytest.mark.integration` and skips if JMRI is unreachable

**Given** the same integration test
**When** it picks the first turnout and prints `t.name`, `t.user_name`, `t.state`
**Then** all three are populated (state may be `UNKNOWN` if the layout is freshly started — that is correct per FR14)
**And** this exercises the same code path the eventual `hello_jmri.py` example (Epic 6) will use

**Given** layout-agnosticism is a hard invariant
**When** any reviewer audits Story 2.5's code
**Then** no string literal in `src/pyjmri/` matches `NT*`, `IS*`, `NS*`, or any DCC-address constant — discovery operates on whatever JMRI returns

## Epic 3: Subscribe to State Changes and Wait Asynchronously

A user can `await sensor.wait_active()`, `wait_state(...)`, `wait_change()`, `wait_inactive()` on any state-bearing entity with optional timeouts that raise `WaitTimeout`. The library transparently maintains a WebSocket alongside HTTP, auto-reconnects after disconnects with bounded backoff, and restores subscriptions so in-flight waits survive. Multi-train evening sessions run unattended through forced disconnects.

### Story 3.1: WebSocket transport + SubscriptionRegistry + reconnect with bounded backoff

As a library user,
I want the same `Client` I already use for HTTP to also maintain a WebSocket connection that auto-reconnects with bounded backoff after a disconnect,
So that I get a single `Client` interface (no separate WS object), and transient network blips don't end my long-running script.

**Acceptance Criteria:**

**Given** Epic 2's `Client` (HTTP-only)
**When** `_transport.WSConnection` is added consuming `websockets.connect(url)` as an async iterator (per architecture — *not* a hand-rolled reconnect loop)
**Then** only `_transport.py` imports `websockets` (transport/domain boundary)
**And** the `Client` constructor and `__aenter__` now establish both HTTP and WS connections; users still see a single `Client` (FR5)

**Given** `_subscriptions.py` is added defining `SubscriptionRegistry`
**When** `registry.ensure(entity_type, name)` is called
**Then** it adds `(entity_type, name)` to its authoritative set if not already present and sends a WS subscribe message
**And** repeated calls for the same `(entity_type, name)` are idempotent (no duplicate subscribe sent)

**Given** the WS connection has dropped and `websockets.connect()` yields a fresh connection
**When** the reconnect handler runs
**Then** `SubscriptionRegistry.replay()` re-sends every `(entity_type, name)` subscribe known to the registry
**And** an INFO log on `pyjmri.reconnect` records "WebSocket reconnected; replaying N subscriptions"

**Given** `ReconnectConfig(initial_delay=0.5, max_delay=30.0, jitter=0.25, max_attempts=None)` is the default
**When** consecutive WS connect failures occur
**Then** the `process_exception` hook on `websockets.connect()` enforces backoff: 0.5 s, ~1.0 s, ~2.0 s, ~4.0 s, ... capped at 30 s, with ±25% jitter (NFR6)
**And** a WARN log on `pyjmri.reconnect` records each failed attempt with `attempt` count and `next_delay`
**And** `max_attempts=None` means retry forever (default per architecture)

**Given** a `ReconnectConfig(max_attempts=N)` is configured
**When** N consecutive failures occur
**Then** the Client raises `JMRIReconnectFailed` (with `attempts` and last `cause` in `context`) and tears down

**Given** Story 3.1's deliverables
**When** unit tests run against `tests/unit/test_subscriptions.py` and `tests/unit/test_reconnect_backoff.py`
**Then** `SubscriptionRegistry` add/idempotent-add/replay behavior is covered against a mock send-channel
**And** the backoff math (initial delay, doubling, cap, jitter envelope) is covered against a deterministic fake clock — no real sleeps, no real network

**Given** the Client now owns long-running coroutines
**When** the Client is constructed
**Then** a single `asyncio.TaskGroup` supervises the WS reconnect-and-receive loop (architecture: "no bare `asyncio.create_task` outside the supervising TaskGroup")
**And** `Client.__aexit__` cancels the TaskGroup, which cleanly cancels every supervised coroutine

### Story 3.2: Per-entity waiter list and `wait_*` primitives

As a library user,
I want `await sensor.wait_active()`, `wait_inactive()`, `wait_state(target)`, and `wait_change()` on every state-bearing entity, with optional timeouts,
So that I can write event-driven scripts (e.g., "drive forward until block 6 occupies") without manual subscription bookkeeping or polling loops.

**Acceptance Criteria:**

**Given** Story 3.1's WS receive loop and SubscriptionRegistry
**When** each state-bearing entity gains `_waiters: list[tuple[Callable[[StateT], bool], asyncio.Future]]` and an `_on_event(new_state)` method called from the WS receive loop
**Then** `_on_event` updates the entity's cached `state`, then iterates `_waiters` and resolves any future whose predicate matches the new state (synchronous fanout; single event loop = no lock needed)
**And** futures whose predicates do not match remain in the list

**Given** an entity already has `_state == target` when a user calls `wait_state(target)`
**When** the wait method runs
**Then** it returns immediately without registering a future (early-return optimization)

**Given** a user calls `await sensor.wait_active()` for the first time
**When** the wait method runs
**Then** it calls `registry.ensure(EntityType.SENSOR, sensor.name)` first (auto-subscription per FR29 — no manual subscription bookkeeping)
**And** registers a `(predicate, future)` pair on the entity's `_waiters`
**And** awaits the future inside an `asyncio.timeout(timeout)` block if `timeout` is provided
**And** raises `WaitTimeout(entity_type, name)` (with `context` populated) if the timeout elapses (FR30)

**Given** every state-bearing entity (Turnout, Sensor, Block, Light, SignalHead, SignalMast)
**When** `wait_state(target)` and `wait_change()` are added with the same predicate-list pattern (FR31, FR32)
**Then** `wait_change()` matches any state different from the entity's state at the time the wait was registered
**And** `Sensor.wait_active()` and `Sensor.wait_inactive()` are convenience wrappers around `wait_state(SensorState.ACTIVE)` / `wait_state(SensorState.INACTIVE)` (FR30)
**And** all `wait_*` methods accept an optional `timeout: float | None = None` argument

**Given** `tests/unit/test_state_machine.py`
**When** the test suite runs
**Then** it covers: synchronous fanout to multiple registered waiters, predicate-mismatched waiters remain in the list, early-return when state already matches, `WaitTimeout` raised on timeout, cancellation cleans up the waiter from `_waiters`

**Given** the architecture's NFR1 budget (sensor event → user wait_* resolution within 100 ms median, idle layout, < 100 subscriptions)
**When** an integration test triggers a sensor change and measures the time from JMRI's WS message to the user's `wait_active()` resolving
**Then** the median is under 100 ms across at least 20 trials
**And** the test is marked `@pytest.mark.integration` and skips if JMRI is unreachable

### Story 3.3: Forced-disconnect resilience integration test

As a library user,
I want proof that my in-flight `wait_*` calls survive a WebSocket reconnect — so that when my Wi-Fi reboots mid-evening-session, my multi-train script keeps waiting rather than hanging or crashing,
So that FR7, FR33, and NFR5 are demonstrably met against a real JMRI instance.

**Acceptance Criteria:**

**Given** Stories 3.1 and 3.2
**When** `tests/integration/test_reconnect_resilience.py` is added
**Then** it includes a test that: (a) connects, discovers, picks the first sensor and the first turnout from the running layout, (b) registers `await asyncio.gather(sensor.wait_change(), turnout.wait_change())` in the background, (c) **forces a WS disconnect** (e.g., by closing the underlying socket from inside the library via a test-only hook), (d) waits for reconnection, (e) verifies the in-flight waits are still pending and the subscription registry shows both entities resubscribed (FR7, FR33)

**Given** the same test
**When** a state change is induced on JMRI's side after the reconnect (via an HTTP command from the test, against whatever entity is convenient — layout-agnostic)
**Then** the still-pending `wait_*` future resolves with the post-reconnect state (level-triggered semantics per NFR5)
**And** the test passes within a bounded time (e.g., 30 s timeout)

**Given** the reconnect happens during the test
**When** the WARN-level reconnect log is captured
**Then** the log message includes the attempt count and shows that exponential backoff was applied

**Given** the test framework's policy on JMRI mocks (none allowed per architecture)
**When** the test runs
**Then** it operates against a real JMRI instance loaded with whatever panel file the developer started; it does not hardcode any entity name, system-name prefix, or DCC address
**And** it skips with a clear message if the running layout has zero sensors or zero turnouts

**Given** the test's force-disconnect hook
**When** a reviewer audits the implementation
**Then** the hook is a documented test-only API on the `Client` (or on `_transport.WSConnection`) gated by an underscore-prefixed name so it never appears in user-facing examples

### Story 3.4: Parameterized unattended stability test (5-min default; 1-hour optional pre-release)

As a library user,
I want a parameterized unattended stability test that defaults to 5 minutes for normal dev use but can be invoked at one hour for pre-release validation, proving the script does not leak memory, file descriptors, or asyncio tasks across forced WS disconnects,
So that NFR4's one-hour stability claim is verifiable on demand without making everyday testing painful.

**Acceptance Criteria:**

**Given** Stories 3.1–3.3
**When** `tests/integration/test_long_run.py` is added
**Then** it defines a single test parameterized by duration with a default of 300 seconds (5 minutes)
**And** the duration can be overridden via a pytest CLI option (e.g., `--duration=3600`) or environment variable
**And** the test is marked `@pytest.mark.integration` AND `@pytest.mark.slow` (or a similar marker) so it does not run by default in `pytest -m "not integration"`

**Given** the test runs at the default 5-minute duration
**When** it executes
**Then** at least one forced WS disconnect is scheduled during the run, exercising the reconnect machinery
**And** the disconnect rate scales with duration to maintain at least 5-per-hour parity for runs ≥ 1 hour (NFR5 enforcement at the long-run setting)

**Given** the test finishes (any duration)
**When** leak metrics are captured
**Then** Python process RSS does not exceed the baseline by more than a documented threshold scaled to duration (e.g., < 10 MB at 5 min, < 50 MB at 60 min) — captured via `psutil` or `resource.getrusage` (NFR4: no memory leak)
**And** the count of open file descriptors at end-of-test is within a small delta of the count at start-of-test (NFR4: no FD leak)
**And** the count of asyncio tasks at end-of-test is within a small delta of the count at start-of-test (NFR4: no task leak)
**And** every forced disconnect was followed by a successful reconnect within the bounded backoff window
**And** every in-flight `wait_*` registered before each disconnect either resolved naturally or remained pending across the disconnect (no waiters orphaned, no cancellation-without-cleanup)

**Given** the architecture's policy that this test is "its own pytest target, invoked manually"
**When** the developer runs the standard `pytest -m "not integration"` (CI invocation)
**Then** this test does not run
**And** when the developer runs `pytest tests/integration/test_long_run.py` (or an equivalent named target)
**Then** the test runs at the default 5-minute duration and reports its leak metrics on completion
**And** when the developer runs the same target with `--duration=3600`
**Then** the test runs for one hour and verifies NFR4's full claim

**Given** the test is layout-agnostic
**When** a reviewer audits it
**Then** no entity names, system-name prefixes, or DCC addresses are hardcoded
**And** if the running layout has zero sensors, the test skips with a clear message rather than failing

**Given** the test produces release-gating evidence
**When** a release is being prepared
**Then** `CONTRIBUTING.md` (Epic 6) will reference this test as part of the release checklist, recommending the 1-hour invocation before each PyPI publish

## Epic 4: Command Layout Entities

A user can throw turnouts, command lights, set memory values, and activate routes — by name. Optimistic by default; opt-in `wait_for_jmri_state=True` waits for JMRI to report the post-command state via WebSocket. The library never returns a false-positive confirmation.

### Story 4.1: HTTP command path + per-entity command methods (optimistic by default)

As a library user,
I want `await turnout.throw()`, `await turnout.close()`, `await light.on()` / `off()`, `await memory.set_value(...)`, and `await route.activate()` — each returning when JMRI has acknowledged the command (no false-positive physical-confirmation claims),
So that I can write scripts that actively control my layout, knowing exactly what the library does and does not promise.

**Acceptance Criteria:**

**Given** Epic 2's `_transport.HTTPClient`
**When** an HTTP command path is added (POST/PUT to JMRI's `/json/<type>/<name>` with the state body, per JMRI JSON v5 contract)
**Then** the command method lives on `_transport.HTTPClient.command(entity_type, name, state)` and is the only place that constructs the wire payload
**And** the method awaits JMRI's HTTP response and returns when JMRI acknowledges (no further I/O)

**Given** `Turnout` from Epic 2
**When** `Turnout.set_state(state: TurnoutState)`, `Turnout.throw()` (alias for `set_state(THROWN)`), and `Turnout.close()` (alias for `set_state(CLOSED)`) are added
**Then** each method invokes the HTTP command path via the `ClientHandle` Protocol and returns once JMRI acknowledges (FR17)
**And** the method's docstring explicitly states "returns when JMRI has accepted the command; the library does not confirm physical layout state because NCE is open-loop" (FR22, FR37)

**Given** the same pattern applied to `Light` (`set_state`, `on()`, `off()` — FR19), `Memory` (`set_value(value: str)` — FR18), and `Route` (`activate()` — FR20)
**When** each method is unit-tested using a Mock `ClientHandle`
**Then** the test verifies that the correct entity-type, name, and command body are sent to the transport layer

**Given** read-only entities (Block, SignalHead, SignalMast in v1)
**When** a reviewer inspects the per-entity modules
**Then** none of them define `set_state`, `set_value`, or any other command method (compile-time read-only)
**And** their docstrings explicitly state that they are read-only in v1

**Given** JMRI returns an HTTP error indicating a commandable entity is currently not controllable (e.g., locked)
**When** the library translates the response
**Then** it raises `LayoutEntityNotControllable` (with `entity_type`, `name`, and JMRI's reason in `context`)
**And** unit tests cover the translation against a synthetic JMRI error response

**Given** FR37's discipline rule (no exceptions for undetectable failures)
**When** a reviewer audits Epic 4
**Then** no new exception types exist for "loco missing on the rails," "turnout physically failed to move," or any other open-loop NCE outcome
**And** the only exception types raised by command methods are: `JMRIConnectionError`, `JMRIRequestTimeout`, `JMRIProtocolError`, `LayoutEntityNotFound`, `LayoutEntityNotControllable`

**Given** an integration test against a running JMRI (simulator preferred for safety)
**When** the test picks the first commandable entity of each type, reads its current state, commands the opposite/different state, and reads back via WS event
**Then** JMRI's reported state matches the commanded state
**And** the test optionally restores the original state at teardown to leave the layout as it found it
**And** the test is layout-agnostic (no hardcoded names or DCC addresses) and skips entity types not present in the running layout

**Given** NFR3's budget (library command-overhead median < 20 ms beyond JMRI's HTTP response time)
**When** an integration microbenchmark runs 20 trials of `turnout.throw()` against a local JMRI simulator
**Then** the median (`call_total_ms − jmri_http_ms`) is under 20 ms
**And** the benchmark is part of the integration suite (skips when JMRI is unreachable; not in CI)

### Story 4.2: `wait_for_jmri_state=True` opt-in via pre-register-wait pattern

As a library user,
I want a `wait_for_jmri_state=True` keyword on every command method that makes the call return only after JMRI reports the post-command state via WebSocket,
So that when I'm composing operations like "activate this route and wait for the cascade of turnout commands to settle in JMRI's model," I can express that without building my own correlation logic — and the library is honest that what I'm seeing is JMRI's commanded state, not the layout's physical state.

**Acceptance Criteria:**

**Given** Story 4.1's per-entity command methods and Story 3.2's per-entity waiter list
**When** each command method gains a `wait_for_jmri_state: bool = False` keyword argument (FR21)
**Then** with `wait_for_jmri_state=False` (the default) the method behaves exactly as in Story 4.1 (optimistic, returns on JMRI ack)
**And** with `wait_for_jmri_state=True` the method implements the pre-register-wait pattern from the architecture:
  1. Call `registry.ensure(entity_type, name)` to guarantee a subscription exists
  2. Register a wait future on the entity's `_waiters` for the predicted post-command state — *before* sending the HTTP command
  3. Send the HTTP command
  4. Await the wait future
  5. On any exception, cancel the wait future and clean up the waiter list

**Given** the docstring on each command method
**When** a user reads it
**Then** the docstring explicitly notes that `wait_for_jmri_state=True` waits for JMRI's reported commanded state, *not* physical layout confirmation (FR22 reinforced — open-loop NCE means physical state is unobservable)

**Given** a unit test with a controlled `ClientHandle` and synthetic WS event injection
**When** the test simulates the race where JMRI's state event arrives between the `ensure(...)` call and the HTTP command being sent
**Then** the wait future still resolves correctly (the pre-register-wait ordering prevents the race)
**And** the test simulates the race where the state event arrives after the HTTP response — the wait future resolves on the event, not on the HTTP response

**Given** a `wait_for_jmri_state=True` operation is in flight when the WS connection drops
**When** the reconnect completes and `SubscriptionRegistry.replay()` re-subscribes the entity
**Then** the surfaced post-reconnect state event resolves the still-pending wait future (level-triggered semantics, per Epic 3 / NFR5)
**And** an integration test demonstrates this end-to-end: command issued → wait registered → WS forced disconnect → reconnect → state event delivers → caller resumes

**Given** a caller cancels a `wait_for_jmri_state=True` operation (e.g., via `asyncio.timeout`)
**When** the cancellation propagates
**Then** the wait future is cancelled and removed from `_waiters`
**And** the in-flight HTTP command is allowed to complete in the background (the user already initiated a state change; cancelling mid-flight could leave JMRI in an indeterminate state)
**And** this contract is documented in the docstring
**And** no orphaned future, task, or subscription leaks

**Given** integration testing against a running JMRI
**When** `tests/integration/test_command_round_trip.py` exercises `await turnout.throw(wait_for_jmri_state=True)` and `await route.activate(wait_for_jmri_state=True)`
**Then** each call returns only after JMRI's reported state matches the commanded state
**And** the test is layout-agnostic and skips when no commandable entities are present

## Epic 5: Drive Locomotives via Throttles

A user can `async with layout.throttle(addr, long=True) as t:` and `t.set_speed(0.4, forward=True)`, set function bits F0–F28, and release deterministically. Multi-loco scripts compose via `asyncio.gather`. Library plumbing is verifiable on the simulator; physical locomotive behavior is verifiable only on real NCE hardware (the simulator has no virtual decoder).

### Story 5.1: Throttle async context manager + acquire/release lifecycle + keep-alive supervision

As a library user,
I want `async with layout.throttle(5327, long=True) as loco:` to acquire a JMRI throttle by DCC address and release it deterministically on context-manager exit, with keep-alive coroutine supervision so a held throttle does not silently expire,
So that I never leak a stuck-throttle session, and the lifecycle is async-correct.

**Acceptance Criteria:**

**Given** Epics 2–4 (Client, transport, command path)
**When** `throttle.py` is added defining `class Throttle` with `__aenter__` / `__aexit__`
**Then** `Throttle` is constructed via `layout.throttle(dcc_address: int, *, long: bool)` (or `client.throttle(...)` — equivalent shape per architecture)
**And** the `Throttle` class lives at `src/pyjmri/throttle.py` and is re-exported in `pyjmri/__init__.py`

**Given** a user enters `async with layout.throttle(5327, long=True) as loco:`
**When** `__aenter__` runs
**Then** an HTTP request is sent to JMRI's throttle endpoint to acquire address 5327 with long-addressing flag (FR23)
**And** if JMRI rejects the acquire (e.g., already held by another client), `ThrottleAcquireFailed` is raised with `dcc_address`, `long`, and JMRI's reason in `context`
**And** if acquire succeeds, a per-throttle keep-alive coroutine is spawned in the Client's `asyncio.TaskGroup` (architecture: "no bare `asyncio.create_task` outside the supervising TaskGroup")

**Given** the keep-alive coroutine
**When** it runs
**Then** it sends a periodic heartbeat to JMRI at `ClientConfig.throttle_keepalive_interval` (default 15.0 s, matching JMRI WiThrottle convention)
**And** the implementation tolerates the v1 reality that keep-alive necessity is verified on hardware (Story 5.3) — if hardware shows it is unnecessary, the coroutine may ship as a no-op stub but the structure is in place for activation
**And** an INFO log on `pyjmri.throttle` records acquire and release lifecycle events with `dcc_address` in `extra={...}`

**Given** the `Throttle` is in scope
**When** the user calls `await loco.release()` explicitly OR the `async with` block exits (FR24, FR27)
**Then** the keep-alive coroutine is cancelled cleanly via the TaskGroup
**And** an HTTP release request is sent to JMRI
**And** the `Throttle` instance is marked released; subsequent calls to any control method raise `ThrottleReleased` (with `dcc_address` in `context`)

**Given** an exception raised inside the `async with` block
**When** `__aexit__` runs
**Then** the keep-alive coroutine is still cancelled cleanly and the throttle is still released (no leaked session even on error paths)

**Given** the FR28 honesty rule (acquire is best-effort; physical loco presence is not implied)
**When** a reviewer reads the `Throttle.__aenter__` docstring
**Then** it explicitly says "successful acquire only means JMRI accepted the throttle; it does not imply a locomotive at this DCC address is physically on the layout or responsive — NCE is open-loop with no DCC-bus feedback"

**Given** unit tests for the throttle lifecycle
**When** they run
**Then** they cover: successful acquire+release roundtrip via Mock `ClientHandle`; `ThrottleAcquireFailed` translation from a synthetic JMRI rejection; `ThrottleReleased` on post-release method calls; keep-alive task starts on acquire and is cancelled on release; exception inside `async with` still releases cleanly

**Given** hardware-mode observation results from Story 5.3 are not yet available at v1 implementation time
**When** the keep-alive coroutine is implemented
**Then** the chosen v1 default behavior — no-op stub vs. active heartbeat — is recorded explicitly in the source as a TODO comment on the keep-alive method, naming Story 5.3 as the hardware observation that will resolve the question
**And** the default is whichever option is safer for the unknown case (the architecture's note "the structure is in place for activation" implies shipping the active heartbeat by default; flipping to a no-op is acceptable only if hardware shows it harmful or wasteful)
**And** the comment includes a one-line procedure for a future maintainer to replace the TODO with the observed answer (e.g., "Confirmed unnecessary on JMRI X.Y / NCE / 2026-MM-DD — safe to no-op")

### Story 5.2: Throttle speed/direction/function controls

As a library user,
I want `loco.set_speed(0.4, forward=True)` and `loco.set_function(2, True)` to drive a held throttle with validated inputs, sending each command to JMRI,
So that I can write the locomotive-control core of any automation script in straightforward Python — speed and direction in one call, function bits one at a time.

**Acceptance Criteria:**

**Given** an acquired `Throttle` from Story 5.1
**When** `loco.set_speed(value: float, *, forward: bool)` is called (FR25)
**Then** `value` is validated to be in the closed range [0.0, 1.0]; out-of-range raises `ValueError` with diagnostic context
**And** speed and direction are sent to JMRI in a single HTTP request (not two separate calls)
**And** an INFO log on `pyjmri.throttle` records the new speed and direction with `dcc_address` in `extra={...}`

**Given** an acquired `Throttle`
**When** `loco.set_function(n: int, on: bool)` is called (FR26)
**Then** `n` is validated to be in the closed range [0, 28]; out-of-range raises `ValueError` with diagnostic context
**And** the function-bit command is sent to JMRI
**And** the docstring notes that higher function bits (F29+, used by some decoders such as ScaleTrains) are deferred to Growth

**Given** a released `Throttle`
**When** `loco.set_speed(...)` or `loco.set_function(...)` is called
**Then** `ThrottleReleased` is raised (carrying `dcc_address` in `context`) — no HTTP traffic is sent (Story 5.1's lifecycle invariant)

**Given** `mypy --strict` over `throttle.py`
**When** type-checking runs
**Then** `set_speed`'s `value: float` and `forward: bool` signatures resolve cleanly with no `Any` leakage
**And** `set_function`'s `n: int` and `on: bool` signatures resolve cleanly

**Given** unit tests for `set_speed` and `set_function`
**When** they run
**Then** they cover: valid inputs send the expected HTTP body via Mock `ClientHandle`; `ValueError` on `set_speed(-0.1)`, `set_speed(1.1)`, `set_function(-1, True)`, `set_function(29, True)`; `ThrottleReleased` after release

### Story 5.3: Multi-throttle integration test (plumbing on simulator; physical correctness on hardware)

As a library user,
I want a multi-throttle integration test that validates the library/JMRI plumbing on the simulator (acquire, command shape, keep-alive task lifecycle, release), and a documented hardware-mode protocol that actually drives locomotives on the basement layout for physical-correctness verification,
So that CI-eligible tests stay simulator-runnable, while the claim "throttles work" is grounded in real DCC hardware before each release.

**Acceptance Criteria:**

**Given** Stories 5.1 and 5.2
**When** `tests/integration/test_throttle_lifecycle.py` is added
**Then** it picks 2–3 DCC addresses from the running layout's roster (layout-agnostic — skips if the roster has fewer than 2 entries)
**And** it acquires each throttle in parallel using `asyncio.gather` of `async with` blocks (or an `AsyncExitStack` pattern)
**And** it issues `set_speed(0.1, forward=True)` and `set_function(0, True)` on each, then `set_speed(0.0, forward=True)` and `set_function(0, False)`
**And** it then releases each throttle

**Given** the test runs on the simulator (the default development environment)
**When** any AC verifies behavior
**Then** the test verifies *library plumbing only*: HTTP request shape via captured calls or response codes, JMRI's reported throttle state via subsequent reads, keep-alive task spawn-and-cancel via inspection of `asyncio.all_tasks()`, post-release `ThrottleReleased` enforcement
**And** the test does *not* assert anything about physical locomotive behavior, since the NCE simulator has no virtual decoder and no observable physical state
**And** a module-level docstring on `test_throttle_lifecycle.py` states this limitation explicitly so a future reader does not mistake "test passes" for "throttles drive real locos"

**Given** the test exits each `async with` block
**When** all throttles are released
**Then** the keep-alive coroutines spawned in the Client TaskGroup have been cancelled cleanly (verified via `asyncio.all_tasks()` inspection — no `pyjmri.throttle.keepalive` tasks remain)
**And** subsequent calls to any released throttle's control methods raise `ThrottleReleased`

**Given** any acquire fails (e.g., a DCC address already held)
**When** the test handles the error
**Then** it surfaces `ThrottleAcquireFailed`'s diagnostic context cleanly
**And** any partially-acquired throttles from the parallel acquire are released before the test fails

**Given** the test is layout-agnostic
**When** a reviewer audits it
**Then** no DCC addresses are hardcoded — the test reads the roster from the live layout
**And** if the roster is empty or has < 2 entries, the test skips with a clear message

**Given** the architecture's open verification item ("confirm whether JMRI's JSON v5 throttle endpoint requires keep-alive")
**When** the simulator-mode test runs
**Then** it can verify only that the keep-alive *coroutine* is correctly supervised — *not* whether keep-alive heartbeats are physically necessary, since the simulator does not model decoder timeout behavior
**And** the keep-alive necessity question is escalated to the hardware-mode validation protocol, which is documented in Story 6.5's `CONTRIBUTING.md` release checklist (cross-reference, not duplicated here)

## Epic 6: Ship to the Community

A new user reads the README, installs via `uv add pyjmri`, follows the 5-minute getting-started, runs three shipped examples against `Basement_Revised_2024.jmri` unmodified, and finds a Jython→pyjmri migration table and a "Limitations" section explaining what the library can and cannot detect.

### Story 6.1: README — 5-minute Quickstart

As a new pyjmri user,
I want a "Quickstart" section in the README that takes me from `uv add pyjmri` to a successful turnout flip in under 5 minutes,
So that I can decide if this library is worth investing in without reading the full architecture.

**Note on dependencies:** Implementable independently of Story 6.6 — the Quickstart text and copy-pasteable script can be authored as soon as Epics 2–4 are complete. Only the final "5-minute timing from `uv add`" acceptance check (the second AC block below) gates on Story 6.6's PyPI publication.

**Acceptance Criteria:**

**Given** the README scaffold from Story 1.4
**When** the "Quickstart" section is filled in
**Then** it contains, in order: (a) one-paragraph "what pyjmri is" framing, (b) prerequisites (JMRI 5.14+ running with web server enabled at `localhost:12080`), (c) install command `uv add pyjmri` and the `pip install pyjmri` alternative, (d) a copy-pasteable async script that connects, discovers, picks the first turnout, prints its `name`/`user_name`/`state`, and flips it, (e) the expected console output

**Given** a clean Python 3.11+ environment with JMRI running and `pyjmri` installed from PyPI (post Story 6.6)
**When** a reader follows the Quickstart from a blank terminal, copying each block in order
**Then** they reach a successful turnout flip in under 5 minutes (FR40)
**And** the script they copy works against `Basement_Revised_2024.jmri` and against any other JMRI panel file (layout-agnostic)

**Given** the Quickstart script
**When** a reviewer compares it against `examples/hello_jmri.py` (Story 6.4)
**Then** the Quickstart script and the example overlap conceptually but the Quickstart is shorter (≤15 lines) and inlined into the README; the example is the runnable file in `examples/`

**Given** the Quickstart references `Client()`, `discover()`, and a turnout command
**When** a reader copies it
**Then** every API call shown in the Quickstart resolves under `from pyjmri import ...` (no reaching into private modules)
**And** every API call has a corresponding docstring from Epics 2–4

### Story 6.2: README — Limitations section

As a pyjmri user,
I want a "Limitations" section that plainly explains what the library can and cannot detect — open-loop NCE, no DCC-bus feedback, no power write on this hardware, no physical-presence detection for locos or accessories,
So that I'm not surprised when a `await turnout.throw()` succeeds while the physical turnout doesn't move.

**Acceptance Criteria:**

**Given** the README scaffold from Story 1.4
**When** the "Limitations" section is filled in
**Then** it explains, in plain English: (a) NCE is open-loop — there is no feedback path from any commanded accessory or decoder back to JMRI, (b) "command acknowledged" means JMRI accepted the command, not that the layout physically moved, (c) layout power is governed by the booster's hardware power on the supported environment and is not under software control, so pyjmri exposes only `power_state()` (read), (d) throttle acquire is best-effort — a successful acquire does not imply a locomotive at that DCC address is physically on the rails or responsive, (e) sensors (block occupancy, etc.) remain the real observable for event-driven waits because they have a real feedback path, (f) the library introduces no authentication of its own and JMRI's web server is unauthenticated by design and intended for trusted-network use — do not expose it to untrusted networks (NFR11)

**Given** the Limitations section
**When** a reviewer cross-checks it against the FR37 list
**Then** every "library does not raise an exception for X" case from FR37 is mentioned in plain language with a brief why
**And** the section is positioned prominently in the README (e.g., directly after Quickstart, *before* the API reference) so a casual reader cannot miss it (FR42)

**Given** the section's tone
**When** a reader from the JMRI community reads it
**Then** it reads as a clear-eyed explanation of the underlying DCC reality, not an apology — these are properties of NCE and of model railroading, not pyjmri shortcomings

### Story 6.3: README — Jython-to-pyjmri migration table

As a JMRI user with existing Jython scripts,
I want a "Migrating from Jython" table mapping common Jython idioms (`AbstractAutomaton.init/handle`, `sensors.provideSensor`, `self.waitSensorActive`, `self.getThrottle`, etc.) to their pyjmri equivalents,
So that I can port my scripts without re-reading the API reference for each idiom.

**Acceptance Criteria:**

**Given** the README scaffold from Story 1.4
**When** the "Migrating from Jython" section is filled in
**Then** it contains the mapping table from the PRD Developer Tool Specific Requirements section (Jython column → pyjmri column), at minimum: `sensors.provideSensor`, `turnouts.getTurnout`, `routes.getRoute`, memory provide+getValue, `self.getThrottle`, `setSpeedSetting`, `setIsForward`, `setF<n>`, `waitSensorActive`, `waitSensorInactive`, `waitMsec`, `AbstractAutomaton init/handle` (FR41)

**Given** the migration table
**When** a reviewer audits each row
**Then** the pyjmri equivalent on the right-hand side is valid v1 syntax that resolves under `from pyjmri import ...`
**And** any row that maps to a deferred Growth/Vision feature (e.g., higher-level patterns) is annotated as such

**Given** the section's audience (Mike, Sarah, JMRI users with Jython history)
**When** they read it
**Then** the framing is "this is a map, not a forced migration" — Jython coexists with pyjmri per the PRD's Business Success "Jython coexists" stance
**And** the table is preceded by a short paragraph explaining the conceptual shift (synchronous polling `init`/`handle` → async/await, `AbstractAutomaton` → top-level `async def`)

### Story 6.4: Three shipped examples — `hello_jmri.py`, `back_and_forth.py`, `multi_train_session.py`

As a new pyjmri user,
I want three shipped example programs in `examples/` that I can run unmodified against `Basement_Revised_2024.jmri` and that demonstrate the journey arc from "first contact" to "multi-train evening session",
So that I have copy-paste starting points for my own scripts and proof that the library works end-to-end.

**Acceptance Criteria:**

**Given** Epics 2–5 are complete
**When** `examples/hello_jmri.py` is added
**Then** it connects with `Client()`, runs `discover()`, prints turnout/sensor/roster counts and the first 5 turnouts' `name`/`user_name`/`state`
**And** it runs against `Basement_Revised_2024.jmri` unmodified (FR43) and against any other JMRI panel file (layout-agnostic)
**And** it ends cleanly on `Ctrl-C` and on natural completion (no leaked tasks)

**Given** `examples/back_and_forth.py` is added
**When** a user runs it against `Basement_Revised_2024.jmri` (NCE simulator) with a chosen DCC address and two sensor names passed via CLI args or env vars
**Then** it ports `jython/MikeBackAndForth.py` — connects, picks the loco's throttle, picks the two sensors, drives forward until sensor A activates, reverses until sensor B activates, repeats
**And** it is at most ~30 lines of meaningful Python (PRD Journey 1 target)
**And** simulator-mode behavior is acknowledged in the docstring (loco doesn't actually move on the simulator); hardware-mode is what proves the example physically works

**Given** `examples/multi_train_session.py` is added
**When** a user runs it against `Basement_Revised_2024.jmri` with multiple DCC addresses and per-loco sensor pairs
**Then** it spawns multiple per-loco coroutines via `asyncio.gather`, each driving its own loco between its own pair of sensors
**And** it demonstrates Journey 2 — survives a forced WS disconnect mid-run (relies on Epic 3's reconnect machinery)
**And** the docstring notes: simulator-mode tests the orchestration; hardware-mode tests the physical behavior

**Given** all three examples
**When** they are reviewed
**Then** none of them hardcode entity names, system-name prefixes, or DCC addresses — defaults may be tuned for the basement layout for zero-friction first-run, but every layout-specific value is overridable via CLI args or environment variables (architecture's layout-agnosticism invariant)
**And** each example imports only from the top-level `pyjmri` namespace (no underscore-prefixed imports)
**And** each example runs cleanly under `mypy --strict` (FR44)

### Story 6.5: `CONTRIBUTING.md` with release checklist

As a maintainer (or future contributor),
I want a `CONTRIBUTING.md` documenting the development setup, the integration-tests-local-only policy, and a release checklist that includes the long-run stability test (Story 3.4) and the hardware-mode throttle protocol (Story 5.3),
So that release discipline is captured in one place that future-me (or a contributor) can follow without re-deriving it.

**Acceptance Criteria:**

**Given** the package skeleton from Epic 1
**When** `python_code/CONTRIBUTING.md` is added
**Then** it contains: (a) developer setup (`uv sync`, running unit tests via `pytest -m "not integration"`), (b) the integration-tests-local-only policy (no headless-JMRI CI in v1), (c) how to run integration tests locally against a real JMRI instance, (d) the release checklist below

**Given** the release checklist section of `CONTRIBUTING.md`
**When** it is written
**Then** it lists, in order, the pre-release verification steps: (1) `ruff check`, `ruff format --check`, `mypy --strict`, `pytest -m "not integration"` all clean locally, (2) full integration suite passes against `Basement_Revised_2024.jmri` simulator, (3) one-hour run of `tests/integration/test_long_run.py --duration=3600` passes (Story 3.4 long-run mode), (4) hardware-mode throttle validation per Story 5.3 (place loco on layout, run script, verify movement and function bit, observe keep-alive over ≥30 s held silence), (5) version bumped in `pyproject.toml`, (6) release notes written including the JMRI version tested against and the keep-alive observation result, (7) `uv build` produces clean sdist + wheel, (8) `uv publish` to PyPI, (9) git tag pushed

**Given** the release checklist is the discipline
**When** any future contributor reads it
**Then** the checklist is enforceable as a series of concrete commands and physical actions, not aspirational prose

**Given** a hardware-mode validation protocol is required (relocated from Story 5.3 — Story 5.3 *establishes* the protocol; this AC *documents* it)
**When** `CONTRIBUTING.md` is written
**Then** it documents a release-time procedure that runs against real NCE hardware on the basement layout, requiring the operator to: (a) place a known-responsive locomotive on the rails at a known DCC address, (b) run a small driving script that uses `pyjmri.Throttle` to start, run for a held duration, change direction, toggle a function (e.g., headlight), and stop, (c) visually confirm the loco moves and the function bit takes effect, (d) record the result in the release notes
**And** the procedure includes a keep-alive observation step: hold a throttle stationary for at least 2× the configured `throttle_keepalive_interval` (default 30 s of held silence), then issue a command and confirm JMRI still considers the throttle held — or, if it doesn't, that's the data point the architecture's open question was waiting for, and the keep-alive coroutine should be activated (not a no-op stub) accordingly
**And** the result of the keep-alive observation is recorded as a comment on `Throttle._keepalive` (or equivalent) so future maintainers inherit the answer (this updates the TODO seeded in Story 5.1)

### Story 6.6: First PyPI publication of `pyjmri` v1

As a library publisher,
I want `pyjmri` v1.0.0 published to PyPI under MIT license, installable via `uv add pyjmri` or `pip install pyjmri` from any machine with internet,
So that FR38 is satisfied end-to-end and the JMRI community can actually try the library.

**Acceptance Criteria:**

**Given** Stories 6.1–6.5 are complete and the release checklist (Story 6.5) has been followed top-to-bottom
**When** `uv build` runs against the final v1.0.0 source
**Then** an sdist (`pyjmri-1.0.0.tar.gz`) and a wheel (`pyjmri-1.0.0-py3-none-any.whl`) are produced under `python_code/dist/`
**And** `twine check dist/*` (or equivalent) passes — METADATA is well-formed, README renders for PyPI, MIT license is declared, `requires-python = ">=3.11"` is set
**And** the wheel includes `src/pyjmri/py.typed` so downstream `mypy --strict` finds it (FR44 verified end-to-end)

**Given** the build artifacts
**When** `uv publish` is run with valid PyPI credentials
**Then** `pyjmri 1.0.0` appears at `https://pypi.org/project/pyjmri/`
**And** the PyPI page renders the README correctly (Quickstart, Limitations, Migration table all visible)

**Given** the package is on PyPI
**When** a fresh test environment runs `uv add pyjmri` (or `pip install pyjmri`)
**Then** the install succeeds against Python 3.11/3.12/3.13 on macOS and Linux
**And** the post-install Quickstart from Story 6.1 runs end-to-end against a live JMRI

**Given** v1.0.0 has shipped
**When** the corresponding git tag `v1.0.0` is pushed to the GitHub remote
**Then** the tag matches the version in `pyproject.toml`
**And** the GitHub release notes (manual or from a release workflow — Growth-deferred) reference: the JMRI version tested against, the keep-alive observation outcome from Story 5.3, the long-run test result from Story 3.4

**Given** the final published artifact
**When** a reviewer audits it from the user-facing surface
**Then** `from pyjmri import Client, Layout, Turnout, TurnoutState, ...` resolves all v1 public types
**And** no underscore-prefixed module appears in the import path of any user-facing example or docstring
**And** the architecture's three boundary lines (public/private, transport/domain, JMRI integration) are visibly maintained in the published source

## Epic 7: v1.0.x Maintenance

**Status:** Post-PRD maintenance track. Opened 2026-05-26 after v1.0.0 shipped. Not part of the original v1 PRD scope; collects bugfixes and small quality improvements that warrant a patch release.

**Scope policy:** every story in Epic 7 must satisfy *all* of: (a) no public-API change, (b) no `pyproject.toml [project].version` bump within the story (the bump is its own discrete commit when a patch release is cut), (c) every quality gate (`ruff check`, `ruff format --check`, `mypy --strict`, unit pytest) passes, (d) the v1.0.0 functional and non-functional requirements remain unchanged.

When enough Epic 7 stories accumulate to warrant a v1.0.1 release, follow the same Phase A / Phase B pattern as Story 6.6 — version bump in a discrete commit, gates 1–5 green, hardware-mode validation if anything touches throttles, TestPyPI dry-run, production publish, tag at the build SHA, RELEASES.md entry.

### Story 7.1: Fix integration-test inter-test interference on shared first-entity

Originates from Epic 6 retrospective action item C3. Two flake events observed on 2026-05-26: `test_sensor_wait_change_median_latency_under_100ms` on `IS1`, and `test_turnout_wait_for_jmri_state_round_trip` on the first turnout (under pytest-cov instrumentation). Both share the same root cause: integration tests pick `sensors[0]` / `turnouts[0]` from `discover()` and therefore all target the same JMRI entity, suffering inter-test state leakage and rate-limit interactions.

The story scope: pin each shared-first-entity test to an explicit JMRI system name, force a known starting state per test via the existing raw-httpx pattern, calibrate timeouts against suite-load reality (5 s for the NFR1 sensor `wait_change`, 10 s for the AC10 turnout round-trip), and verify two consecutive `pytest -m "integration and not slow"` runs pass plus one `pytest --with pytest-cov`. No production source change; tests only.

See `_bmad-output/implementation-artifacts/7-1-fix-integration-test-inter-test-interference.md` for full acceptance criteria.
