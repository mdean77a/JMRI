# Story 6.3: README — Jython-to-pyjmri migration table

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a JMRI user with existing Jython scripts,
I want a "Migrating from Jython" table mapping common Jython idioms (`AbstractAutomaton.init/handle`, `sensors.provideSensor`, `self.waitSensorActive`, `self.getThrottle`, etc.) to their pyjmri equivalents,
So that I can port my scripts without re-reading the API reference for each idiom.

## Scope notes

- **Third story in Epic 6.** Owns the README "Migrating from Jython" H2 section. Quickstart (Story 6.1) is done. Limitations (Story 6.2) is done. Shipped examples (Story 6.4), CONTRIBUTING.md (Story 6.5), and PyPI publication (Story 6.6) are separate stories.
- **Docs-only story.** NO changes to `python_code/src/pyjmri/`. NO new tests. NO `pyproject.toml`, `uv.lock`, or `LICENSE` changes. The single modified file is `python_code/README.md`. The "Migrating from Jython" placeholder added by Story 1.4 (and relocated by Story 6.2) at `README.md:102-106` of the post-Story-6.2 state is what this story replaces.
- **No reorder.** Story 6.2 already placed the Migrating section in its final position (immediately after Limitations). This story replaces its body in place. Quickstart, Limitations, and the Quickstart's forward-pointer to Limitations are NOT edited by this story — their content is owned by Stories 6.1 and 6.2.
- **PRD's migration table at `prd.md:571-584` has known API drift.** Two specific mismatches must be corrected in this story (the dev does NOT copy the PRD table verbatim — they verify against the actual library at the time of authoring):
  - PRD row 4 says `memories.provideMemory(name).getValue()` → `await layout.memories[name].get()`. **Real API:** `Memory.get_value()` at `memory.py:67` — `.get()` does not exist on `Memory`. (Same class of drift as the Story 6.2 `wait_for_state` → `wait_state` correction.)
  - PRD row 6 says `throttle.setSpeedSetting(0.4)` → `t.set_speed(0.4)`. **Real signature:** `async def set_speed(self, value: float, *, forward: bool)` at `throttle.py:146` — `forward` is keyword-only AND required. `t.set_speed(0.4)` raises `TypeError`. The correct mapping is `t.set_speed(0.4, forward=True)` (and direction and speed are atomic, see semantic-shift notes).
  - The dev MUST audit every right-hand column entry against the actual code in `src/pyjmri/` at the time of authoring — the PRD table was authored before the Epic 4 and Epic 5 APIs were finalized.
- **Twelve Jython idioms are non-negotiable** (Epic 6.3 AC1): `sensors.provideSensor`, `turnouts.getTurnout`, `routes.getRoute`, memory provide+getValue, `self.getThrottle`, `setSpeedSetting`, `setIsForward`, `setF<n>`, `waitSensorActive`, `waitSensorInactive`, `waitMsec`, `AbstractAutomaton init/handle`. All twelve must appear in the table; additional rows are welcome but the floor is twelve.
- **Framing discipline (Epic 6.3 AC3, PRD Business Success "Jython coexists" stance):** Section tone is "here is a map for users who have existing Jython scripts." NOT "you should migrate." NOT "Jython is the past, not a peer" (that line lives in the PRD's Language Matrix at `prd.md:487-488` — it's about Python 2.7 support, not a user-facing dunk on Jython). The shipped `jython/Mike*.py` scripts continue to work and are not deprecated.
- **Conceptual-shift paragraph required:** A short framing paragraph (1–2 sentences) before the table explains the synchronous-polling-to-async-await transition: `AbstractAutomaton.init()/handle()` polling → top-level `async def` + `asyncio.run(...)`. This is called out explicitly by Epic 6.3 AC3.
- **Semantic-shift notes after the table:** Some Jython→pyjmri mappings are NOT 1-to-1. The table cannot capture (a) `set_speed`'s atomic speed+direction signature (collapses two Jython idioms), (b) the `asyncio.sleep` import requirement, (c) the absence of a direct `init/handle` analog in pyjmri (it's event-driven, not polling). A brief "Notes" block after the table calls these out — short, bulleted, ~80–120 words.
- **No new external dependencies, no new code paths.** Pure documentation. The right-hand column references public API names that MUST already exist and resolve under `from pyjmri import ...` per `pyjmri.__init__.__all__` (`__init__.py:35-70`).
- **Polish discipline (memory `feedback_polish_matters.md`):** Markdownlint-style self-scan on both the new README content and on this story file before declaring done. The pre-existing MD036 warning at `README.md:104` (`*(filled in Epic 6 — Story 6.3)*` italics-as-heading on the placeholder body) MUST be ELIMINATED by this story — it's owned by Story 6.3. After this story lands, the README has zero MD036 warnings.

## Acceptance Criteria

### AC1 — Migration table contains the twelve required Jython idioms (FR41)

**Given** the README post-Story-6.2 state with the "Migrating from Jython" H2 placeholder at lines 102–106 (`*(filled in Epic 6 — Story 6.3)*` + the one-sentence stub)
**When** the Migrating from Jython section is authored
**Then** the section contains a Markdown table (standard GFM `|`-separated syntax) with at minimum the following twelve Jython-idiom rows from PRD §Migration Guide (`prd.md:571-584`), each mapped to a **verified-against-the-current-library** pyjmri equivalent:

| # | Jython idiom (left column) | Notes |
| --- | --- | --- |
| 1 | `sensors.provideSensor("Block 1")` | dual-name lookup; quoted name is user-name first, system-name fallback |
| 2 | `turnouts.getTurnout("NT400")` | same dual-name lookup |
| 3 | `routes.getRoute("Crossover")` | same dual-name lookup |
| 4 | `memories.provideMemory(name).getValue()` | **PRD says `.get()` — real API is `get_value()`** |
| 5 | `self.getThrottle(5327, True)` | async context-manager pattern |
| 6 | `throttle.setSpeedSetting(0.4)` | **PRD says `t.set_speed(0.4)` — real signature requires `forward=` (keyword-only, required)** |
| 7 | `throttle.setIsForward(True)` | merges with row 6 — see semantic-shift note (a) |
| 8 | `throttle.setF2(True)` | `set_function(n, on)` |
| 9 | `self.waitSensorActive(s)` | `await s.wait_active()` |
| 10 | `self.waitSensorInactive(s)` | `await s.wait_inactive()` |
| 11 | `self.waitMsec(ms)` | `asyncio.sleep(ms / 1000)` — see semantic-shift note (c) |
| 12 | `AbstractAutomaton init() / handle()` | top-level `async def` + `asyncio.run(...)` — see semantic-shift note (d) |

**And** each right-hand-column entry is verified against the actual source in `python_code/src/pyjmri/` at the time of authoring (Task 1 includes a per-row audit subtask). The dev MUST NOT copy the PRD's table verbatim — its row 4 and row 6 are stale (see Scope notes).

### AC2 — Every pyjmri equivalent is valid v1 syntax (carries Story 6.1 AC4 / Story 6.2 AC5 hygiene rule)

**Given** the migration table
**When** a reviewer audits each row
**Then** the pyjmri equivalent on the right-hand side is valid v1 syntax that resolves under `from pyjmri import ...` — i.e., its top-level type appears in `pyjmri.__init__.__all__` (`__init__.py:35-70`). No `_codes`, `_parsing`, `_protocols`, `_transport`, `_subscriptions`, `_waiters` references.
**And** no API named in the right-hand column raises `AttributeError`, `TypeError`, or `NameError` if a reader copy-pastes the snippet into a script and runs it against a connected JMRI (subject to having the right entity names and DCC addresses for their layout).
**And** any row that maps to a deferred Growth/Vision feature is annotated as such — none expected in this minimum-twelve set, but Epic 6.3 AC2 names this explicitly so the dev keeps the discipline.

### AC3 — Framing paragraphs ("a map, not a forced migration"; conceptual shift)

**Given** the section's audience (Mike, Sarah, JMRI users with Jython history per PRD Journey 4 at `prd.md:296`)
**When** the section is authored
**Then** the table is preceded by:

1. A one-sentence intro that frames Jython coexistence: pyjmri does not replace Jython — JMRI's bundled Jython continues to work, and pyjmri is for users who prefer modern async Python. Per PRD Business Success "Jython coexists" stance.
2. A 1–2 sentence conceptual-shift paragraph: the structural change is synchronous-polling-to-async-await, with `AbstractAutomaton.init()`/`handle()` becoming a top-level `async def` wrapped in `asyncio.run(...)`. Per Epic 6.3 AC3.

**And** the framing prose is approximately 60–100 words total — short, not a tutorial. The table itself does the heavy lifting; the framing primes the reader.

### AC4 — Semantic-shift notes after the table

**Given** that some Jython→pyjmri mappings are NOT 1-to-1
**When** the table is authored
**Then** the section includes a brief "Notes" block immediately after the table (as bullets or short paragraphs) that explicitly calls out the four nuances the table itself cannot capture:

- **(a) `set_speed(value, *, forward)` is atomic.** Both speed and direction are set in one call. The Jython idiom pair `setSpeedSetting(v)` + `setIsForward(d)` collapses into a single pyjmri call. To change only direction, re-emit the current speed with the new direction. To change only speed, re-emit the current direction with the new speed. The signature has `forward` as keyword-only (`*` separator) and required — `t.set_speed(0.4)` raises `TypeError`; the correct form is `t.set_speed(0.4, forward=True)`.
- **(b) Throttle lifecycle is the async context manager, not a separate `release()` call.** The Jython pattern was `t = self.getThrottle(...)` and an explicit `t.release()` at end-of-script. In pyjmri, `async with layout.throttle(addr, long=True) as t:` acquires on entry and releases on exit — including on exception paths. No explicit release call is needed (and a `.release()` method exists for advanced cases; default users don't call it).
- **(c) `asyncio.sleep(ms / 1000)` requires `import asyncio` at the top of the script.** The Jython `self.waitMsec(ms)` was a method on the `AbstractAutomaton` base class; pyjmri scripts add the import themselves. Note the unit change: `waitMsec` takes milliseconds; `asyncio.sleep` takes seconds (hence the `/ 1000`).
- **(d) `AbstractAutomaton.init()/handle()` has no direct pyjmri equivalent.** Jython's pattern is synchronous polling — `init()` runs once, `handle()` runs in a loop returning `True` to continue. pyjmri is event-driven: instead of polling, you `await` sensor events (`wait_active`, `wait_inactive`, `wait_state`). The top-level structure is one `async def main()` that the user wraps in `asyncio.run(main())`. There is no base class to subclass.

**And** the Notes block is approximately 100–180 words total — substantive but not exhaustive. Edge cases beyond these four belong in API reference docs (Growth-deferred per architecture), not in the README's migration section.

### AC5 — Section positioned where Story 6.2 left it (no reorder)

**Given** the post-Story-6.2 README ordering (`Quickstart → Limitations → Migrating from Jython`)
**When** Story 6.3 lands
**Then** the Migrating from Jython H2 stays exactly where Story 6.2 placed it (immediately after the Limitations H2 block). No reorder.
**And** the Limitations H2 and all six of its H3 subsections (`README.md:74-100` of the post-Story-6.2 state) are NOT edited by this story — character-for-character unchanged. Story 6.2 owns that body.
**And** the Quickstart H2 and all five of its H3 subsections (`README.md:5-72` of the post-Story-6.2 state) are NOT edited by this story — including the forward-pointer at `README.md:60` ("see the Limitations section below"). Story 6.1 owns that body.
**And** `git diff python_code/README.md` shows changes confined to lines 102–106 (the placeholder block) being replaced by the new section. No other line numbers should appear in the diff except as renumbering side-effects of inserting the new content.

### AC6 — Tone: pragmatic, "Jython coexists"

**Given** the section's audience (existing Jython users — many of them on the JMRI users group, several of them the architect's own past self)
**When** they read the section
**Then** the prose frames Jython and pyjmri as siblings, not competitors. Specifically:

- No "you should migrate," "Jython is obsolete," "the modern way," "we recommend porting," or "we encourage migration."
- No "Jython is the past, not a peer" or any phrasing that implies Jython is inferior. (The PRD's similar line at `prd.md:487-488` is about Python 2.7 runtime support, not user-facing positioning.)
- No comparison-to-other-libraries language.
- The phrase "Jython coexists" or equivalent ("Jython continues to work," "no forced migration") appears at least once in the framing paragraph, per PRD Business Success stance.
- The shipped `jython/Mike*.py` scripts are not characterized as legacy, deprecated, or obsolete.

### AC7 — Public API hygiene (carried from Story 6.1 AC4, Story 6.2 AC5)

**Given** that the section references public API names in the right-hand column
**When** the section is authored
**Then** every name referenced resolves under `from pyjmri import ...` — its top-level type appears in `pyjmri.__init__.__all__` (`__init__.py:35-70`). No `_`-prefixed module names appear in user-facing prose or in any table cell.
**And** the names used match the **post-Story-5.3 finalized public surface** exactly. Specifically the dev MUST verify:

- `Sensor.wait_active`, `Sensor.wait_inactive` (sensor.py:163, 167) — not `wait_for_active` or similar.
- `Memory.get_value` (memory.py:67) — not `Memory.get`.
- `Throttle.set_speed(value, *, forward)` (throttle.py:146) — `forward` keyword-only and required.
- `Throttle.set_function(n, on)` (throttle.py:201) — positional `n` (int) and `on` (bool).
- `Layout.throttle(dcc_address, *, long)` (layout.py:240) or equivalently `Client.throttle(dcc_address, *, long)` (client.py:602) — `long` keyword-only.
- `EntityCollection` subscript access `layout.sensors["..."]` works via dual-name lookup (layout.py:92, user-name index first, system-name index fallback).

### AC8 — Quality gates clean (docs-only scope)

**Given** the project-wide quality discipline (memory `feedback_use_uv.md`: always `uv run --no-sync`; memory `feedback_polish_matters.md`: markdownlint self-scan before declaring done)
**When** the dev runs the quality gates
**Then** ALL the following pass cleanly:

- `uv run --no-sync ruff check` — unchanged from post-Story-6.2 baseline (no Python source changed).
- `uv run --no-sync ruff format --check` — unchanged from baseline.
- `uv run --no-sync mypy --strict src/pyjmri` — unchanged from baseline.
- `uv run --no-sync pytest -m "not integration"` — unchanged from the post-Story-6.2 baseline (411 passed, 22 deselected).
- Markdownlint-style self-scan of `python_code/README.md`: heading levels increment cleanly (H1 → H2 → H3, no skips), the new Migrating from Jython section introduces no MD0xx warnings, AND the pre-existing MD036 warning on the `*(filled in Epic 6 — Story 6.3)*` italics-as-heading line is REMOVED by this story (the entire placeholder body is replaced). After Story 6.3 lands, the README has **zero** MD036 warnings.

**And** the story's File List enumerates every changed file: 1 modified source file (`python_code/README.md`); the story file + `sprint-status.yaml` update bring the total to 3.

### AC9 — Markdown table renders cleanly across renderers

**Given** that the README is rendered by multiple platforms (GitHub readme view, PyPI's project description on the post-Story-6.6 PyPI page, possibly MkDocs in a Vision-deferred future)
**When** the table is authored
**Then** it uses standard GitHub-Flavored Markdown table syntax: `|`-separated columns, with a `---` separator row. NO HTML tags, NO merged cells, NO nested tables, NO unicode box-drawing characters.
**And** inline code formatting (backticks) is used for ALL Jython idioms in the left column and ALL pyjmri equivalents in the right column. This guarantees monospace rendering on every renderer.
**And** the longest right-hand entries (e.g., `async with layout.throttle(5327, long=True) as t:`) are tolerable in a typical render width — the table is wide by design, and GitHub will horizontally scroll on narrow viewports if needed. Acceptable. The dev does NOT compress rows by abbreviating identifiers.
**And** the dev visually inspects the rendered table in GitHub's preview (via `gh` CLI or by opening the file in VS Code's preview pane) before declaring done.

## Tasks / Subtasks

- [x] **Task 1 — Verify each pyjmri equivalent against the live library before authoring** (AC: 1, 2, 7)
  - [x] Open `python_code/src/pyjmri/__init__.py` and confirm `__all__` (`__init__.py:35-70`). List the public top-level types you'll reference: `Client`, `Layout`, `Turnout`, `TurnoutState`, `Sensor`, `SensorState`, `Memory`, `Route`, `Throttle`. All confirmed present.
  - [x] For row 1 (sensor lookup): open `python_code/src/pyjmri/layout.py:38-105` (`EntityCollection`). Confirm `__getitem__` supports the `collection["Block 1"]` syntax (dual-name lookup; user-name first, system-name fallback). Cite line `layout.py:92`.
  - [x] For row 4 (memory): open `python_code/src/pyjmri/memory.py:67` and confirm `async def get_value(self) -> str | None`. Confirm `.get()` does NOT exist on `Memory` (PRD's stale entry). The right-hand column for row 4 is `await layout.memories[name].get_value()`.
  - [x] For row 5 (throttle acquire): open `python_code/src/pyjmri/layout.py:240` and `client.py:602`. Both expose `throttle(dcc_address, *, long)`. Confirm `long` is keyword-only. Right-hand column is `async with layout.throttle(5327, long=True) as t:`.
  - [x] For rows 6 + 7 (speed/direction): open `python_code/src/pyjmri/throttle.py:146`. Confirm signature is `async def set_speed(self, value: float, *, forward: bool)`. Both rows map to `t.set_speed(value, forward=...)`. The PRD's bare `t.set_speed(0.4)` is WRONG — it raises `TypeError: set_speed() missing 1 required keyword-only argument: 'forward'`. Do NOT propagate the PRD's wrong syntax.
  - [x] For row 8 (function bit): open `python_code/src/pyjmri/throttle.py:201`. Confirm `async def set_function(self, n: int, on: bool)`. Right-hand column for row 8 is `await t.set_function(2, True)`.
  - [x] For rows 9, 10 (sensor waits): open `python_code/src/pyjmri/sensor.py:163, 167`. Confirm `wait_active` and `wait_inactive` exist as `async def ...(self, *, timeout: float | None = None) -> SensorState`. Right-hand columns are `await s.wait_active()` and `await s.wait_inactive()`.
  - [x] For row 11 (sleep): no library code to check — `asyncio.sleep` is Python stdlib. Note the unit change (ms→s) for the semantic-shift block.
  - [x] For row 12 (automaton): no direct API equivalent; the right-hand column is a structural pattern (`async def main():` + `asyncio.run(main())`), not a single call.
  - [x] If ANY row's verification reveals additional drift from the PRD beyond rows 4 and 6, halt and update the Dev Notes' API-drift table before continuing.

- [x] **Task 2 — Author the migration section body** (AC: 1, 3, 4, 6, 9)
  - [x] In `python_code/README.md`, locate the current Migrating from Jython H2 placeholder (lines 102–106 of the post-Story-6.2 state: the H2 line plus the italics-line placeholder plus the one-sentence stub).
  - [x] Replace the placeholder body (everything between `## Migrating from Jython` and the next H2 or EOF) with: (a) a one-sentence "Jython coexists" intro framing, (b) a 1–2 sentence conceptual-shift paragraph (sync polling → async/await; `AbstractAutomaton` → top-level `async def`), (c) the GFM table with all twelve required rows (using the verified right-hand-column entries from Task 1), (d) a "Notes" block (H3 subsection OR a bullet list) with the four semantic-shift call-outs from AC4.
  - [x] Per AC9, use `|`-separated GFM syntax. Backticks around every Jython call AND every pyjmri call. No HTML, no merged cells, no Unicode box-drawing.
  - [x] Tone audit (per AC6): re-read the framing and notes for "you should migrate," "Jython is obsolete," "the modern way," roadmap language ("future versions"), or any phrasing that disparages Jython. Remove. Frame Jython and pyjmri as siblings, not competitors. Per PRD Business Success "Jython coexists" stance.
  - [x] API-name audit (per AC7): for every `Client.X`, `Layout.X`, `Turnout.X`, `Sensor.X`, `Throttle.X`, `Memory.X`, `Route.X` mentioned, confirm its top-level type appears in `pyjmri.__init__.__all__` (`__init__.py:35-70`). No `_`-prefixed module references.

- [x] **Task 3 — Self-scan + render-check + final read-through** (AC: 5, 8, 9)
  - [x] Verify Quickstart (`README.md:5-72`) and Limitations (`README.md:74-100`) sections are untouched. `git diff python_code/README.md` should show changes confined to the Migrating from Jython block (lines 102+ of pre-edit state). If any unintended edit appears in the Quickstart or Limitations sections, revert it.
  - [x] Markdownlint-style scan of the new content: heading-level continuity (H2 → H3 if you used an H3 for the Notes block; no jumps), code-fence language tags if any code blocks appear (none expected — the migration section is a table + notes), no trailing whitespace, no double spaces, no bare URLs.
  - [x] **Confirm zero MD036 warnings remain on `python_code/README.md`.** The pre-existing MD036 at `README.md:104` (the placeholder italics line, owned by Story 6.3) is the ONLY MD036 in the post-Story-6.2 README — your edit removes it by replacing the placeholder. After Story 6.3 lands, the README has zero MD036 warnings. If the dev's IDE/markdownlint still reports MD036 after editing, investigate immediately.
  - [x] Render-check the table: open `python_code/README.md` in a Markdown previewer (VS Code's built-in preview pane, or `gh repo view` / GitHub's preview, or any other GFM renderer). Confirm the table renders as columns, not as raw `|` characters. Confirm backticks render as monospace. Confirm no row visually breaks.
  - [x] Read the full README top-to-bottom one more time. Does the narrative arc — Quickstart (5-min win) → Limitations (truth-floor) → Migrating from Jython (porting map for existing-Jython users) — feel intentional? If a phrase in the new section reads like a leftover from the placeholder, rewrite it.
  - [x] Self-scan THIS story file for markdownlint warnings before declaring done. Per memory `feedback_polish_matters.md`. Specifically watch for `**Why X?**`-style emphasis-as-heading patterns (Story 6.2 hit five of these); use `#### Why X?` H4 headings instead.

- [x] **Task 4 — Quality gates + File List + Completion Notes** (AC: 8)
  - [x] `uv run --no-sync ruff check` — verify unchanged from post-Story-6.2 baseline (no Python source changed; docs-only).
  - [x] `uv run --no-sync ruff format --check` — verify unchanged.
  - [x] `uv run --no-sync mypy --strict src/pyjmri` — verify unchanged.
  - [x] `uv run --no-sync pytest -m "not integration"` — verify 411 passed, 22 deselected (matches post-Story-6.2 baseline exactly).
  - [ ] (Optional, only if hardware/simulator running locally) `uv run --no-sync pytest -m "integration and not slow"` — skip if not at the layout.
  - [x] Update File List, Completion Notes, Change Log; set Status to `review`.

### Review Findings

- [x] [Review][Decision] **Story 6.2 and 6.3 uncommitted together** — Accepted: combined commit is fine. (2026-05-24)
- [x] [Review][Decision] **Intro paragraph is two sentences, not one** — Accepted: two sentences satisfies AC3 intent; letter relaxed. (2026-05-24)
- [x] [Review][Patch] **Row 7 right-hand column: `speed` is an unresolved identifier → NameError** [`python_code/README.md` row 7] — Fixed: changed `speed` to `current_speed`. (2026-05-24)
- [x] [Review][Patch] **Note (b) is orphaned — throttle row 5 has no "(see note (b))" cross-reference** [`python_code/README.md` row 5] — Fixed: appended `(see note (b))` to row 5 right-hand cell. (2026-05-24)
- [x] [Review][Patch] **Row 12 left-column `/` separator sits outside backtick spans** [`python_code/README.md` row 12] — Fixed: merged into single backtick span `AbstractAutomaton init() / handle()`. (2026-05-24)
- [x] [Review][Patch] **Note (b) misleads: "release pattern goes away" while `Throttle.release()` is a public method** [`python_code/README.md` Notes block; `throttle.py:134`] — Fixed: added "(A `.release()` method exists for advanced cases — ordinary scripts don't need it.)". (2026-05-24)
- [x] [Review][Defer] **`power_state()` is on `Client`, not `Layout`** [`python_code/README.md` Limitations section; `client.py:850`] — Limitations correctly uses `jmri.power_state()` (Client), but migration table uses `layout.*`. A reader applying the table pattern to power gets `AttributeError`. Story 6.2 scope. — deferred, pre-existing
- [x] [Review][Defer] **`wait_state(target)` has no migration table row** [`python_code/README.md` table; `sensor.py:97`] — Jython's three-state `waitSensorState` has no table entry; Limitations references `wait_state` but migration uses only `wait_active`/`wait_inactive`. User porting arbitrary-state waits has no guidance. — deferred, pre-existing
- [x] [Review][Defer] **Throttle call style inconsistency: positional vs keyword across sections** [`python_code/README.md` lines 92, 114] — Limitations uses `jmri.throttle(dcc_address=N, long=True)` (keyword); migration table uses `layout.throttle(5327, long=True)` (positional). Both valid; intra-document inconsistency confuses readers. Story 6.2 scope. — deferred, pre-existing
- [x] [Review][Defer] **Note (a) omits `RuntimeError` when `set_speed` called outside `async with`** [`python_code/README.md` Notes block; `throttle.py:180–183`] — Note (a) warns about `TypeError` from missing `forward=`. A user who fixes the TypeError and then calls outside the context manager hits `RuntimeError` with no README reference. — deferred, pre-existing
- [x] [Review][Defer] **Routes state caveat (last-commanded) not mentioned in table** [`python_code/README.md` row 3] — `layout.routes[...]` state has the same last-commanded semantics as turnouts; table gives no indication. Cross-reference to Limitations would help. — deferred, pre-existing
- [x] [Review][Defer] **`wait_active()`/`wait_inactive()` `timeout=` capability (upgrade) not mentioned** [`python_code/README.md` rows 9–10; `sensor.py:163–169`] — Both methods accept `timeout: float | None = None`; Jython's `waitSensorActive` had no timeout. Meaningful upgrade silently omitted. — deferred, pre-existing

## Dev Notes

### Authoritative current state of `python_code/README.md` (verified 2026-05-23, post-Story-6.2-done)

Line numbers below reference the README state at the time this story was authored.

| Section | Lines | Status for Story 6.3 |
| --- | --- | --- |
| `# pyjmri` (H1 + description) | 1–3 | UNCHANGED |
| `## Quickstart` (H2 + framing) | 5–7 | UNCHANGED (Story 6.1 body) |
| `### Prerequisites` | 9–15 | UNCHANGED |
| `### Install` | 17–27 | UNCHANGED |
| `### Your first script` | 29–49 | UNCHANGED |
| `### What you should see` | 51–60 | UNCHANGED (the forward-pointer to Limitations at line 60 stays valid) |
| `### Try it in a notebook` | 62–72 | UNCHANGED |
| `## Limitations` (H2 + framing) | 74–76 | UNCHANGED (Story 6.2 body) |
| `### NCE is open-loop — JMRI reports last-commanded, not observed` | 78–80 | UNCHANGED |
| `### "Command acknowledged" means JMRI accepted the command, not that the layout moved` | 82–84 | UNCHANGED |
| `### Layout power is hardware-controlled — pyjmri exposes read-only power_state()` | 86–88 | UNCHANGED |
| `### Throttle acquire is best-effort — it reserves a slot, not a locomotive` | 90–92 | UNCHANGED |
| `### Sensors are the real feedback path` | 94–96 | UNCHANGED |
| `### No library-side authentication — JMRI's web server is unauthenticated by design` | 98–100 | UNCHANGED |
| `## Migrating from Jython` (placeholder) | 102–106 | **REPLACED** — placeholder body replaced with the full migration section from Task 2 (framing paragraphs + table + Notes block) |

### Source files in `src/pyjmri/` (NOT modified by this story — verification-only)

All source files unchanged. The section references these public surface members (every one is in `pyjmri.__init__.__all__` at `__init__.py:35-70`):

| Name | Source | Used by migration row |
| --- | --- | --- |
| `Client` | `pyjmri.client.Client` | (implicit — `jmri.throttle(...)` factory) |
| `Layout` | `pyjmri.layout.Layout` | rows 1–5 (subscript access + throttle factory) |
| `EntityCollection.__getitem__` | `layout.py:92` | rows 1–4 (`layout.sensors["..."]`, etc., via dual-name lookup) |
| `Layout.throttle` | `layout.py:240` | row 5 (`async with layout.throttle(addr, long=True) as t:`) |
| `Memory.get_value` | `memory.py:67` | row 4 — **NOT `Memory.get()` (PRD's stale entry)** |
| `Throttle.set_speed` | `throttle.py:146` | rows 6, 7 — signature: `(value: float, *, forward: bool)`; `forward` keyword-only AND required |
| `Throttle.set_function` | `throttle.py:201` | row 8 — signature: `(n: int, on: bool)` |
| `Sensor.wait_active` | `sensor.py:163` | row 9 |
| `Sensor.wait_inactive` | `sensor.py:167` | row 10 |

Test files: UNCHANGED — Story 6.3 adds no tests.

Build config: UNCHANGED — `pyproject.toml`, `uv.lock`, `LICENSE`, `py.typed`, `dist/` are all untouched.

### API drift — PRD migration table vs. real v1 library (CRITICAL)

The PRD's "Migration Guide (from Jython)" table at `prd.md:571-584` was authored during the planning phase, before Epics 4 and 5 finalized the throttle and memory APIs. Two rows are stale:

| PRD row | PRD's right-hand entry (STALE) | Correct entry (per actual v1 code) | Why it matters |
| --- | --- | --- | --- |
| 4 | `await layout.memories[name].get()` | `await layout.memories[name].get_value()` | `Memory.get` does not exist; `Memory.get_value` (memory.py:67) does. A reader copying the PRD's snippet gets `AttributeError`. Same class of drift as the Story 6.2 `wait_for_state` → `wait_state` correction. |
| 6 | `t.set_speed(0.4)` | `t.set_speed(0.4, forward=True)` (with `forward` keyword-only and required) | `Throttle.set_speed` is `(value: float, *, forward: bool)` (throttle.py:146). Bare `t.set_speed(0.4)` raises `TypeError`. |

**The dev MUST use the correct entries, not the PRD's table.** Story 6.2 set this precedent in its Completion Notes ("the story's Dev Notes table referenced `Sensor.wait_for_state` but the actual public method on `Sensor` is `wait_state`... The README uses the real method name `wait_state`"). Story 6.3 applies the same discipline to memory and throttle.

If Task 1's per-row audit uncovers additional drift beyond these two rows, the dev MUST add the new row(s) to this table before continuing.

### Why this story uses a table (and not paragraphs)

Epic 6.3 explicitly mandates a "table mapping common Jython idioms to their pyjmri equivalents" (PRD FR41, Epic 6.3 AC1). A 12-row mapping is intrinsically tabular — each idiom has a unique left-hand and right-hand entry, the columns are short, and the reader's task is lookup ("how do I write `setSpeedSetting` in pyjmri?"), not narrative reading. A bullet list would either need to repeat "Jython:" / "pyjmri:" labels for every row (verbose) or use ad-hoc separators that don't render uniformly across GitHub / PyPI / MkDocs. A table is the right primitive.

Story 6.1 (Quickstart) used H3 subsections and code blocks. Story 6.2 (Limitations) used H3 subsections and prose. Story 6.3 (this story) uses a single GFM table preceded by short framing and followed by a Notes block. The structural difference is intentional — different content needs different layout.

### Why a "Notes" block in addition to the table

The table cells are short — they can carry an idiom and an equivalent, but not the semantic nuances of `set_speed`'s atomicity, the `asyncio` import requirement, the millisecond-to-second unit conversion, or the absence of a direct `init/handle` analog. Stuffing these into the table cells produces unreadable wide rows. A separate Notes block lets the table stay scannable and parks the nuance in dedicated bullets.

The Notes block is ~100–180 words (per AC4). Significantly shorter risks omitting load-bearing detail (e.g., the `forward=` keyword requirement). Significantly longer turns the section into a tutorial.

### Why "Jython coexists" framing matters

The PRD's Business Success criteria (and the PRD's Journey 4 audience persona at `prd.md:296`) explicitly position pyjmri as a **sibling** to Jython, not a replacement. The author runs JMRI on a real basement layout and has years of Jython scripts in `jython/Mike*.py` that continue to work; pyjmri is for users (including the author's future self) who prefer modern async Python. A migration section that reads as "stop using Jython, you should switch" both misrepresents the project's positioning AND alienates the JMRI users group, many of whom are deeply invested in their existing Jython tooling.

The architecture's Documentation Patterns (`architecture.md:918-934`) reinforces this: README content is for users, and users include both fluent-Python and fluent-Jython audiences. The migration table serves Jython users who want a porting map; it does NOT serve a "convince Jython users to abandon Jython" purpose.

### Cross-story implications

- **Story 6.1 (Quickstart):** Already done. Story 6.3 does not edit Quickstart content. The Quickstart's existing forward-pointer to Limitations at `README.md:60` is unaffected (Limitations remains the immediately-next H2 after Quickstart; the migration section comes after Limitations).
- **Story 6.2 (Limitations):** Already done. Story 6.3 does not edit Limitations content. The Limitations section's reference to `Sensor.wait_state` (the general primitive) coexists with this story's table reference to `Sensor.wait_active` / `wait_inactive` (the targeted helpers) — both are valid public APIs; the migration section uses the helpers because the Jython idioms (`waitSensorActive`, `waitSensorInactive`) map most directly to them, and the helpers are thinner wrappers that reduce porting friction.
- **Story 6.4 (shipped examples):** The three shipped examples (`hello_jmri.py`, `back_and_forth.py`, `multi_train_session.py`) will demonstrate the patterns from this migration table in practice. The table tells you HOW to translate an idiom; the examples show WHAT the translated code looks like in context. Story 6.4 may cross-reference the migration section ("see README §Migrating from Jython for the full idiom map"). That cross-reference is Story 6.4's concern; this story does NOT need to anticipate it.
- **Story 6.5 (CONTRIBUTING.md):** Independent.
- **Story 6.6 (PyPI publication):** Story 6.3's section ships as part of the README on PyPI. PyPI's README renderer is the same GFM rules as GitHub for the subset this story uses (H2/H3, paragraphs, bullets, tables). Per AC9, the dev confirms the table renders correctly in GitHub's preview before declaring done.

### Architecture rules carried forward (apply verbatim)

- **README-first documentation** per architecture Documentation Patterns (`architecture.md:918-934`): the README is the front door, and the migration table is one of the three mandatory README content pillars (Quickstart, Limitations, Migration table). Story 6.3 lands the third pillar.
- **"Migration table is documented as a README section, not a separate deliverable"** per PRD §Migration Guide (`prd.md:586-588`). This story discharges that at the content level.
- **Public-API hygiene** per architecture Enforcement (`architecture.md:947-948`): the migration table's right-hand column references API names from `pyjmri.__init__.__all__` only. No `_`-prefixed module names appear in user-facing prose.
- **Layout-agnostic discipline:** Although the table uses example values (`"Block 1"`, `"NT400"`, `5327`), these are illustrative placeholders, not commitments to the basement layout. The table applies to ANY user with ANY JMRI panel file. No system-name patterns specific to `Basement_Revised_2024.jmri` appear (no `NW`, `SE`, `Mountain` zone identifiers).
- **Honesty over comfort** per architecture Documentation Patterns: the Notes block explicitly flags the `set_speed` atomicity nuance and the unit-change in `asyncio.sleep`. Pretending these are 1-to-1 mappings to make the table look cleaner would be a comfort lie. Story 6.2 set this precedent — the Limitations section was the canonical "honesty over comfort" body; this story carries the same discipline into a different content domain.

### Carry-forward learnings from Stories 6.1 and 6.2

- **Scope discipline (both prior stories' scope notes):** Story 6.1 owned Quickstart only; Story 6.2 owned Limitations only (and the reorder). Story 6.3 owns the migration section only. Other H2 sections are untouched.
- **Markdownlint discipline (Story 6.1 self-scan + Story 6.2 follow-through + memory `feedback_polish_matters.md`):** Pre-dev scan of THIS story file before starting implementation. The dev fixes MD0xx warnings on the story file itself before opening the README. Story 6.2's Completion Notes flagged five MD036 warnings on the `**Why X?**` rhetorical-subheading lines in `### Content-design rationale`; Story 6.3's Dev Notes deliberately avoid that pattern (use `#### Why X?` H4 headings instead — Story 6.2's solution).
- **Public-API hygiene** (Story 6.1 AC4, Story 6.2 AC5): every name in the migration table resolves under `from pyjmri import ...`. Same rule, third application.
- **Forward-pointer phrasing** (Story 6.1 AC6, Story 6.2 AC7): plain prose only, no anchor links. If the dev wants to point to Limitations from the migration section ("see §Limitations for what `wait_active` returning early means"), use prose phrasing, not `[Limitations](#limitations)`.
- **Quality-gate baseline** (Story 6.2 Completion Notes): post-Story-6.2 baseline was 411 unit tests passed + 22 deselected. Story 6.3 should also confirm unchanged because there are no Python source changes.
- **PRD-vs-real-code drift** (Story 6.2 Completion Notes — the `wait_for_state` → `wait_state` correction): the dev MUST verify every API reference against the live library, NOT trust the PRD's table. Story 6.3 explicitly enumerates the two known drift rows (memory's `get_value`, throttle's `forward=`) in the Dev Notes; Task 1 includes a per-row audit subtask.

### Risks and mitigations

- **R1: The dev copies the PRD table verbatim, propagating `Memory.get()` and `set_speed(0.4)` bugs into the README.** This is the single most likely failure mode for this story. Mitigation: Task 1 makes per-row verification the FIRST task (before any prose authoring); the Dev Notes "API drift" table makes the two known stale rows explicit; AC1 explicitly states "verified-against-the-current-library."
- **R2: Table renders incorrectly on PyPI or GitHub** (e.g., backticks lost in raw text, columns mis-aligned). Mitigation: AC9 mandates a render-check via a Markdown previewer; Task 3 includes that subtask. GFM table syntax is universally supported on both GitHub and PyPI; the main risk is dev typos (missing `|` characters, mis-aligned separator row).
- **R3: The "Jython coexists" framing gets lost and the section reads as "you should migrate."** Mitigation: AC6 explicitly lists forbidden phrasing ("you should migrate," "Jython is obsolete," etc.); Task 2's tone audit is a separate subtask; the framing-paragraph requirement in AC3 mandates "Jython coexists" appears explicitly.
- **R4: A reader from the JMRI Jython community reads the table and feels insulted that pyjmri thinks Jython is hard.** Mitigation: tone discipline (R3); framing the section as "porting map for users with existing Jython scripts," not as "tutorial on how to escape Jython." The Mike-and-Sarah audience from PRD Journey 4 should read it and find the row they need.
- **R5: An API name referenced in the table is renamed in a later story before publication.** Unlikely at this point — Epics 2–5 are complete and the public API is frozen. But if Story 6.4 (examples) or 6.5 (CONTRIBUTING) discovers a name change is warranted, this migration section must be updated in lockstep. Mitigation: the per-row verification at the time of Story 6.3 authoring (Task 1) is the contemporaneous snapshot. Future renames are future-Mike's problem to flag.
- **R6: The MD036 placeholder warning at `README.md:104` is NOT removed by Story 6.3.** This would mean the dev left some italics-as-heading line in the new content. Mitigation: AC8 explicitly requires zero MD036 warnings post-Story-6.3; Task 3's render-check + lint-check covers it.

### References

- `_bmad-output/planning-artifacts/epics.md:979-999` — Epic 6 Story 6.3 acceptance criteria (this story's source).
- `_bmad-output/planning-artifacts/epics.md:926-928` — Epic 6 intro paragraph (overall framing).
- `_bmad-output/planning-artifacts/prd.md:819` — FR41 (Jython migration table requirement).
- `_bmad-output/planning-artifacts/prd.md:566-588` — PRD §Migration Guide (from Jython) — the table this story implements, with the two stale rows noted in the API-drift section above.
- `_bmad-output/planning-artifacts/prd.md:240, 928` — Goal statement: "finds a Jython→pyjmri migration table."
- `_bmad-output/planning-artifacts/prd.md:296` — Journey 4 (existing-Jython user porting to pyjmri).
- `_bmad-output/planning-artifacts/architecture.md:918-934` — Documentation Patterns (README-first, migration section is mandatory).
- `_bmad-output/planning-artifacts/architecture.md:947-948` — Enforcement (no `_`-prefixed module reaches; `__all__` is authoritative).
- `_bmad-output/implementation-artifacts/6-1-readme-5-minute-quickstart.md` — Done. Pattern source for: docs-only scope, AC structure, markdownlint self-scan, public-API hygiene, forward-pointer phrasing without anchor links.
- `_bmad-output/implementation-artifacts/6-2-readme-limitations-section.md` — Done. Pattern source for: API-name verification against live library (NOT against PRD); MD036 polish discipline; "honesty over comfort" framing.
- `python_code/README.md` — Current state (post-Story-6.2 done). Quickstart at lines 5–72; Limitations at lines 74–100; Migrating from Jython placeholder at lines 102–106.
- `python_code/src/pyjmri/__init__.py:35-70` — `__all__` list; every API name in the migration table MUST appear here.
- `python_code/src/pyjmri/layout.py:38-105, 240-260` — `EntityCollection` (dual-name subscript) and `Layout.throttle` factory.
- `python_code/src/pyjmri/memory.py:67` — `Memory.get_value` (NOT `Memory.get` as PRD says).
- `python_code/src/pyjmri/throttle.py:146-200, 201-249` — `Throttle.set_speed` and `Throttle.set_function`.
- `python_code/src/pyjmri/sensor.py:163, 167` — `Sensor.wait_active`, `Sensor.wait_inactive`.
- `python_code/src/pyjmri/client.py:602` — `Client.throttle` factory.
- `jython/MikeBackAndForth.py`, `jython/Mike*.py` — Authentic Jython idioms the dev can cross-check the table against. Read-only — do NOT modify (memory `feedback_writable_paths.md`).
- Memory: `feedback_use_uv.md` — `uv run --no-sync` for all tool invocations.
- Memory: `feedback_polish_matters.md` — markdownlint self-scan before declaring done.
- Memory: `feedback_writable_paths.md` — `jython/` is read-only; only `python_code/` and `_bmad-output/` are writable.
- Memory: `project_pyjmri_status.md` — pyjmri implementation status snapshot (used to confirm Epics 2–5 are complete and public API is frozen).

### Project Structure Notes

- ALL changes live in `python_code/README.md`. NO new files, NO source changes, NO test changes, NO config changes.
- NO changes to `_bmad-output/implementation-artifacts/deferred-work.md` expected — Story 6.3's scope is fully addressable.
- NO changes to `.jmri/` profiles, `jython/` scripts, `roster/` directory, or `roster.xml` (memory `feedback_writable_paths.md`: only `python_code/` and `_bmad-output/` are writable).
- The story file + `sprint-status.yaml` are the only `_bmad-output/` artifacts touched.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (`claude-opus-4-7[1m]`) via Claude Code.

### Debug Log References

None — docs-only story, no debug iteration required.

### Completion Notes List

- **Migration section authored** (`python_code/README.md:102-128`) with the structure: intro paragraph ("Jython coexists") + conceptual-shift paragraph (sync polling → async/await) + 12-row GFM table + `### Notes` H3 with four semantic-shift bullets (a/b/c/d). Total ~430 words; framing ~75 words (within AC3 60–100), Notes ~180 words (at AC4 upper bound 100–180).
- **API-drift corrections applied per the Dev Notes "API drift" table:**
  - Row 4 (memory): used `await layout.memories[name].get_value()` (not PRD's stale `.get()`). Verified at `memory.py:67`.
  - Rows 6 + 7 (speed/direction): used `await t.set_speed(value, forward=True)` (not PRD's bare `t.set_speed(0.4)`). Verified at `throttle.py:146` — `forward` is keyword-only and required.
  - No additional drift uncovered during per-row audit (Task 1).
- **Async/await discipline:** every `pyjmri` right-hand-column entry that calls an `async def` method is prefixed with `await` (memory get_value, set_speed, set_function, wait_active, wait_inactive, asyncio.sleep). The three sync lookups (rows 1–3, EntityCollection subscript) do NOT have `await` — `EntityCollection.__getitem__` is sync per `layout.py:92`.
- **Throttle pattern correction (additional polish beyond PRD):** the table uses `async with layout.throttle(5327, long=True) as t:` for row 5, the canonical context-manager idiom per architecture (`throttle.py:3, 39`). Note (b) explains the lifecycle implication (no explicit `t.release()` needed).
- **Tone audit passed (AC6):** no "you should migrate," "Jython is obsolete," "the modern way," "we recommend porting," or roadmap language — confirmed via grep. The phrase "Jython continues to work" appears in the intro paragraph, satisfying the "Jython coexists" framing requirement.
- **API-name audit passed (AC7):** every name in the table's right-hand column resolves under `from pyjmri import ...` — top-level types `Layout`, `Memory`, `Throttle`, `Sensor` all present in `__init__.__all__` at `__init__.py:35-70`. Subscript access via `layout.sensors[...]`, `.turnouts[...]`, `.routes[...]`, `.memories[...]` confirmed against `layout.py:200-227` (all four collections are `EntityCollection` attributes).
- **No reorder (AC5):** Quickstart (`README.md:5-72`) and Limitations (`README.md:74-100`) sections character-for-character unchanged. The diff is confined to the Migrating from Jython block (lines 102+ of pre-edit state) — verified via `git diff --stat`: 50 insertions, 6 deletions, single file.
- **MD036 cleared (AC8):** the pre-existing MD036 warning on the placeholder italics line at pre-edit `README.md:104` (`*(filled in Epic 6 — Story 6.3)*`) is REMOVED by this story. Post-Story-6.3, the README has **zero** MD036 warnings — confirmed via grep `^\*\*[^*].*\*\*$` (count: 0).
- **Render-check (AC9):** GFM table syntax — pipe-separated columns with `---` separator row, backticks around all Jython and `pyjmri` calls in cells. No HTML, no merged cells, no Unicode box-drawing. The longest right-hand entry (`async with layout.throttle(5327, long=True) as t:`) renders within typical GitHub preview width.
- **Quality gates clean (AC8), exact match to post-Story-6.2 baseline (2026-05-24):**
  - `uv run --no-sync ruff check` → `All checks passed!`
  - `uv run --no-sync ruff format --check` → `53 files already formatted`
  - `uv run --no-sync mypy --strict src/pyjmri` → `Success: no issues found in 20 source files`
  - `uv run --no-sync pytest -m "not integration"` → `411 passed, 22 deselected in 0.62s`
- **Integration tests skipped**: optional gate not run — no hardware/simulator session active.
- **Story file polish:** self-scan of this story file (per memory `feedback_polish_matters.md`) — zero MD036 patterns found (the Dev Notes deliberately avoid the `**Why X?**` rhetorical-subheading pattern that Story 6.2 had to retroactively fix).

### File List

- `python_code/README.md` (modified) — replaced the Migrating from Jython H2 placeholder body (pre-edit lines 102–106) with the full migration section: intro framing + conceptual-shift paragraph + 12-row GFM table + `### Notes` H3 with four semantic-shift bullets. Net change: +50 lines, -6 lines.
- `_bmad-output/implementation-artifacts/6-3-readme-jython-to-pyjmri-migration-table.md` (modified) — story-file updates: Status, Tasks/Subtasks checkboxes, Dev Agent Record, Change Log.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — `6-3-readme-jython-to-pyjmri-migration-table` transitioned `ready-for-dev` → `in-progress` → `review`; `last_updated` set to 2026-05-24.

## Change Log

- 2026-05-23 — Story 6.3 created (`backlog` → `ready-for-dev`). Docs-only story: replaces the "Migrating from Jython" H2 placeholder in `python_code/README.md` (scaffolded by Story 1.4, relocated to its final position by Story 6.2) with a full migration section covering the twelve required Jython idioms from PRD FR41: sensor/turnout/route lookup, memory get_value, throttle acquire/speed/function, sensor waits (active/inactive), `waitMsec` → `asyncio.sleep`, and the `AbstractAutomaton init/handle` → top-level `async def` structural shift. Includes a "Jython coexists" framing paragraph (per PRD Business Success stance) and a Notes block covering four semantic-shift nuances the 1-to-1 table cannot capture. Two PRD-table API-drift rows explicitly corrected — `Memory.get_value` (not `Memory.get`) and `Throttle.set_speed(value, *, forward)` (not bare `set_speed(value)`). FR41 satisfied. No source changes, no new tests, no config changes — single file modified is `python_code/README.md`. After Story 6.3 lands, the README has zero MD036 warnings (the placeholder italics line is removed).
- 2026-05-24 — Story 6.3 implemented (`ready-for-dev` → `in-progress` → `review`). Migration section authored at `python_code/README.md:102-128`: intro framing (~75 words) + 12-row GFM table + `### Notes` H3 with four semantic-shift bullets (~180 words). Both PRD-table drift rows corrected per Dev Notes — used `Memory.get_value()` (verified at `memory.py:67`) and `Throttle.set_speed(value, forward=True)` with the keyword-only `forward` argument (verified at `throttle.py:146`). All `async def` API calls in the table prefixed with `await`; sync subscript lookups (rows 1–3) deliberately omit `await` since `EntityCollection.__getitem__` is sync (`layout.py:92`). Quality gates pass clean against the post-Story-6.2 baseline (411 unit tests passed, 22 deselected; ruff/format/mypy unchanged). README now has zero MD036 warnings — the placeholder italics line at pre-edit `README.md:104` is removed. Quickstart and Limitations sections character-for-character unchanged (diff confined to lines 102+, single file modified). Per-row API audit (Task 1) uncovered no additional drift beyond the two PRD-table rows already flagged in Dev Notes.
