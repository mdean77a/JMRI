# Story 9.4: Fleet-catalog example + read-only boundary + docs + v1.2 release

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a JMRI layout owner,
I want a fleet-catalog report, an enforced read-only boundary, documentation for the Roster feature, and the v1.2 release prepared,
so that I get a printable reference/maintenance sheet of my whole fleet (PRD Journey 6) and the Epic 9 increment ships under the established release discipline.

## Acceptance Criteria

1. **Read-only boundary test (FR56).** A unit test asserts that `RosterEntry`, `Roster`, and `FunctionLabel` expose **no** mutating/command method (no create/edit of entry, function label, or decoder config; no `set_*`/`command`/`throttle`/`wait_*` surface). It mirrors the Story 8.3 `tests/unit/test_operations_boundary.py` pattern (parametrize forbidden method names × representative instances; `hasattr(...) is False`). Instances are constructed directly (no live JMRI). (AC-1)
2. **`Roster` collection surface is read-only and minimal.** A companion assertion confirms `Roster`'s only roster-specific public method is `by_address` (plus the inherited `EntityCollection` read-only mapping surface: iteration, `values`, `__len__`, name lookup). No mutating method leaks from the base class. (AC-2)
3. **`examples/roster_catalog.py` (FR59).** Run against `Basement_Revised_2024.jmri` **unmodified**, it: connects, calls `discover_roster()`, and prints a per-loco fleet reference sheet — **road number, model, decoder family/model, owner, DCC address, and comment** — plus a **decoder-family/model rollup** (counts per family/model). (AC-3)
4. **Graceful degradation.** When the roster is empty (or JMRI has no roster configured), the example prints an explanatory message and exits cleanly (exit 0) — **not** a traceback. A connection/transport failure prints a short reason + the JMRI URL hint (exit 1); an invalid `--url` is reported in one line (exit 2). It reuses the `except* JMRIError` + `_leaf_messages` pattern from `operations_report.py`. (AC-4)
5. **Example hygiene (hard invariants).** The example imports **only** from the top-level `pyjmri` namespace (`from pyjmri import Client, JMRIError, Roster` — no `from pyjmri.roster import ...`), runs clean under `mypy --strict`, and hardcodes **no** entity name or DCC address. It is layout-agnostic: the basement default (`localhost:12080`) is overridable via `--url`, matching `operations_report.py` exactly. (AC-5)
6. **Roster documentation section (README).** A `## Roster (read-only)` section is added to `python_code/README.md` (parallel to the existing `## Operations (read-only)` section), explaining: the **roster-vs-Operations distinction** (full DecoderPro catalog vs the operationally-active subset); that the roster is a **standalone read-only subsystem** discovered via `discover_roster()` (mirroring Operations); **`by_address` / name lookup** semantics; **warn-and-drive** for an unknown address vs **raise** for an unknown name; the **snapshot-staleness caveat** (FR54); and that **capability is inferred from function labels, not the decoder family** (with a pointer to `classify_capability` / `firable_startup_functions` and `capability_aware_startup.py`). It links to `examples/roster_catalog.py`. (AC-6)
7. **Read-only boundary stated in docs.** The README Roster section states the read-only boundary explicitly — inspection only; **editing stays in DecoderPro** — mirroring the Operations "Read-only in this release" subsection. (AC-7)
8. **CONTRIBUTING / release notes record roster test setup.** `CONTRIBUTING.md` (and/or `RELEASES.md`) records any roster fixture/profile setup needed to run the roster **integration** tests (a populated roster in the target profile), and the unit-test baseline citation in `CONTRIBUTING.md` is updated to the post-9.4 count. (AC-8)
9. **v1.2 release — Phase A only (Epic 8 pattern).** Phase A is performed: bump `pyproject.toml` to `version = "1.2.0"`, run `uv lock`, add a `## v1.2.0` section to `RELEASES.md` (free-form prose + bullets, matching the v1.1.0 format), run **all gates green** (`ruff check`, `ruff format --check`, `mypy --strict src/pyjmri` + `mypy --strict examples/`, `pytest -m "not integration"`), then `uv build` + `uv run --no-sync twine check dist/*` (expect PASSED). (AC-9)
10. **STOP before Phase B.** The process **stops before** `uv publish`, the git tag, and the GitHub release — those are Mikey's manual Phase B. No `uv publish`/tag/release is performed in this story. (AC-10)
11. **No hardware gate required.** No throttle *hardware* validation gate is required for this story (the roster is read-only metadata). The `capability_aware_startup.py` physical "visibly correct startup" check remains an **optional manual** hardware step, not a release blocker. (AC-11)
12. **Quality gates green.** `uv run --no-sync ruff check`, `ruff format --check`, `mypy --strict src/pyjmri`, `mypy --strict examples/roster_catalog.py` (and the other examples), and `pytest -m "not integration"` all pass. Exports stay alphabetical where touched (RUF022). (AC-12)

> **Scope fence — Story 9.4 is the boundary test + `roster_catalog.py` + Roster docs + v1.2 Phase-A release ONLY.** Do **NOT** add any mutating/decoder-programming surface to `RosterEntry`/`Roster`/`FunctionLabel` (that is Vision, not v1.2). Do **NOT** change parsing, `discover_roster`, `throttle_for_entry`, or `classify_capability` behavior delivered in Stories 9.1–9.3 — Story 9.4 is documentation, an example, a boundary test, and release mechanics. Do **NOT** perform Phase B (`uv publish`, git tag, GitHub release). `src/pyjmri/` source is **not** modified except an exports/`__all__` touch only if a genuinely missing public name is discovered (none expected — `Roster`, `RosterEntry`, `FunctionLabel`, `Capability`, `classify_capability`, `firable_startup_functions` already export). Epics 1–8 behavior is byte-for-byte unchanged.

## Tasks / Subtasks

- [x] **Task 1 — Read-only boundary test** (AC: 1, 2)
  - [x] Create `tests/unit/test_roster_boundary.py`, mirroring `tests/unit/test_operations_boundary.py`.
  - [x] Reuse the `_FORBIDDEN_METHODS` tuple verbatim (build/move/assign/manifest/`set_*`/`command`/`throttle`/`get_state`/`wait_*` …); roster types must expose none of them.
  - [x] `_INSTANCES`: construct `FunctionLabel(num=0, label=None, lockable=False)`, a minimal `RosterEntry(...)` (all `kw_only` fields; `user_name=None`, `function_labels=()`), and `Roster([])`. All built directly — no fixtures, no live JMRI.
  - [x] Parametrize `test_roster_type_exposes_no_mutating_method(entity, method_name)` → `assert hasattr(entity, method_name) is False` with a roster-specific FR56 message.
  - [x] Add `test_roster_exposes_only_read_only_collection_surface`: assert `by_address` is present and callable, and that none of the forbidden mutators are present on a `Roster([])` instance. (Do **not** assert an exact `dir()` equality like the Operations container test — `Roster` inherits a richer `EntityCollection` mapping surface; assert the read-only invariants instead.)
- [x] **Task 2 — `examples/roster_catalog.py`** (AC: 3, 4, 5)
  - [x] Copy the structural skeleton from `examples/operations_report.py`: module docstring (PRD Journey 6 opener + "Run it" / "Graceful degradation" blocks), `from __future__ import annotations`, `argparse`, `asyncio`, `from pyjmri import Client, JMRIError, Roster`, `_leaf_messages` helper, `_parse_args()` with a single `--url` arg (default `None`), `main(args)` with `Client(url) if url is not None else Client()`, `except* JMRIError` handling, `SystemExit(2)` on bad `--url`, `if __name__ == "__main__": asyncio.run(main(_parse_args()))`.
  - [x] Implement `print_catalog(roster: Roster) -> None`: per entry (over `roster.values()`), print road number, model, `decoder_family`/`decoder_model`, owner, `dcc_address`, comment — each with a `or "—"` fallback for `None`. Then a decoder rollup: count entries per `(decoder_family, decoder_model)` (or family alone), printed as a counts table. Use `collections.Counter` or a plain dict; keep output plain text.
  - [x] Empty-roster path: `if len(roster) == 0:` print an explanatory line ("No roster entries are configured in JMRI …") and return (exit 0).
  - [x] Hardcode **no** loco name/address. `--url` is the only knob; basement default is `localhost:12080` via bare `Client()`.
- [x] **Task 3 — Roster documentation** (AC: 6, 7, 8)
  - [x] Append a `## Roster (read-only)` section to `python_code/README.md` after the Operations section (after the `### Read-only in this release` Operations subsection, ~line 167). Include a short `discover_roster()` code block, the roster-vs-Operations distinction (a `### Roster is not Operations` subsection, the mirror of the existing `### Operations is not the roster`), `by_address`/name lookup semantics, warn-and-drive vs raise, the snapshot caveat (FR54), the capability-from-labels note (pointing at `classify_capability`/`firable_startup_functions`/`capability_aware_startup.py`), a link to `examples/roster_catalog.py`, a "fully simulator-testable" note (roster is pure JSON data, not subject to the open-loop blind spot), and a "read-only — editing stays in DecoderPro" boundary statement.
  - [x] In `CONTRIBUTING.md`: update the unit-test baseline citation (currently cites the Story 8.3 number) to the post-9.4 count, and note any roster fixture/profile setup needed for the roster **integration** tests (a populated roster in `Basement_Revised_2024.jmri`).
- [x] **Task 4 — v1.2 release, Phase A only** (AC: 9, 10, 11)
  - [x] Bump `pyproject.toml` `version` `1.1.0` → `1.2.0` (a clean, isolated edit).
  - [x] Run `uv lock` to refresh the lockfile.
  - [x] Add a `## v1.2.0` section at the top of `RELEASES.md` (under the title, above `## v1.1.0`), free-form prose + bullets in the v1.1.0 format: read-only Roster subsystem (`discover_roster()` → `Roster`), `RosterEntry`/`FunctionLabel`, `by_address`/name lookup, `throttle_for_entry`, `classify_capability`/`firable_startup_functions`, the two new examples, warn-and-drive (FR55), empty-roster graceful degrade (FR57); "JMRI version tested against: JMRI 5.14.0"; "Hardware-mode validation: not required (roster is read-only metadata)"; a Phase-B `(Published … )` placeholder.
  - [x] Run all gates (Task 5). Then `rm -rf dist/ && uv build` and `uv run --no-sync twine check dist/*` — expect `PASSED`.
  - [x] **STOP.** Do not `uv publish`, do not `git tag`, do not create a GitHub release. Leave Phase B for Mikey.
- [x] **Task 5 — Quality gates** (AC: 12)
  - [x] `uv run --no-sync ruff check`
  - [x] `uv run --no-sync ruff format --check` (separate CI gate — run both)
  - [x] `uv run --no-sync mypy --strict src/pyjmri`
  - [x] `uv run --no-sync mypy --strict examples/roster_catalog.py` (the new example must type-check; run the other examples too)
  - [x] `uv run --no-sync pytest -m "not integration"` (baseline at story start: **662 passed / 27 deselected**; expect it to rise with the new boundary tests)

### Review Findings

Code review 2026-06-17 (3 adversarial layers over the uncommitted 9.4 diff: `roster_catalog.py`, `test_roster_boundary.py`, docs/release/config). 1 patch, 0 deferred, 9 dismissed. Auditor verified AC-1…AC-12 and the src/pyjmri scope fence all met (no `src/` behavior change; exports untouched).

**Resolution (2026-06-18):** Patch applied — added the six `MutableMapping` mutators (`__setitem__`, `__delitem__`, `pop`, `popitem`, `clear`, `setdefault`) to `_FORBIDDEN_METHODS`. All absent today (still passes); now guards a future base-class regression. Boundary test 76 → 94 cases; full suite **756 passed / 27 deselected**. CONTRIBUTING baseline citations updated 738 → 756 (three places, incl. the release-checklist line that still cited the 8.3 baseline). Gates green: ruff check + format, mypy --strict (src + examples).

- [x] [Review][Patch] Boundary test's `_FORBIDDEN_METHODS` omits the standard `Mapping` mutators — confirmed `EntityCollection` is a read-only `collections.abc.Mapping` (not `MutableMapping`), so `__setitem__`/`__delitem__`/`pop`/`popitem`/`clear`/`setdefault` are all absent today and the test passes; but the list only forbids domain verbs, so a future switch of the base to `MutableMapping` (making `roster[k]=v`/`roster.pop(...)`/`roster.clear()` real) would slip past the FR56 "enforced by the class surface" guard. Add the six mutators to harden the test. [tests/unit/test_roster_boundary.py:_FORBIDDEN_METHODS]

Dismissed (by-design or no-impact): non-`JMRIError` exception → traceback escape (mirrors `operations_report.py`; the "no traceback" contract covers JMRI-unreachable/malformed, which are `JMRIError`); tautological `len()==0`/`values()==[]` and the redundant forbidden-loop in the companion test (consistent with the Operations precedent); layout-command verbs applied to frozen records (intentional — proves no command surface leaks onto data); whitespace-only metadata splitting the rollup key (JMRI never emits it; `_fmt` is copied verbatim from the sibling example); out-of-range `dcc_address` printed verbatim (correct for a read-only report); `.gitignore` vs `pyproject` exclude path bases (both resolve correctly; tools run from `python_code/`); `train_out_and_back.py` excision + `pyproject` tooling excludes (your authorized decision, documented in the Dev Agent Record); RELEASES.md long-run evidence reuse (AC-9 requires no long-run test).

## Dev Notes

### What this story is, in one sentence

The Epic 9 "ship it" story: prove the roster is read-only with a boundary test, give the user a printable fleet catalog (`roster_catalog.py`), document the Roster subsystem in the README, and run the v1.2 release **up to but not including** publish — exactly the Epic 8 / v1.1 pattern.

### Mirror Story 8.3, not reinvent it

Story 8.3 did this same shape for Operations. Read these first and copy their structure:

- **Boundary test:** `tests/unit/test_operations_boundary.py` — parametrize `_FORBIDDEN_METHODS` × `_INSTANCES`, `assert hasattr(...) is False`. [Source: tests/unit/test_operations_boundary.py:32-129]
- **Example:** `examples/operations_report.py` — docstring shape, `--url` argparse, `Client(url) if url else Client()`, `except* JMRIError` + `_leaf_messages`, exit codes 0/1/2. [Source: examples/operations_report.py:1-167]
- **README section:** the existing `## Operations (read-only)` block at README.md:139-167 is the exact template for the new `## Roster (read-only)` block. [Source: python_code/README.md:139-167]
- **Release:** `RELEASES.md` `## v1.1.0` (the v1.2.0 section copies this format) and `CONTRIBUTING.md`'s release checklist. [Source: python_code/RELEASES.md:3, python_code/CONTRIBUTING.md]

### The Roster API the example/test consume (do NOT reinvent)

`RosterEntry` is a frozen `kw_only` dataclass; its public attributes (use these exact names): `name`, `user_name` (**always `None`**), `dcc_address`, `long_address`, `road_name`, `road_number`, `model`, `mfg`, `owner`, `comment`, `image_path`, `max_speed_pct`, `decoder_family`, `decoder_model`, `function_labels`. [Source: src/pyjmri/roster.py:60-93]

`FunctionLabel`: `num`, `label` (`str | None`), `lockable`. [Source: src/pyjmri/roster.py:40-57]

`Roster` (subclass of `EntityCollection[RosterEntry]`): iterate / `.values()` / `len()` / `roster[name]`, plus `by_address(dcc_address) -> RosterEntry | None` (get-style; logs a WARNING + returns `None` on a miss, never raises). `_find_by_address` is private — the example/test use only the public surface. [Source: src/pyjmri/roster.py:131-200]

The catalog's per-loco columns map to: road number → `road_number`; model → `model`; decoder family/model → `decoder_family` / `decoder_model`; owner → `owner`; DCC address → `dcc_address`; comment → `comment`. The rollup counts by `decoder_family` (and/or `decoder_model`). All metadata fields are `str | None`, so render with a `or "—"` fallback.

### Hard invariants carried from 9.1–9.3 (the dev agent WILL trip on these otherwise)

- **Top-level imports only** in examples: `from pyjmri import ...`. `mypy --strict` covers `examples/` and is a CI gate — the example must type-check, including `argparse.Namespace` access. [project memory: examples are mypy-strict]
- **`ruff format --check` is a SEPARATE gate** from `ruff check`. Run both; lint-clean ≠ format-clean.
- **Exports are alphabetical** (RUF022 enforces case-sensitive sort with lowercase functions last). The public roster names already export from `src/pyjmri/__init__.py`; do not add to `__all__` unless something is genuinely missing (nothing is expected to be).
- **Layout-agnosticism:** no hardcoded roster name, DCC address, function number, or fleet count anywhere in `src/` or the example. The basement default is the bare `Client()` host (`localhost:12080`) overridable via `--url` — same as `operations_report.py`.
- **Decoder family/model are NOT capability tags** — they are date-stamped definition-file names (e.g. "ESU LokSound 5"). The catalog prints them as *identity* metadata; it must not infer capability from them. Capability inference lives in `classify_capability` (labels only) and belongs to the *capability* example, not the catalog. [Source: src/pyjmri/roster.py:120-128]
- **`user_name` is always `None`** for roster entries — the boundary test cannot assert a meaningful `user_name`, and the catalog should key on `name`/`road_number`, not `user_name`.

### Roster is fully simulator-testable (unlike throttles)

The roster is pure JSON metadata JMRI serves regardless of hardware, so unlike throttle/sensor paths it is **not** subject to the NCE open-loop blind spot — `roster_catalog.py` and the boundary test are fully exercisable on the simulator with a populated roster. The README Roster section should say so. [project memory: roster is read-only metadata, simulator-faithful]

### Release: Phase A vs Phase B (do not cross the line)

Phase A (this story): version bump, `uv lock`, RELEASES.md entry, gates green, `uv build`, `twine check`. Phase B (NOT this story, Mikey does it manually): `uv publish`, `git tag`, GitHub release. The story explicitly **stops** after `twine check dist/* → PASSED`. [Source: epics.md Story 9.4 "v1.2 release" AC; mirrors Epic 8 Phase-A pattern]

### Previous-story intelligence (Story 9.3, just completed + code-reviewed)

9.3 shipped `throttle_for_entry`, `classify_capability`, `firable_startup_functions`, `Capability`, and `examples/capability_aware_startup.py`, and went through code review with 5 patches applied (narrowed `discover_roster` exception catch; silent `Roster._find_by_address`; ASCII guard on function-key parsing; DEBUG trace on skipped F-keys; a unit-level acquire-seam test). Test baseline is now **662 passed / 27 deselected**. The Roster public surface is stable and complete for this story — 9.4 adds **no** new `src/` behavior. [Source: _bmad-output/implementation-artifacts/9-3-throttle-for-entry-capability-classification-startup-example.md#Review-Findings]

### Project Structure Notes

- New files: `tests/unit/test_roster_boundary.py`, `examples/roster_catalog.py`.
- Modified files: `python_code/README.md`, `python_code/CONTRIBUTING.md`, `python_code/RELEASES.md`, `python_code/pyproject.toml`, `python_code/uv.lock` (via `uv lock`), and `dist/` build artifacts (gitignored — do not commit `dist/`).
- No `src/pyjmri/` modification expected. If one proves necessary, it is a scope-fence exception to call out explicitly in the Dev Agent Record.
- All paths are under `python_code/` (the only writable code tree). [project memory: only `python_code/` and `_bmad-output/` are writable]

### Testing Requirements

- Unit (`pytest -m "not integration"`) is the gating suite; the new boundary test runs here with no live JMRI.
- An optional roster **integration** test (against a live JMRI with a populated roster) may already exist from 9.1/9.2; if so, ensure the CONTRIBUTING note documents the profile/fixture setup. Do not add a *hardware* gate.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-9.4] — the four AC clusters verbatim.
- [Source: _bmad-output/planning-artifacts/prd.md] — FR54–FR59, Journey 6 (catalog journey, lines ~563-617), roster-vs-Operations distinction, read-only boundary (FR56), `roster_catalog.py` (FR59).
- [Source: tests/unit/test_operations_boundary.py] — boundary-test template (8.3).
- [Source: examples/operations_report.py] — read-only discovery example template (8.3).
- [Source: src/pyjmri/roster.py:40-200] — `FunctionLabel`, `RosterEntry`, `Roster`, `by_address`.
- [Source: python_code/README.md:139-167] — Operations docs section template.
- [Source: python_code/RELEASES.md:1-40 / CONTRIBUTING.md] — release-notes format + Phase-A checklist.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (dev-story workflow)

### Debug Log References

- Full gate run (Phase A): `ruff check` clean; `ruff format --check` 75 files clean; `mypy --strict src/pyjmri` (22 files) clean; `mypy --strict examples/` (7 files) clean; `pytest -m "not integration"` → **756 passed, 27 deselected**.
- Build: `uv build` → `pyjmri-1.2.0.tar.gz` + `pyjmri-1.2.0-py3-none-any.whl`; `twine check dist/*` → PASSED (both).
- Boundary test alone: 76 passed (25 forbidden methods × 3 instances + 1 collection-surface test).
- Example verified without live JMRI via an inline smoke of `print_catalog` over an empty `Roster([])` and a hand-built 3-entry roster (empty-path message, per-loco sheet, and decoder rollup all render correctly).

### Completion Notes List

- **Task 1** — `tests/unit/test_roster_boundary.py` mirrors `test_operations_boundary.py`: parametrized `_FORBIDDEN_METHODS` × `RosterEntry`/`FunctionLabel`/`Roster`, plus a read-only collection-surface assertion (`by_address` callable; no mutator leaks; Mapping surface present). `RosterEntry.user_name` is always `None`, so no user-name assertion.
- **Task 2** — `examples/roster_catalog.py`: top-level-`pyjmri`-only imports, `--url`-only CLI, `discover_roster()` (no `discover()` first), `except* JMRIError`/`_leaf_messages`, exit codes 0/1/2. Prints per-loco road number, model, decoder family/model, owner, DCC address (+ long/short), comment, then a decoder rollup sorted by count. `mypy --strict` clean.
- **Task 3** — README `## Roster (read-only)` section added after the Operations section (distinction, lookup/unknown-loco rules, snapshot caveat, capability-from-labels, simulator-testable, read-only boundary). CONTRIBUTING baseline updated to **756 passed / 27 deselected** (three citations) and a roster-fixture note added to the integration-test policy.
- **Task 4** — `pyproject.toml` → `1.2.0`; `uv lock` (pyjmri 1.1.0 → 1.2.0); `RELEASES.md` `## v1.2.0` section added; built + `twine check` PASSED. **Stopped before Phase B** — no `uv publish`, no git tag, no GitHub release.
- **Out-of-scope gate fix (user-directed):** `examples/train_out_and_back.py` is Mikey's personal driving script and was not `mypy --strict` clean, which would have reddened the `mypy --strict examples/` release gate. Per Mikey's decision it **stays tracked in the repo** (he explicitly does not want his scripts gitignored); the gate is kept green instead by excluding the file from both `[tool.mypy]` and `[tool.ruff]` in `pyproject.toml`. No `src/pyjmri/` behavior changed; the script's content is untouched. (An earlier `git rm --cached` + `.gitignore` approach was reverted at the user's direction.)
- **Scope fence honored:** no `src/pyjmri/` behavior changes; the boundary test confirmed the existing roster surface is already read-only (test passed first run — the invariant held, nothing to fix). No new public names needed; `__all__` untouched.

### File List

- `python_code/tests/unit/test_roster_boundary.py` (new)
- `python_code/examples/roster_catalog.py` (new)
- `python_code/README.md` (modified — Roster section)
- `python_code/CONTRIBUTING.md` (modified — baseline + roster fixture note)
- `python_code/RELEASES.md` (modified — v1.2.0 section)
- `python_code/pyproject.toml` (modified — version 1.2.0; mypy/ruff exclude for the personal driving script so it doesn't gate the build)
- `python_code/uv.lock` (modified — version 1.2.0)
- `python_code/examples/train_out_and_back.py` (unchanged — stays tracked per user direction; excluded from mypy/ruff only)

## Change Log

| Date | Version | Description | Author |
|---|---|---|---|
| 2026-06-17 | 0.1 | Story drafted (create-story; context engine) | Create-Story |
| 2026-06-17 | 1.0 | Implemented: boundary test, `roster_catalog.py`, Roster docs, v1.2 Phase-A release (build + twine PASSED, stopped before publish). Gates green (756 passed). | Dev-Story |
| 2026-06-18 | 1.1 | Code review: 1 patch (hardened boundary test with Mapping mutators); status → done. Personal driving script kept tracked (not gitignored) per user direction, excluded from mypy/ruff only. | Code-Review |
