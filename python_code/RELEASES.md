# pyjmri release notes

## v1.2.1

Bug-fix release. No API changes — no new public names, no changed
signatures, no behavior changes to code that was already working.

- **`discover()` no longer discards a whole layout over one bad entity.**
  A single signal mast in a non-basic signalling system (e.g. British
  BR-2003, aspects "Danger"/"Off") raised `JMRIProtocolError` out of
  `discover()`, throwing away every turnout, sensor, and route already
  fetched. The per-entity build loop now logs the offending entity at
  WARNING and skips it, mirroring the resilience the WebSocket dispatch
  path already applied to the same parsers. The mast is omitted from the
  `Layout`; the rest of the layout is returned. Verified against a real
  BR-2003 layout: 73 turnouts / 123 sensors / 49 routes returned, 24
  masts skipped with a warning each. Reported and fixed by
  [@honzup](https://github.com/honzup) (PR #3) — the first outside
  contribution to pyjmri. The skip is deliberately narrow: a companion
  regression test asserts that a non-`JMRIProtocolError` raised during
  parse/build still propagates out of `discover()` rather than being
  swallowed behind a warning and a silently truncated `Layout`.

- **Fixed a subscription race that made a second `Client` in the same
  process miss its first `wait_change()` event** roughly half the time.
  Two cooperating defects:
  - `SubscriptionRegistry.ensure()` was fire-and-forget — it sent the
    subscribe frame and returned before JMRI had processed it and
    attached its event listener, so a state change commanded immediately
    after `ensure()` could go silently unobserved. `ensure()` now waits
    (bounded, 2 s) for JMRI's ack — the entity envelope echoed back on
    the WebSocket — released via a new `notify_envelope()` hook called
    from the Client's WS dispatch. On timeout it warns and degrades to
    the previous behavior rather than failing the call.
  - `WSConnection.run()` never closed the socket on cancellation, leaving
    it to the garbage collector. JMRI's delayed cleanup of the stale
    connection widened the race window for the next `Client`. `run()`
    now closes the active connection in a `finally`.

- **Integration tests no longer toggle real layout sensors.** A new
  `provisioned_internal_sensor` fixture PUTs a unique in-memory internal
  sensor per test (never saved to the panel) instead of hard-pinning
  `IS1` ("NW Staging Close") and `IS2`, which on the basement layout
  drive real staging-yard routes. Both affected tests now also prime the
  subscription before their measured loops.

- **New `scripts/smoke_test_published.sh`** — builds a throwaway uv
  project outside the repo, installs the published wheel from PyPI, and
  asserts version, imports, the roster API, and the presence of every
  discover routine. Passing a JMRI URL as the second argument adds a live
  sweep of all discover routines with per-entity counts. README gains a
  matching read-only "Verify your install" smoke test.

JMRI version tested against: JMRI 5.14.0

Long-run test: skipped for this release; v1.0.0 evidence reused
(`duration=3600s disconnects=5 reconnects=5 rss_delta=-5.1MB fd_delta=0
task_delta=0 status=PASS`). **This reuse is weaker than in v1.0.1 and
v1.2.0**, both of which left the transport untouched: v1.2.1 does modify
`_subscriptions.py` and `_transport.py`, the exact machinery the long-run
test characterizes. The substituted evidence is what the fix itself was
validated against — two-client repro 8/8 (previously ~50% failure),
the integration suite run 5× consecutively clean, and a 5-minute
reconnect soak green — plus a clean full integration suite (23 passed,
2 skipped) at release time. A full one-hour long-run should be treated
as owed against the next release that touches this code.

Hardware-mode validation (release-checklist step 6): waived. v1.2.1
changes no throttle code — the diff is confined to the discovery and
subscription paths — so the v1.0.1 observation stands (JMRI keeps the
throttle held after 30 s silence; the v1 no-op keep-alive stub remains
correct).

## v1.2.0

Adds read-only discovery of JMRI's Roster (DecoderPro catalog) subsystem
(Epic 9). No changes to existing Epic 1–7 behavior — purely additive.

> Note: v1.1.0 was prepared but never published (see below), so this is also
> the **first published build to include the read-only Operations subsystem**
> (Epic 8): `Client.discover_operations()`, the `Operations` container, and the
> `Location`/`Train`/`Car`/`Engine` entity classes. See the v1.1.0 section for
> the Operations release notes.

- New `Client.discover_roster()` returns a typed, read-only `Roster`
  container enumerating every catalogued locomotive, looked up by roster
  name (`roster[name]`) or DCC address (`roster.by_address(addr)`).
- Two read-only entity classes (`RosterEntry`, `FunctionLabel`) exposing
  each entry's identity (road number, model), addressing, decoder
  identifiers (family/model), per-function labels, and owner/comment
  metadata.
- The roster is the complete DecoderPro catalog — distinct from
  Operations (the operationally-active subset deployed on the layout) and
  from the live `Layout`. Read-only in this release: no decoder-programming
  or CV-write surface (deferred to a future command increment).
- `Client.throttle_for_entry(target)` acquires a throttle straight from a
  `RosterEntry`, roster name, or DCC address, deriving long/short
  addressing from the matched entry. An address **not** in the roster
  warns and still drives best-effort (FR55); an unresolvable name raises.
- Capability classification (`classify_capability()`,
  `firable_startup_functions()`) infers what a loco can do from its
  function **labels**, never from decoder-family strings.
- A roster fetch failure or an empty roster degrades to an empty `Roster`
  rather than raising (FR57), structurally isolated from `discover()`.
- New examples `examples/roster_catalog.py` (a fleet-catalog report) and
  `examples/capability_aware_startup.py`, plus a README Roster section.

JMRI version tested against: JMRI 5.14.0

Long-run test: skipped for this release; v1.0.0 evidence reused
(`duration=3600s disconnects=5 reconnects=5 rss_delta=-5.1MB fd_delta=0
task_delta=0 status=PASS`). Epic 9 adds only read paths (HTTP discovery +
parsing) plus an additive throttle convenience built on the existing
acquire path; it does not touch the WebSocket transport, reconnect
machinery, or supervised-task plumbing, so the v1.0.0 long-run result
still characterizes the same code.

Hardware-mode validation: not required. The roster is a pure read-only
metadata subsystem with no throttle/DCC or physical-state dependency. The
`capability_aware_startup.py` example's "visibly correct startup" check
(sound actually plays, loco actually moves) remains an optional manual
hardware step, not a release gate.

(Published 2026-06-18)

## v1.1.0

> **Never published — superseded by v1.2.0.** This version was prepared
> (Story 8.3: version bump, notes, build) but Phase B was skipped: no PyPI
> upload, git tag, or GitHub release was ever made. The Operations feature
> documented here first reached PyPI inside **v1.2.0**. These notes are kept
> as the Operations release record.

Adds read-only discovery of JMRI's Operations subsystem (Epic 8). No
changes to existing Epic 1–6 behavior — purely additive.

- New `Client.discover_operations()` returns a typed, read-only
  `Operations` container enumerating locations, trains, cars, and
  engines, looked up by name like a `Layout` collection.
- Four read-only entity classes (`Location`, `Train`, `Car`, `Engine`)
  plus nested value objects (`Track`, `Placement`, `RouteStop`),
  exposing each entity's operational state (a car's location and train
  assignment; a train's route and position; an engine's deployment).
- Operations is the operationally-active subset actually deployed on the
  layout — distinct from the roster (the DecoderPro catalog). Read-only
  in this release: no build-train / move-assign-car / generate-manifest
  surface (deferred to a future command increment).
- A layout with no Operations data configured discovers empty
  collections rather than raising (FR50).
- New example `examples/operations_report.py` (a "where is every car"
  report) and a README Operations section.

JMRI version tested against: JMRI 5.14.0

Long-run test: skipped for this release; v1.0.0 evidence reused
(`duration=3600s disconnects=5 reconnects=5 rss_delta=-5.1MB fd_delta=0
task_delta=0 status=PASS`). Epic 8 adds only read paths (HTTP discovery +
parsing); it does not touch the WebSocket transport, reconnect
machinery, or supervised-task plumbing, so the v1.0.0 long-run result
still characterizes the same code.

Hardware-mode validation: not required. Operations is a pure read-only
data subsystem with no throttle/DCC or physical-state dependency; the
Operations integration tests run fully against the NCE simulator with
Operations data loaded. No throttle code changed in this release.

(Not published — folded into v1.2.0; see the note above.)

## v1.0.1

Security-pass cleanup; no API changes.

- Make the JMRI version-string parser tolerant of build suffixes (e.g.
  `5.14+Rdea51dcccf`); previously such versions raised
  `JMRIProtocolError` and blocked `discover()`.
- Document the plaintext-HTTP default and the TLS opt-in path on
  `Client` so callers know when to pass `https://` / `wss://`.
- Add `SECURITY.md` with a private-disclosure policy and threat-model
  scope.

JMRI version tested against: JMRI 5.14.1

Long-run test: skipped for this release; v1.0.0 evidence reused
(`duration=3600s disconnects=5 reconnects=5 rss_delta=-5.1MB fd_delta=0
task_delta=0 status=PASS`). No source changes in v1.0.1 touch the
WebSocket transport, reconnect machinery, or supervised-task plumbing,
so the v1.0.0 long-run result still characterizes the same code.

Hardware-mode validation (release-checklist step 6): drive and
keep-alive scripts both passed against the basement layout, DCC 1032,
on JMRI 5.14.1 / NCE USB / 2026-06-02. JMRI keeps throttle held after
30 s silence — v1 no-op keep-alive stub remains correct.

(Published 2026-06-02)

## v1.0.0

JMRI version tested against: JMRI 5.14.1

Long-run test result (Story 3.4): pyjmri long-run: duration=3600s disconnects=5 reconnects=5 rss_delta=-5.1MB fd_delta=0 task_delta=0 status=PASS

Hardware-mode keep-alive observation (Story 5.3): JMRI keeps throttle held after 30 s silence on JMRI 5.14.1 / NCE USB / 2026-05-26.

(Published 2026-05-26)
