# Story 6.2: README — Limitations section

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a pyjmri user,
I want a "Limitations" section that plainly explains what the library can and cannot detect — open-loop NCE, no DCC-bus feedback, no power write on this hardware, no physical-presence detection for locos or accessories,
So that I'm not surprised when `await turnout.throw()` succeeds while the physical turnout doesn't move.

## Scope notes

- **Second story in Epic 6.** Owns the README Limitations H2 section. Quickstart (Story 6.1) is done; Migrating from Jython (Story 6.3), shipped examples (Story 6.4), CONTRIBUTING.md (Story 6.5), and PyPI publication (Story 6.6) are separate stories.
- **Docs-only story.** NO changes to `python_code/src/pyjmri/`. NO new tests. NO `pyproject.toml`, `uv.lock`, or `LICENSE` changes. The single modified file is `python_code/README.md`. The Limitations H2 placeholder added by Story 1.4 (`*(filled in Epic 6 — Story 6.2)*` at `README.md:80-84` of the post-Story-6.1 state) is what this story replaces.
- **Reorder is in scope.** Epic 6.2 AC2 mandates "positioned prominently … directly after Quickstart, *before* the API reference." Today the README ordering is `Quickstart → Migrating from Jython → Limitations`. This story moves Limitations to be the immediate next H2 after Quickstart, producing `Quickstart → Limitations → Migrating from Jython`. The Migrating H2 line and its placeholder body are not edited — they move as a block, preserving Story 6.3's contract on that placeholder.
- **Six required content topics (Epic 6.2 AC1):** (a) NCE open-loop, (b) "command acknowledged" ≠ "layout moved", (c) layout power is hardware-controlled — pyjmri exposes read-only `power_state()` only, (d) throttle acquire is best-effort with no physical-presence implication, (e) sensors remain the real feedback observable for `wait_*`, (f) no library-side authentication — JMRI's web server is unauthenticated by design and intended for trusted-network use (NFR11). All six are NON-NEGOTIABLE — the AC fails if any one is missing.
- **FR37 cross-check (Epic 6.2 AC2):** Every "library does not raise an exception for X" case from FR37 must be mentioned in plain language with a brief why. FR37 names two examples explicitly — "missing locomotive on the rails" and "turnout that physically failed to move" — both must appear in the section's content (covered by (a)/(b)/(d)). Add any other FR37 cases discovered during authoring.
- **Tone discipline (Epic 6.2 AC3):** "Clear-eyed explanation of the underlying DCC reality, not an apology — these are properties of NCE and of model railroading, not pyjmri shortcomings." No hedging, no "unfortunately," no "sadly." Frame each item as "here is how the world works, here is what that means for your code." Honest, not defensive.
- **Forward-pointer from Quickstart already exists.** The Quickstart's "What you should see" subsection at `README.md:60` already says "see the Limitations section below for what 'accepted' does and does not imply on NCE hardware." That phrase "below" remains valid after the reorder because Limitations stays below Quickstart — just immediately below rather than two H2s down. No edit to the Quickstart cross-reference text is required by this story; the dev MUST verify it still reads naturally post-reorder.
- **No new external dependencies, no new code paths.** The Limitations section is pure prose. It MAY reference public API names (`Client.power_state`, `Throttle.acquire`, `wait_*`) — those names must already exist and resolve under `from pyjmri import ...` per `pyjmri.__init__.__all__`. It MUST NOT promise any API that doesn't exist yet.
- **Polish discipline (memory `feedback_polish_matters.md`):** Markdownlint-style self-scan on both the new README content and on this story file before declaring done. The story file `6-1-readme-5-minute-quickstart.md` was published with MD036 warnings on the two remaining Epic 6 placeholders (lines 76 and 82 of the post-6.1 README); Story 6.2 removes one of those (the Limitations placeholder) and Story 6.3 removes the other. By end of this story, only the Migrating from Jython placeholder warning remains — acceptable, pre-existing, owned by Story 6.3.

## Acceptance Criteria

### AC1 — Limitations section: six required content topics

**Given** the README post-Story-6.1 state with the Limitations H2 placeholder at lines 80–84 (`*(filled in Epic 6 — Story 6.2)*` + the one-sentence "A clear explanation…" stub)
**When** the Limitations section is authored
**Then** the section contains, in plain English, the following six topics. Each topic is either its own H3 subsection OR a clearly delineated bullet/paragraph block — the dev's call on micro-structure, but each topic MUST be discoverable on a single scroll-and-read pass.

(a) **NCE is open-loop.** There is no feedback path from any commanded accessory (turnout, route, light) or any decoder (locomotive throttle) back to JMRI on the NCE platform that `pyjmri` is tested against. JMRI knows what it *commanded*; it does not know what physically happened. State JMRI reports for a turnout, light, or route is the last-commanded state, not an observed state. (PRD FR37, memory `project_jmri_state_model.md`, memory `project_nce_open_loop.md`.)

(b) **"Command acknowledged" means JMRI accepted the command, not that the layout physically moved.** When `await turnout.set_state(THROWN)` returns, the library has confirmed that JMRI's JSON web server accepted the request and updated its internal model. The DCC bus may not have delivered the packet successfully, the turnout coil may have failed, the decoder may be unpowered — none of these failure modes produce an exception from pyjmri because the library has no signal to detect them with. Visual confirmation at the layout is the only ground truth. This is true on the NCE simulator *and* on real NCE hardware (memory `project_nce_open_loop.md`).

(c) **Layout track power is hardware-controlled — pyjmri exposes only read.** The booster's physical power switch (and the NCE control panel) is the source of truth for whether the rails are energized. JMRI can *observe* the booster's power state, and `pyjmri` surfaces that observation via the read-only `Client.power_state()` (`PowerState.{ON, OFF, UNKNOWN}`). pyjmri does NOT expose a power-write method because the NCE platform pyjmri targets has no JMRI-controllable power-on; turning the layout on or off is a physical action. (PRD FR16; `power.py`; architecture sec. on power.)

(d) **Throttle acquire is best-effort.** `await jmri.throttle(dcc_address=N, long=True).acquire()` returning successfully means JMRI accepted the acquire request and reserved that throttle slot. It does NOT mean a locomotive at DCC address N is on the rails, powered, or responsive. The decoder may be unaddressed, mis-addressed, asleep, or not present at all. Driving the throttle (`set_speed`, `set_function`) sends DCC packets toward that address whether or not a decoder is listening. Visual / audible confirmation at the layout is the only ground truth. (PRD FR37; memory `project_throttle_simulator_blindspot.md`.)

(e) **Sensors are the real feedback path.** Block-occupancy detectors and other sensors wired through JMRI hardware DO have a true upstream signal — they tell JMRI what the *physical* world is doing. `await sensor.wait_for_state(ACTIVE)` is therefore a meaningful event-driven primitive: it waits for an actual electrical change at the layout, not for a software echo. When event-driven correctness matters (waiting for a train to reach a block, confirming a route cleared), drive the wait off a sensor, not off a turnout/route state. (PRD FR37; architecture event model.)

(f) **No library-side authentication. JMRI's web server is unauthenticated by design.** pyjmri does NOT add an authentication layer. JMRI's JSON web server is unauthenticated and intended for use on a trusted network only — typically the same machine or the same LAN as the layout. Do NOT expose JMRI's web server to the public internet; doing so makes your layout commandable by anyone who can reach it. (PRD NFR11.)

**And** every topic includes a brief "what this means for your code" or "what this means in practice" sentence. The reader walks away with both *the fact* and *the consequence*.

### AC2 — Section positioned prominently (directly after Quickstart, before any reference material)

**Given** the current README ordering (post-Story-6.1: `Quickstart → Migrating from Jython → Limitations`)
**When** Story 6.2 lands
**Then** the new ordering is `Quickstart → Limitations → Migrating from Jython`. The Limitations H2 sits immediately after the last H3 subsection of the Quickstart H2 (`### Try it in a notebook`). The Migrating from Jython H2 (currently `## Migrating from Jython` at `README.md:74` of the post-6.1 state) moves down to sit AFTER the Limitations H2 block.
**And** the Migrating from Jython placeholder body is NOT edited (no whitespace changes, no word changes). Only its position in the file changes. Story 6.3 owns its body.
**And** the Quickstart's existing forward-pointer ("see the Limitations section below" at the end of `### What you should see`, `README.md:60` of the post-6.1 state) reads naturally under the new ordering — confirmed by reading the Quickstart top-to-bottom and verifying the sentence still flows. The phrase "below" remains literally accurate because Limitations is still below Quickstart, just immediately below.

### AC3 — FR37 cross-check: every documented limitation has a "library does not raise" plain-language entry

**Given** PRD FR37 ("The library does not raise exceptions for failure modes it cannot detect…")
**When** a reviewer audits the Limitations section against FR37
**Then** the two examples FR37 names explicitly — "missing locomotive on the rails" and "turnout that physically failed to move" — each appear in plain language somewhere in the section (covered by AC1(d) and AC1(a)/(b) respectively).
**And** for each of the six AC1 topics, the section makes explicit that pyjmri does NOT raise an exception for the underlying failure mode. The reader is never left wondering "would pyjmri have told me?"
**And** any FR37 cases discovered during authoring that aren't covered by AC1(a)-(f) are added as additional topics (the AC1 list is the floor, not the ceiling). Examples that may surface: route that JMRI fired but no turnouts moved (NCE bus failure mid-route); light commanded ON whose decoder is unpowered; signal mast aspect set to a value the physical signal cannot display.

### AC4 — Tone: clear-eyed, not apologetic

**Given** the tone discipline (Epic 6.2 AC3)
**When** a reader from the JMRI community reads the section
**Then** the prose frames each limitation as "this is a property of DCC and of NCE hardware" rather than "this is a missing pyjmri feature." Specifically:

- No "unfortunately," "sadly," "regrettably," or similar hedging adverbs.
- No "we plan to," "future versions may," or roadmap implications. (The Vision/Growth deferred items live in the PRD, not the README's Limitations section.)
- No comparison to other libraries or to JMRI's Java/Jython surface — the section explains DCC reality, not market positioning.
- "pyjmri does not X because Y" framing is allowed and preferred where Y is a property of the hardware (e.g., "pyjmri does not expose a power-write method because the NCE platform has no JMRI-controllable power-on").

**And** the section reads as approximately 250–500 words of prose total (rough budget — adjust for content density). NOT a multi-page treatise. The Limitations section is a forthright disclosure, not a textbook chapter.

### AC5 — Public API hygiene: every API name referenced is in `pyjmri.__init__.__all__`

**Given** the section may reference public API names (e.g., `Client.power_state`, `turnout.set_state`, `sensor.wait_for_state`, `Throttle.acquire`)
**When** the section is authored
**Then** every API name referenced resolves under `from pyjmri import ...` — i.e., its top-level type appears in `pyjmri.__init__.__all__` (`__init__.py:35-70`). No reaching into `_codes`, `_parsing`, `_protocols`, `_transport`, `_subscriptions`, `_waiters`.
**And** the section does NOT name any API that doesn't exist in the post-Story-5.3 implementation. If an API would help the reader but doesn't ship in v1, omit it — Limitations is not a roadmap.

### AC6 — Quality gates clean (docs-only scope)

**Given** the project-wide quality discipline (memory `feedback_use_uv.md`: always `uv run --no-sync`; memory `feedback_polish_matters.md`: markdownlint self-scan before declaring done)
**When** the dev runs the quality gates
**Then** ALL the following pass cleanly:

- `uv run --no-sync ruff check` — unchanged from baseline (no Python source changed).
- `uv run --no-sync ruff format --check` — unchanged from baseline.
- `uv run --no-sync mypy --strict src/pyjmri` — unchanged from baseline (no source changed).
- `uv run --no-sync pytest -m "not integration"` — unchanged from post-Story-6.1 baseline.
- Markdownlint-style self-scan of `python_code/README.md`: heading levels increment cleanly (H1 → H2 → H3, no skips), the new Limitations section introduces no MD0xx warnings, the Migrating from Jython placeholder retains its pre-existing MD036 warning (owned by Story 6.3 — not this story's job to fix).

**And** the story's `File List` enumerates every changed file: 1 modified source file (`python_code/README.md`); the story file + `sprint-status.yaml` update bring the total to 3.

### AC7 — README-internal cross-references stable across the reorder

**Given** the Quickstart's existing forward-pointer to Limitations (`README.md:60` of the post-6.1 state, the phrase "see the Limitations section below")
**When** the reorder lands
**Then** the forward-pointer continues to read naturally because Limitations is still below Quickstart (just immediately below). No edit to the Quickstart text is required.
**And** no anchor-style links (`[Limitations](#limitations)`) are introduced — plain prose phrases ("see the Limitations section below," "as the Limitations section explains") are stable across GitHub, MkDocs, and PyPI renderers (AC6 of Story 6.1 established this discipline).
**And** the dev re-reads the full README top-to-bottom after the edit to confirm narrative flow: Quickstart promises a quick win, Limitations sets the truth-floor immediately after the win, Migrating from Jython then helps the existing-Jython reader port their code. The progression should feel intentional.

## Tasks / Subtasks

- [x] **Task 1 — Author the Limitations section body** (AC: 1, 3, 4, 5)
  - [x] Open `python_code/README.md`. Identify the current Limitations H2 block (placeholder at lines 80–84 of the post-6.1 state).
  - [x] Draft six topic paragraphs covering AC1(a)-(f). Suggested structure: a 1–2 sentence intro paragraph framing "what pyjmri can and cannot tell you," then six H3 subsections (one per topic) OR a single bullet-list per topic — the dev's call. Story 6.1 used H3 subsections inside the Quickstart H2 (Prerequisites / Install / Your first script / What you should see / Try it in a notebook); Story 6.2 may follow the same pattern for consistency, or use a bullet-with-bold-leads style — either is acceptable so long as each topic is single-scroll discoverable.
  - [x] For each topic, include the "what this means for your code" consequence sentence (AC1 closing requirement).
  - [x] Cross-check against FR37 (PRD line 812). Confirm "missing locomotive on the rails" appears (topic d) and "turnout that physically failed to move" appears (topic a or b). Add any FR37 cases discovered during authoring beyond AC1(a)-(f).
  - [x] Tone audit: re-read for hedging adverbs ("unfortunately," "sadly," etc.) and roadmap language ("future versions may") and remove them. Per AC4.
  - [x] API-name audit: for every `Client.X`, `Turnout.X`, `Sensor.X`, `Throttle.X`, `PowerState.X` mentioned, confirm it appears in `pyjmri.__init__.__all__` (`__init__.py:35-70`). Per AC5.

- [x] **Task 2 — Reorder so Limitations sits immediately after Quickstart** (AC: 2, 7)
  - [x] In `python_code/README.md`, cut the Migrating from Jython H2 block (currently at lines 74–78 of the post-6.1 state: the H2 line plus its 2-line placeholder body plus surrounding blank lines).
  - [x] Paste the Migrating from Jython block AFTER the Limitations section block, preserving the blank-line spacing.
  - [x] Confirm the final ordering reads: H1 (line 1) → `## Quickstart` H2 → (Quickstart subsections including `### Try it in a notebook`) → `## Limitations` H2 → (Limitations content from Task 1) → `## Migrating from Jython` H2 → (Migrating placeholder, unchanged).
  - [x] Verify the Migrating from Jython placeholder body is character-for-character unchanged. (`git diff python_code/README.md` should show the Migrating block as a pure move, not a re-edit.)
  - [x] Re-read the Quickstart's "What you should see" closing sentence (`see the Limitations section below`) — confirm it still flows naturally now that Limitations is the immediately-next H2. Per AC7.

- [x] **Task 3 — Self-scan + final read-through** (AC: 4, 6, 7)
  - [x] Markdownlint-style scan of the new Limitations content: heading-level continuity (H2 → H3 if you used H3 subsections, no jumps), code-fence language tags if any code blocks appear (none expected — Limitations is prose), no trailing whitespace, no double spaces, no bare URLs.
  - [x] Confirm the only remaining MD036 warning on the README (after the Story 6.2 edit) is the Migrating from Jython placeholder's `*(filled in Epic 6 — Story 6.3)*` italics-as-heading line. That warning is pre-existing, owned by Story 6.3, NOT introduced by Story 6.2.
  - [x] Read the full README top-to-bottom one more time. Does the narrative flow Quickstart → Limitations → Migrating from Jython feel intentional? If a phrase reads like a leftover from the placeholder, rewrite it.
  - [x] Self-scan THIS story file for markdownlint warnings before declaring done. Per memory `feedback_polish_matters.md`.

- [x] **Task 4 — Quality gates + File List + Completion Notes** (AC: 6)
  - [x] `uv run --no-sync ruff check` — verify unchanged (this is docs-only).
  - [x] `uv run --no-sync ruff format --check` — verify unchanged.
  - [x] `uv run --no-sync mypy --strict src/pyjmri` — verify unchanged.
  - [x] `uv run --no-sync pytest -m "not integration"` — verify unchanged from post-Story-6.1 baseline.
  - [ ] (Optional, only if hardware/simulator is running locally) `uv run --no-sync pytest -m "integration and not slow"` — skip if Mikey is not at the layout.
  - [x] Update File List, Completion Notes, Change Log; set Status to `review`.

### Review Findings

- [x] [Review][Patch] Bare `THROWN` used in prose — must be `TurnoutState.THROWN` [python_code/README.md:84]
- [x] [Review][Patch] `wait_state` "does not raise" sentence misleading — raises `WaitTimeout` when `timeout=` provided; qualify to "without a `timeout=` argument" [python_code/README.md:96]
- [x] [Review][Patch] `Client.power_state()` naming inconsistent with `jmri.throttle()` convention — change to `jmri.power_state()` [python_code/README.md:88]
- [x] [Review][Patch] Throttle subsection lacks an explicit code-consequence sentence ("what this means for your code") — AC1 closing requirement [python_code/README.md:90-92]
- [x] [Review][Defer] `PowerState.UNKNOWN` conditions not explained (JMRI codes 0 and 1 both map to UNKNOWN) — deferred, pre-existing, API reference scope
- [x] [Review][Defer] Double `discover()` call silently abandons in-flight `wait_state` waiters — deferred, pre-existing, out of Limitations scope
- [x] [Review][Defer] `set_state(TurnoutState.UNKNOWN)` raises `ValueError` undocumented — deferred, pre-existing, out of Limitations scope
- [x] [Review][Defer] "Throttle slot" term not defined for readers unfamiliar with WiThrottle protocol — deferred, pre-existing, jargon acceptable in context
- [x] [Review][Defer] `wait_state` returns immediately on cache hit — "waits for actual electrical change" not universally true — deferred, pre-existing, API nuance
- [x] [Review][Defer] `ThrottleAcquireFailed` raised on JMRI rejection not mentioned in Limitations — deferred, out of scope (Limitations covers undetectable failures, JMRI rejection is detectable)

## Dev Notes

### Authoritative current state of `python_code/README.md` (verified 2026-05-23, post-Story-6.1-done)

Line numbers below reference the current README state at the time this story was authored.

| Section | Lines | Status for Story 6.2 |
| --- | --- | --- |
| `# pyjmri` (H1 + description) | 1–3 | UNCHANGED |
| `## Quickstart` (H2 + framing) | 5–7 | UNCHANGED |
| `### Prerequisites` | 9–15 | UNCHANGED |
| `### Install` | 17–27 | UNCHANGED |
| `### Your first script` | 29–49 | UNCHANGED |
| `### What you should see` | 51–60 | UNCHANGED (the forward-pointer to Limitations at line 60 stays valid) |
| `### Try it in a notebook` | 62–72 | UNCHANGED |
| `## Migrating from Jython` (placeholder) | 74–78 | **MOVED** — same content, repositioned AFTER the new Limitations section |
| `## Limitations` (placeholder) | 80–84 | **REPLACED** — placeholder body replaced with the full section from Task 1; H2 line repositioned to immediately follow `### Try it in a notebook` |

### Source files in `src/pyjmri/` (NOT modified by this story)

All source files unchanged. The section may reference these public surface members (every one is in `pyjmri.__init__.__all__` at `__init__.py:35-70`):

| Name | Source | Used by Limitations topic |
| --- | --- | --- |
| `Client` | `pyjmri.client.Client` | (c) `power_state()` method |
| `Client.power_state` | `client.py:850-888` | (c) — explicit read-only-by-design docstring at lines 853–857 |
| `PowerState` | `pyjmri.power.PowerState` (`__init__.py:42`) | (c) — names the three states `{ON, OFF, UNKNOWN}` |
| `Turnout.set_state` | `turnout.py:76` | (a)(b) — "command acknowledged" wording |
| `Sensor.wait_for_state` (Epic 3 wait primitive) | `sensor.py` + `_waiters.py` | (e) — the real feedback path |
| `Throttle.acquire` | `client.py:473` (acquire) + Throttle class from Story 5.1 | (d) — best-effort framing |

Test files: UNCHANGED — Story 6.2 adds no tests.

Build config: UNCHANGED — `pyproject.toml`, `uv.lock`, `LICENSE`, `py.typed`, `dist/` are all untouched.

### Why this story reorders rather than just filling the placeholder

Epic 6.2 AC2 says the section is "positioned prominently … directly after Quickstart, *before* the API reference." The current README has no API reference section (one is Growth-deferred per architecture — Sphinx/MkDocs is post-v1). But the architectural intent is clear: a casual reader who scrolls past Quickstart MUST encounter Limitations before they go off and write code that assumes turnout commands are confirmed by physical movement. Putting Limitations immediately after Quickstart satisfies that intent; putting it third (current placeholder ordering) does not.

The reorder costs nothing — the Migrating from Jython placeholder is two non-content lines that move as a block. Story 6.3 will fill that placeholder later; its content is independent of where the H2 sits.

### Content-design rationale

#### Why six topics and not fewer?

Epic 6.2 AC1 names six required content blocks (a)–(f). Each represents a distinct failure mode or user-visible behavior. Collapsing two topics into one (e.g., merging (a) and (b)) risks the reader missing one of the two. Honesty about open-loop NCE benefits from separate prominent topics for "the platform has no feedback" (a) and "what that means when your `await` returns" (b) — the first is the abstract fact, the second is the concrete consequence the reader will encounter in their code.

#### Why include `power_state()` even though it's read-only?

Topic (c) explicitly names what pyjmri DOES expose (`power_state()`, read-only) so that the reader knows the surface area. Otherwise topic (c) reads as a pure negative ("you can't control power"), which is less useful than the full picture ("you can observe power, you can't control it, here's why").

#### Why include the no-authentication topic (f) — isn't that obvious?

NFR11 explicitly requires it in user-facing materials. It is NOT obvious to a Python developer arriving from a web-services background — they may assume any HTTP-speaking service has auth. The single-sentence honest disclosure prevents the "I exposed JMRI to my home VPS and now my turnouts are being thrown by strangers" surprise. Cheap to include; high value if it saves one person from that surprise.

#### Why "approximately 250–500 words" (AC4 budget)?

The full Limitations section needs to be readable in one sitting (≈ 1–2 minutes). Six topics × ~50–80 words each lands in the 250–500 range. Significantly shorter risks under-explaining; significantly longer reads as a treatise rather than a disclosure. The budget is approximate — adjust for content density, but if you find yourself writing 1000+ words, reconsider what's essential.

#### Why no code blocks in this section?

Limitations is a truth-floor disclosure, not a tutorial. Code belongs in Quickstart (5-minute walkthrough), in the migration table (Story 6.3, paired before/after snippets), and in the shipped examples (Story 6.4). A code block in Limitations would distract from the "here is what is and isn't true" message.

### Cross-story implications

- **Story 6.1 (Quickstart):** Already done. Its forward-pointer to Limitations at `### What you should see` remains valid after the reorder (Limitations is still below Quickstart, just immediately below). No edit to Quickstart required.
- **Story 6.3 (Jython migration table):** The Migrating from Jython placeholder body is character-for-character unchanged by Story 6.2; only its position in the file changes. Story 6.3 fills the placeholder body wherever it ends up sitting. No coupling between the two stories beyond ordering.
- **Story 6.4 (shipped examples):** Independent. The examples will reference Limitations from their own docstrings ("see README Limitations section for what this command does and doesn't confirm") — that cross-reference is Story 6.4's concern.
- **Story 6.5 (CONTRIBUTING.md):** Independent.
- **Story 6.6 (PyPI publication):** Story 6.2's section ships as part of the README on PyPI. PyPI's README renderer is the same Markdown rules as GitHub for the subset Story 6.2 uses (H2/H3, paragraphs, bullets). No PyPI-specific concerns.

### Architecture rules carried forward (apply verbatim)

- **README-first documentation** per architecture `Documentation Patterns` (`architecture.md:918-934`): the 5-minute getting-started is the front door, the Limitations section is the immediately-next mandatory disclosure. Story 6.2 lands the second of those two pillars.
- **"Limitations section is mandatory README content (FR42)"** — architecture `Documentation Patterns` (`architecture.md:933-934`). This story discharges that mandate at the content level.
- **Public-API hygiene** per architecture `Enforcement` (`architecture.md:947-948`): Limitations references API names from `pyjmri.__init__.__all__` only. No `_` -prefixed module names appear in user-facing prose.
- **Honesty over comfort** per architecture `Documentation Patterns` (Limitations is mandatory, not optional): the entire purpose of the section.
- **Layout-agnostic discipline:** Although Limitations is prose (no script), references to layout-specific values (system names like `NT400`, panel-file names like `Basement_Revised_2024.jmri`) MUST be avoided. The section applies to any user, on any layout, against any NCE setup. Generic phrasing ("a turnout," "your locomotive") only.

### Carry-forward learnings from Story 6.1

- **Scope discipline (Story 6.1 scope notes):** "Other H2 sections … remain placeholders for Stories 6.2 and 6.3." Story 6.2 is now the second of those — it owns its own placeholder, leaves Story 6.3's alone, and (uniquely) reorders the file. The reorder is in scope because Epic 6.2 AC2 explicitly mandates it; if Epic 6.3 ever mandates a reorder, that's Story 6.3's call.
- **Markdownlint discipline (Story 6.1 self-scan + memory `feedback_polish_matters.md`):** Pre-dev scan of THIS story file before starting implementation. The dev fixes MD0xx warnings on the story file itself before opening the README — Story 6.1 set this precedent. Pre-existing warnings on Story 6.3's placeholder are out of scope and stay.
- **Public-API hygiene** (Story 6.1 AC4): every name in the Quickstart resolved under `from pyjmri import ...`. Same rule applies here for any API name Story 6.2 mentions.
- **Forward-pointer phrasing** (Story 6.1 AC6): "see the Limitations section below" uses no anchor links — plain prose only, stable across renderers. Story 6.2's reorder preserves the "below" phrasing's truth (Limitations is still below Quickstart in the file).
- **Quality-gate baseline** (Story 6.1 Completion Notes): post-Story-5.3 baseline was 411 unit tests passed + 22 deselected. Story 6.1 confirmed unchanged. Story 6.2 should also confirm unchanged because there are no Python source changes.

### Risks and mitigations

- **R1: The reorder accidentally deletes or duplicates a section.** The cut-and-paste of the Migrating from Jython block could go wrong. Mitigation: `git diff python_code/README.md` before commit; verify exactly two H2 line changes (Limitations placeholder content replaced; Migrating block moved). The Migrating placeholder text must be a pure relocation, not a re-edit — verify by visually scanning the diff.
- **R2: The Quickstart's "see the Limitations section below" forward-pointer reads awkwardly after the reorder.** Currently Limitations is two H2s down ("scroll past Migrating, then Limitations"); after the reorder it's the immediately-next H2. The phrase "below" remains literally accurate; the dev reads the Quickstart top-to-bottom to confirm the sentence still flows. If it doesn't, a minor rephrase ("see the Limitations section that follows" or "see the next section, Limitations") is acceptable — but the AC1d expected-output sentence and AC6 prose-not-anchor discipline are NOT in scope to change.
- **R3: The Limitations content drifts into roadmap territory ("future versions will …").** Per AC4, no roadmap language. Mitigation: explicit tone audit task (Task 1, last subtask). Roadmap content lives in PRD's Vision/Growth sections, not in README's Limitations.
- **R4: A reader from the JMRI Jython community reads Limitations as a complaint about NCE.** The tone discipline (AC4) addresses this — frame each item as a property of DCC and NCE, not as a pyjmri shortcoming. NCE is the platform pyjmri targets; pyjmri does not apologize for the platform's design. The Mike-and-Sarah audience from PRD Journey 4 should read it and nod, not bristle.
- **R5: An API name referenced in Limitations gets renamed in a later story before publication.** Unlikely at this point — Epics 2–5 are complete and public API is frozen. But if Story 6.4 (examples) or 6.5 (CONTRIBUTING) discovers a name change is warranted, the Limitations section must be updated in lockstep. Mitigation: dev runs a final REPL check before declaring done — `uv run --no-sync python -c "from pyjmri import PowerState; print(PowerState)"` and similar for every API name referenced.

### References

- `_bmad-output/planning-artifacts/epics.md:958-978` — Epic 6 + Story 6.2 acceptance criteria (this story's source).
- `_bmad-output/planning-artifacts/epics.md:926-928` — Epic 6 intro paragraph (overall framing).
- `_bmad-output/planning-artifacts/prd.md:812` — FR37 (library does not raise exceptions for failure modes it cannot detect; documented in user-facing materials).
- `_bmad-output/planning-artifacts/prd.md:820` — FR42 (Limitations section requirement).
- `_bmad-output/planning-artifacts/prd.md:881-885` — NFR11 (no library-side auth; JMRI unauthenticated by design; trusted-network use).
- `_bmad-output/planning-artifacts/architecture.md:918-934` — Documentation Patterns (README-first, Limitations mandatory).
- `_bmad-output/planning-artifacts/architecture.md:947-948` — Enforcement (no `_` -prefixed module reaches; `__all__` is authoritative).
- `_bmad-output/implementation-artifacts/6-1-readme-5-minute-quickstart.md` — Most recent done story. Pattern source for: docs-only scope discipline, AC structure, markdownlint self-scan, public-API hygiene, forward-pointer phrasing without anchor links.
- `python_code/README.md` — Current state (post-Story-6.1 done). Quickstart at lines 5–72; Migrating from Jython placeholder at lines 74–78; Limitations placeholder at lines 80–84.
- `python_code/src/pyjmri/__init__.py:35-70` — `__all__` list; every API name in the Limitations section MUST appear here.
- `python_code/src/pyjmri/client.py:850-888` — `Client.power_state()` (read-only by design; docstring at lines 853–857 documents NCE booster as source of truth).
- `python_code/src/pyjmri/power.py` — `PowerState.{UNKNOWN, ON, OFF}` enum.
- `python_code/src/pyjmri/turnout.py:76-124` — `Turnout.set_state` docstring (FR22 honesty about `wait_for_jmri_state` semantics — the same honesty Limitations expands on for the optimistic-by-default path).
- Memory: `project_jmri_state_model.md` — JMRI's reported state is "last commanded," not observed.
- Memory: `project_nce_open_loop.md` — Open-loop applies on simulator AND on real hardware.
- Memory: `project_throttle_simulator_blindspot.md` — Throttle commands accepted on simulator with no virtual loco; physical correctness needs hardware.
- Memory: `feedback_use_uv.md` — `uv run --no-sync` for all tool invocations.
- Memory: `feedback_polish_matters.md` — markdownlint self-scan before declaring done.

### Project Structure Notes

- ALL changes live in `python_code/README.md`. NO new files, NO source changes, NO test changes, NO config changes.
- NO changes to `_bmad-output/implementation-artifacts/deferred-work.md` expected — Story 6.2's scope is fully addressable.
- NO changes to `.jmri/` profiles, `jython/` scripts, `roster/` directory, or `roster.xml` (memory `feedback_writable_paths.md`: only `python_code/` and `_bmad-output/` are writable).
- The story file + `sprint-status.yaml` are the only `_bmad-output/` artifacts touched.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (`claude-opus-4-7[1m]`) via Claude Code.

### Debug Log References

None — docs-only story, no debug iteration required.

### Completion Notes List

- **Limitations section authored** (`python_code/README.md:74-100`) with intro + six H3 subsections covering AC1(a)–(f): NCE open-loop; "command acknowledged" semantics; read-only `power_state()`; best-effort throttle acquire; sensors as the real feedback path; no library-side authentication. Each topic includes an explicit "pyjmri does not raise" sentence (AC3) and a "what this means in practice" consequence sentence (AC1 closing requirement).
- **README reordered** (Task 2): Limitations H2 sits immediately after the Quickstart's `### Try it in a notebook` subsection at `README.md:74`, with the Migrating from Jython H2 placeholder moved to `README.md:102` as a pure relocation — its body is character-for-character unchanged (verified via `git diff`). The Quickstart's forward-pointer at `README.md:60` ("see the Limitations section below") continues to read naturally because Limitations is still below Quickstart, just immediately below.
- **FR37 cross-check passed**: both named examples appear in plain language — "missing locomotive on the rails" in topic (d), "turnout that physically failed to move" in topic (b). No additional FR37 cases surfaced during authoring beyond the six in AC1.
- **API-name audit passed (AC5)**: every public API name referenced — `Client.power_state()`, `PowerState.{ON, OFF, UNKNOWN}`, `turnout.set_state`, `jmri.throttle(dcc_address, long=...)` (the `Client.throttle` factory), `set_speed`, `set_function`, `sensor.wait_state`, `SensorState.ACTIVE` — resolves under `from pyjmri import ...` (top-level types `Client`, `PowerState`, `Turnout`, `Throttle`, `Sensor`, `SensorState` all present in `__init__.__all__` at `__init__.py:35-70`). Verified via inspection of `__init__.py`, `client.py:850-888`, `turnout.py:76`, `throttle.py:60-201`, `sensor.py:97-167`. **Note:** the story's Dev Notes table referenced `Sensor.wait_for_state` but the actual public method on `Sensor` is `wait_state` (with siblings `wait_change`, `wait_active`, `wait_inactive`). The README uses the real method name `wait_state`. Similarly, the public throttle pattern is the `async with` context manager — I used that idiom rather than the internal `acquire` mentioned in some Dev Notes references.
- **Tone audit passed (AC4)**: no hedging adverbs ("unfortunately"/"sadly"/"regrettably") and no roadmap language ("future versions"/"we plan to") in the new section — confirmed via grep.
- **Word-count discussion with Mikey**: the section came in at ~580 prose words, slightly over the AC4 "approximately 250–500 words (rough budget — adjust for content density)" soft cap. Mikey chose to leave at ~580 (option 1 of 3 offered) given the content-density requirements (six topics each carrying a "does not raise" sentence + consequence sentence + the substantive failure-mode list). Well below the "1000+ words, reconsider what's essential" red line in the Dev Notes rationale.
- **Polish — story-file MD036 fix**: self-scan of this story file (per memory `feedback_polish_matters.md`) found 5 MD036 (emphasis-as-heading) warnings on the `**Why X?**` rhetorical-subheading lines in `### Content-design rationale` (lines 179, 183, 187, 191, 195). Mikey approved converting them to `#### Why X?` H4 headings — pure formatting change, no spec content modified. Story file now scans clean for MD036.
- **README MD036 remaining**: only the Migrating from Jython placeholder italics line at `README.md:104` (`*(filled in Epic 6 — Story 6.3)*`). Pre-existing, owned by Story 6.3, deliberately out of scope per the story's Tone-discipline guidance.
- **Quality gates clean** (AC6, verified 2026-05-23, matches Story 6.1 baseline exactly):
  - `uv run --no-sync ruff check` → `All checks passed!`
  - `uv run --no-sync ruff format --check` → `53 files already formatted`
  - `uv run --no-sync mypy --strict src/pyjmri` → `Success: no issues found in 20 source files`
  - `uv run --no-sync pytest -m "not integration"` → `411 passed, 22 deselected in 0.58s`
- **Integration tests skipped**: optional gate not run — no hardware/simulator session active.

### File List

- `python_code/README.md` (modified) — replaced Limitations H2 placeholder body with the six-topic section; moved the Migrating from Jython H2 block to sit after Limitations (pure relocation, body unchanged).
- `_bmad-output/implementation-artifacts/6-2-readme-limitations-section.md` (modified) — story-file updates: Status, Tasks/Subtasks checkboxes, Dev Agent Record, Change Log; plus 5 MD036 polish fixes in `### Content-design rationale` per memory `feedback_polish_matters.md`.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — `6-2-readme-limitations-section` transitioned `ready-for-dev` → `in-progress` → `review`; `last_updated` set to 2026-05-23.

## Change Log

- 2026-05-23 — Story 6.2 created (`backlog` → `ready-for-dev`). Docs-only story: replaces the Limitations H2 placeholder in `python_code/README.md` (scaffolded by Story 1.4, untouched by Story 6.1) with a full Limitations section covering six required topics: (a) NCE open-loop, (b) "command acknowledged" semantics, (c) read-only `power_state()`, (d) best-effort throttle acquire, (e) sensors as the real feedback path, (f) no library-side authentication / JMRI trusted-network posture. Also reorders the README so Limitations sits immediately after Quickstart (per Epic 6.2 AC2: "directly after Quickstart, before the API reference"), moving the Migrating from Jython placeholder down without editing its body. FR37 cross-checked (every documented limitation has a plain-language "library does not raise" entry); FR42 satisfied; NFR11 disclosed in topic (f). No source changes, no new tests, no config changes — single file modified is `python_code/README.md`.
- 2026-05-23 — Story 6.2 implemented (`ready-for-dev` → `in-progress` → `review`). Limitations section authored at `python_code/README.md:74-100` (intro + 6 H3 subsections, ~580 prose words, content-density justified per discussion with Mikey). Migrating from Jython block relocated to `README.md:102-106` as a pure move (body byte-identical). API-name audit corrected the README to use the real public surface (`Sensor.wait_state`, not the `wait_for_state` referenced in some Dev Notes table entries; `async with jmri.throttle(...) as loco:` context-manager idiom rather than a bare `.acquire()` call). Quality gates pass clean against the post-Story-6.1 baseline (411 unit tests passed, 22 deselected; ruff/format/mypy unchanged). Story file received a polish pass per memory `feedback_polish_matters.md`: 5 MD036 emphasis-as-heading patterns in `### Content-design rationale` converted to `#### Why X?` H4 headings (formatting only, no spec change).
