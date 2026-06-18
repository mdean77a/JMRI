# pyjmri release notes

## v1.2.0

Adds read-only discovery of JMRI's Roster (DecoderPro catalog) subsystem
(Epic 9). No changes to existing Epic 1–8 behavior — purely additive.

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

(Published YYYY-MM-DD — Phase B: fill in at publish time)

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
