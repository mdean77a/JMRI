---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain-skipped', 'step-06-innovation-skipped', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
date: '2026-05-05'
lastEdited: '2026-06-09'
editHistory:
  - date: '2026-05-06'
    changes: 'Validation polish: lifted date into frontmatter; reframed httpx/websockets implementation hints; sharpened NFR9 CI-scope contract; added Assumed JMRI JSON Contract subsection.'
  - date: '2026-06-09'
    changes: 'Promoted read-only Operations discovery (locations, trains, cars, engines) from Vision to active v1.1 Growth scope. Added FR45–FR50, Journey 5, Operations JSON-contract endpoints, NFR2 Operations bound; narrowed Exec Summary/Vision deferral to Operations command features only. Roster-vs-Operations distinction made explicit.'
releaseMode: phased
inputDocuments: []
documentCounts:
  briefs: 0
  research: 0
  brainstorming: 0
  projectDocs: 0
classification:
  projectType: developer_tool
  domain: general
  domainFlavor: iot / process-control
  complexity: medium
  projectContext: greenfield-code-brownfield-environment
workflowType: 'prd'
---

# Product Requirements Document - JMRI

**Author:** Mikey
**Date:** 2026-05-05

## Executive Summary

`pyjmri` is a modern, async-only Python 3.11+ client library and automation
framework for JMRI (Java Model Railroad Interface). It lives outside JMRI as a
normal Python process, discovers any layout by querying JMRI's JSON web
service, and exposes a typed runtime model plus async primitives that mirror
the conceptual building blocks JMRI users already know from Jython —
sensors, turnouts, throttles, memories, routes, signals — but as proper
asyncio operations with honest, optimistic command semantics that respect the
open-loop reality of the underlying DCC hardware.

The target user is a JMRI layout owner who wants to automate their layout in
modern Python rather than the deprecated Jython 2.7 that JMRI currently
embeds. v1 covers the primitives needed to write programs analogous to the
existing `jython/Mike*.py` examples (route traversal, multi-loco
sequencing, sensor-driven back-and-forth running). A post-v1.0
increment adds **read-only discovery of JMRI's Operations subsystem**
(locations, trains, cars, engines) as its own typed surface, distinct
from the layout model and from the roster. Operations *command*
features (train build, car movement, manifest generation), Warrants,
LogixNG, and full Dispatcher integration remain deferred.

The library is the author's tool first and a JMRI-community release second.
It is layout-agnostic by construction: it carries zero assumptions about the
author's basement layout and works against whatever layout the running JMRI
has loaded.

### What Makes This Special

- **External-process Python 3, not in-JVM Jython.** Type hints, `asyncio`,
  real packaging, `pytest`, modern IDEs, and AI-assisted editing all become
  available — none of which Jython 2.7 supports.
- **JMRI's JSON web service is the only integration surface.** The library
  reads no panel XML and embeds no JMRI internals. Every capability is
  grounded in what JMRI already exposes to network clients, keeping the
  library aligned with JMRI's stable network contract rather than its
  internal file format.
- **Async-only API.** Long-running event-driven programs (sensor
  subscriptions, multi-train sequencing, interlocking logic) are the primary
  workload. The Jython `AbstractAutomaton` `init()`/`handle()` polling
  pattern is replaced by first-class `asyncio` with WebSocket-driven
  subscriptions.
- **Honest, optimistic command semantics.** Commands return when JMRI
  has acknowledged them; the library does not pretend to confirm physical
  layout state, because the user's DCC hardware (NCE) is open-loop —
  there is no feedback path from a commanded turnout back to JMRI.
  `unknown` is a first-class state, surfaced to scripts rather than
  silently coerced. Sensors (block occupancy, etc.) remain the real
  observable for event-driven waits.
- **Runtime model from JSON discovery.** Connect to a running JMRI; the
  library enumerates all turnouts, sensors, blocks, lights, memories,
  routes, signal heads, signal masts, and roster entries via the JSON
  API and exposes them as typed Python objects. No code-generation
  step, no XML parser to maintain. (Sections are not exposed by JMRI's
  JSON API and are correspondingly out of scope.)

The core insight: JMRI's JSON web service is now a sufficient integration
surface to drive a layout end-to-end from outside the JVM. That single
fact unlocks the modern Python ecosystem for layout automation without
requiring any change to JMRI itself.

## Project Classification

- **Project Type:** `developer_tool` — a Python 3 client library (with
  optional CLI utilities) acting as an external client of JMRI's web
  service; effectively a JMRI client SDK.
- **Domain:** `general`, with strong IoT / process-control flavor.
  Real-time sensors, actuators, signals, and blocks on a physical or
  simulated model railroad. No regulatory regime.
- **Complexity:** medium. Load-bearing concerns are async network
  programming, WebSocket subscription state, and command-vs-observed-state
  reconciliation under network and timing variability.
- **Project Context:** greenfield code, brownfield environment.
  `python_code/` is empty, but the library must integrate with a
  long-running JMRI instance and a fully-built layout. Primary
  development target: the `Basement_Revised_2024.jmri` profile
  (38 blocks / no sections / ~45 locos), connecting to either real
  NCE hardware or NCE simulation depending on which machine launched
  JMRI — a distinction the library is required to be transparent to.
- **Distribution:** planned PyPI release for the JMRI community as a
  single package with flat module structure (`pyjmri.client`,
  `pyjmri.layout`, plus per-entity modules — see Developer Tool
  Specific Requirements). CLI utilities are deferred to Growth.

## Success Criteria

### User Success

- A new user installs with `uv add pyjmri` (or equivalent), points at a
  running JMRI's host:port, and has a connected, fully-enumerated, typed
  layout model in **under 5 minutes**.
- A user can write a 30-line Python 3 program that does what
  `jython/MikeBackAndForth.py` does (subscribe to two sensors, drive a
  loco between them) — async, type-checked, no `AbstractAutomaton`
  boilerplate, no Jython 2.7 syntax.
- A long-running automation script runs **up to one hour unattended**,
  surviving transient WebSocket drops via auto-reconnect with
  subscription restoration, without leaking coroutines, file handles,
  or memory.
- `unknown` is exposed as a real state in the typed model. When the
  library reads turnout/sensor state at startup and finds `unknown`, it
  surfaces that to the script rather than coercing to a known value.
  Scripts can therefore be written with the assumption that JMRI has
  already been initialized to a known state, and detect when that
  assumption is false.
- Commands are honest: when `await turnout.throw()` returns, the library
  has confirmed only that JMRI accepted the command. It does not pretend
  the layout physically moved (NCE is open-loop). This is documented up
  front, not buried.
- Throttle acquisition is best-effort and documented as such: a
  successful "acquire" does not imply a locomotive at that DCC address
  is physically present or responsive.
- The library behaves identically against real NCE hardware and the
  NCE simulator — same command path, same library API. Only physical
  outcomes (which we don't pretend to observe anyway) differ.

### Business Success (community-OSS reframing)

- **Author utility:** v1 is useful enough to the author that he writes
  *new* automation for `Basement_Revised_2024.jmri` in `pyjmri` going
  forward. Existing Jython scripts may continue to coexist; this is a
  modern-Python *option*, not a forced replacement.
- **Distribution:** the library is published on PyPI as `pyjmri` under
  the MIT license, with a public source repository and a contribution
  guide.
- **Community signal:** within 6 months of v1 release, at least one
  independent JMRI user runs the library against their own layout and
  files structured feedback (issue, discussion, or blog post). This is
  a qualitative signal, not a vanity metric.

### Technical Success

- Async correctness: zero blocking I/O in the event loop. Type-checked
  with `mypy --strict` (or equivalent); linted clean with `ruff`.
- Dependency management: `uv` is the canonical project tool;
  `pyproject.toml` + `uv.lock` are the source of truth.
- Resilience: WebSocket auto-reconnect with exponential backoff;
  subscription state restored after reconnect; no stuck-throttle
  states. Verified against forced-disconnect tests over a one-hour run.
- API coverage (v1): turnout, sensor, block, light, memory, route,
  signalHead, signalMast (read-only), throttle, power, roster,
  rosterEntry — read paths and (where applicable) command paths.
- API coverage (post-v1.0, read-only): Operations `location`, `train`,
  `car`, `engine` — enumerated as a typed subsystem distinct from the
  roster, exposing operational state (e.g., a car's current location
  and train assignment). Read paths only; no build, move, or manifest.
- `unknown` state is round-tripped correctly through the typed model
  for every entity that JMRI can report as unknown.
- Test suite: unit tests for all primitives; integration tests run
  against a real JMRI instance launched with `Basement_Revised_2024.jmri`
  (which auto-selects NCE simulator on the development machine).
- Supported runtimes: Python 3.11+, macOS and Linux (Windows
  best-effort). Requires JMRI 5.14 or later.

### Measurable Outcomes (v1 acceptance)

- ≥3 example programs ported from `jython/Mike*.py` and runnable
  against `Basement_Revised_2024.jmri`.
- Continuous one-hour multi-train automation run completes without
  manual intervention, including a forced mid-run WebSocket disconnect.
- New-user "first turnout flip" walkthrough completes in ≤5 minutes
  including install via `uv`.
- All command failure modes that the library *can* detect (server
  reject, WebSocket disconnect, request timeout, malformed response)
  raise a typed exception covered by tests. Failure modes the library
  *cannot* detect (loco missing at DCC address, turnout failed to
  physically move) are explicitly documented as out-of-scope.

## Product Scope

### MVP — Minimum Viable Product

**Connectivity**
- HTTP client and WebSocket client (specific library choices left to implementation)
- Configurable host:port; default `localhost:12080`
- Async-only; single `Client` owning HTTP + WS connections
- Auto-reconnect on WebSocket failure, with subscription restoration

**Discovery (read-only at startup)**
- Enumerate, via JSON API, the entity types: turnout, sensor, block,
  light, memory, route, signalHead, signalMast, roster, rosterEntry
- Build a typed runtime model with both `name` (system name) and
  `userName` lookup
- Expose `power` state as a top-level property
- Surface `unknown` states explicitly; do not coerce or hide them

**Control & Read**
- Read current state of every enumerated entity (including `unknown`)
- Read power state (read-only; layout power is governed by the
  booster's hardware power and is not under software control on the
  supported environment)
- Set state where applicable: turnout (closed/thrown), light (on/off),
  memory (string value)
- Activate a route by name (where supported by JMRI)

**Throttles**
- Acquire by DCC address with explicit long/short flag
- Set speed (0..1 float), direction (forward/reverse), function bits
  F0..F28
- Release / context-manager lifecycle to prevent stuck-throttle leaks
- Best-effort semantics; documented limitation that "acquire" does not
  imply physical loco presence

**Eventing**
- WebSocket-driven state-change subscriptions per entity
- `await sensor.wait_active()`, `wait_inactive()`, `wait_state(...)`,
  `wait_change()` primitives with timeouts (sensors are the real
  observable)
- Equivalent for any other entity that emits state-change events,
  understanding that for command-only entities the events reflect
  JMRI's commanded state, not physical state

**Command Semantics**
- Optimistic by default: `await turnout.throw()` returns when JMRI has
  acknowledged the command. The library does not block waiting for
  physical confirmation that does not exist.
- Optional opt-in: `wait_for_jmri_state=True` causes the call to wait
  for JMRI to report the new commanded state via WebSocket — useful for
  composed operations like "set route" where you want to see the
  cascade of turnout commands settle in JMRI's model. Documented as a
  view of *JMRI's* state, not the layout's.
- Typed exceptions: `JMRIConnectionError`, `JMRIRequestTimeout`,
  `LayoutEntityNotFound`, etc. No exceptions for things the library
  cannot detect (e.g., absent locomotive, turnout that physically
  failed to move; NCE has no feedback path of any kind).

**Packaging & Quality**
- `pyjmri` on PyPI; MIT license
- `pyproject.toml`; `uv` as the project tool; type-hinted; `py.typed`
- README + getting-started + API reference + 3 worked examples ported
  from `Mike*.py`
- `pytest` test suite + integration harness

### Growth Features (Post-MVP)

- Additional entity coverage: oblock, layoutBlock, reporter, idTag,
  audio, configProfile, time, panel, consist
- **Read-only Operations discovery (active v1.1 increment):** enumerate
  JMRI's Operations subsystem — locations, trains, cars, engines — as
  typed read-only objects carrying operational state. Distinct from the
  roster, which catalogs every DecoderPro-programmed engine the user
  owns; Operations entities are the operationally-active subset actually
  on the layout. Command, build, move, and manifest operations stay in
  Vision.
- Higher-level patterns library: asyncio analogs of common Jython
  automation patterns (back-and-forth, route-traversal, multi-loco
  sequencer)
- CLI utilities: `pyjmri-status`, `pyjmri-discover`, `pyjmri-throttle`,
  shipped as entry points in the same package
- Friendlier error messages with diagnostic hints (e.g., "throttle
  rejected; is the layout power on?")
- Optional structured logging integration; optional OpenTelemetry
  tracing
- Hosted documentation site (Sphinx or MkDocs)
- Contribution guidelines, issue templates, CI badges

### Vision (Future)

- Operations *command* integration — train build, car movement,
  manifest generation, schedules — as a first-class subsystem, building
  on the read-only Operations discovery delivered in Growth
- Warrants integration via `oblock` + `signalMast` types
- LogixNG bridge or modern-Python replacement
- Dispatcher integration (sections, automatic block control) — sections
  exposed only if/when JMRI exposes them via JSON
- Interactive Jupyter notebook integration with notebook-friendly
  helpers
- Optional code-generated typed layout module (deferred ADR-3 option)
- Sensor-event recording and replay for offline test/simulation
- Multi-JMRI federation (multiple layouts, multiple connections from
  one client process)

## User Journeys

### Journey 1 — Mike, the author: porting his first Jython script

**Who:** Mike, the author and primary user. Runs an N-scale basement
layout, ~45 locos, 38 blocks, no sections. Has a Jython codebase he
wrote between 2019 and 2024. Wants modern Python.

**Opening:** Mike sits down on a Tuesday evening with `pyjmri` v0.1
installed and `Basement_Revised_2024.jmri` running on his office
laptop (NCE simulator). He opens his old `MikeBackAndForth.py` —
forty lines of Jython using `AbstractAutomaton`, `init()`, `handle()`,
and global `sensors` / `turnouts` lookups. He's done with that.

**Action:** He types:

```python
async with Client("localhost:12080") as jmri:
    layout = await jmri.discover()
    fwd = layout.sensors["Block 1"]
    rev = layout.sensors["Block 6"]
    async with layout.throttle(5327, long=True) as loco:
        while True:
            loco.set_speed(0.4, forward=True)
            await fwd.wait_active()
            loco.set_speed(0.4, forward=False)
            await fwd.wait_inactive()
            await rev.wait_active()
```

**Climax:** `python my_script.py` from his terminal — not from inside
JMRI's script window. The loco starts moving. He gets type-checking
in his editor while writing it. When he typos `"Block 1"` as
`"Block 12"` (no such sensor), pyjmri raises `LayoutEntityNotFound`
at lookup, not three minutes into the run when `wait_active` would
have hung silently.

**Resolution:** What was 60+ lines of Jython is 12 lines of Python 3.
He commits it to `python_code/` and starts on the next port.

**Capabilities revealed:** `Client` connection lifecycle (async
context manager); `discover()` returning a typed `Layout`; sensor and
throttle lookup with fail-fast errors; throttle as async context
manager; `wait_active`/`wait_inactive` on sensors; clean exit on
`Ctrl-C`.

### Journey 2 — Mike runs a multi-train evening session

**Who:** Same Mike, now using pyjmri for real. It's a Friday night,
trains running for company. He starts a multi-loco script that
sequences three trains around different loops, each with its own
sensors and routes.

**Opening:** Mike runs `python evening_session.py` and walks away to
the kitchen for an hour.

**Rising action:** Around minute 23, his Wi-Fi router reboots (the
office machine is on Wi-Fi). The pyjmri WebSocket disconnects.

**Climax:** pyjmri logs `JMRIDisconnected — backing off, retrying`
and starts the exponential-backoff reconnect. Eight seconds later
it re-establishes the WebSocket, **re-subscribes to the same set of
sensors and turnouts** that the script was watching, and hands the
script back its in-flight `await sensor.wait_active()` calls — they
just keep waiting. The locos kept moving the whole time (commands
were already on the rails before the disconnect; new commands queued
in JMRI's command station are fine).

**Resolution:** Mike comes back from the kitchen. The script is
still running. He never knew anything happened until he checks the
log next morning.

**Capabilities revealed:** WebSocket auto-reconnect; subscription
restoration after reconnect; structured logging at the right level
(WARN for transient, INFO for routine); long-running stability up
to one hour; in-flight `wait_*` calls survive reconnects.

### Journey 3 — A new user, Python developer, no Jython history

**Who:** Sarah. Active on the JMRI users list, runs an HO layout,
strong Python developer at her day job, has read about JMRI's
Jython scripting but has never written one because Python 2.7 is a
nonstarter for her. Hears about pyjmri on the list.

**Opening:** Sarah opens a fresh terminal. Her JMRI is running with
her own panel file loaded. She runs:

```bash
uv add pyjmri
```

and opens the README.

**Action:** She follows the 5-minute getting-started:

```python
from pyjmri import Client
import asyncio

async def main():
    async with Client() as jmri:
        layout = await jmri.discover()
        print(f"{len(layout.turnouts)} turnouts, "
              f"{len(layout.sensors)} sensors, "
              f"{len(layout.roster)} locos")
        for t in list(layout.turnouts.values())[:5]:
            print(t.name, t.user_name, t.state)

asyncio.run(main())
```

**Climax:** It prints actual data from her layout. She didn't have
to read panel XML, didn't have to learn JMRI's internal naming
conventions first; her existing layout names just *appeared* in
Python objects with type hints her IDE could autocomplete on.

**Resolution:** She writes a 15-line script that flips a single
turnout. It works. She decides this is worth investing in and starts
porting her ideas — none of which she ever wrote in Jython — to
pyjmri.

**Capabilities revealed:** `uv add` distribution path; zero-config
defaults (`Client()` with no args defaults to `localhost:12080`);
discovery returns iterable typed collections; `name` and `user_name`
exposed; reasonable `__repr__` / printable values for state enums;
no JMRI-XML knowledge required to be productive.

### Journey 4 — Failure modes: when things actually go wrong

**Who:** Any user. The "things break" journey.

**Scene A — JMRI isn't running.**
User runs their script. pyjmri attempts to connect. It fails fast with
`JMRIConnectionError: could not connect to localhost:12080 — is JMRI
running with the web server enabled?` — not a 30-second hang, not a
generic `ConnectionRefusedError`.

**Scene B — the layout is in `unknown` state at startup.**
JMRI is fresh-started. The user forgot to run his initialize-turnouts
script first. The pyjmri user does:

```python
turnout = layout.turnouts.by_user_name("South Turnout 100")
if turnout.state is TurnoutState.UNKNOWN:
    raise RuntimeError("Layout not initialized — "
                       "run init_turnouts before this script")
```

`unknown` is a real state in the enum, surfaced at the API. The user
is forced to think about it. The library does not silently treat it
as `closed`.

**Scene C — ghost throttle.**
User acquires throttle 5327. The loco at 5327 is on the workbench,
not the layout. pyjmri reports no error (it can't — NCE is
open-loop, and the command station has no feedback path of any kind:
it just emits DCC packets onto the rails regardless of whether the
target accessory or decoder physically exists). Commands send. The
loco doesn't move. The user looks at the layout, realizes the loco
is on the bench. The pyjmri docs section on "Limitations" explicitly
says this can happen — and explains *why* (NCE has no feedback, so
the library cannot detect missing or unresponsive locos, accessories,
or anything else on the DCC bus). The user is annoyed at themselves
but not at the library.

**Capabilities revealed:** clear connection-failure message; first-
class `unknown` state in enums; documented limitations as a real
README section explaining the open-loop NCE reality, not an apology
buried at the bottom.

### Journey 5 — Mike inspects his Operations session from Python

**Who:** Same Mike, now running a prototypical operating session. He
has JMRI's Operations module configured: locations (his yards, towns,
and staging), a fleet of cars, the engines actually on the layout, and
several trains with assigned routes. He wants to *see* the operational
picture from Python — not from JMRI's GUI tables — so he can build his
own reports and, later, feed automation decisions.

**Opening:** Mike opens a Python REPL against his running JMRI. His
roster has ~45 engines (everything he ever programmed in DecoderPro),
but only a handful are on the layout tonight. He doesn't want the
roster — he wants what's *operating*.

**Action:** He writes:

```python
async with Client() as jmri:
    layout = await jmri.discover()
    ops = await jmri.discover_operations()
    print(f"{len(ops.locations)} locations, {len(ops.trains)} trains, "
          f"{len(ops.cars)} cars, {len(ops.engines)} engines")
    for train in ops.trains:
        print(train.name, "→", train.current_location)
    for car in ops.cars:
        print(car.road_number, "at", car.location, "on", car.train)
```

**Climax:** It prints the *operational* truth: four engines on the
layout (not the 45 in the roster), each car's current location and
train assignment, each train's position along its route. The roster
never knew which engines were deployed; Operations does. Mike now has
the live operating state as plain typed Python objects.

**Resolution:** He writes a 20-line script that prints a "where is
every car" report at the start of each session. He notes the obvious
next want — *moving* cars and *building* trains from Python — and is
content that read-only inspection shipped first and is solid.

**Capabilities revealed:** `discover_operations()` returning a typed
Operations container distinct from `Layout`; read-only enumeration of
locations, trains, cars, engines; operational state per entity
(location, train assignment, route position) that the roster cannot
provide; empty collections (not errors) when no Operations data is
configured; clear read-only boundary — no build/move surface in this
increment.

### Journey Requirements Summary

| Capability | From journeys |
|---|---|
| Async `Client` with context manager and zero-config defaults | 1, 3, 4 |
| Layout discovery returning typed collections | 1, 3 |
| Both system name and user name lookup | 1, 3 |
| Throttle as async context manager; speed / direction / functions | 1, 2 |
| Sensor `wait_active` / `wait_inactive` / `wait_change` with timeouts | 1, 2 |
| WebSocket auto-reconnect with subscription restoration | 2 |
| In-flight `wait_*` calls survive reconnects | 2 |
| `uv add` distribution path | 3 |
| `unknown` as a first-class state in enums | 4 |
| Fail-fast lookup errors (`LayoutEntityNotFound`) and connection errors (`JMRIConnectionError`) | 1, 4 |
| Connection-failure messages with actionable hints | 4 |
| Documented limitations (open-loop NCE, no presence detection, no command-bus feedback at all) as README content | 4 |
| Structured logging at WARN/INFO levels | 2 |
| One-hour unattended stability target | 2 |
| Read-only Operations discovery (locations, trains, cars, engines) as a typed subsystem distinct from the roster | 5 |
| Operational state per entity (location, train assignment, route position) the roster cannot provide | 5 |
| Empty Operations collections (not errors) when no Operations data is configured | 5 |

## Developer Tool Specific Requirements

### Project-Type Overview

`pyjmri` is a Python 3 client library distributed as a single package on
PyPI, consumed by Python developers writing scripts and long-running
programs against a JMRI instance. It is not a CLI-first product, not a
service, not a multi-language SDK, and not a JMRI plugin. It targets a
small but technically capable audience: model-railroad hobbyists who
write code.

### Language and Runtime Matrix

- **Python:** 3.11+. No support for Python 2.7 (Jython is the past,
  not a peer).
- **Operating systems:** macOS and Linux are first-class development
  targets. Windows is not deliberately tested but is expected to work
  — `pyjmri` is a thin Python web client over an HTTP/JSON + WebSocket
  surface that JMRI itself supports cross-platform, so platform-
  specific failures are unlikely. The project will accept reasonable
  Windows fixes from contributors but commits no proactive testing
  effort to it for v1.
- **JMRI:** requires JMRI 5.14 or later, communicating over the JSON v5
  API. JMRI versions before 5.14 are not supported. If a future JMRI
  release shifts the JSON contract, the library issues a clean error
  rather than silently misbehaving.

### Installation Methods

- **Primary:** `uv add pyjmri` (project consumers using `uv`).
- **Alternative:** `pip install pyjmri` (for users on traditional
  Python tooling).
- **Source / contributor:** `git clone … && uv sync` (development
  install via `uv` with `pyproject.toml` dependencies).
- All paths land at the same code; PyPI is the canonical channel.

### Public API Surface (Illustrative, Not Locked)

Module layout is illustrative for v1; final names are subject to
implementation review.

```
pyjmri/
├── __init__.py     # re-exports: Client, Layout, common enums/exceptions
├── client.py       # Client (HTTP + WebSocket connection lifecycle)
├── layout.py       # Layout (typed runtime model from discovery)
├── turnout.py      # Turnout, TurnoutState
├── sensor.py       # Sensor, SensorState
├── block.py        # Block, BlockState
├── light.py        # Light, LightState
├── memory.py       # Memory
├── route.py        # Route
├── signal.py       # SignalHead, SignalMast (read-only in v1)
├── throttle.py     # Throttle (async context manager)
├── roster.py       # Roster, RosterEntry
├── exceptions.py   # JMRIError hierarchy
└── automaton.py    # higher-level patterns (Growth; may be a stub in v1)
```

Public types each user will routinely touch:

- `Client` — connection lifecycle (async context manager); methods
  `discover()`, `subscribe(...)`, plus per-entity convenience.
- `Layout` — typed container of all enumerated entities, indexed by
  both system name and user name.
- `Turnout`, `Sensor`, `Block`, `Light`, `Memory`, `Route`,
  `SignalHead`, `SignalMast` — each carrying state, identity, and
  async methods (`get_state()`, `set_state()`, `wait_state()`,
  `wait_change()` where applicable).
- `Throttle` — async context manager; `set_speed(value, forward)`,
  `set_function(n, on)`, `release()`.
- State enums — `TurnoutState.{UNKNOWN, CLOSED, THROWN, INCONSISTENT}`,
  `SensorState.{UNKNOWN, ACTIVE, INACTIVE, INCONSISTENT}`, etc.
- Exception hierarchy — `JMRIError` base, with concrete subclasses for
  connection, timeout, and lookup failures.

### Code Examples (Shipped with v1)

Three worked examples, plus a README quickstart:

1. **`hello_jmri.py`** — connect, enumerate, print first 5 turnouts.
   The 5-minute getting-started.
2. **`back_and_forth.py`** — port of `jython/MikeBackAndForth.py`.
   Single loco, two sensors, async wait pattern.
3. **`multi_train_session.py`** — `asyncio.gather` of multiple
   per-loco coroutines, each with its own sensor subscriptions.
   Demonstrates the Journey 2 use case.

All examples are runnable against `Basement_Revised_2024.jmri` (which
auto-selects NCE simulator on the development machine) without
modification.

### Migration Guide (from Jython)

A documented mapping from common Jython idioms to pyjmri, shipped as
a section of the v1 documentation:

| Jython | pyjmri |
|---|---|
| `sensors.provideSensor("Block 1")` | `layout.sensors["Block 1"]` |
| `turnouts.getTurnout("NT400")` | `layout.turnouts["NT400"]` |
| `routes.getRoute("Crossover")` | `layout.routes["Crossover"]` |
| `memories.provideMemory(name).getValue()` | `await layout.memories[name].get()` |
| `self.getThrottle(5327, True)` | `async with layout.throttle(5327, long=True) as t:` |
| `throttle.setSpeedSetting(0.4)` | `t.set_speed(0.4)` |
| `throttle.setIsForward(True)` | `t.set_speed(0.4, forward=True)` |
| `throttle.setF2(True)` | `t.set_function(2, True)` |
| `self.waitSensorActive(s)` | `await s.wait_active()` |
| `self.waitSensorInactive(s)` | `await s.wait_inactive()` |
| `self.waitMsec(ms)` | `await asyncio.sleep(ms / 1000)` |
| `AbstractAutomaton` `init()` / `handle()` | top-level `async def` + `asyncio.run(...)` |

The migration guide is a documentation section, not a separate
deliverable. Its purpose is reducing porting friction for users
with existing Jython code (including the author).

### Implementation Considerations

- **Single async event loop.** The `Client` owns one event loop's
  worth of connections; users don't manage HTTP and WebSocket
  separately. Threading is not a v1 concern; if a user wants to
  call pyjmri from a synchronous context (e.g., from a Jupyter
  cell), they wrap in `asyncio.run`.
- **No global state.** Everything hangs off the `Client` / `Layout`
  instances. No module-level connections. This matters for
  testability and for users who might run two `Client`s against
  two JMRI instances (deferred to Vision; v1 design must not
  preclude it).
- **Type-checked at strict mypy level.** This is the audience —
  developers who care — and a primary point of differentiation
  from Jython.
- **Tests run against a real JMRI process.** Integration tests run
  against `Basement_Revised_2024.jmri` (NCE simulator on the
  development machine). **No JMRI mocks.** Mocking JMRI's JSON
  contract — across HTTP responses, WebSocket subscription
  semantics, command-station behavior, and version evolution —
  would require more engineering than the rest of the library
  combined, and would still drift from real JMRI. Unit tests cover
  library internals that don't touch JMRI (response parsing,
  state-machine logic, reconnect/backoff timing). Anything that
  requires JMRI uses the integration harness.

### Assumed JMRI JSON Contract

The library binds to JMRI's JSON v5 web service surface. The v1
implementation depends on the following entity-type endpoints being
exposed by JMRI's web server:

- `turnout`, `sensor`, `block`, `light`, `memory`, `route`,
  `signalHead`, `signalMast` — read state, set state (where
  applicable), and subscribe to state-change events
- `roster`, `rosterEntry` — read locomotive metadata and identifiers
- `power` — read layout-power state
- `throttle` — acquire by DCC address, set speed / direction /
  function bits, release
- `location`, `train`, `car`, `engine` — read-only Operations
  subsystem discovery (post-v1.0); enumerate and read operational
  state. Not subscribed to or commanded in this increment.

If a future JMRI release renames, removes, or changes the JSON shape
of any of these endpoints, the library fails at the affected
operation with a typed error (see FR4, FR34, NFR8) rather than
silently misbehaving. This list is the authoritative blast-radius
checklist when reviewing JMRI upgrades.

### Skipped Sections (Not Applicable)

- **Visual design / UI** — `pyjmri` has no GUI. Logging and CLI
  output are the only user-visible surfaces.
- **Store compliance** — `pyjmri` is distributed via PyPI; no app
  store reviews apply.

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**Approach:** Problem-solving MVP. The MVP is defined by the smallest
set of primitives that lets the author write programs equivalent to
the existing `jython/Mike*.py` suite — and lets a Python-fluent JMRI
user write similar programs of their own — entirely outside JMRI's
JVM. It is not a platform MVP (we are not building extension points
for others) and not a revenue MVP (this is community OSS). The
faster we hit the threshold of "Mike can replace his Jython scripts
and Sarah can write her first one," the faster we get real feedback
against the JMRI JSON contract and the asyncio runtime in practice.

**Resource model:** Solo developer (the author). No team, no fixed
deadlines. This means MVP cuts must be honored — anything not in
the MVP scope must wait for actual time to exist, not be promised
on a phantom roadmap. The phased structure (MVP → Growth → Vision)
is sequenced in priority order, not date order.

**Phased delivery is intentional.** The full feature space is large;
shipping it as a single release would push a working library months
out for a solo developer. Cutting at MVP gets a working library into
the author's own use quickly, validates the JSON-API + asyncio
architecture against a real layout, and sets up community feedback
before Growth-phase work begins.

### MVP Feature Set (Phase 1)

The MVP feature set is fully specified in **Product Scope → MVP —
Minimum Viable Product** above. Mapped to the journeys it supports:

- **Connectivity, discovery, and read/write of core entities**
  (turnout, sensor, block, light, memory, route, signalHead,
  signalMast, throttle, power, roster, rosterEntry) — supports
  Journey 1 (porting), Journey 3 (new-user onboarding), and
  Journey 4 (failure modes).
- **WebSocket subscriptions with auto-reconnect** and in-flight
  `wait_*` survival — supports Journey 2 (multi-train evening
  session).
- **Optimistic command semantics + first-class `unknown` state +
  typed exceptions** — supports the honest-API differentiator
  across all journeys.
- **`uv add`-based distribution + 3 worked examples + README
  quickstart + Jython migration table** — supports the
  community-release Business Success criterion.

### Post-MVP Features

**Phase 2 — Growth:** specified in **Product Scope → Growth
Features** above. Covers read-only Operations discovery (locations,
trains, cars, engines — the active v1.1 increment), additional entity
types (oblock, layoutBlock, reporter, idTag, audio, configProfile,
time, panel, consist), higher-level patterns library, CLI utilities,
hosted documentation site, and ergonomic refinements.

**Phase 3 — Vision:** specified in **Product Scope → Vision (Future)**
above. Covers Operations *command* integration (train build, car
movement, manifests, schedules), Warrants, LogixNG, Dispatcher,
Jupyter integration, layout-codegen, sensor recording/replay, and
multi-JMRI federation.

### Risk Mitigation Strategy

**Technical risks**

- *JMRI JSON contract drift between releases.* Mitigation: declare
  JMRI 5.14 as the minimum supported version; document the specific
  JMRI version used for testing each release; if a JMRI upgrade
  breaks the contract, raise a clean error rather than allowing
  silent misbehavior. No JMRI mocks (mocking would cost more than
  the rest of the project).
- *WebSocket subscription / reconnect correctness.* Mitigation:
  forced-disconnect integration tests; one-hour-unattended run as
  an acceptance gate; subscription restoration covered by tests;
  exponential backoff documented and bounded.
- *Async correctness — leaked tasks, deadlocks, blocking I/O.*
  Mitigation: strict mypy; reviews that flag blocking calls;
  task-supervision pattern in `Client`; tests that exercise
  high-concurrency `asyncio.gather` paths.
- *NCE open-loop reality misleading library users.* Mitigation:
  explicit `unknown` state in enums; optimistic semantics
  documented up front; "Limitations" README section; no API shape
  that implies confirmation the library cannot deliver.

**Market / community risks**

Low. The audience is small and niche; there is no commercial
exposure. The realistic downside is "library is published and no
one outside the author uses it." The Business Success "community
signal" target (one independent user filing structured feedback in
6 months) is the canary; if it fails, the library remains useful to
the author and the community release was simply not absorbed.

**Resource risks**

The dominant risk. Solo developer, hobby time. Mitigations:

- MVP cut is firm and small. Anything that smells like Growth gets
  pushed to Growth, not crammed into MVP.
- The author's own basement layout is the v1 acceptance environment
  — no need to coordinate with external testers for the cutover.
- The library remains useful at any partial state: even if Growth
  is never started, MVP solves the author's stated problem.
- If progress stalls, the explicit "Jython coexists with pyjmri"
  stance (from Business Success) means there is no forced migration
  deadline.

## Functional Requirements

### Connection & Session

- FR1: A user script can connect to a JMRI instance by specifying host and port.
- FR2: A user script can use default connection settings (`localhost:12080`) without explicit configuration.
- FR3: A user script can manage `Client` lifecycle as an async context manager so that resources are released deterministically on exit.
- FR4: A user script can detect when JMRI is unreachable and receive a typed connection error including diagnostic context (host, port, suggested cause).
- FR5: The library transparently maintains a WebSocket connection alongside the HTTP connection without exposing two separate clients to the user.
- FR6: The library automatically reconnects to JMRI's WebSocket after a transient disconnect, using a bounded backoff strategy, without intervention from the user script.
- FR7: The library restores all entity subscriptions after a WebSocket reconnect such that in-flight `wait_*` calls in user scripts continue to function across the disconnect.

### Layout Discovery

- FR8: A user script can request a complete layout discovery and receive a typed `Layout` object enumerating all known entities of the supported types.
- FR9: A user script can access enumerated entities by both system name (e.g., `NT400`) and user name (e.g., "Staging NW Turnout 400").
- FR10: A user script can iterate the full collection of any entity type without invoking additional discovery calls.
- FR11: A user script can detect when a requested entity does not exist and receive a typed lookup error rather than `None` or a silent failure.
- FR12: The discovered layout includes, at minimum: turnouts, sensors, blocks, lights, memories, routes, signal heads, signal masts, and roster entries.

### Entity Read

- FR13: A user script can read the current state of any enumerated entity in a typed form (e.g., `TurnoutState.CLOSED`, `SensorState.ACTIVE`).
- FR14: A user script can distinguish `unknown` state from every other state for any entity where JMRI reports unknown.
- FR15: A user script can read the value of any memory by name and receive a typed value.
- FR16: A user script can read the current power state of the layout. (Read-only; see Entity Control note for why power is not controllable.)

### Entity Control

- FR17: A user script can command a turnout to a state (closed or thrown) by name.
- FR18: A user script can set the value of a memory by name.
- FR19: A user script can command a light on or off.
- FR20: A user script can activate a route by name.
- FR21: A user script can choose, per command, to receive only optimistic command-acknowledgement (default) or to wait for JMRI to report the post-command state via WebSocket (opt-in).
- FR22: The library never returns a false-positive confirmation for a command outcome it cannot verify (NCE has no feedback path; the library does not pretend otherwise).

**Deliberately omitted from MVP:**

- *Power control.* Track power on the supported hardware is governed by the booster's physical power, not by software commands routed through JMRI. The library therefore exposes no power-on / power-off operation. Reading power state (FR16) is supported as a status read.
- *Internal-sensor write.* Setting internal sensors as an inter-script signaling mechanism is not in MVP. The use cases that motivated this pattern are covered by memory writes (FR18) where they apply.

### Throttle & Locomotive Control

- FR23: A user script can acquire a throttle for a DCC address, specifying long or short addressing.
- FR24: A user script can manage throttle lifecycle as an async context manager so that throttles are released deterministically on exit.
- FR25: A user script can set throttle speed (0.0..1.0) and direction in a single call.
- FR26: A user script can set throttle function bits F0..F28 individually. (Higher function bits, used by some decoders such as ScaleTrains, are deferred to Growth.)
- FR27: A user script can release a throttle explicitly to free it for other scripts or operators.
- FR28: A successful throttle acquire is documented as best-effort; the library does not imply a locomotive is physically present at the address.

### Event Subscription & Wait Primitives

- FR29: A user script can subscribe to state changes on any state-bearing entity via the layout model, without manual subscription bookkeeping.
- FR30: A user script can `await` a sensor becoming active or inactive, with an optional timeout that raises a typed timeout error when exceeded.
- FR31: A user script can `await` an entity reaching a specific state, with an optional timeout.
- FR32: A user script can `await` the next state change of an entity, regardless of which state it transitions to.
- FR33: A user script's in-flight `wait_*` calls survive a WebSocket reconnect and resume waiting against the restored subscription.

### Error Handling & Diagnostics

- FR34: The library raises typed exceptions from a documented `JMRIError` hierarchy for every error condition the library can detect (connection failure, request timeout, lookup failure).
- FR35: Connection-failure exceptions include actionable diagnostic context (host, port, suggested cause).
- FR36: The library emits structured log events at levels appropriate to severity (WARN for transient/recoverable conditions, INFO for routine state, DEBUG for detail) without forcing any specific logging configuration on the user.
- FR37: The library does not raise exceptions for failure modes it cannot detect (e.g., missing locomotive on the rails, turnout that physically failed to move); such limitations are documented in user-facing materials, not buried.

### Distribution, Documentation & Tooling

- FR38: A user can install the library from PyPI using `uv add` or `pip install`.
- FR39: A contributor can install the library from source using `uv sync` after cloning the repository.
- FR40: A user can read a getting-started guide that takes them from install to a successful turnout flip in five minutes or less.
- FR41: A user can read a Jython-to-pyjmri migration table that maps common Jython idioms to their pyjmri equivalents.
- FR42: A user can read a "Limitations" section that explains what the library can and cannot detect (NCE open-loop, no DCC feedback path of any kind, no power control on this hardware).
- FR43: A user can run three shipped example programs (`hello_jmri.py`, `back_and_forth.py`, `multi_train_session.py`) against `Basement_Revised_2024.jmri` without modification.
- FR44: A developer can use the library against their own user scripts under `mypy --strict` and have all public types resolve cleanly (the library ships a `py.typed` marker).

### Operations (Read-Only Discovery)

- FR45: A user script can enumerate JMRI Operations locations and access each location by both system and user name, receiving a typed read-only object.
- FR46: A user script can enumerate JMRI Operations trains and read each train's read-only operational state (e.g., assigned route and current location) as exposed by JMRI.
- FR47: A user script can enumerate JMRI Operations cars (rolling stock) and read each car's read-only operational state (e.g., current location, assigned train, destination) as exposed by JMRI.
- FR48: A user script can enumerate JMRI Operations engines and read their read-only operational state. Operations engines are a distinct subsystem from the roster (FR12): the roster catalogs every engine the user has programmed in DecoderPro, whereas Operations engines are the operationally-active subset actually deployed on the layout.
- FR49: Operations discovery is read-only in this increment. The library exposes no operation to build a train, move or assign a car, or generate a manifest; those are deferred to Vision (see Product Scope).
- FR50: A layout whose JMRI has no Operations data configured discovers empty Operations collections rather than raising an error; Operations support is layout-agnostic in the same way as the layout-entity discovery in FR8–FR12.

## Non-Functional Requirements

### Performance

- NFR1: Sensor state-change events propagate from JMRI's WebSocket
  message arrival to user-script `wait_*` resolution within 100 ms
  at the median, under steady-state load (idle layout, fewer than
  100 active subscriptions).
- NFR2: Layout discovery against a layout the size of the author's
  basement (~370 entities across the supported types) completes
  within 2 seconds on a current macOS or Linux laptop, against a
  JMRI instance running on the same machine. Read-only Operations
  discovery, where Operations data is configured, completes within an
  additional 1 second for an Operations roster of comparable size
  (up to ~200 cars, ~50 engines, ~25 trains, ~25 locations).
- NFR3: Library overhead on a single command round-trip
  (`await turnout.throw()` → JMRI ack → caller resumes) does not
  exceed 20 ms beyond what JMRI's HTTP response itself takes.

These targets are measured against `Basement_Revised_2024.jmri`
running its NCE simulator on the development machine; real-hardware
latency is additionally bounded by NCE DCC-bus timing, which is out
of the library's control.

### Reliability

- NFR4: A user script subscribed to fewer than 100 entities can run
  unattended for at least one hour against a stable JMRI instance
  without leaking memory, file descriptors, or asyncio tasks.
- NFR5: A user script's in-flight `wait_*` calls survive at least
  five forced WebSocket disconnects per hour without intervention.
  State-change events that occur *during* the disconnect window are
  delivered as the post-reconnect state (i.e., level-triggered, not
  edge-triggered, across a reconnect boundary); this is documented.
- NFR6: WebSocket reconnect attempts use bounded exponential backoff
  with sensible defaults (initial 0.5 s, doubled on each failure,
  capped at 30 s) so that a long JMRI outage does not produce a
  tight reconnect loop.

### Compatibility

- NFR7: The library supports Python 3.11 and later. Older Python
  versions are rejected at install time via `pyproject.toml`
  declarations.
- NFR8: The library supports JMRI 5.14 and later. The minimum
  required JMRI version is documented in the README, and the
  specific JMRI version used for testing each `pyjmri` release is
  recorded in that release's notes.
- NFR9: The library runs on macOS and Linux as first-class
  development targets, gated by automated CI on each release.
  Windows has no CI gate; the library is expected to function on
  Windows (it is a thin Python web client over HTTP/JSON +
  WebSocket, which JMRI supports cross-platform), and the project
  accepts contributor-reported Windows regressions but commits no
  proactive testing effort to Windows for v1.

### Security & Network Posture

- NFR10: The library defaults to `localhost:12080`. Connecting to a
  remote JMRI requires explicit user configuration (host argument).
- NFR11: The library introduces no authentication of its own and
  does not represent itself as providing security. JMRI's web server
  is unauthenticated by design and intended for trusted-network use;
  the library's documentation states this clearly so a user does
  not assume otherwise.

### Categories Deliberately Skipped

- *Scalability* — single-user library against a single JMRI; no
  growth-curve concerns.
- *Accessibility* — no GUI, no public-audience surface.
- *Integration* — entirely covered by Functional Requirements
  (FR1–FR12, FR23 et seq.).
- *Maintainability / code quality* — covered by Technical Success
  criteria above (`mypy --strict`, `ruff` clean, `py.typed`).
