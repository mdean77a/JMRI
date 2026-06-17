---
title: "Product Brief: pyjmri Roster (Read-Only)"
status: "complete"
created: "2026-06-16"
updated: "2026-06-16"
inputs:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/epics.md
  - _bmad-output/implementation-artifacts/deferred-work.md
  - _bmad-output/implementation-artifacts/8-1-operations-wire-format-parsing-and-read-only-entity-classes.md
  - _bmad-output/implementation-artifacts/8-2-operations-container-and-discover-operations-integration.md
  - _bmad-output/implementation-artifacts/8-3-operations-read-only-boundary-example-and-docs.md
  - python_code/src/pyjmri/ (operations.py, _parsing.py, client.py, layout.py, throttle.py, roster.py stub)
  - roster.xml (44-locomotive fleet)
  - JMRI JSON API v5 (/json/v5/roster, rosterEntry, functionKeys) — confirmed from JMRI master source
---

# Product Brief: pyjmri Roster (Read-Only)

## Executive Summary

pyjmri lets Python scripts drive Mike Dean's JMRI layout over the web API — discover turnouts and sensors, command entities, run throttles. But it has a blind spot: it knows nothing about the **roster**, JMRI's catalog of every locomotive owned, regardless of whether the loco is on the layout tonight. To drive a loco today, a script must hardcode a bare DCC address (`throttle(5327)`), with no idea what that engine is, what decoder it carries, or what its function buttons do.

This feature adds a **read-only Roster** to pyjmri: `layout.roster` becomes a queryable collection of `RosterEntry` objects, each exposing a loco's identity (road name/number, model, manufacturer, owner, comment, photo path) and its **function-key map and decoder identifiers** straight from JMRI's JSON API. Two things become possible that aren't today: (1) generating a fleet reference document from a short script, and (2) **capability-aware throttle startup** — looking up the engine you're about to drive and adapting the startup sequence to *that specific decoder*, so a loco whose function keys are labeled "Startup"/"Horn"/"Bell" gets its sound sequence while a loco with only "Headlight" gets a minimal one.

Beyond those two use cases, the roster is the single biggest **ergonomics and adoption** win pyjmri can make: every script, README example, and demo becomes `throttle_for_entry(layout.roster['UP 5327'])` instead of an opaque integer — pick a loco by name, and the library knows what it is.

Now is the right time: v1.0.0 shipped, the read-only-subsystem pattern is proven by Epic 8 (Operations), the JSON wire format is confirmed to carry the function and decoder data we need, and a parser stub already exists. This is a high-leverage addition that closes the gap between "the layout I can see" and "the fleet I own."

## The Problem

When a pyjmri script wants to run a train, it must already know the engine's DCC address as a bare integer. That number carries no meaning. The script can't answer simple questions a human reads off the DecoderPro roster in seconds:

- *Which engine is 5327?* (A UP SD40-2? A switcher?)
- *Does it have sound, or is it motor-only?*
- *What does F9 do on this loco — startup/shutdown, or nothing?*

So two everyday tasks are needlessly hard. **Building a fleet catalog** — "list all 44 locos with their road numbers, decoders, owners, and addresses" — requires reading XML files or clicking through the JMRI GUI by hand, even though the data is one HTTP call away. And **a reusable startup routine is impossible to write correctly**: a sequence that fires F9 (startup) and F2 (horn) is right for a sound loco but meaningless — or wrong — on a motor-only decoder. Without roster data, every startup script is hardcoded per-loco and breaks the moment you swap engines. The cost is friction on the two things Mike does most: surveying the fleet and getting a chosen loco moving.

## The Solution

Add a read-only Roster as a first-class part of the layout model:

- **`layout.roster`** — a `RosterEntry` collection fetched in parallel inside the existing `Client.discover()` call, so there is no new entry point to learn. Roster info is available *while* operating the layout, which is the whole point of folding it into `Layout` (Operations stays a separate concern). Beyond name lookup, the collection supports **lookup by DCC address** (`layout.roster.by_address(5327)`) — the address is the key the operator actually knows, since they may not remember a loco's roster name. The roster fetch is **failure-isolated**: a roster error or timeout degrades to an empty roster and is surfaced as a warning — it must never cancel turnout/sensor/signal discovery that the rest of the layout depends on.
- **`RosterEntry`** — a frozen, read-only object exposing `dcc_address`, `long_address`, `road_name`, `road_number`, `model`, `mfg`, `owner`, `comment`, `image_path`, `max_speed_pct`, `decoder_family`, `decoder_model`, and a **`function_labels`** map (per-function `label` + `lockable` flag) parsed from the JSON `functionKeys` array. (`comment`, `owner`, `image_path`, `max_speed_pct` are already in the wire format and turn the catalog into a maintenance log, value inventory, and photo sheet at near-zero added surface.)
- **`layout.throttle_for_entry(...)`** — a convenience that resolves a `Throttle` from a **DCC address** (the primary path, since the operator may not know names), a roster name, or a `RosterEntry`, deriving long/short addressing from the matched entry. So you write `async with layout.throttle_for_entry(5327) as t:` and get a throttle for whatever loco that address belongs to. **If the address is not in the roster, the call raises a clear error** ("no roster entry for DCC address 5327") rather than silently acquiring an unknown loco — catching the common case of a mistyped address. **Staleness contract:** the entry is a discovery-time snapshot; if a loco is re-addressed in JMRI after `discover()`, the snapshot is stale. This is documented prominently, and re-running `discover()` refreshes it.
- **Capability-aware startup logic** — a documented, testable decision function that classifies a loco primarily from its **function labels** (a key labeled "Startup"/"Sound"/"Horn"/"Bell" implies sound capability), using `decoder_family`/`decoder_model` only as a weak secondary hint, and **falling back to a minimal motor-only startup whenever labels are blank or unrecognized**. Decoder *family strings are definition-file names, not capability tags* — the design does not treat them as authoritative.
- **Two shipped examples** — `roster_catalog.py` (prints the full fleet reference document plus a decoder-family rollup) and a capability-aware-startup script that branches on the classification above to run the right startup sequence for whatever engine you hand it.

The whole subsystem is **read-only**: pyjmri reads roster metadata over JSON, never edits it. Roster editing stays in DecoderPro, where it belongs.

## What Makes This Different

This isn't a new pattern — it's the deliberate reuse of a proven one. Epic 8 (Operations) established the read-only-subsystem template in this codebase: frozen dataclasses, `EntityCollection` dual-name lookup, a read-only boundary test, simulator-testable discovery. Roster slots straight into it.

The unfair advantage is **the data is already in the wire format and the scaffolding already exists**. The JSON `/json/v5/roster` response carries `decoderFamily`, `decoderModel`, and the full `functionKeys` array (label + lockable per F0–F28) — confirmed from JMRI master source — so capability-aware logic needs nothing JMRI doesn't already serve. A `parse_roster_entry` stub from Epic 2 is waiting to be filled, and `roster.py` is an empty module already reserved in the architecture. Low new surface, high confidence — *provided* the capability classification keys off the right signal (labels, not family strings) and the discovery integration is failure-isolated.

## Who This Serves

**Primary user: Mike (and pyjmri users like him)** — a hobbyist running an N-scale layout from Python scripts. He has ~44 locos in the roster but only a handful on the layout in any session. He wants three things this enables:

1. **The fleet surveyor** — writes short report scripts ("what do I own, what decoders, what addresses, what did each cost, what's the known issue?"). Today he reads XML or clicks the GUI; he wants `for loco in layout.roster: print(...)`.
2. **The automation author** — writes a startup routine once and reuses it across engines. The "aha moment" is handing his script a different loco and watching it *do the right thing* — sound startup for the labeled-sound loco, a quiet roll for the motor-only switcher — because it read the loco's function labels instead of being told.
3. **Everyone reading the docs** — pick-a-loco-by-name (`throttle_for_entry(roster['UP 5327'])`) makes every example and demo legible. This is the broadest adoption lever in the feature.

## Success Criteria

- **Catalog works:** `roster_catalog.py` prints all 44 locos with road number, model, decoder, owner, comment, and address from a single `discover()` — no manual XML reading — plus a decoder-family rollup.
- **Capability branch works (simulator-verifiable):** given fixture roster data, the startup logic *issues the correct function commands* — e.g. a fixture with a "Startup"/"Horn" label triggers the sound sequence; a labels-blank fixture triggers the minimal motor-only path. This asserts the decision function and command plumbing on the simulator.
- **Capability branch works (hardware, manual):** on the physical layout, a sound loco and a motor-only loco run visibly different, correct startup sequences. Explicitly a hardware-only check (the NCE simulator has no virtual loco); documented as manual verification, not a CI gate.
- **Ergonomic bridge works:** `layout.throttle_for_entry(5327)` acquires a throttle by DCC address (also accepts a name/entry); the stale-address contract is documented.
- **Address lookup + clear miss:** `layout.roster.by_address(N)` returns the entry; an unknown address (via lookup or `throttle_for_entry`) raises a clear, named error identifying the missing address — proven by test.
- **Failure isolation:** an injected roster-fetch failure leaves the rest of `discover()` fully populated (turnouts/sensors/etc. intact) and yields an empty roster + warning — proven by test.
- **Graceful per-entry degradation:** a malformed roster entry is skipped (not fatal); good entries still load. Covered by an explicit malformed-entry test, alongside empty and partial cases.
- **Zero regression:** existing Epic 1–6 behavior unchanged; `discover()` still passes all current tests, with a stated roster latency budget so the added fetch doesn't materially slow discovery.
- **Quality gates green:** ruff, `ruff format --check`, `mypy --strict` (src + examples), and `pytest -m "not integration"` all pass; new public types exported alphabetically and documented.
- **Read-only enforced:** a boundary test confirms `RosterEntry` and the roster collection expose no mutating methods.

## Scope

**In scope (this pass):**
- `RosterEntry` read-only entity: identity + `owner`/`comment`/`image_path`/`max_speed_pct` + `decoder_family`/`decoder_model` + `function_labels` map.
- `layout.roster` collection fetched in parallel inside `discover()`, **failure-isolated** from the rest of discovery, with `by_address()` lookup alongside name lookup.
- `layout.throttle_for_entry(address | name | entry)` convenience with a clear unknown-address error and a documented staleness contract.
- Capability-classification decision function (label-driven, family-as-hint, minimal-startup fallback).
- Two examples: `roster_catalog.py` (with decoder rollup) and capability-aware startup.
- Tests: fixture-driven parsing pinned to a **captured live `/json/v5/roster` payload**; empty / partial / malformed-entry; failure-isolation; boundary; one layout-specific integration test. Docs + version bump following the Epic 8 release pattern.

**Explicitly out of scope:**
- **Roster groups** — no group-based lookup/filter this pass (JSON exposes them via a separate endpoint; deferred).
- **Any roster mutation** — no creating/editing entries, function labels, or CVs. Read-only only.
- **WebSocket roster subscription** — roster is fetched as a one-shot snapshot; live "watch the roster" is deferred (JMRI supports it). The staleness contract documents the snapshot semantics.
- **Deep decoder capability tree** — we expose decoder identifier strings and infer capability from function labels; we do not model the decoder's CV/feature definitions.
- **`max_speed_pct` auto-clamping in `throttle_for_entry`** — the field is exposed, but wiring it into automatic speed scaling is deferred to a follow-up (noted as a strong candidate).
- **Markdown/HTML catalog output** — text catalog ships; a shareable photo-bearing fleet sheet is a fast follow.
- **F29+ functions** — the throttle path caps at F0–F28 per the existing v1 limitation.

## Risks & Open Questions

- **API-pattern difference (resolved, by design):** roster folds into `Layout` while Operations is standalone (`discover_operations()`). This is intentional — the operator wants roster info *while* operating layout functions, so it belongs on the live `Layout`, whereas Operations is a distinct planning concern. The "pay-nothing-if-unused" tradeoff is accepted and mitigated by failure-isolation + a latency budget.
- **DCC address collisions:** address-keyed lookup assumes addresses are unique across roster entries (true for this fleet). If two entries ever share an address, `by_address` must behave predictably (e.g. surface the ambiguity) rather than silently return one — to be specified at the story level.
- **Capability classification reliability:** function labels are user-entered and often left blank/default; classification will mis-detect any loco the owner didn't curate. Mitigated by the conservative minimal-startup fallback, but the flagship use case is only as good as the label data.
- **Hardware verification gap:** capability-aware startup's physical correctness can only be confirmed on hardware, not the simulator.
- **Wire-format fidelity:** the `function_labels` model must be pinned to a *captured* live JSON payload (including how `visible`/icon fields appear), not assumed from source.

## Vision

If this succeeds, the roster becomes the natural front door to driving the layout from Python: you pick a loco by name, and pyjmri knows what it is and what it can do. The obvious next steps are all additive: **roster groups** (drive "all my switchers"); **`max_speed_pct`-aware throttles** (auto-clamp speed per loco for safety/realism); a **roster↔Operations join** by road+number (connect "the fleet I own" to "the trains I'm running tonight"); a shareable **Markdown/HTML fleet sheet**; an optional **live subscription**; and a community-shared **"startup profile" convention** keyed off decoder/function data, so hobbyists swap startup routines the way they swap DecoderPro decoder definitions. The read-only roster is the foundation that makes all of it possible.
