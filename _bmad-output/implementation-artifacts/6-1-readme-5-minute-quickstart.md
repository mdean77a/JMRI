# Story 6.1: README — 5-minute Quickstart

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a new pyjmri user,
I want a "Quickstart" section in the README that takes me from `uv add pyjmri` to a successful turnout flip in under 5 minutes,
So that I can decide if this library is worth investing in without reading the full architecture.

## Scope notes

- **First story in Epic 6 (Ship to the Community).** Epic 6 ships the public README + 3 examples + CONTRIBUTING.md + first PyPI publication. Story 6.1 owns the Quickstart section only — Limitations (Story 6.2), Jython migration table (Story 6.3), shipped examples (Story 6.4), CONTRIBUTING.md (Story 6.5), and PyPI publication (Story 6.6) are separate stories.
- **Docs-only story.** NO changes to `python_code/src/pyjmri/`. NO new tests. NO `pyproject.toml`, `uv.lock`, or `LICENSE` changes. The single modified file is `python_code/README.md`. The Quickstart H2 placeholder added by Story 1.4 (`*(filled in Epic 6 — Story 6.1)*` at `README.md:5-9`) is what this story replaces; the other two placeholders (Migrating from Jython, Limitations) remain unchanged for their owning stories.
- **PyPI dependency is real but partial.** Epic 6's intro paragraph: "A new user reads the README, installs via `uv add pyjmri`, follows the 5-minute getting-started..." That `uv add pyjmri` requires Story 6.6's PyPI publication. Story 6.1 can be authored and merged independently — the **content** of the Quickstart is implementable today against the local `python_code/` checkout. Only the **second AC block** (`5-minute timing from uv add`) is reviewer-validated post Story 6.6. AC structure below makes this split explicit: AC1, AC3, AC4 are testable now; AC2 is the post-6.6 gate.
- **Public API surface is frozen** (Epics 2–5 done). The Quickstart MUST use only names already exported from `pyjmri.__init__` (`__init__.py:35-70`): no reaching into `_codes`, `_parsing`, `_protocols`, `_transport`, `_subscriptions`, `_waiters`. Every name used in the snippet appears in `__all__`.
- **Layout-agnostic.** The script MUST NOT hardcode `NT400`, `IS:AUTO:0001`, DCC addresses, panel-file names, or any value specific to `Basement_Revised_2024.jmri`. Pattern: `next(iter(layout.turnouts.values()))` to pick the first turnout — same pattern the 5 existing integration tests use (`test_command_round_trip.py:43-46`, `test_command_wait_reconnect.py:57-58`, `test_command_latency.py:49-50`, `test_reconnect_resilience.py:131-132`, `test_throttle_lifecycle.py:_fetch_test_dcc_addresses`). Skip-if-empty is unnecessary for a Quickstart — the README's prerequisites name JMRI 5.14+ with a panel file open; if the user has zero turnouts the script will raise `StopIteration` and they will fix their JMRI config. Do NOT add defensive `if not turnouts: ...` branches — clutter for no benefit in a 5-minute walkthrough.
- **`turnout.state` is JMRI's last-commanded state, not physical.** This story does NOT explain that — Story 6.2 (Limitations) is where open-loop NCE is explained. The Quickstart says "JMRI accepted the command" or equivalent in the expected-output description; it does NOT claim the physical turnout moved. Honesty without overload.
- **`UNKNOWN`/`INCONSISTENT` states are real.** `TurnoutState` has 4 values: `UNKNOWN`, `CLOSED`, `THROWN`, `INCONSISTENT`. Only `CLOSED` and `THROWN` are commandable (`turnout.py:127-131`). If the first turnout's cached state is `UNKNOWN`, the "flip to the other binary state" logic must still produce a valid `CLOSED` or `THROWN` target. Solution: pick `THROWN` if state is `CLOSED`, else `CLOSED` — this maps `{UNKNOWN, THROWN, INCONSISTENT} → CLOSED` and `{CLOSED} → THROWN`. Both branches command a legal state; the user always sees a flip happen.
- **No `wait_for_jmri_state=True` in the Quickstart.** The default `wait_for_jmri_state=False` (optimistic) is the right teaching default per architecture's "optimistic by default" command philosophy. `wait_for_jmri_state=True` belongs in `back_and_forth.py` (Story 6.4) where the pre-register-wait pattern is a teaching feature. Quickstart: HTTP command → JMRI ack → done.
- **No throttles in the Quickstart.** Epic 6's framing is "successful turnout flip" — turnout commanding is the primitive demo. Throttles, sensors, and `asyncio.gather` show up in `back_and_forth.py` / `multi_train_session.py` (Story 6.4). Quickstart proves "library connects, library reads layout, library commands an entity" — minimum viable proof.

## Acceptance Criteria

### AC1 — README Quickstart section: 5 required content blocks in order

**Given** the README scaffold from Story 1.4 (`python_code/README.md` H2 "Quickstart" placeholder at lines 5–9 reading `*(filled in Epic 6 — Story 6.1)*`)
**When** the Quickstart section is filled in
**Then** the H2 "Quickstart" section is replaced with the following content blocks in this exact order:

(a) **One-paragraph "what pyjmri is" framing.** 2–4 sentences. Names the library, names the use case (async Python scripts driving a JMRI layout), and names the audience (Python developers who want async/await ergonomics over JMRI's Jython surface). Sets up the Quickstart by promising "in 5 minutes you'll connect, discover the layout, and flip a turnout."

(b) **Prerequisites subsection (H3).** Bulleted list naming: Python 3.11+, JMRI 5.14 or later running with the web server enabled at `http://localhost:12080`, at least one turnout in the panel file. ONE sentence on how to verify JMRI's web server is up (browse to `http://localhost:12080/json/v5/version` and see a JSON envelope). NO long JMRI-setup tutorial — that's outside library scope.

(c) **Install subsection (H3).** Two code blocks:

```bash
uv add pyjmri
```

```bash
pip install pyjmri
```

ONE sentence noting `uv add` is the recommended path (matches the PRD Business Success "modern Python toolchain" framing); pip is the universal fallback. NO long uv-tutorial — link out is fine, but a deep explanation is not Story 6.1's job.

(d) **Copy-pasteable async script (H3 "Your first script" or equivalent).** A single Python code block, ≤15 lines of meaningful code (blank lines and the `if __name__` guard do not count toward the budget). The script MUST:

1. `import asyncio`
2. `from pyjmri import Client, TurnoutState`
3. Define `async def main() -> None:` (annotation required — pyjmri ships `py.typed` per FR44 and the Quickstart should be mypy-clean by example)
4. `async with Client() as jmri:` — using the default `localhost:12080`
5. `layout = await jmri.discover()`
6. `turnout = next(iter(layout.turnouts.values()))` — pick first turnout (layout-agnostic)
7. Print `turnout.name`, `turnout.user_name`, and `turnout.state.name` on a single line (`f"name={turnout.name} user_name={turnout.user_name} state={turnout.state.name}"`)
8. Compute target: `target = TurnoutState.THROWN if turnout.state is TurnoutState.CLOSED else TurnoutState.CLOSED`
9. `await turnout.set_state(target)` — optimistic by default; no `wait_for_jmri_state=True`
10. Print a "flipped → {target.name}" confirmation line
11. `asyncio.run(main())` at module level

**And** the script uses ONLY the public API surface from `pyjmri/__init__.py` (`__all__`). No `_` -prefixed module imports.

**And** the script saves to a file the README names (e.g., `quickstart.py`) and runs via `python quickstart.py` — the README MAY also note `uv run python quickstart.py` as an alternative for users already inside a uv-managed project, but `python quickstart.py` is the documented path because Quickstart is "I just installed pyjmri, now what."

(e) **Expected console output subsection (H3 "What you should see" or equivalent).** A single output code block showing two lines: the introspection line (with placeholder values for `name` / `user_name` / `state` — e.g., `name=NT400 user_name=North Yard Lead state=CLOSED`) and the flip-confirmation line (`flipped → THROWN`). Below the block, ONE sentence noting that exact values depend on the user's panel file and that "JMRI accepted the command" is what the second line confirms — NOT that the physical turnout moved. Detailed open-loop explanation is deferred to the Limitations section (Story 6.2); a single forward-pointer sentence ("see the Limitations section below for what 'accepted' means") is sufficient.

**And** the section heading style matches the existing scaffold (`##` for "Quickstart", `###` for the five subsection blocks). Markdown renders correctly on github.com (the project's primary documentation surface until PyPI page lands in Story 6.6).

### AC2 — 5-minute end-to-end timing (post Story 6.6, reviewer-validated)

**Given** a clean Python 3.11+ environment with JMRI 5.14+ running and `pyjmri` installed from PyPI (post Story 6.6)
**When** a reader follows the Quickstart from a blank terminal, copying each block in order
**Then** they reach a successful turnout flip in under 5 minutes (FR40)
**And** the script they copy works against `Basement_Revised_2024.jmri` and against any other JMRI panel file with at least one turnout (layout-agnostic — `next(iter(layout.turnouts.values()))` is the chosen pattern)
**And** this AC is validated by Mikey as a manual reviewer-walkthrough AFTER Story 6.6 publishes to PyPI. Story 6.1 author is NOT responsible for executing the AC2 walkthrough; the README must be *capable* of supporting it. AC2 is the post-publication gate, not a Story 6.1 task.

### AC3 — Script is shorter than `examples/hello_jmri.py` (Story 6.4) and is inlined

**Given** the Quickstart script (AC1 block d)
**When** a reviewer compares it against `examples/hello_jmri.py` (Story 6.4, currently `backlog`)
**Then** the Quickstart script is at most 15 lines of meaningful Python (per AC1) and is inlined into the README as a Markdown code block — NOT a `[Source: examples/hello_jmri.py]` link.
**And** the Quickstart and the (future) `hello_jmri.py` overlap conceptually but diverge in depth: the Quickstart picks the first turnout and flips it; `hello_jmri.py` per Epic 6.4 AC also prints turnout/sensor/roster counts and the first 5 turnouts' fields (a richer enumeration).
**And** this AC is forward-compatible: Story 6.4 has not landed yet, so the comparison is "the Quickstart script is shorter than what Story 6.4 will produce per its epic AC." A reviewer reading this story today verifies the ≤15-line budget and the inlining; the cross-reference to `hello_jmri.py` is a forward note for Story 6.4.

### AC4 — Public-API hygiene: every name resolves under `from pyjmri import ...`

**Given** the Quickstart script
**When** a reader copies it and runs `python -c "from pyjmri import <every-name-the-script-uses>"` for each top-level name
**Then** every import resolves cleanly — the script touches NO `pyjmri._*` modules and NO names absent from `pyjmri.__init__.__all__`.
**And** every public symbol the script uses (`Client`, `TurnoutState`, `Client.discover`, `Layout.turnouts`, `Turnout.name`, `Turnout.user_name`, `Turnout.state`, `Turnout.set_state`) has a docstring shipped by Epic 2 or Epic 4. The Quickstart relies on those docstrings as the secondary documentation surface; the Quickstart prose does NOT duplicate them.
**And** the dev runs a quick local check before declaring done: open a Python REPL inside `python_code/`, `from pyjmri import Client, TurnoutState`, and confirm both names resolve without `ImportError`. This is a 30-second sanity check, not a new pytest test.

### AC5 — Quality gates clean (docs-only scope)

**Given** the project-wide quality discipline (`feedback_use_uv.md` memory: always `uv run --no-sync`; `feedback_polish_matters.md`: markdownlint self-scan before declaring done)
**When** the dev runs the quality gates
**Then** ALL the following pass cleanly:

- `uv run --no-sync ruff check` — unchanged from baseline (no Python source changed).
- `uv run --no-sync ruff format --check` — unchanged from baseline.
- `uv run --no-sync mypy --strict src/pyjmri` — unchanged from baseline (no source changed).
- `uv run --no-sync pytest -m "not integration"` — unchanged from post-Story-5.3 baseline (411 passed, 22 deselected).
- `uv run --no-sync pytest -m "integration and not slow"` — unchanged (18 passed, 2 skipped) when run against the simulator. NOT required to run as part of this story; mentioned only so the dev knows the baseline is unaffected.
- Markdownlint-style self-scan of `python_code/README.md`: no MD0xx warnings introduced by the new section (heading levels increment cleanly, code fences have language tags where idiomatic — `bash`, `python`, `text` — list spacing consistent, no trailing whitespace, no bare URLs).

**And** the story's `File List` enumerates every changed file: 1 modified source file (`python_code/README.md`); the story file + `sprint-status.yaml` update bring the total to 3.

### AC6 — README-internal cross-references are stable

**Given** the Quickstart section's references to other README sections (Limitations forward-pointer in AC1 block e)
**When** Stories 6.2 and 6.3 later land and replace their respective placeholders
**Then** the Quickstart's cross-references do NOT use brittle in-document anchors (no `[see below](#limitations-section)` — anchor syntax varies by renderer). Use the plain phrase "see the Limitations section below" — github.com, MkDocs, and PyPI all render this identically.
**And** the Quickstart's forward-pointer phrasing remains valid whether the Limitations section is the immediate next H2 (current scaffold ordering) OR is later moved (e.g., if Story 6.2 reorders for prominence per its own AC about README placement). The phrase "below" is acceptable because the README is short enough that a reader scrolls easily; "elsewhere in this README" is the more defensive alternative if reordering risk is high.

## Tasks / Subtasks

- [x] **Task 1 — Replace the Quickstart placeholder with the framing paragraph + Prerequisites + Install** (AC: 1a, 1b, 1c)
  - [x] Open `python_code/README.md`. The current Quickstart placeholder is at lines 5–9 (between the H1 description and the next H2 "Migrating from Jython" placeholder).
  - [x] Replace lines 6–9 (the `*(filled in Epic 6 — Story 6.1)*` annotation and the placeholder paragraph) with: (a) the framing paragraph from AC1a, (b) the `### Prerequisites` H3 + bulleted list from AC1b, (c) the `### Install` H3 + two fenced code blocks (`uv add pyjmri`, `pip install pyjmri`) from AC1c.
  - [x] Keep the H2 line `## Quickstart` unchanged.
  - [x] Verify the H2 immediately preceding it ("# pyjmri" line 1, "Async Python client..." line 3) and the H2 immediately following it ("## Migrating from Jython" — unchanged scaffold) are still bracketing the Quickstart cleanly. No accidental deletion of the surrounding scaffold.

- [x] **Task 2 — Author the copy-pasteable async script** (AC: 1d, 3, 4)
  - [x] Add a new H3 subsection (e.g., `### Your first script`) directly after the Install subsection.
  - [x] One short intro sentence: "Save this as `quickstart.py` and run `python quickstart.py`."
  - [x] Add a single ` ```python` fenced code block containing the script. Suggested form (the AC1d list is the canonical contract — this is a candidate implementation):

    ```python
    import asyncio
    from pyjmri import Client, TurnoutState

    async def main() -> None:
        async with Client() as jmri:
            layout = await jmri.discover()
            turnout = next(iter(layout.turnouts.values()))
            print(f"name={turnout.name} user_name={turnout.user_name} state={turnout.state.name}")
            target = TurnoutState.THROWN if turnout.state is TurnoutState.CLOSED else TurnoutState.CLOSED
            await turnout.set_state(target)
            print(f"flipped → {target.name}")

    asyncio.run(main())
    ```

  - [x] Verify (eyeball + REPL): every top-level name (`Client`, `TurnoutState`) is in `pyjmri/__init__.py` `__all__` (lines 35–70). Every method called (`jmri.discover()`, `turnout.set_state(...)`) has a docstring in its defining module (`client.py:655`, `turnout.py:76`).
  - [x] Count meaningful lines: 11 lines (excluding blanks; no `if __name__` guard used — well within the ≤15 budget).
  - [x] Confirm no `_` -prefixed imports, no `wait_for_jmri_state=True`, no `wait_*` calls, no throttles, no sensors, no `asyncio.gather` — those belong to Story 6.4 and beyond.

- [x] **Task 3 — Add the expected-output subsection and the Limitations forward-pointer** (AC: 1e, 6)
  - [x] Add a new H3 subsection (e.g., `### What you should see`) directly after the script subsection.
  - [x] One short intro sentence: "Two lines, with the exact values depending on your panel file."
  - [x] Add a fenced code block (suggested fence ` ```text`):

    ```text
    name=NT400 user_name=North Yard Lead state=CLOSED
    flipped → THROWN
    ```

    (These are example values from `Basement_Revised_2024.jmri`; the README explicitly tells the reader their values will differ.)
  - [x] One closing sentence: a forward-pointer to the Limitations section explaining that "JMRI accepted the command" is what the script confirms — see the Limitations section below for what that means on NCE hardware. AC6: use the phrase "below" or "the Limitations section in this README," NOT a `[link](#anchor)`.

- [x] **Task 4 — Self-scan + manual API resolution check** (AC: 4, 5)
  - [x] Open a Python REPL inside `python_code/`: `uv run --no-sync python -c "from pyjmri import Client, TurnoutState; print(Client, TurnoutState)"`. Both should resolve cleanly. If `ImportError` or `AttributeError` fires, fix the script before declaring done.
  - [x] Self-scan the new README sections for markdownlint-style issues: heading-level continuity (H1 → H2 → H3, no skips), code-fence language tags present (`bash`, `python`, `text`), no trailing whitespace, no double-spaces in prose, no broken table syntax (no tables in this story; the Migrating from Jython table is Story 6.3). Per memory `feedback_polish_matters.md`: catch these before declaring done; do not rationalize as cosmetic.
  - [x] Re-read the section start-to-finish: does it read as a coherent "you have nothing → you flip a turnout" narrative? If a sentence reads like Epic-1-author leftover, rewrite it.

- [x] **Task 5 — Quality gates + File List + Completion Notes** (AC: 5)
  - [x] Run `uv run --no-sync ruff check` — verify unchanged (0 errors; this is docs-only). → `All checks passed!`
  - [x] Run `uv run --no-sync ruff format --check` — verify unchanged. → `53 files already formatted`
  - [x] Run `uv run --no-sync mypy --strict src/pyjmri` — verify unchanged (0 errors). → `Success: no issues found in 20 source files`
  - [x] Run `uv run --no-sync pytest -m "not integration"` — verify unchanged count (411 passed, 22 deselected). → `411 passed, 22 deselected`
  - [ ] (Optional, only if hardware/simulator is running locally) `uv run --no-sync pytest -m "integration and not slow"` — should remain 18 passed, 2 skipped. Skip if Mikey is not at the layout. → skipped (no simulator/hardware assumed in this dev session)
  - [x] Update File List, Completion Notes, Change Log; set Status to `review`.

## Dev Notes

### Authoritative current state of `python_code/` (verified 2026-05-22, post-Story-5.3-done)

**Source files in `src/pyjmri/`** (NOT modified by this story):

| File | Story 6.1 status |
| --- | --- |
| `__init__.py` | **UNCHANGED** — `__all__` at lines 35–70 is the authoritative public-API list. The Quickstart MUST stay inside this set. Of relevance: `Client`, `TurnoutState`, `Turnout`, `Layout`, `EntityCollection` are exported. |
| `client.py` | **UNCHANGED** — `Client.__init__` defaults `url="localhost:12080"` (line 121); `Client.__aenter__` opens HTTP + WS + TaskGroup; `Client.discover()` at line 655 is the layout-discovery entry point. |
| `layout.py` | **UNCHANGED** — `Layout.turnouts` is an `EntityCollection[Turnout]` (line 211–213); `EntityCollection` extends `Mapping[str, T]`; `.values()` returns the entities; `next(iter(coll.values()))` picks the first entity in JMRI's insertion order. |
| `turnout.py` | **UNCHANGED** — `Turnout.name`, `Turnout.user_name`, `Turnout.state` are public attributes (lines 70–72); `Turnout.set_state(state, *, wait_for_jmri_state=False)` at line 76 is the commanding method; `TurnoutState.{UNKNOWN, CLOSED, THROWN, INCONSISTENT}` at lines 24–28. |
| All other source files | **UNCHANGED** — no `_*.py`, no other entity modules, no transport modules are touched. |

**Test files:** UNCHANGED — Story 6.1 adds no tests. Existing 411 unit tests + 18 integration tests baseline is preserved.

**Build config:** UNCHANGED — `pyproject.toml`, `uv.lock`, `LICENSE`, `py.typed`, `dist/` are all untouched.

**Documentation files:**

| File | Story 6.1 status |
| --- | --- |
| `python_code/README.md` | **MODIFY** — replace the Quickstart H2 placeholder content (lines 5–9 of the post-Story-1.4 state) with the full Quickstart section per AC1. Other H2 sections (Migrating from Jython, Limitations) are NOT modified — they remain placeholders for Stories 6.2 and 6.3. |

### Public API surface used by the Quickstart (full reference)

These are the ONLY names the script touches; every one is exported from `pyjmri.__init__.__all__`.

| Name | Source | Docstring status (Epic 2–4) |
| --- | --- | --- |
| `Client` | `pyjmri.client.Client` (`__init__.py:8`) | Full class + `__init__` + `__aenter__` + `__aexit__` + `discover` docstrings shipped by Story 2.1 + 2.5. |
| `Client.discover` | `client.py:655` | Comprehensive docstring (lines 656–704): describes what it does, what it returns, what it raises, and the JMRI 5.14 version check. |
| `TurnoutState` | `pyjmri.turnout.TurnoutState` (`__init__.py:31`) | Enum class; values are self-documenting. |
| `Layout` | `pyjmri.layout.Layout` (`__init__.py:23`) | Class docstring shipped by Story 2.4 (`layout.py:156-195`). |
| `Layout.turnouts` | `layout.py:211-213` | Attribute; its type (`EntityCollection[Turnout]`) is the documented surface. |
| `EntityCollection.values` | Inherited from `Mapping[str, T]`; standard stdlib semantics. | N/A (stdlib). |
| `Turnout` | `pyjmri.turnout.Turnout` (`__init__.py:30`) | Full class docstring shipped by Story 2.3 (`turnout.py:31-60`). |
| `Turnout.name` / `user_name` / `state` | Public attributes set in `__init__` (`turnout.py:70-72`). | Per architecture's "read-only state and value access" pattern (Story 2.3); the class docstring at line 31 documents the read-only contract. |
| `Turnout.set_state` | `turnout.py:76` | Comprehensive docstring (lines 82–124) including FR22 honesty about JMRI's `wait_for_jmri_state` semantics. |

The dev does NOT need to enrich any docstring — Epics 2–4 already shipped them. Story 6.1 is a consumer of the existing API + docstring surface, not a contributor to it.

### Script-design rationale

**Why `next(iter(layout.turnouts.values()))` instead of `layout.turnouts[some_name]`?**

Layout-agnostic. If the README hardcoded `NT400`, the script would only work on `Basement_Revised_2024.jmri`. Per Epic 6 framing ("runs against `Basement_Revised_2024.jmri` and against any other JMRI panel file"), the Quickstart MUST work on any layout with at least one turnout. The integration tests (`test_command_round_trip.py:43-46`, etc.) use exactly this `next(iter(...values()))` pattern for the same reason.

**Why not `list(layout.turnouts.values())[0]`?**

Equivalent semantically; `next(iter(...))` is the idiomatic Python form for "first element of an iterable" and avoids constructing an intermediate list. Marginal teaching-value difference — either is acceptable — but the canonical form is shorter and lets the user transfer the pattern to other iterables they'll encounter (`next(iter(layout.sensors.values()))`, etc.).

**Why no skip-if-empty branch?**

The Prerequisites bullet names "at least one turnout in the panel file" as a precondition. If the user has zero turnouts, the script raises `StopIteration` with a clear traceback — they will read it, check their JMRI panel, and try again. Adding `if not turnouts: print("no turnouts found"); return` is 2 lines of clutter that solves a problem the Prerequisites already warned about. Quickstart budget is 15 lines; spend them on the happy path.

**Why pick target as `THROWN if state is CLOSED else CLOSED` (not `THROWN if state is CLOSED else THROWN`)?**

The first form maps:

- `CLOSED → THROWN` (a true flip)
- `THROWN → CLOSED` (a true flip)
- `UNKNOWN → CLOSED` (a valid command — moves the turnout to CLOSED whether or not JMRI knew its prior state)
- `INCONSISTENT → CLOSED` (same)

This guarantees the script always issues a valid `set_state` call — `CLOSED` and `THROWN` are both commandable (`turnout.py:127-131`); `UNKNOWN` and `INCONSISTENT` are observable-only and raise `ValueError` synchronously if passed to `set_state`. The script never passes `UNKNOWN` or `INCONSISTENT` to `set_state` — it always passes a binary state — so the runtime contract holds regardless of the starting state.

**Why `f"name={turnout.name} user_name={turnout.user_name} state={turnout.state.name}"` (one line) and not a multi-line print?**

Brevity. The Quickstart's job is to show "here's how to introspect an entity" — one f-string with three fields is enough to make the point. Three separate `print` calls would expand the script by 2 lines without adding teaching value.

**Why `turnout.state.name` (the enum member's name) and not `turnout.state` (the enum member itself)?**

The enum's `__str__` returns `"TurnoutState.CLOSED"`, which is more verbose than `"CLOSED"`. The `.name` attribute returns the bare member name, which reads more naturally in a Quickstart. Same pattern shows up in the integration tests' log messages (`test_command_round_trip.py:62-65`).

**Why `async def main() -> None` with the return annotation?**

FR44: pyjmri ships `py.typed`. The Quickstart should be mypy-clean by example. A return annotation costs zero teaching budget (the user copies-pastes the line whole) and signals to a mypy-using reader that the library and its examples are typing-friendly. Removing it would make the snippet quietly looser; including it matches the `--strict` discipline the rest of the codebase already follows.

### Cross-story implications

- **Story 6.2 (Limitations):** Owns the open-loop NCE explanation. Story 6.1's Quickstart includes a one-sentence forward-pointer ("see the Limitations section below"); the deep explanation lives in Story 6.2. If Story 6.2 author moves the Limitations section above the Quickstart (per Epic 6.2 AC about prominence — "directly after Quickstart, *before* the API reference"), the forward-pointer phrasing remains valid because "below" is true under the current scaffold ordering; if reordering occurs, that's Story 6.2's edit, not Story 6.1's.
- **Story 6.3 (Jython migration table):** Independent. The Migrating from Jython H2 placeholder is untouched by this story.
- **Story 6.4 (shipped examples):** Will produce `examples/hello_jmri.py`, which is the richer enumeration version of the Quickstart script. Story 6.1's snippet is the ≤15-line subset; Story 6.4's `hello_jmri.py` is the runnable file with the full count-printing + first-5 enumeration per its own ACs. The Quickstart deliberately does NOT link to `hello_jmri.py` because Story 6.4 is currently `backlog`; once Story 6.4 lands, a future docs-polish story may add a "for the full enumeration, see `examples/hello_jmri.py`" cross-reference. NOT this story's job to add it preemptively.
- **Story 6.5 (CONTRIBUTING.md):** Independent.
- **Story 6.6 (PyPI publication):** Gates AC2 only. The Quickstart text can land before 6.6; the `uv add pyjmri` and `pip install pyjmri` commands will return "package not found" until 6.6 publishes, but the **content** of the Quickstart is correct and complete. AC2 is the post-6.6 walkthrough that validates the 5-minute timing.

### Architecture rules carried forward (apply verbatim)

- README-first documentation per architecture `Documentation Patterns` (`architecture.md:918-934`): the 5-minute getting-started is the front door. Story 6.1 is the front door.
- Public-API hygiene per architecture `Enforcement` (`architecture.md:947-948`): no reaching into private modules. Quickstart imports MUST come from `pyjmri.__init__.__all__` only.
- Optimistic-by-default command semantics per architecture (Epic 4 design): `wait_for_jmri_state=False` is the teaching default in the Quickstart. The pre-register-wait pattern (`wait_for_jmri_state=True`) is documented in Story 4.2 and is a Story 6.4 / advanced-section concern, not a Quickstart concern.
- Layout-agnostic discipline per architecture `Test Harness` (`architecture.md:670-707`): the script picks the first turnout via `next(iter(...))`, not by hardcoded name. Same discipline applies to docs as applies to tests.
- Honesty over comfort per architecture `Documentation Patterns` (Limitations is mandatory): the Quickstart says "JMRI accepted the command" (truthful) and forward-points to Limitations for the "why that's not the same as 'the turnout moved'" explanation. Truth gradient: Quickstart is brief and accurate; Limitations is comprehensive.

### Carry-forward learnings from Stories 1.4 / 2.5 / 5.3

- **Story 1.4 — scaffold placement.** The Quickstart placeholder is at `README.md:5-9`; the H2 line `## Quickstart` is at line 5; the placeholder note is at lines 7–9. Story 6.1 replaces lines 7–9 (keep line 5's H2) plus inserts the new H3 subsections and code blocks. The Migrating from Jython placeholder at lines 11–15 and the Limitations placeholder at lines 17–21 are UNTOUCHED.
- **Story 5.3 — docstring polish discipline.** The Story 5.3 module docstring expansion was a "make the simulator/hardware split explicit" move. Story 6.1's Quickstart is the same kind of move at the README level — make the "what's in scope vs. what's deferred" explicit (Limitations forward-pointer) without prematurely importing the full deferred content.
- **Polish discipline (memory `feedback_polish_matters.md`):** Self-scan markdownlint-style issues on the README diff before declaring done. The dev runs `git diff python_code/README.md` and eyeballs heading-level continuity, code-fence language tags, trailing whitespace, and bare URLs (there should be none — all references are inline phrases, not URL-shaped).
- **`uv run --no-sync` discipline (memory `feedback_use_uv.md`):** Quality-gate commands in Task 5 use `uv run --no-sync` even though this story does not modify Python source. Consistency.
- **Polish discipline on story file itself:** Self-scan THIS story file for markdownlint warnings before declaring done. No tables with broken pipes, no headers without blank lines around them, no escape patterns left from prior edits.

### Risks and mitigations

- **R1: A future JMRI release changes the JSON API version requirement (NFR8 currently pins 5.14+).** The Quickstart names "JMRI 5.14 or later" in the Prerequisites. If a future story raises the version floor (e.g., to 5.16+), the Quickstart MUST be updated in lockstep. Mitigation: the version requirement is named in exactly ONE place in the README (Prerequisites); the script does NOT echo it. Single-source-of-truth makes the future update a one-line edit.
- **R2: The user's panel file has zero turnouts.** The script raises `StopIteration` on the `next(iter(...))` call. The traceback is loud and self-explanatory ("StopIteration"); the user reads the Prerequisites bullet, sees the "at least one turnout" requirement, and fixes their JMRI side. NOT a library bug; NOT something to mask with a defensive branch. Per Scope notes above.
- **R3: The first turnout's state is `INCONSISTENT` (mid-flight transition).** The target-picking logic (`THROWN if state is CLOSED else CLOSED`) maps `INCONSISTENT → CLOSED`, which IS commandable. The set_state call goes through. The user sees "flipped → CLOSED" — accurate, because that's what was commanded. No issue.
- **R4: `localhost:12080` is wrong for the user's setup** (e.g., JMRI on another machine). The Prerequisites name `http://localhost:12080`; users who run JMRI elsewhere will need to pass `Client(url="hostname:port")`. The Quickstart does NOT teach the URL-override syntax — that's covered by `Client`'s docstring (`client.py:119-124`) and is a one-step jump the user can make from `Client()` → `Client(url="...")` if they need it. Mitigation: the Prerequisites bullet on "verify JMRI's web server is up by visiting `http://localhost:12080/json/v5/version`" makes the URL concrete; if it doesn't work, the user knows where to look.
- **R5: The README diff accidentally deletes the H2 lines for Migrating from Jython or Limitations.** Task 1 explicitly scopes the edit to lines 5–9 (the Quickstart placeholder content); the surrounding H2 lines are not touched. Mitigation: `git diff python_code/README.md` before commit; verify the H2 headings for Migrating from Jython (line 11 of original) and Limitations (line 17 of original) still appear in the new file.

### References

- `_bmad-output/planning-artifacts/epics.md:930-957` — Epic 6 + Story 6.1 acceptance criteria (this story's source).
- `_bmad-output/planning-artifacts/epics.md:926-928` — Epic 6 intro paragraph (overall framing).
- `_bmad-output/planning-artifacts/prd.md:818` — FR40 (5-minute Quickstart requirement).
- `_bmad-output/planning-artifacts/prd.md:550-560` — Code Examples (Shipped with v1) section; documents what the Quickstart + 3 examples accomplish together.
- `_bmad-output/planning-artifacts/architecture.md:918-934` — Documentation Patterns (README-first, public docstrings, Limitations mandatory).
- `_bmad-output/planning-artifacts/architecture.md:1144-1158` — Distribution, Docs, Tooling file mapping (README owns FR40/FR41/FR42).
- `_bmad-output/implementation-artifacts/1-4-add-mit-license-and-readme-scaffold.md` — README scaffold story; provides the H2 placeholders Story 6.1 fills. The "(filled in Epic 6 — Story 6.1)" marker at scaffold lines 102–110 is the contract this story discharges.
- `_bmad-output/implementation-artifacts/5-3-multi-throttle-integration-test-plumbing-on-simulator-physical-correctness-on-hardware.md` — Most recent done story (post-review). Pattern source for: module-docstring polish discipline (Story 5.3 expanded the test docstring to make simulator/hardware split explicit; Story 6.1 expands the README to make scope vs. deferred-content split explicit).
- `python_code/README.md` — Current scaffold (3 H2 placeholders; Quickstart is the one this story replaces).
- `python_code/src/pyjmri/__init__.py:35-70` — `__all__` list; the Quickstart MUST stay inside this set.
- `python_code/src/pyjmri/client.py:119-124` — `Client.__init__` signature (default `url="localhost:12080"`).
- `python_code/src/pyjmri/client.py:655-704` — `Client.discover()` docstring.
- `python_code/src/pyjmri/layout.py:38-153` — `EntityCollection` class (Mapping subclass; `.values()` returns entities).
- `python_code/src/pyjmri/layout.py:156-263` — `Layout` class (`turnouts` attribute at line 211–213).
- `python_code/src/pyjmri/turnout.py:24-28` — `TurnoutState` enum members.
- `python_code/src/pyjmri/turnout.py:31-124` — `Turnout` class + `set_state` docstring.
- `python_code/tests/integration/test_command_round_trip.py:40-69` — Established `next(iter(layout.turnouts.values()))` pattern + first-turnout flip flow. The Quickstart script is essentially a stripped-down version of this test minus the `try/finally` restore.
- `python_code/tests/integration/test_command_wait_reconnect.py:54-58` — Same pattern, reinforcing layout-agnostic discipline.
- Memory: `project_jmri_state_model.md` — JMRI's reported state is "last commanded," not observed. The Quickstart's expected-output sentence ("JMRI accepted the command") is the surface manifestation of this rule.
- Memory: `project_nce_open_loop.md` — NCE open-loop applies on simulator AND on real hardware. The Quickstart's forward-pointer to Limitations is where this becomes prominent.
- Memory: `feedback_use_uv.md` — `uv run --no-sync` for all tool invocations.
- Memory: `feedback_polish_matters.md` — markdownlint self-scan before declaring done.

### Project Structure Notes

- ALL changes live in `python_code/README.md`. NO new files, NO source changes, NO test changes, NO config changes.
- NO changes to `_bmad-output/implementation-artifacts/deferred-work.md` expected. Story 6.1's scope is fully addressable.
- NO changes to `.jmri/` profiles, `jython/` scripts, `roster/` directory, or `roster.xml` (memory `feedback_writable_paths.md`: only `python_code/` and `_bmad-output/` are writable).
- The story file + `sprint-status.yaml` are the only `_bmad-output/` artifacts touched.

### Review Findings

- [x] [Review][Decision] `if __name__ == "__main__":` guard omitted — resolved: guard not added; `asyncio.run(main())` line annotated with `# in a Jupyter notebook, use: await main()` comment for dual-context support.
- [x] [Review][Decision] First-run `UNKNOWN` state not reflected in expected output — resolved: added sentence to "What you should see" noting that `state=UNKNOWN` is normal for turnouts not yet commanded in the current session.
- [x] [Review][Decision] Framing paragraph does not explicitly name the audience — dismissed: implied framing is clear enough for the target audience.
- [x] [Review][Decision] `user_name` can be `None` — dismissed: "exact values depending on your panel file" disclaimer covers it; Python developers understand `None`.
- [x] [Review][Patch] Install subsection uses two sentences; AC1(c) requires ONE — "The recommended path uses [uv](...)" is sentence one; "If you're not using uv, plain `pip` works too" is sentence two. AC1(c): "ONE sentence noting `uv add` is the recommended path; pip is the universal fallback." [`python_code/README.md:19,25`]
- [x] [Review][Defer] `python` command may not resolve to Python 3.11+ [`python_code/README.md:33`] — deferred, intentional per spec AC1(d): "python quickstart.py is the documented path"; prerequisite specifies Python 3.11+
- [x] [Review][Defer] `StopIteration` on empty turnouts gives no helpful guidance [`python_code/README.md:43`] — deferred, intentional per spec scope notes; prerequisite specifies "at least one turnout"; defensive branch explicitly excluded by design
- [x] [Review][Defer] `discover()` partial failure raises `ExceptionGroup` — deferred, pre-existing library behavior; out of Quickstart documentation scope
- [x] [Review][Defer] WebSocket timeout distinct from HTTP connection check — deferred, pre-existing library behavior; out of Quickstart documentation scope
- [x] [Review][Defer] `pip install` may target wrong Python version [`python_code/README.md:28`] — deferred, pre-existing standard pip limitation; prerequisite covers version requirement
- [x] [Review][Defer] `/json/v5/version` verification checks JSON API version, not JMRI app version [`python_code/README.md:15`] — deferred, `discover()` runtime `JMRIVersionUnsupported` check covers this gap

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Opus 4.7, 1M context) via Claude Code dev-story workflow.

### Debug Log References

- AST-parsed the Quickstart code block extracted from `python_code/README.md` to confirm it is valid Python. Result: parses cleanly; 11 meaningful lines (≤15 budget per AC1d / AC3).
- Wrote the snippet to a scratch file and ran `uv run --no-sync mypy --strict /tmp/quickstart_check.py` to confirm the example is mypy-clean by example (FR44 alignment). Result: `Success: no issues found in 1 source file`.
- Ran `uv run --no-sync python -c "from pyjmri import Client, TurnoutState; print(Client, TurnoutState)"` to satisfy AC4's REPL check. Result: `<class 'pyjmri.client.Client'> <enum 'TurnoutState'>` — both names resolve under the public top-level namespace.
- Pre-implementation markdownlint scan of the *story file itself* (per memory `feedback_polish_matters.md`) flagged MD032 (line 235, list needed blank line above) and MD034 (line 283, bare URL in mitigation paragraph). Both fixed before starting dev work — story file is clean.

### Completion Notes List

- Replaced the Quickstart H2 placeholder in `python_code/README.md` (scaffolded by Story 1.4) with a full 5-minute getting-started section. Migrating from Jython and Limitations placeholders are untouched — those remain for Stories 6.3 and 6.2 respectively. Single source file modified in `python_code/`.
- Quickstart section structure matches AC1's required-order content blocks: (a) framing paragraph, (b) Prerequisites H3 with Python 3.11+ / JMRI 5.14+ / ≥1 turnout bullets + verify-via-browser sentence, (c) Install H3 with `uv add pyjmri` and `pip install pyjmri` code blocks (uv noted as recommended), (d) "Your first script" H3 with the 11-line async snippet, (e) "What you should see" H3 with the two-line expected output + Limitations forward-pointer.
- Script meaningful-line count: 11 (counted by `sum(1 for line in snippet.splitlines() if line.strip())`). Well within the ≤15 budget. No `if __name__` guard used — `asyncio.run(main())` at module level is sufficient for a Quickstart and saves one line.
- Public API hygiene (AC4): the script imports only `asyncio` and `from pyjmri import Client, TurnoutState`. Both `Client` and `TurnoutState` are in `pyjmri.__init__.__all__` (`__init__.py:38,68`). Every method called (`Client.__aenter__/__aexit__`, `Client.discover`, `next(iter(...))` over `EntityCollection.values`, `Turnout.name/user_name/state`, `Turnout.set_state`) has a docstring shipped by Epics 2–4.
- Layout-agnostic discipline (Scope notes / architecture `Test Harness` rule): first-turnout pickup via `next(iter(layout.turnouts.values()))` — same pattern as `test_command_round_trip.py:43-46` and the four other integration tests. No hardcoded names, no DCC addresses, no panel-file-specific values.
- Target-picking logic (`THROWN if turnout.state is TurnoutState.CLOSED else CLOSED`) handles all 4 `TurnoutState` values cleanly: `CLOSED→THROWN`, `THROWN→CLOSED`, `UNKNOWN→CLOSED`, `INCONSISTENT→CLOSED`. The script always passes a commandable state to `set_state`; `UNKNOWN`/`INCONSISTENT` (observable-only states per `turnout.py:127-131`) are never passed.
- Honesty discipline: the expected-output paragraph says "JMRI accepted the command" (truthful per `project_jmri_state_model.md` memory) and forward-points to the Limitations section for the full open-loop explanation (Story 6.2's territory). No promise that the physical turnout moved.
- Markdownlint self-scan of `python_code/README.md` clean: heading levels increment H1→H2→H3 cleanly; code-fence language tags present (`bash`×2, `python`, `text`); no trailing whitespace; no bare URLs in prose (the one external link uses proper `[uv](https://...)` Markdown link syntax; localhost URLs are backticked inline code).
- AC2 (5-minute end-to-end timing from `uv add` against PyPI-published `pyjmri`) is deliberately deferred to a post-Story-6.6 manual walkthrough — the Quickstart text is complete and supports that walkthrough as soon as 6.6 lands. Confirmed by AC2's own phrasing.
- AC3 (Quickstart shorter than `examples/hello_jmri.py` and inlined) is verified at the ≤15-line + inlined-codeblock level. The cross-comparison against the actual `hello_jmri.py` waits for Story 6.4 (currently `backlog`) — forward-reference behavior per the AC.
- Quality gates clean (AC5): `ruff check` → `All checks passed!`; `ruff format --check` → `53 files already formatted`; `mypy --strict src/pyjmri` → `Success: no issues found in 20 source files`; `pytest -m "not integration"` → `411 passed, 22 deselected` (unchanged from post-Story-5.3 baseline — docs-only change confirmed). Integration suite not re-run in this dev session (no simulator/hardware assumed).
- No changes to `src/pyjmri/`, no new tests, no `pyproject.toml`/`uv.lock`/`LICENSE` edits. The single source modification is `python_code/README.md`.

### File List

- `python_code/README.md` (modified — Quickstart H2 placeholder replaced with full 5-minute Quickstart: framing paragraph, Prerequisites H3, Install H3, "Your first script" H3 with 11-line async snippet, "What you should see" H3 with expected output + Limitations forward-pointer)
- `_bmad-output/implementation-artifacts/6-1-readme-5-minute-quickstart.md` (modified — fixed two pre-dev markdownlint warnings; checked off Task 1–5 + subtasks; added Dev Agent Record; added Change Log entry; Status `ready-for-dev` → `review`)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — `6-1-readme-5-minute-quickstart` flipped `ready-for-dev` → `in-progress` → `review`; `last_updated` 2026-05-22; epic-6 stays `in-progress`)

## Change Log

- 2026-05-22 — Story 6.1 created (`backlog` → `ready-for-dev`). Docs-only story: replaces the Quickstart H2 placeholder in `python_code/README.md` (scaffolded by Story 1.4) with a full 5-minute getting-started section: framing paragraph, Prerequisites (Python 3.11+, JMRI 5.14+, web server at `localhost:12080`, ≥1 turnout), Install (`uv add pyjmri` + `pip install pyjmri`), copy-pasteable async script (≤15 meaningful lines, public API only, layout-agnostic via `next(iter(layout.turnouts.values()))`, optimistic `set_state` without `wait_for_jmri_state=True`), expected console output (two lines, placeholder values), and a forward-pointer to the Limitations section. AC2 (5-minute end-to-end timing from `uv add`) gates on Story 6.6's PyPI publication; AC1, AC3, AC4, AC5, AC6 are testable now. Public-API hygiene per `pyjmri.__init__.__all__`; no `_` -prefixed imports; no `wait_*` calls, throttles, or sensors (those are Story 6.4 territory). FR40 satisfied at the content level pre-publication.
- 2026-05-22 — Story 6.1 implemented (`ready-for-dev` → `in-progress` → `review`). `python_code/README.md` Quickstart H2 placeholder replaced with the full section per AC1: framing paragraph + Prerequisites H3 + Install H3 + "Your first script" H3 (11-line async snippet using only `Client` and `TurnoutState` from `pyjmri.__init__.__all__`) + "What you should see" H3 (two-line expected output + Limitations forward-pointer using the plain phrase "below" per AC6). Script AST-parses cleanly and is mypy `--strict` clean (FR44 alignment confirmed). `Client` / `TurnoutState` resolve under `from pyjmri import ...` per AC4 REPL check. Markdownlint self-scan clean on the new README sections (heading-level continuity H1→H2→H3, code-fence language tags `bash`/`python`/`text`, no trailing whitespace, no bare URLs in prose — external link uses proper `[uv](https://...)` syntax, localhost URLs are backticked). Quality gates clean: `ruff check`, `ruff format --check`, `mypy --strict src/pyjmri`, `pytest -m "not integration"` all match post-Story-5.3 baseline (411 passed, 22 deselected). No changes to `src/pyjmri/`, no new tests, no `pyproject.toml`/`uv.lock`/`LICENSE` edits. Two pre-dev markdownlint warnings on this story file (MD032 line 235, MD034 line 283) were fixed before starting dev work per `feedback_polish_matters.md` discipline.
