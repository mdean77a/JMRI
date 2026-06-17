# Sprint Change Proposal — Decouple Roster Discovery from Layout

- **Date:** 2026-06-17
- **Author:** Mikey (with Claude, correct-course workflow)
- **Epic:** 9 — Capability-Aware Roster (Read-Only), v1.2
- **Scope classification:** Moderate (reimplementation of a reviewed story + targeted revert; planning artifacts updated)
- **Status:** Approved — handed off to dev-story for reimplementation

## 1. Issue Summary

During code review of Epic 9 (Stories 9.1 and 9.2, both in `review`), the architectural decision to **fold the roster into `Client.discover()`/`Layout`** was reconsidered and reversed.

The roster is a read-only, non-subscribed, point-in-time snapshot — structurally identical to the Operations subsystem (Epic 8), which is discovered through its own `Client.discover_operations()` method. Folding the roster into `discover()` instead of giving it a parallel `discover_roster()` method created avoidable complexity that exists *only* to make the fold safe:

- **`_fetch_roster_isolated()`** — a bespoke "never raises" wrapper required because the roster shared `discover()`'s `asyncio.TaskGroup`, where any real exception would cancel the eight sibling layout fetches (the FR57 failure-isolation requirement).
- **A layout↔roster import cycle** — worked around in `layout.py` with a `TYPE_CHECKING` declaration plus a function-local lazy import.
- **WS-index carve-outs** — explicit "deliberately NOT in `_ENTITY_SPECS` / NOT in `self._entities`" comments.

The decisive evidence: the FR55 reversal (2026-06-16) made the roster **not** a runtime dependency of throttles (an unknown address warns-and-drives). With no hard dependency forcing the roster onto `Layout`, it is a free-standing reference subsystem — exactly like Operations. Modelling it as a standalone `discover_roster()` deletes all the above complexity and makes the two read-only snapshot subsystems symmetric.

**Issue type:** reconsideration of an original design decision (not a technical failure or new requirement).

## 2. Impact Analysis

### Epic Impact
- **Epic 9** remains valid and completable; same FR set (FR51–FR59). The "Key divergence from Epic 8" framing **inverts** into "Alignment with Epic 8."
- Epics 1–8 are unaffected. No resequencing. MVP (v1.0, shipped) is unaffected.

### Story Impact
- **Story 9.1** (parser + `RosterEntry`/`FunctionLabel`): paradigm-agnostic; **deliverables unchanged**. Three forward-looking references updated for accuracy. Stays in `review`.
- **Story 9.2** (the fold): **rewritten** as a standalone `discover_roster()` spec and reset `review` → `ready-for-dev`. The `roster.py` `Roster` container (`EntityCollection[RosterEntry]` + `by_address` + first-wins collision) is **reused unchanged**; the fold in `client.py`/`layout.py` is reverted. File renamed to `9-2-discover-roster-standalone-by-address-graceful-degrade.md`.
- **Stories 9.3 / 9.4** (backlog): premises re-pointed off `Layout`. `throttle_for_entry` moves to `Client`; examples call `discover_roster()`.

### Artifact Conflicts (all resolved in this proposal)
- **prd.md** — FR57 reframed (graceful-degrade + structural isolation), NFR2 (roster off the `discover()` bound), FR12 (roster moved to `discover_roster()`/FR51), increment intro, Journey 6 narrative + code, API coverage + Public types, FR51 collection reference, change-log. (13 edits.)
- **epics.md** — Epic List summary + NFR line + Notes, FR-inventory intro, tech-requirements block, Epic 9 intro/scope, "Alignment with Epic 8" (inverted), full Story 9.2 rewrite, Stories 9.3/9.4 references, FR57 coverage-map brief, change-log.
- **architecture.md** — new "Roster Subsystem (Read-Only)" decision section (mirror of Operations, records the rejected fold), FR51–FR59 requirements mapping, directory-tree touch-ups, discover() minimum-coverage list, change-log. (Additive — architecture predated Epic 9.)
- **UX** — N/A (pyjmri has no GUI).

### Technical / Code Impact (the dev-story handoff)
- `client.py` — delete `_fetch_roster_isolated`; remove the roster task + return from `discover()`; add `async def discover_roster() -> Roster` (mirror `discover_operations()`); graceful-degrade as a method-level `try/except`.
- `layout.py` — revert: remove the `roster` attribute, the `TYPE_CHECKING` import, and the lazy import-cycle workaround.
- `roster.py` — **no change** (container reused).
- `__init__.py` — **no change** (`Roster` stays exported).
- `tests/unit/test_discover_roster.py` — rewritten to drive `discover_roster()`.
- `tests/integration/test_discovery.py` — roster timing moved onto `discover_roster()`.

## 3. Recommended Approach

**Direct Adjustment with targeted reimplementation of Story 9.2.** Selected over a full rollback because Story 9.1 and the `roster.py` container are fully reusable, and over an MVP review because the MVP already shipped. The change **net-removes** complexity (deletes the TaskGroup wrapper and the import cycle) and improves cross-epic symmetry. Risk is **Low**: the reverted/rewritten code is unreleased (Story 9.2 was in `review`, never merged to a release), and the reused container is unchanged.

**Design decisions (Mikey, 2026-06-17):**
1. `discover_roster()` **keeps graceful-degrade** — a fetch failure returns an empty `Roster` + WARNING rather than raising (preserves FR57's spirit at the method boundary).
2. `throttle_for_entry` lives on **`Client`** (it already owns throttle acquisition); a `RosterEntry` argument needs no roster, while name/address resolution against a `Roster` is a Story 9.3 design detail.

## 4. Detailed Change Proposals

All artifact edits enumerated in §2 have been **applied** to `prd.md`, `epics.md`, `architecture.md`, the two story files, and `sprint-status.yaml`. The rewritten Story 9.2 (`9-2-discover-roster-standalone-by-address-graceful-degrade.md`) is the authoritative re-implementation spec, including the exact `discover_roster()` shape, the revert checklist (AC-11), and the rewritten test plan.

## 5. Implementation Handoff

- **Scope:** Moderate.
- **Route to:** Developer agent (dev-story) on `9-2-discover-roster-standalone-by-address-graceful-degrade`.
- **Responsibilities:** revert the `client.py`/`layout.py` fold; add `Client.discover_roster()`; rewrite the roster unit + integration tests; keep `roster.py` and the `Roster` export unchanged; run all gates (`ruff check`, `ruff format --check`, `mypy --strict src/pyjmri`, `pytest -m "not integration"`).
- **Out of scope (Story 9.3):** `Client.throttle_for_entry`, capability classification, startup example.
- **Success criteria:** AC-1…AC-11 met; `python -c "import pyjmri"` clean with no layout↔roster cycle; full suite green; no hardcoded fleet facts in `src/`.
- **Then:** Story 9.2 returns to `review` for the code review that triggered this correction; Story 9.1 proceeds through its own review unchanged.

## 6. Sprint Status Changes

- `9-2-fold-roster-into-layout-discover-by-address-failure-isolation` (review) → renamed `9-2-discover-roster-standalone-by-address-graceful-degrade` (**ready-for-dev**).
- `9-1` unchanged (`review`). `9-3`/`9-4` unchanged (`backlog`). `epic-9` remains `in-progress`.
