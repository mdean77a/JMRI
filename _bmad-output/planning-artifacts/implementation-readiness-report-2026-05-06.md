---
project: JMRI (pyjmri)
date: 2026-05-06
stepsCompleted:
  - step-01-document-discovery
  - step-02-prd-analysis
  - step-03-epic-coverage-validation
  - step-04-ux-alignment
  - step-05-epic-quality-review
  - step-06-final-assessment
filesIncluded:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/epics.md
---

# Implementation Readiness Assessment Report

**Date:** 2026-05-06
**Project:** JMRI (pyjmri client)

## Step 1 — Document Inventory

### Documents Assessed

| Type         | File                                          | Format | Size (bytes) | Modified   |
|--------------|-----------------------------------------------|--------|--------------|------------|
| PRD          | `_bmad-output/planning-artifacts/prd.md`      | Whole  | 44,618       | 2026-05-06 |
| Architecture | `_bmad-output/planning-artifacts/architecture.md` | Whole | 66,930   | 2026-05-06 |
| Epics+Stories| `_bmad-output/planning-artifacts/epics.md`    | Whole  | 86,270       | 2026-05-06 |

### Documents Not Present (by design)

- **UX Design**: Not applicable. pyjmri has no user interface; UX assessment in Step 4 will be skipped with rationale recorded.
- **Individual Story Files**: Not applicable. User confirmed stories live inside `epics.md`.

### Duplicates

None.

### Other Artifacts (informational, not assessed as inputs)

- `prd-validation-report.md` — output of a prior PRD validation run.

## Step 2 — PRD Analysis

### Functional Requirements (44 total)

**Connection & Session**
- **FR1**: A user script can connect to a JMRI instance by specifying host and port.
- **FR2**: A user script can use default connection settings (`localhost:12080`) without explicit configuration.
- **FR3**: A user script can manage `Client` lifecycle as an async context manager so that resources are released deterministically on exit.
- **FR4**: A user script can detect when JMRI is unreachable and receive a typed connection error including diagnostic context (host, port, suggested cause).
- **FR5**: The library transparently maintains a WebSocket connection alongside the HTTP connection without exposing two separate clients to the user.
- **FR6**: The library automatically reconnects to JMRI's WebSocket after a transient disconnect, using a bounded backoff strategy, without intervention from the user script.
- **FR7**: The library restores all entity subscriptions after a WebSocket reconnect such that in-flight `wait_*` calls in user scripts continue to function across the disconnect.

**Layout Discovery**
- **FR8**: A user script can request a complete layout discovery and receive a typed `Layout` object enumerating all known entities of the supported types.
- **FR9**: A user script can access enumerated entities by both system name (e.g., `NT400`) and user name (e.g., "Staging NW Turnout 400").
- **FR10**: A user script can iterate the full collection of any entity type without invoking additional discovery calls.
- **FR11**: A user script can detect when a requested entity does not exist and receive a typed lookup error rather than `None` or a silent failure.
- **FR12**: The discovered layout includes, at minimum: turnouts, sensors, blocks, lights, memories, routes, signal heads, signal masts, and roster entries.

**Entity Read**
- **FR13**: A user script can read the current state of any enumerated entity in a typed form (e.g., `TurnoutState.CLOSED`, `SensorState.ACTIVE`).
- **FR14**: A user script can distinguish `unknown` state from every other state for any entity where JMRI reports unknown.
- **FR15**: A user script can read the value of any memory by name and receive a typed value.
- **FR16**: A user script can read the current power state of the layout (read-only).

**Entity Control**
- **FR17**: A user script can command a turnout to a state (closed or thrown) by name.
- **FR18**: A user script can set the value of a memory by name.
- **FR19**: A user script can command a light on or off.
- **FR20**: A user script can activate a route by name.
- **FR21**: A user script can choose, per command, to receive only optimistic command-acknowledgement (default) or to wait for JMRI to report the post-command state via WebSocket (opt-in).
- **FR22**: The library never returns a false-positive confirmation for a command outcome it cannot verify.

*Deliberately omitted from MVP*: power control (booster-governed); internal-sensor write (covered by memory writes).

**Throttle & Locomotive Control**
- **FR23**: A user script can acquire a throttle for a DCC address, specifying long or short addressing.
- **FR24**: A user script can manage throttle lifecycle as an async context manager so that throttles are released deterministically on exit.
- **FR25**: A user script can set throttle speed (0.0..1.0) and direction in a single call.
- **FR26**: A user script can set throttle function bits F0..F28 individually. (Higher bits deferred to Growth.)
- **FR27**: A user script can release a throttle explicitly to free it for other scripts or operators.
- **FR28**: A successful throttle acquire is documented as best-effort; the library does not imply a locomotive is physically present at the address.

**Event Subscription & Wait Primitives**
- **FR29**: A user script can subscribe to state changes on any state-bearing entity via the layout model, without manual subscription bookkeeping.
- **FR30**: A user script can `await` a sensor becoming active or inactive, with an optional timeout that raises a typed timeout error when exceeded.
- **FR31**: A user script can `await` an entity reaching a specific state, with an optional timeout.
- **FR32**: A user script can `await` the next state change of an entity, regardless of which state it transitions to.
- **FR33**: A user script's in-flight `wait_*` calls survive a WebSocket reconnect and resume waiting against the restored subscription.

**Error Handling & Diagnostics**
- **FR34**: The library raises typed exceptions from a documented `JMRIError` hierarchy for every error condition the library can detect (connection failure, request timeout, lookup failure).
- **FR35**: Connection-failure exceptions include actionable diagnostic context (host, port, suggested cause).
- **FR36**: The library emits structured log events at levels appropriate to severity (WARN for transient/recoverable, INFO for routine, DEBUG for detail) without forcing any specific logging configuration.
- **FR37**: The library does not raise exceptions for failure modes it cannot detect (missing locomotive, turnout that physically failed to move); such limitations are documented.

**Distribution, Documentation & Tooling**
- **FR38**: A user can install the library from PyPI using `uv add` or `pip install`.
- **FR39**: A contributor can install the library from source using `uv sync` after cloning the repository.
- **FR40**: A user can read a getting-started guide that takes them from install to a successful turnout flip in five minutes or less.
- **FR41**: A user can read a Jython-to-pyjmri migration table that maps common Jython idioms to their pyjmri equivalents.
- **FR42**: A user can read a "Limitations" section that explains what the library can and cannot detect.
- **FR43**: A user can run three shipped example programs (`hello_jmri.py`, `back_and_forth.py`, `multi_train_session.py`) against `Basement_Revised_2024.jmri` without modification.
- **FR44**: A developer can use the library against their own user scripts under `mypy --strict` and have all public types resolve cleanly (the library ships a `py.typed` marker).

**Total FRs: 44**

### Non-Functional Requirements (11 total)

**Performance**
- **NFR1**: Sensor state-change events propagate from JMRI's WebSocket message arrival to user-script `wait_*` resolution within 100 ms at the median, under steady-state load (idle layout, fewer than 100 active subscriptions).
- **NFR2**: Layout discovery against a layout the size of the author's basement (~370 entities) completes within 2 seconds on a current macOS or Linux laptop, against a JMRI instance running on the same machine.
- **NFR3**: Library overhead on a single command round-trip does not exceed 20 ms beyond what JMRI's HTTP response itself takes.

**Reliability**
- **NFR4**: A user script subscribed to fewer than 100 entities can run unattended for at least one hour against a stable JMRI instance without leaking memory, file descriptors, or asyncio tasks.
- **NFR5**: A user script's in-flight `wait_*` calls survive at least five forced WebSocket disconnects per hour without intervention. State-change events that occur during the disconnect window are delivered as the post-reconnect state (level-triggered across a reconnect boundary).
- **NFR6**: WebSocket reconnect uses bounded exponential backoff with sensible defaults (initial 0.5 s, doubled on each failure, capped at 30 s).

**Compatibility**
- **NFR7**: The library supports Python 3.11 and later. Older Python versions are rejected at install time via `pyproject.toml` declarations.
- **NFR8**: The library supports JMRI 5.14 and later. Minimum version documented in README; specific JMRI version used for testing each release recorded in release notes.
- **NFR9**: macOS and Linux are first-class development targets, gated by automated CI on each release. Windows has no CI gate; project accepts contributor-reported Windows regressions but commits no proactive testing effort for v1.

**Security & Network Posture**
- **NFR10**: The library defaults to `localhost:12080`. Connecting to a remote JMRI requires explicit user configuration (host argument).
- **NFR11**: The library introduces no authentication of its own and does not represent itself as providing security. JMRI's web server is unauthenticated by design; documentation states this clearly.

**Total NFRs: 11**

*Deliberately skipped categories*: Scalability, Accessibility, Integration (covered by FRs), Maintainability (covered by Technical Success).

### Additional Requirements & Constraints

**Technical / packaging**
- Async-only; single `Client` owning HTTP + WS connections; no global state.
- `uv` is canonical project tool; `pyproject.toml` + `uv.lock` are source of truth.
- `mypy --strict` and `ruff` clean; `py.typed` marker.
- MIT license; PyPI as `pyjmri`.
- Single async event loop; users wrap in `asyncio.run` for sync contexts.

**Testing constraints**
- **No JMRI mocks.** Integration tests run against a real JMRI process (Basement_Revised_2024.jmri / NCE simulator). Unit tests cover only library internals that don't touch JMRI.

**Assumed JMRI JSON v5 contract surface (blast-radius checklist for upgrades)**
- Endpoints: `turnout`, `sensor`, `block`, `light`, `memory`, `route`, `signalHead`, `signalMast` (read/set/subscribe); `roster`, `rosterEntry` (read); `power` (read); `throttle` (acquire/set/release).

**Acceptance gates (v1)**
- ≥3 example programs ported from `jython/Mike*.py` runnable against `Basement_Revised_2024.jmri`.
- Continuous one-hour multi-train run including a forced mid-run WebSocket disconnect.
- 5-minute new-user "first turnout flip" walkthrough including `uv` install.
- All detectable command failure modes raise typed exceptions covered by tests.

**Deferred to Growth/Vision (must not be in MVP epics)**
- Operations module, Warrants, LogixNG, Dispatcher integration.
- CLI utilities (`pyjmri-status`, `pyjmri-discover`, `pyjmri-throttle`).
- Higher entity types (oblock, layoutBlock, reporter, idTag, audio, configProfile, time, panel, train, engine, location, consist).
- Function bits above F28; sections (not exposed by JMRI JSON).

### PRD Completeness Assessment (initial)

The PRD is exceptionally well-structured for traceability:

- **Strengths:** Numbered FRs/NFRs in clean ranges (FR1–FR44, NFR1–NFR11). Each is testable. Explicit out-of-scope notes (power control, internal-sensor write, sections, ops/warrants/LogixNG). Acceptance gates are concrete and measurable. Honest semantics (open-loop, `unknown` first-class) are repeated consistently. Assumed JSON contract is enumerated.
- **Watch items for traceability:** A few requirements are documentation-bearing rather than code-bearing (FR40, FR41, FR42, FR43). These must trace to story-level doc deliverables, not code stories alone. NFR9's CI gate (macOS + Linux) is process-bearing — must trace to a CI/build story. NFR4's "no leaks over 1 hr" and NFR5's "≥5 forced disconnects/hr" are integration-test stories — must trace to a long-run/chaos story.

## Step 3 — Epic Coverage Validation

The epics document is a single file (`epics.md`) of 6 epics and 22 stories. The document includes its own self-declared FR Coverage Map; this section validates that map independently against the PRD.

### Functional Requirement Coverage Matrix

| FR | PRD Topic (paraphrased) | Epic / Story | Status |
|----|--------------------------|--------------|--------|
| FR1 | Connect by host:port | Epic 2 / Story 2.1 | ✅ Covered |
| FR2 | Default `localhost:12080` | Epic 2 / Story 2.1 | ✅ Covered |
| FR3 | `Client` async context manager | Epic 2 / Story 2.1 | ✅ Covered |
| FR4 | Typed connection error w/ diagnostics | Epic 2 / Story 2.1 | ✅ Covered |
| FR5 | Single Client owns HTTP+WS | Epic 3 / Story 3.1 | ✅ Covered |
| FR6 | Auto-reconnect bounded backoff | Epic 3 / Story 3.1 | ✅ Covered |
| FR7 | Subscriptions restored on reconnect | Epic 3 / Stories 3.1, 3.3 | ✅ Covered |
| FR8 | `discover()` returns typed `Layout` | Epic 2 / Story 2.5 | ✅ Covered |
| FR9 | Dual-name (user/system) lookup | Epic 2 / Story 2.4 | ✅ Covered |
| FR10 | Iterate full entity collection | Epic 2 / Story 2.4 | ✅ Covered |
| FR11 | `LayoutEntityNotFound` typed error | Epic 2 / Story 2.4 | ✅ Covered |
| FR12 | Min entity types incl. all 9 | Epic 2 / Story 2.5 | ✅ Covered |
| FR13 | Read state in typed form | Epic 2 / Story 2.3 | ✅ Covered |
| FR14 | `unknown` distinguishable | Epic 2 / Stories 2.2, 2.3 | ✅ Covered |
| FR15 | Memory value read | Epic 2 / Story 2.3 | ✅ Covered |
| FR16 | Power state read (read-only) | Epic 2 / Story 2.3 | ✅ Covered |
| FR17 | Command turnout | Epic 4 / Story 4.1 | ✅ Covered |
| FR18 | Set memory value | Epic 4 / Story 4.1 | ✅ Covered |
| FR19 | Command light on/off | Epic 4 / Story 4.1 | ✅ Covered |
| FR20 | Activate route | Epic 4 / Story 4.1 | ✅ Covered |
| FR21 | Optimistic vs `wait_for_jmri_state=True` | Epic 4 / Story 4.2 | ✅ Covered |
| FR22 | No false-positive confirmations | Epic 4 / Story 4.1 | ✅ Covered |
| FR23 | Acquire throttle (long/short) | Epic 5 / Story 5.1 | ✅ Covered |
| FR24 | Throttle async context manager | Epic 5 / Story 5.1 | ✅ Covered |
| FR25 | Speed + direction in one call | Epic 5 / Story 5.2 | ✅ Covered |
| FR26 | Function bits F0..F28 | Epic 5 / Story 5.2 | ✅ Covered |
| FR27 | Explicit release | Epic 5 / Story 5.1 | ✅ Covered |
| FR28 | Best-effort acquire (no presence implied) | Epic 5 / Story 5.1 | ✅ Covered |
| FR29 | Subscribe via layout model | Epic 3 / Story 3.2 | ✅ Covered |
| FR30 | `wait_active`/`wait_inactive` w/ timeout | Epic 3 / Story 3.2 | ✅ Covered |
| FR31 | `wait_state(...)` w/ timeout | Epic 3 / Story 3.2 | ✅ Covered |
| FR32 | `wait_change()` w/ timeout | Epic 3 / Story 3.2 | ✅ Covered |
| FR33 | In-flight waits survive reconnect | Epic 3 / Stories 3.2, 3.3 | ✅ Covered |
| FR34 | `JMRIError` hierarchy | Epic 2 / Story 2.1 | ✅ Covered |
| FR35 | Actionable diagnostic context | Epic 2 / Story 2.1 | ✅ Covered |
| FR36 | Structured logging WARN/INFO/DEBUG | Epic 2 / Story 2.1 | ✅ Covered |
| FR37 | No exceptions for undetectable failures | Epic 4 / Story 4.1 | ✅ Covered |
| FR38 | Install via `uv add` / `pip install` | Epic 1 / Story 1.1 + Epic 6 / Story 6.6 | ✅ Covered (end-to-end) |
| FR39 | `uv sync` from source | Epic 1 / Story 1.1 | ✅ Covered |
| FR40 | 5-min getting-started | Epic 6 / Story 6.1 | ✅ Covered |
| FR41 | Jython migration table | Epic 6 / Story 6.3 | ✅ Covered |
| FR42 | Limitations section | Epic 6 / Story 6.2 | ✅ Covered |
| FR43 | Three shipped examples | Epic 6 / Story 6.4 | ✅ Covered |
| FR44 | `py.typed` marker; mypy strict resolves | Epic 1 / Story 1.1 + Epic 6 / Story 6.6 | ✅ Covered (end-to-end) |

### Non-Functional Requirement Coverage Matrix

| NFR | PRD Topic | Epic / Story | Status |
|-----|-----------|--------------|--------|
| NFR1 | Sensor event → wait_* < 100 ms median | Epic 3 / Story 3.2 | ✅ Covered (integration test in AC) |
| NFR2 | Discover < 2 s for ~370 entities | Epic 2 / Story 2.5 | ✅ Covered (integration test in AC) |
| NFR3 | Command overhead < 20 ms over JMRI HTTP | Epic 4 / Story 4.1 | ✅ Covered (microbench in AC) |
| NFR4 | 1-hr unattended; no leaks | Epic 3 / Story 3.4 | ✅ Covered (parameterized to 1-hr mode) |
| NFR5 | ≥5 forced WS disconnects/hr survived | Epic 3 / Stories 3.3, 3.4 | ✅ Covered |
| NFR6 | Bounded exp backoff (0.5 → 30 s) | Epic 3 / Story 3.1 | ✅ Covered |
| NFR7 | Python 3.11+ requirement | Epic 1 / Story 1.1 | ✅ Covered (pyproject + install-time check) |
| NFR8 | JMRI 5.14+ requirement | Epic 2 / Story 2.5 | ✅ Covered (raises `JMRIVersionUnsupported`) |
| NFR9 | macOS + Linux CI gate | Epic 1 / Story 1.3 | ✅ Covered (CI matrix) |
| NFR10 | Default `localhost:12080`; remote requires explicit | Epic 2 / Story 2.1 | ✅ Covered |
| NFR11 | Library introduces no auth; document JMRI's unauthenticated trust model | (claimed by epics for Epic 2; documentation lands in Epic 6 / Story 6.2 — **not explicit**) | ⚠️ Partial — see gap below |

### Coverage Statistics

- Total PRD FRs: **44**
- FRs covered in epics: **44** (**100 %**)
- Total PRD NFRs: **11**
- NFRs fully covered: **10** (**91 %**)
- NFRs partially covered: **1** (NFR11 documentation)

### Reverse-Trace: Items in Epics Not in PRD

None. Every story's FR/NFR claims trace back to a PRD requirement or to an explicit Architecture-derived "Additional Requirement" that the epics doc lists in its own Requirements Inventory (e.g., starter-template choice, transport library selection, internal layering boundaries). No scope creep into Growth/Vision: Operations, Warrants, LogixNG, Dispatcher, CLI utilities, oblock/layoutBlock/reporter, function bits > F28, and sections are all correctly absent from the MVP epics.

### Deliberate Omissions (PRD-aligned, correctly excluded)

| Excluded item | Rationale |
|---|---|
| Power write | PRD: booster-governed hardware; software cannot control. |
| Internal-sensor write | PRD: covered by memory writes (FR18). |
| Sections | PRD: not exposed by JMRI JSON v5. |
| Operations / Warrants / LogixNG / Dispatcher | PRD: Growth/Vision deferred. |
| CLI utilities | PRD: Growth deferred. |
| Function bits > F28 | PRD/Story 5.2: Growth deferred (decoder-specific, e.g., ScaleTrains). |
| Higher entity types (oblock, layoutBlock, reporter, idTag, audio, configProfile, time, panel, train, engine, location, consist) | PRD: Growth deferred. |
| Headless-JMRI CI for integration tests | Story 1.3 / 6.5: integration tests local-only for v1; Growth-deferred. |

### Identified Gaps

**Minor — NFR11 documentation not explicitly listed in Story 6.2 acceptance criteria.**

- **Gap:** NFR11 requires the library's documentation to "state clearly" that JMRI's web server is unauthenticated and intended for trusted-network use, so users do not assume otherwise. The epics doc's Epic 2 header claims to "support" NFR11, but Epic 2 is implementation, not documentation. The natural home is Story 6.2 (Limitations section), whose AC enumerates five plain-English topics (NCE open-loop, optimistic acks, no power write, best-effort throttle acquire, sensors-as-real-observable) — but **does not include the "no auth / trusted-network only" topic**.
- **Impact:** Low. The information is in the PRD; a developer writing the README will likely include it. But without an explicit AC, it could ship missing, leaving a security-posture surprise for users.
- **Recommendation:** Add a sixth bullet to Story 6.2's "Then it explains, in plain English" list: *"(f) the library introduces no authentication of its own; JMRI's web server is unauthenticated by design and intended for trusted-network use — do not expose it to untrusted networks."*

No critical or high-priority gaps. All 44 FRs have a clear story-level home with concrete, testable acceptance criteria.

## Step 4 — UX Alignment

### UX Document Status

**Not Applicable.** No UX document exists, and none is required.

### Justification (PRD-aligned)

The PRD's *Developer Tool Specific Requirements → Skipped Sections* states explicitly:

> *Visual design / UI — `pyjmri` has no GUI. Logging and CLI output are the only user-visible surfaces.*

`pyjmri` is a developer-tool library (`projectType: developer_tool`). Its user-visible surfaces are:

| Surface | Treated as | Coverage |
|---|---|---|
| The Python API (types, method signatures, docstrings) | "API UX" | FR3, FR8, FR9, FR11, FR13–FR16, FR21–FR28, FR29–FR33, FR44 + every story's Google-docstring requirement |
| README (Quickstart / Limitations / Migration table) | Documentation UX | Epic 6 / Stories 6.1, 6.2, 6.3 |
| Log output (level discipline; structured `extra={}`) | Operator UX | FR36 + Story 2.1 logging foundation |
| Exception messages (actionable diagnostic strings) | Failure-mode UX | FR4, FR34, FR35 + Story 2.1 exception hierarchy |

Each of these is covered by a story with concrete acceptance criteria.

### CLI Utilities (`pyjmri-status`, `pyjmri-discover`, `pyjmri-throttle`)

The PRD lists these under **Growth Features (Post-MVP)** — explicitly not in v1. No CLI stories appear in the MVP epics, and that is correct.

### Alignment Issues

None.

### Warnings

None.

### Architecture-supports-UX check

Not applicable — there is no UX. The architecture is wholly supportive of the four "API/docs/logs/exceptions" surfaces above (single async event loop, Protocol-typed handles, NullHandler logger setup, exception hierarchy with `context: dict`, Google-style docstring discipline, `__all__` everywhere).

## Step 5 — Epic Quality Review

Validated 6 epics and 22 stories against best-practice standards: user value, epic/story independence, no forward dependencies, sizing, AC quality, and starter-template handling.

### Epic Independence (forward-dependency check)

| Epic | Independently valuable end-state? | Depends on (backward) | Forward refs found? |
|------|-----------------------------------|------------------------|---------------------|
| 1 | A developer can `uv add pyjmri`, types resolve, CI runs (empty stub) | none | None |
| 2 | A user can connect, discover, and read every entity (read-only is a viable end-state) | Epic 1 | None |
| 3 | A user can subscribe and `await` state changes; reconnect resilience | Epics 1–2 | None |
| 4 | A user can issue commands (default optimistic; opt-in `wait_for_jmri_state` uses Epic 3) | Epics 1–3 | None |
| 5 | A user can drive locomotives via throttles | Epics 1–4 | One soft forward ref in Story 5.3 → Story 6.5 (minor; see below) |
| 6 | A new user reads README, runs examples, installs from PyPI | Epics 1–5 | One soft forward ref in Story 6.1 → Story 6.6 (minor; see below) |

**Verdict:** No critical forward dependencies. Epic ordering is monotonically backward-only.

### User Value Check (Epic-by-Epic)

| Epic | Title is technical? | User-value framing in goal? | Verdict |
|------|----|----|---------|
| 1 | "Buildable, Type-checked Library Foundation" — sounds technical | "A developer can install pyjmri…" frames the developer-as-user explicitly | ✅ Acceptable for `developer_tool` projectType — installability and type-resolution *are* the first user-facing capabilities for a library |
| 2 | "Connect to JMRI and Discover the Layout" | Strong | ✅ |
| 3 | "Subscribe to State Changes and Wait Asynchronously" | Strong | ✅ |
| 4 | "Command Layout Entities" | Strong | ✅ |
| 5 | "Drive Locomotives via Throttles" | Strong | ✅ |
| 6 | "Ship to the Community" | Strong | ✅ |

### Story Sizing & Acceptance Criteria

- **AC quality is exceptional.** Every story uses Given/When/Then BDD format consistently. Each story has 5–9 AC blocks covering happy path, error/edge cases, type-check verification, integration-test markers, and architectural-invariant audits (e.g., "no `httpx` import outside `_transport.py`," "no hardcoded entity names," "no `asyncio.create_task` outside the supervising TaskGroup").
- **Sizing:** Stories are appropriately sized for solo-developer cadence. The two largest (Story 2.1, Story 5.1) bundle tightly-coupled concerns in a way that splitting would create more friction than it saves.
- **Within-epic dependencies:** All linear and backward-only. Story N.k uses Stories N.1…N.(k-1) — no leapfrogging.

### Starter Template Compliance

- **Architecture specifies a starter:** `uv init --lib --name pyjmri` (Astral first-party scaffold).
- **Epic 1, Story 1.1 IS that starter setup story.** ✅ AC explicitly references the command and the resulting `src/`-layout, `uv_build` backend, `py.typed`, `.python-version`.

### Greenfield Indicators

- Initial project setup story: ✅ Story 1.1.
- Quality gate config: ✅ Story 1.2.
- CI/CD set up early: ✅ Story 1.3 (third story in Epic 1).
- LICENSE + README scaffolded for community release: ✅ Story 1.4.
- Project context is "greenfield code, brownfield environment" — `python_code/` empty; integration with running JMRI handled in Epic 2+.

### Database / Entity-Creation Timing

N/A — pyjmri stores no persistent state. JMRI is the system of record.

### Detailed Quality Findings

#### 🔴 Critical Violations

**None.**

#### 🟠 Major Issues

**None.**

#### 🟡 Minor Concerns

1. **Story 5.3 contains an AC block that belongs in Story 6.5.**
   - **Location:** Story 5.3 ("Multi-throttle integration test"), the AC starting "Given a hardware-mode validation protocol is also required, When `CONTRIBUTING.md` (Epic 6) is written, Then it documents a release-time procedure…"
   - **Issue:** This AC describes content to be authored in `CONTRIBUTING.md`, which is the deliverable of Story 6.5, not Story 5.3. Story 5.3 is about the simulator-mode integration test plus *defining* the hardware-mode protocol; *documenting* the protocol in CONTRIBUTING.md is Story 6.5's job (and Story 6.5 already references "hardware-mode throttle validation per Story 5.3").
   - **Impact:** Minor. Both stories agree on what gets done; placement is the only issue.
   - **Recommendation:** Move the "Given a hardware-mode validation protocol… CONTRIBUTING.md is written…" AC block from Story 5.3 to Story 6.5 (or duplicate-with-cross-reference). Story 5.3's responsibility ends at *establishing* the protocol; Story 6.5 *documents* it.

2. **Story 6.1's full acceptance verification gates on Story 6.6.**
   - **Location:** Story 6.1, AC "Given a clean Python 3.11+ environment with JMRI running and `pyjmri` installed from PyPI (post Story 6.6)…"
   - **Issue:** The Quickstart's content can be authored before publishing, but the "5 minutes from `uv add pyjmri`" timing AC is fully verifiable only after PyPI publication.
   - **Impact:** Minor. The dependency is acknowledged inline. No real ordering problem — just an integration-verification gate.
   - **Recommendation:** Add a one-line note at the top of Story 6.1 stating "Implementable independently; final 5-minute timing verification gates on Story 6.6." Optional polish.

3. **NFR11 documentation absent from Story 6.2 acceptance criteria** (already flagged in Step 3).
   - **Recommendation:** Add bullet (f) to Story 6.2's plain-English Limitations list: "*The library introduces no authentication of its own; JMRI's web server is unauthenticated by design and intended for trusted-network use — do not expose it to untrusted networks.*"

4. **Story 5.1's keep-alive coroutine ships as a possibly-no-op stub pending hardware verification.**
   - **Location:** Story 5.1, "the implementation tolerates the v1 reality that keep-alive necessity is verified on hardware (Story 5.3) — if hardware shows it is unnecessary, the coroutine may ship as a no-op stub but the structure is in place for activation."
   - **Issue:** The AC "keep-alive task starts on acquire and is cancelled on release" is satisfiable by the stub. The functional question — *does JMRI's WiThrottle actually need keep-alive heartbeats?* — is deferred to a hardware-mode observation in Story 5.3 / Story 6.5's release procedure.
   - **Impact:** Minor and pragmatic. This matches the recorded throttle-simulator blind-spot reality. The structure exists; the parameter is a tunable.
   - **Recommendation:** Add an AC to Story 5.1: *"Given hardware-mode observation results from Story 5.3 are not yet available, When the keep-alive coroutine is implemented, Then a TODO comment on `Throttle._keepalive` records the open question and a default behavior is documented (no-op stub vs. active heartbeat) so the maintainer's chosen default is explicit, not implicit."*

5. **Stories 2.1 and 5.1 are larger than typical.**
   - Story 2.1 bundles HTTP transport + Client lifecycle + exception hierarchy + logging foundation.
   - Story 5.1 bundles Throttle async context manager + acquire/release + keep-alive supervision.
   - **Impact:** Minor. For a solo developer working from the architecture document, the bundling reduces inter-story friction. AC blocks for each concern are individually testable. This is a stylistic choice, not a defect.
   - **Recommendation:** Leave as-is unless a future contributor needs more granular slicing. No action required.

### Best Practices Compliance Checklist (per epic)

| Epic | User value | Independent | Stories sized | No forward deps | Clear ACs | FR traceability |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 2 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 3 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 4 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 5 | ✅ | ✅ | ✅ | ⚠️ minor (AC placement) | ✅ | ✅ |
| 6 | ✅ | ✅ | ✅ | ⚠️ minor (verification gate) | ✅ | ✅ |

## Step 6 — Final Assessment

### Overall Readiness Status

# ✅ READY (with minor polish)

The pyjmri planning corpus (PRD + Architecture + Epics with embedded stories) is **implementation-ready**. Phase 4 (development per `bmad-dev-story` / `bmad-quick-dev`) can begin immediately, optionally addressing the four minor polish items below — none of which block starting Story 1.1.

### What Makes This Corpus Ready

- **100 % FR coverage** (44 / 44) and **91 % full NFR coverage** (10 / 11; one minor documentation gap on NFR11).
- **No critical or major epic-quality violations.** Epic ordering is monotonically backward-only; every story has rich Given/When/Then ACs covering happy path, errors, edge cases, type-checking, and architectural-invariant audits.
- **Honest scope discipline.** PRD's "deliberately omitted" items (power write, internal-sensor write, sections, ops/warrants/LogixNG, F29+ function bits, CLI utilities, additional entity types) are uniformly absent from MVP epics. No scope creep.
- **Traceability to architecture is explicit.** Stories cite specific architecture decisions (TaskGroup discipline, transport/domain boundary, `_codes`/`_parsing` privacy, `Mapping` protocol on `EntityCollection`, dual-name lookup with collision rule, `process_exception` hook on `websockets.connect()`).
- **Project-context fit:** starter template (`uv init --lib`) is concrete; CI matrix is path-scoped to `python_code/**` so it doesn't churn on JMRI panel/roster/Jython commits (matches the recorded preference); no JMRI mocks (matches recorded constraint); layout-agnosticism enforced as an architectural invariant in every relevant story (matches the recorded preference that the library targets only Basement_Revised_2024.jmri's runtime contract, not its specific entity names).
- **Realism about hardware.** Throttle-simulator blind spot is acknowledged head-on: Story 5.3 separates simulator-mode plumbing tests from a hardware-mode physical-correctness protocol, and Story 6.5 makes the hardware run a release-checklist line item.

### Minor Polish Items (recommended, non-blocking)

1. **Add NFR11 disclosure to Story 6.2 ACs.** Add bullet (f): *"The library introduces no authentication of its own; JMRI's web server is unauthenticated by design and intended for trusted-network use — do not expose it to untrusted networks."* Closes the only NFR partial-coverage item.

2. **Move the "Given a hardware-mode validation protocol… CONTRIBUTING.md is written…" AC block from Story 5.3 to Story 6.5.** Keeps Story 5.3 strictly about test code; keeps Story 6.5 the single home for CONTRIBUTING.md content. Both stories already cross-reference each other.

3. **Add a one-line note to Story 6.1's header:** "Implementable independently; final 5-minute timing AC gates on Story 6.6." Eliminates ambiguity about whether 6.1 can start before 6.6.

4. **Add an AC to Story 5.1** capturing the keep-alive-stub-vs-active decision: *"Given hardware-mode observation results from Story 5.3 are not yet available, When the keep-alive coroutine is implemented, Then a TODO comment on the keep-alive method records the open question and the chosen v1 default (stub vs. active heartbeat) is documented explicitly."* Makes the deferred decision visible rather than implicit.

### Recommended Next Steps

1. **Apply the four polish items** above (≈30 minutes of editing in `epics.md`). Optional but tidy.
2. **Begin implementation at Story 1.1** (`bmad-dev-story` against `epics.md` Story 1.1, or `bmad-quick-dev`).
3. **Sprint-plan or proceed linearly.** With 22 stories and a solo cadence, you can simply work top-down through the epics. If you want a tracked sprint structure, run `/bmad-sprint-planning`.
4. **CI early.** Story 1.3 lands the GitHub Actions matrix. Don't push Stories 2.1+ before 1.3 is green — every later integration test relies on the local-skip pattern that 1.3 establishes.
5. **Hardware-mode test rehearsal.** Before Story 5.3, do a dry run on the basement layout once (any throttle, any loco) so the keep-alive observation step in Story 5.3 / 6.5 isn't blocked by an unrelated NCE/USB issue at release time.

### Issue Summary

- 🔴 Critical: **0**
- 🟠 Major: **0**
- 🟡 Minor (polish): **4** (one NFR doc bullet, one AC placement, one header note, one TODO-tracking AC)
- ⚠️ Coverage gaps: **0 FR**, **1 NFR partial** (subsumed in minor #1)

### Final Note

This is one of the cleanest planning packages I've reviewed. The PRD numbers requirements; the Architecture pins them to concrete library/file/module decisions; the Epics trace every requirement to a story with testable ACs; the Stories enforce architectural invariants as audit-style ACs. The honest-semantics discipline (open-loop NCE, `unknown` first-class, no false-positive confirmations) is woven through every layer instead of being a footnote. Phase 4 (implementation) can begin immediately.

---

**Assessor:** Implementation Readiness check (`bmad-check-implementation-readiness` skill).
**Date:** 2026-05-06.
**Inputs assessed:** `prd.md`, `architecture.md`, `epics.md` (stories embedded). UX: N/A by design.

