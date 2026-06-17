# Story 9.2: Discover the roster via a standalone discover_roster() with by_address + graceful-degrade

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **Correct-course reimplementation (2026-06-17).** This story was previously implemented as a *fold* of the roster into `Client.discover()`/`Layout` (see Change Log). That design was reversed (see `_bmad-output/planning-artifacts/sprint-change-proposal-2026-06-17.md`): the roster is now a **standalone read-only subsystem** discovered through `Client.discover_roster()`, mirroring `discover_operations()`. This story reimplements roster discovery on that basis — the working-tree fold (`discover()` roster task, `_fetch_roster_isolated`, `Layout.roster` + import-cycle workaround) must be **reverted** and replaced. The `Roster` container in `roster.py` is paradigm-agnostic and is **reused unchanged**.

## Story

As a library user,
I want `await jmri.discover_roster()` to return a `Roster` — looked up by system name, user name, or DCC address — discovered independently of `discover()`,
so that I can `roster.by_address(5327)`, and a roster hiccup never touches my layout discovery.

## Acceptance Criteria

1. `Client.discover_roster()` issues `GET /json/v5/roster`, parses each envelope via Story 9.1's `parse_roster_entry`, and returns a `Roster` collection. It is a **separate entry point** from `discover()`, mirroring `discover_operations()` — it returns a `Roster`, **not** a `Layout`. (AC-1)
2. The shared cached version gate (`>= 5.14`) is honored: whichever discovery runs first (`discover()`, `discover_operations()`, or `discover_roster()`) probes `/json/v5/networkService`; the result is cached for the Client's lifetime and `discover_roster()` issues **no** second probe. (AC-2)
3. `discover_roster()` does **not** mutate the WebSocket-dispatch entity index (`self._entities`) — it is a non-subscribed snapshot, exactly like Operations (Epic 8). (AC-3)
4. **Graceful-degrade (FR57):** a roster fetch failure or timeout is caught at the `discover_roster()` method boundary; the method returns an **empty** `Roster` with a logged `WARNING` rather than raising. Because `discover_roster()` is a separate call (no shared `asyncio.TaskGroup` with the layout fetches), it is structurally impossible for a roster failure to affect `discover()`. A unit test injects a roster-fetch failure and asserts an empty `Roster` + WARNING. (AC-4)
5. Name/user-name access on the `Roster` collection is Mapping-style (`roster["1029 NW2 Switcher"]`) and raises `LayoutEntityNotFound` on a miss, consistent with the layout collections. (AC-5)
6. A client-side address→entry index backs `by_address(n: int) -> RosterEntry | None`: it returns the matched entry, or `None` (a `get()`-style find, **not** a raise; FR51/FR55 lookup path) and logs an informative `WARNING` naming the address on a miss. (AC-6)
7. The address-collision case (two entries sharing a DCC address) is handled by a **documented first-wins rule** with a logged `WARNING`. (AC-7)
8. An empty JMRI roster yields an empty `Roster` collection (not an error; FR58), and an individual **malformed** entry is skipped with a logged `WARNING` while the good entries still load (per-entry skip-and-continue). (AC-8)
9. An integration test against `Basement_Revised_2024.jmri` (NCE simulator) calls `discover_roster()` and asserts the ~44-entry roster is populated within ~1 second (the NFR2 roster bound); test entries are pinned by attribute filter (`next(e for e in ... if ...)`), never positional `[0]`; the test is marked `@pytest.mark.integration` and skips cleanly if JMRI is unreachable. (AC-9)
10. **Layout-agnosticism:** no hardcoded roster name, DCC address, or count appears anywhere in `src/pyjmri/` — discovery operates on whatever JMRI returns. (AC-10)
11. **Fold fully reverted:** `Layout` no longer carries a `roster` attribute; `layout.py` no longer imports `Roster` (the `TYPE_CHECKING` declaration and the lazy/function-local import added by the prior implementation are removed); `discover()` no longer fetches or returns the roster; `_fetch_roster_isolated` is removed (its logic moves into `discover_roster()`). `python -c "import pyjmri"` still succeeds and there is no longer a layout↔roster import cycle. (AC-11)

## Tasks / Subtasks

- [x] **Task 1 — `Roster` container in `roster.py` (REUSE — verify unchanged)** (AC: 5, 6, 7)
  - [x] The prior implementation already added `class Roster(EntityCollection[RosterEntry])` with `by_address` (get-style, warn-on-miss) and the first-wins collision rule + module logger + `"Roster"` in `__all__`. This is paradigm-agnostic — **keep it as-is**. Confirm it still imports `from pyjmri.layout import EntityCollection` (the one true import edge is `roster.py → layout.py`; with the fold reverted, `layout.py` no longer imports `roster.py`, so the cycle is gone — `roster.py`'s import of `EntityCollection` stands alone).
  - [x] Confirm the `Roster` docstring still documents that entries have no user name (`user_name is None`), so `roster[key]` resolves via the roster-ID (system-name) index.

- [x] **Task 2 — Revert the fold in `layout.py`** (AC: 11)
  - [x] Remove the `roster: Roster | None = None` parameter from `Layout.__init__`, the `self.roster` attribute, the `if TYPE_CHECKING: from pyjmri.roster import Roster` declaration, and the function-local lazy `from pyjmri.roster import Roster` import used for the empty default. Revert the `Layout` docstring `Args:` entry for `roster`. After this, `layout.py` has **zero** roster references (back to its pre-9.2 state for the roster).
  - [x] Confirm `python -c "import pyjmri"` succeeds and `mypy --strict src/pyjmri` is clean — there is no longer any layout↔roster cycle to work around.

- [x] **Task 3 — Revert the fold in `discover()` + remove `_fetch_roster_isolated`** (AC: 11)
  - [x] In `discover()`, remove `roster_task = tg.create_task(_fetch_roster_isolated(http))` from the `asyncio.TaskGroup` block, remove `roster=Roster(roster_task.result())` from the returned `Layout(...)`, and remove the roster-specific "deliberately NOT in `_ENTITY_SPECS`" comment that the fold added. Restore the `discover()` docstring (drop the roster paragraph).
  - [x] Delete `async def _fetch_roster_isolated(...)`; its fetch + per-entry skip-and-continue logic moves into `discover_roster()` (Task 4).

- [x] **Task 4 — Add `Client.discover_roster()`** (AC: 1, 2, 3, 4, 8)
  - [x] Add `async def discover_roster(self) -> Roster` to `client.py`, modelled on `discover_operations()` (client.py ~:787). Body: raise `RuntimeError` if `self._http is None`; run the cached version gate (reuse the existing `self._version_checked` probe — **no** second probe, AC-2); then fetch + parse the roster.
  - [x] **Graceful-degrade (AC-4):** wrap the fetch + parse in `try/except Exception` → `logger.warning("roster discovery failed; returning empty roster: %s", exc)` and `return Roster([])`. This is the deliberate isolation boundary (add `# noqa: BLE001` only if `ruff` actually flags it — avoid a dead `RUF100`). No `asyncio.TaskGroup` is needed for a single fetch.
  - [x] Inside the `try`: `payload = await _fetch_collection(http, "roster")` (URL `/json/v5/roster`; envelope `type` is `"rosterEntry"` — `parse_roster_entry` already handles that mismatch). Parse each envelope with **per-entry skip-and-continue** (AC-8): `try: entries.append(parse_roster_entry(env)) except JMRIProtocolError as exc: logger.warning("skipping malformed roster entry: %s", exc)`. Return `Roster(entries)`.
  - [x] Do **not** touch `self._entities` (AC-3) — `discover_roster()` builds and returns a `Roster` only, with a short comment mirroring `discover_operations()`'s "deliberately does NOT rebuild self._entities" note.
  - [x] Add a Google-style docstring mirroring `discover_operations()`: separate entry point, returns `Roster` not `Layout`, snapshot-not-live (re-run to refresh), shared cached version gate, graceful-degrade on fetch failure. Keep imports (`parse_roster_entry`, `Roster`/`RosterEntry`) — they are already present from the prior implementation.

- [x] **Task 5 — `Roster` export (verify)** (AC: 1)
  - [x] `src/pyjmri/__init__.py` already exports `Roster` (alphabetical, before `RosterEntry`). Keep it — `Roster` remains public.

- [x] **Task 6 — Rewrite unit tests** (AC: 1, 2, 3, 4, 5, 6, 7, 8, 11)
  - [x] Rewrite `tests/unit/test_discover_roster.py` to drive `discover_roster()` (not `discover()`), mirroring `tests/unit/test_discover_operations.py` (`patch_http_factory`, `_version_payload`, fixture-responder). Map `/json/v5/roster` → `load_fixture("roster")`.
  - [x] `discover_roster()` returns a `Roster` with all fixture entries (`len(roster) == len(load_fixture("roster"))` — derive, do not hardcode; AC-10).
  - [x] Single version probe shared with `discover()`: call `discover()` then `discover_roster()` on the same Client; assert the version endpoint is hit exactly once (AC-2).
  - [x] `by_address` hit (pinned by attribute filter) returns the entry; miss returns `None` + WARNING via `caplog` (AC-6).
  - [x] `roster["<name from fixture>"]` resolves (pin via `next(...)`); unknown key raises `LayoutEntityNotFound` (AC-5).
  - [x] **Graceful-degrade (headline, AC-4):** responder raises (or returns a non-list) for `/json/v5/roster`; assert `discover_roster()` returns an empty `Roster` (`len == 0`) and a WARNING is logged — and that it does **not** raise. Drop the old "siblings survive" assertion (structurally moot now); instead add a test that `discover()` and `discover_roster()` are independent (a roster-endpoint failure leaves a separate `discover()` call fully populated).
  - [x] Empty roster → `len == 0`, no error (AC-8). Malformed-entry skip: one good + one malformed `rosterEntry` → only the good one loads + WARNING (AC-8).
  - [x] Address-collision first-wins: construct `Roster([...])` directly with two entries sharing a `dcc_address`; assert `by_address` returns the **first** + WARNING (AC-7).
  - [x] `_entities` not clobbered: after `discover()` + `discover_roster()`, assert no roster keys are in `jmri._entities` and the turnout/sensor keys are intact (AC-3).

- [x] **Task 7 — Integration test** (AC: 9)
  - [x] In `tests/integration/test_discovery.py` (or `test_roster_discovery.py`, matching convention): `@pytest.mark.integration`, warm the version check, then time `discover_roster()` and assert `len(roster) > 0` within ~1 second. Remove the prior `discover()`-folded roster integration assertion.
  - [x] Pin a probe entry by attribute filter (`next(e for e in roster.values() if e.function_labels)`), never `[0]`. Skip cleanly if JMRI is unreachable.

- [x] **Task 8 — Gates (run all; `uv run --no-sync` only)**
  - [x] `uv run --no-sync ruff check`
  - [x] `uv run --no-sync ruff format --check` (separate CI gate — run both)
  - [x] `uv run --no-sync mypy --strict src/pyjmri`
  - [x] `uv run --no-sync pytest -m "not integration"` (must stay green; net test count may shift as the failure-isolation test is reframed)

### Review Findings

Code review 2026-06-17 (Blind Hunter + Edge Case Hunter + Acceptance Auditor). Acceptance Auditor: all 9.1 + 9.2 ACs satisfied. 1 patch, 0 decision-needed, 0 defer, 12 dismissed as noise/by-design/faithful-translation.

- [x] [Review][Patch] Non-dict roster list element collapses the whole roster instead of per-entry skip (FR58/AC-8) [src/pyjmri/_parsing.py:114 `_data` → `client.py discover_roster` per-entry loop] — a non-dict element in the `/json/v5/roster` list made `_data` call `payload.get("data")` → `AttributeError`, which escaped the inner `except JMRIProtocolError` and was caught by `discover_roster`'s outer `except Exception`, degrading the *entire* roster to empty. **FIXED 2026-06-17:** `_data` now raises `JMRIProtocolError` ("envelope is not a JSON object") on a non-dict payload, so the inner skip-and-continue handles it (FR58 honored). Added `test_non_dict_entry_is_skipped_not_whole_roster` (discover path) and `test_raises_on_non_dict_envelope` (parser). Full suite 636 passed; the shared `_data` hardening introduced no regressions in operations/layout parsers.

## Dev Notes

### What this story is, in one sentence

Reimplement roster discovery as a standalone `Client.discover_roster() -> Roster` mirroring `discover_operations()` — reverting the earlier fold of the roster into `discover()`/`Layout` — while reusing the paradigm-agnostic `Roster` container (`EntityCollection[RosterEntry]` + `by_address`) unchanged.

### Why this changed (correct-course 2026-06-17)

The roster is a read-only, non-subscribed, point-in-time snapshot — structurally identical to Operations (Epic 8). The prior design folded it into `discover()`, which forced: (a) a never-raise `_fetch_roster_isolated` wrapper purely to stop a roster error cancelling the layout fetches in `discover()`'s shared `asyncio.TaskGroup` (FR57); and (b) a layout↔roster import cycle worked around with `TYPE_CHECKING` + a lazy import. Modelling the roster like Operations — its own `discover_roster()` call — deletes both: a separate call cannot cancel sibling fetches, and `layout.py` no longer imports `Roster`. FR57 is then satisfied by a simple method-level `try/except` → empty `Roster` + WARNING.

### `discover_roster()` — exact shape (mirror `discover_operations()`)

```python
async def discover_roster(self) -> Roster:
    """Fetch the JMRI roster and return a read-only Roster snapshot.

    A separate entry point from discover() (mirroring discover_operations()):
    returns a Roster, not a Layout, and does not touch the WS-dispatch index.
    The roster is a non-subscribed point-in-time snapshot; re-run to refresh.
    The >= 5.14 version gate is the shared cached probe. A fetch failure
    degrades to an empty Roster + WARNING rather than raising (FR57).
    """
    if self._http is None:
        raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
    http = self._http
    if not self._version_checked:
        version_payload = await http.get("/json/v5/networkService")
        _check_jmri_version(version_payload)
        self._version_checked = True
    try:
        payload = await _fetch_collection(http, "roster")  # URL /json/v5/roster
        entries: list[RosterEntry] = []
        for env in payload:
            try:
                entries.append(parse_roster_entry(env))
            except JMRIProtocolError as exc:
                logger.warning("skipping malformed roster entry: %s", exc)
        return Roster(entries)
    except Exception as exc:  # isolation boundary (FR57) — add noqa only if ruff flags it
        logger.warning("roster discovery failed; returning empty roster: %s", exc)
        return Roster([])
    # Deliberately does NOT rebuild self._entities — the roster is a
    # non-subscribed snapshot with no _on_event (like Operations).
```

[Source: src/pyjmri/client.py:787 (`discover_operations` — the structural template), :720 (`discover` version-gate pattern), :1112 (`_fetch_roster_isolated` — delete; logic moves here), :1078 (`_fetch_collection`)]

### `Roster` container — reused unchanged

The prior implementation's `Roster(EntityCollection[RosterEntry])` (materialize-once, build `_by_address`, first-wins collision + WARNING, get-style `by_address`) is paradigm-agnostic and correct — do not rewrite it. The only conceptual change around it is *who builds it*: `discover_roster()` now, not `discover()`.

### Why `by_address` returns `None` (not raise) but `roster[key]` raises

Unchanged from the prior design (the FR55 split):

- **`by_address(n)` is a `get()`-style find** — an address absent from the roster is a normal case (a new, un-catalogued loco). Return `None` + WARNING. Story 9.3's `Client.throttle_for_entry` builds warn-and-drive on top of this.
- **`roster[key]` (name/user-name) raises `LayoutEntityNotFound`** — consistent with the other collections (a name that resolves to nothing is a lookup error). Inherited from `EntityCollection.__getitem__`.

### Real-data finding to preserve (still applies)

The basement fleet has **duplicate DCC addresses**: address 41 → "ALCO 2-6-0 Steam" vs "ALCO 2-6-0 Steam Nate"; address 606 → "ALCO PA 606" vs "ALCO PA 606 Update" (two roster entries for the same physical loco, confirmed in JMRI's own wire format). The first-wins collision rule (AC-7) handles both with WARNINGs and is exercised by live data, not just the synthetic unit test. **PO decision (2026-06-16, Mikey): keep first-wins.** 2 collision WARNINGs fire on every `discover_roster()` against this layout — expected, not a regression.

### Project Structure Notes

All paths under `python_code/` (the only writable tree; `.jmri` profiles and shared JMRI assets incl. `roster.xml`/`roster/` are read-only — the library reads JMRI's JSON over HTTP, never the profile XML):

- `src/pyjmri/roster.py` — **REUSE** `class Roster(...)` + `by_address` as-is.
- `src/pyjmri/client.py` — **UPDATE**: delete `_fetch_roster_isolated`; remove the roster task + return from `discover()`; add `discover_roster()`.
- `src/pyjmri/layout.py` — **REVERT**: remove the `roster` param/attribute and the `TYPE_CHECKING`/lazy `Roster` import (back to no roster references).
- `src/pyjmri/__init__.py` — **NO CHANGE**: `Roster` stays exported.
- `tests/unit/test_discover_roster.py` — **REWRITE** to drive `discover_roster()`.
- `tests/integration/test_discovery.py` (or `test_roster_discovery.py`) — **UPDATE** to time `discover_roster()`.
- `tests/unit/fixtures/roster.json` — **EXISTS** (live 44-entry capture; reuse as-is).

Scope fence: `Client.throttle_for_entry`, capability classification, and the startup example are **Story 9.3** — do not build them here. `_codes.py`, `throttle.py`, `operations.py`, and the eight existing entity modules are not touched. Epics 1–8 behavior is unchanged.

### Testing Requirements

- Framework `pytest`; unit tests async (`patch_http_factory` in `tests/unit/conftest.py`). Mirror `test_discover_operations.py` exactly for structure.
- **No hardcoded fleet facts** in `src/` or as test oracles (AC-10): derive counts from `len(load_fixture("roster"))`; pin probes with `next(e for e in ... if <attribute>)`.
- Required unit cases: (1) `discover_roster()` populated; (2) single shared version probe across `discover()` + `discover_roster()`; (3) `by_address` hit + miss(`None`+WARNING); (4) name hit + `LayoutEntityNotFound` miss; (5) **graceful-degrade** — fetch failure → empty `Roster` + WARNING, no raise; (6) `discover()` unaffected by a roster-endpoint failure; (7) empty roster; (8) malformed-entry skip; (9) collision first-wins; (10) `_entities` has no roster keys.
- Integration: `@pytest.mark.integration`, skips if JMRI unreachable, asserts roster populated within ~1s, probe pinned by attribute filter. Fully simulator-testable (pure metadata — no NCE open-loop blind spot).
- Run before declaring done (always `uv run --no-sync`): `ruff check`; `ruff format --check`; `mypy --strict src/pyjmri`; `pytest -m "not integration"`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 9.2] — rewritten story statement + acceptance criteria (standalone `discover_roster()`, graceful-degrade)
- [Source: _bmad-output/planning-artifacts/epics.md — "Roster increment (v1.2) — additional technical requirements"] — standalone `discover_roster()`, graceful-degrade, client-side address index, reuse `EntityCollection`, wire format
- [Source: _bmad-output/planning-artifacts/architecture.md — "Roster Subsystem (Read-Only)"] — the decision section this story implements (separate entry point, snapshot, graceful-degrade, rejected fold)
- [Source: _bmad-output/planning-artifacts/prd.md — FR51, FR55 (amended 2026-06-16), FR57 (reframed 2026-06-17), FR58]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-06-17.md] — the correct-course proposal that reversed the fold
- [Source: src/pyjmri/client.py:787 (`discover_operations` template), :720 (`discover`), :1112 (`_fetch_roster_isolated` — delete), :1078 (`_fetch_collection`)]
- [Source: src/pyjmri/operations.py:184 (`Operations` container template)]
- [Source: tests/unit/test_discover_operations.py] — unit test template incl. `does_not_clobber_entity_index`
- [Source: _bmad-output/implementation-artifacts/9-1-roster-wire-format-parsing-and-capability-aware-entity-classes.md] — Story 9.1 entity classes/parser this story consumes

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (1M context)

### Debug Log References

- Gates (all `uv run --no-sync`): `ruff check` → All checks passed; `ruff format --check` → 70 files already formatted; `mypy --strict src/pyjmri` → Success, no issues in 22 source files; `pytest -m "not integration"` → **634 passed / 26 deselected** (baseline at reimplementation start was 633/26; the roster unit file went from 10 → 11 tests — added the shared-version-probe test and the discover()-independence test, reframed the failure test as graceful-degrade).
- `python -c "import pyjmri"` → import OK; the layout↔roster cycle is gone (`layout.py` no longer imports `roster.py`; the one-way edge `roster.py → layout.py` for `EntityCollection` stands alone).
- Broad `except Exception` in `discover_roster()` was NOT flagged by ruff (BLE001), so no `# noqa` was added (avoids a dead RUF100), matching the prior `_fetch_roster_isolated` precedent.
- **Live integration run against the basement layout (`localhost:12080`): `pytest tests/integration/test_discovery.py -m integration` → 3 passed (0.36s)**, including `test_discover_roster_populates_within_budget` — `discover_roster()` populates the roster and completes well within the 1s warm roster bound, probe pinned by attribute filter.

### Completion Notes List

- **Reverted the fold** (AC-11): `layout.py` lost the `roster` param/attribute, the `TYPE_CHECKING` `Roster` import, and the lazy import-cycle workaround — back to zero roster references. `discover()` lost the roster TaskGroup task, the `roster=Roster(...)` return arg, and the roster-specific no-clobber comment; its docstring now points at `discover_roster()`. `_fetch_roster_isolated` deleted.
- **Added `Client.discover_roster() -> Roster`** mirroring `discover_operations()`: shared cached `>= 5.14` version gate (no second probe), then a method-level `try/except` graceful-degrade boundary (FR57) — any roster fetch failure returns `Roster([])` + WARNING rather than raising; inner per-entry `try/except JMRIProtocolError` does the FR58 skip-and-continue. Does not touch `self._entities`.
- **Reused `roster.py`'s `Roster` container unchanged** (`EntityCollection[RosterEntry]` + `by_address` get-style find + first-wins collision). Only its docstrings were corrected to reference `discover_roster()` instead of the fold.
- `__init__.py` unchanged — `Roster` was already exported (before `RosterEntry`).
- **Rewrote `tests/unit/test_discover_roster.py`** (11 tests) to drive `discover_roster()`: populated path, shared version probe across `discover()` + `discover_roster()`, `by_address` hit + miss(`None`+WARNING), name hit + `LayoutEntityNotFound` miss, graceful-degrade (fetch failure → empty `Roster` + WARNING, no raise), `discover()`-independence under a roster-endpoint failure, empty roster, malformed-entry skip, first-wins collision, and the `_entities` no-touch invariant (asserts `discover_roster()` leaves the index exactly as `discover()` built it). All counts/probes layout-agnostic.
- **Updated the integration test** to time `discover_roster()` warm against the 1s roster bound (was a `discover()`-folded assertion).
- Scope respected: no `throttle_for_entry`, no capability classification, no examples (Story 9.3). `_codes.py`, `throttle.py`, `operations.py`, and the eight entity modules untouched. Epics 1–8 behavior unchanged.

### File List

- `python_code/src/pyjmri/client.py` — UPDATED: deleted `_fetch_roster_isolated`; removed the roster task + return from `discover()` (docstring repointed to `discover_roster()`); added `async def discover_roster() -> Roster` with method-level graceful-degrade.
- `python_code/src/pyjmri/layout.py` — REVERTED: removed the `roster` param/attribute, the `TYPE_CHECKING` `Roster` import, the lazy import-cycle workaround, and the docstring `Args` entry.
- `python_code/src/pyjmri/roster.py` — UPDATED (docstrings only): `Roster`/module docstrings now reference `Client.discover_roster()` (mirroring `discover_operations()`) instead of the `Layout` fold. Container code unchanged.
- `python_code/tests/unit/test_discover_roster.py` — REWRITTEN: 11 unit tests driving `discover_roster()`.
- `python_code/tests/integration/test_discovery.py` — UPDATED: `test_discover_roster_populates_within_budget` times `discover_roster()` (warm, 1s bound).
- `python_code/src/pyjmri/_parsing.py` — UPDATED (code-review patch): `_data` now raises `JMRIProtocolError` on a non-dict envelope (was `AttributeError`), so the roster per-entry skip-and-continue catches a non-dict list element (FR58); hardens all envelope parsers.
- `python_code/tests/unit/test_roster_parsing.py` — UPDATED (code-review patch): added `test_raises_on_non_dict_envelope`.
- `python_code/tests/unit/test_discover_roster.py` — UPDATED (code-review patch): added `test_non_dict_entry_is_skipped_not_whole_roster` (now 12 unit tests).

## Change Log

| Date | Change |
|------|--------|
| 2026-06-16 | Story 9.2 drafted (create-story) as a **fold** of the roster into `Client.discover()`: parallel failure-isolated fetch landing on `layout.roster`; `Roster(EntityCollection[RosterEntry])` with client-side `by_address` index; per-entry skip-and-continue; no WS-index mutation. Status → ready-for-dev. |
| 2026-06-16 | Story 9.2 implemented (fold): `Roster` container + `by_address`; `_fetch_roster_isolated` never-raise boundary folded into `discover()`'s TaskGroup; `Layout.roster` attribute (lazy import to break the layout↔roster cycle); `Roster` exported. 10 unit + 1 integration test. All gates green (633 passed / 26 deselected). Status → review. |
| 2026-06-17 | **Correct-course (see sprint-change-proposal-2026-06-17.md): fold reversed.** Story rewritten to discover the roster through a standalone `Client.discover_roster() -> Roster` mirroring `discover_operations()`, with method-level graceful-degrade (empty `Roster` + WARNING) replacing the shared-TaskGroup failure-isolation. Reimplementation reverts the `discover()` roster task, `_fetch_roster_isolated`, and the `Layout.roster` attribute + import-cycle workaround; the `roster.py` `Roster` container is reused unchanged. File renamed `9-2-fold-roster-into-layout-...` → `9-2-discover-roster-standalone-by-address-graceful-degrade`. Status reset review → ready-for-dev. |
| 2026-06-17 | Story 9.2 **reimplemented** (dev-story): fold reverted in `layout.py`/`client.py`, `_fetch_roster_isolated` deleted, `Client.discover_roster()` added with graceful-degrade; `roster.py` container reused (docstrings corrected). Roster unit test rewritten to drive `discover_roster()` (11 tests); integration test repointed. All gates green (634 passed / 26 deselected; ruff check + format clean; mypy --strict clean). Live integration run against the basement layout: 3 passed. No layout↔roster import cycle. Status → review. |
| 2026-06-17 | **Code review** (Blind Hunter + Edge Case Hunter + Acceptance Auditor): all 9.1 + 9.2 ACs satisfied; 1 patch, 12 dismissed. Patch applied — hardened `_data` to raise `JMRIProtocolError` on a non-dict envelope so a non-dict roster list element is skipped per-entry (FR58/AC-8) instead of collapsing the whole roster; +2 tests. All gates green (636 passed / 26 deselected). Status → done. |
