# Story 6.5: `CONTRIBUTING.md` with release checklist

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a maintainer (or future contributor),
I want a `python_code/CONTRIBUTING.md` that documents the developer setup, the integration-tests-local-only policy, how to run integration tests locally, and a concrete release checklist whose steps reference the long-run stability test (Story 3.4) and the hardware-mode throttle validation protocol (relocated here from Story 5.3),
So that release discipline lives in one place future-me (or a contributor) can follow without re-deriving it.

## Scope notes

- **Fifth story in Epic 6.** Owns the new file `python_code/CONTRIBUTING.md` and nothing else. Stories 6.1 (Quickstart), 6.2 (Limitations), 6.3 (Migration table), and 6.4 (examples/) are done; Story 6.6 (PyPI publish) is downstream and runs the checklist this story authors.
- **Documentation-only story.** NO changes to `python_code/src/pyjmri/`. NO test changes. NO `pyproject.toml` changes. NO README edits. NO changes to `python_code/examples/`. The keep-alive TODO comment at `throttle.py:316-345` is NOT updated by this story — the release checklist documents the procedure that updates it when an operator runs the checklist; the comment update is a release-time action, not implementation work for Story 6.5.
- **One new file, one location.** Create `python_code/CONTRIBUTING.md` (verified absent at story-authoring time via `test -f python_code/CONTRIBUTING.md` → DOES NOT EXIST). The architecture's project structure at `architecture.md:978` and `architecture.md:1150` both place it at this path. No sibling files (no `RELEASING.md`, no `CHANGELOG.md` — Growth-deferred per PRD).
- **Cross-references existing artifacts; does NOT duplicate them.** The release checklist references concrete commands and files that already exist (`tests/integration/test_long_run.py --duration=3600`, `uv build`, `uv publish`, `pyproject.toml` version field, the throttle.py keep-alive TODO comment). Where another document already says something authoritatively (Limitations, Migration table, integration-test guidance in module docstrings), `CONTRIBUTING.md` points at it rather than re-stating it.
- **The release checklist must be enforceable, not aspirational** (AC3). Each numbered step is either (a) a shell command a maintainer can copy-paste, or (b) a physical action with an unambiguous "did it work? yes / no / record the result" verification. No prose like "ensure everything is in good shape" — that is the bug AC3 explicitly forbids.
- **Hardware-mode validation protocol is OWNED by Story 6.5.** Story 5.3 (`test_throttle_lifecycle.py:19-24`) explicitly forward-references `CONTRIBUTING.md`'s release checklist for the protocol. Story 5.1 (`throttle.py:316-345`) seeds the keep-alive TODO that the protocol's keep-alive observation step updates. This story produces the procedure both forward-references point at.
- **Keep-alive observation interval is 2× `ClientConfig.throttle_keepalive_interval` (default 15 s → 30 s of held silence).** Per `architecture.md:1375-1379` and `_protocols.py` defaults and AC4 of this story. The "30 s of held silence" wording in the checklist matches the default; the doc must also explain why (it is "2× the configured interval", not a magic number — a maintainer who tunes the interval can recompute the wait).
- **Integration-tests-local-only policy is the v1 stance, not aspirational.** Per `architecture.md:701-705` and `prd.md:701-707`. The actual CI workflow at `.github/workflows/ci.yml` runs `pytest -m "not integration"` and CONTRIBUTING.md restates that policy as the contributor-facing rule. Headless-JMRI CI is Growth-deferred per `architecture.md:360-361`; the doc should mention "Growth-deferred" once, not propose a different approach.
- **`uv` is the canonical toolchain; pip is a universal fallback.** README's Install section at `README.md:18-27` already establishes the `uv` first, `pip` second ordering. CONTRIBUTING.md uses `uv run --no-sync` for every tool invocation (per memory `feedback_use_uv.md`) and `uv sync` for developer install (per `architecture.md:1237-1239`). No `pip install -e .` or `pip install -r requirements.txt` — `uv sync` covers it.
- **No badge / hyperlink lint discipline.** No markdown anchor links into other documents (no `[Quickstart](README.md#quickstart)` — those rot). Use conceptual phrases like "see the Quickstart in `README.md`" — same anchor-free discipline Story 6.3 used for migration-table cross-references.
- **Polish discipline (memory `feedback_polish_matters.md`):** Pre-dev markdownlint self-scan of this story file. Self-scan of `CONTRIBUTING.md` before declaring done. Use `#### Why X?` H4 headings, not `**Why X?**` italics-as-heading lines (which trigger MD036). No `*(filled in later)*` placeholder lines.
- **Approximate target length: 250–400 lines for `CONTRIBUTING.md`.** Comparable to the README's substantive sections combined. Substantive but not a tutorial — every paragraph earns its place by either (a) telling the operator what to do, (b) documenting an enforceable check, or (c) explaining a non-obvious "why" the operator needs to make a judgment call. If the file grows past ~450 lines, the dev has likely re-explained content owned by README or by module docstrings — pull back.

## Acceptance Criteria

### AC1 — `python_code/CONTRIBUTING.md` exists with the four required sections (Epic AC #1)

**Given** the package skeleton from Epic 1 and the documentation deliverables tracked in `architecture.md:1144-1158`
**When** `python_code/CONTRIBUTING.md` is added
**Then** it contains, in this top-to-bottom order, sections covering:

1. **Developer setup.** `uv sync` to install runtime + dev dependencies; how to confirm Python 3.11+ is in scope (`uv run --no-sync python --version`); how to run the standard unit-test invocation `uv run --no-sync pytest -m "not integration"`; the expected baseline (post-Story-6.4: **411 passed, 22 deselected**). The section names the four quality gates (`ruff check`, `ruff format --check`, `mypy --strict src/pyjmri`, `pytest -m "not integration"`) and gives the canonical command for each — every command is prefixed with `uv run --no-sync` (memory `feedback_use_uv.md`).
2. **Integration-tests-local-only policy** (FR42 / architecture sec. Test Strategy at `architecture.md:701-705`). Explains that v1 integration tests require a real JMRI instance and are excluded from CI; CI runs unit tests only on macOS + Linux × Python 3.11/3.12/3.13 (per `.github/workflows/ci.yml`); headless-JMRI CI is Growth-deferred (per `architecture.md:360-361`) — not under consideration for v1. The doc explicitly states "no PR is blocked on missing integration coverage; integration evidence is the maintainer's pre-release responsibility."
3. **How to run integration tests locally.** Pre-conditions: a running JMRI 5.14+ instance at `localhost:12080` (default), the basement simulator profile or an equivalent layout; the conftest's skip-on-absence fixture (`architecture.md:699-700`) handles JMRI-unreachable cleanly. Invocations: `uv run --no-sync pytest tests/integration/` for the full integration suite (excluding the `slow` long-run test); `uv run --no-sync pytest -m integration` (equivalent); `uv run --no-sync pytest -m "integration and not slow"` (explicit form); the long-run-specific invocation appears in the Release Checklist below, not here (avoid duplication).
4. **Release checklist** — see AC2 for the full ordered list.

**And** AC1 also requires:
- a one-paragraph intro at the top explaining the doc's purpose ("This file is for maintainers and contributors to pyjmri. End-users wanting the library should read `README.md` and the examples in `examples/`.")
- a brief "Reporting issues" or "Filing a PR" paragraph (≤8 lines) telling a contributor where to file bugs (GitHub Issues at `https://github.com/mdean77a/JMRI`) and what to expect (the v1 doc says: maintainer reviews are best-effort; PRs that include passing tests against simulator + a note about hardware-mode if relevant are merged faster). The "Reporting issues" paragraph is allowed to be brief — v1 maintainership is one person; this story is not authoring a multi-contributor governance doc.

### AC2 — Release checklist has the 9 specified steps, in order, as enforceable commands or physical actions (Epic AC #2)

**Given** the release checklist section
**When** it is written
**Then** it lists, in order, these 9 numbered pre-release verification steps. Each step has the form **(command or action) → (success criterion / what to record)**. Every command uses `uv run --no-sync` for tool invocations (memory `feedback_use_uv.md`).

1. **Linting and formatting clean locally.** `uv run --no-sync ruff check` → expect `All checks passed!`. `uv run --no-sync ruff format --check` → expect `N files already formatted` (N varies; the count itself is not the gate — the gate is "no files need reformatting"). If either fails, fix before continuing.
2. **Type-checking clean.** `uv run --no-sync mypy --strict src/pyjmri` → expect `Success: no issues found in 20 source files` (post-Story-6.4 baseline; the number may grow but must never decrease without an explicit Story changing the source surface). `uv run --no-sync mypy --strict examples/` → expect `Success: no issues found in 3 source files`.
3. **Unit tests clean.** `uv run --no-sync pytest -m "not integration"` → expect `411 passed, 22 deselected` (post-Story-6.4 baseline; the passed count may grow, the deselected count may grow with new `@pytest.mark.integration` tests). Any failure halts the release.
4. **Full integration suite passes against the basement simulator.** Start JMRI with `Basement_Revised_2024.jmri` (or equivalent), confirm web server at `localhost:12080`, then `uv run --no-sync pytest -m integration` → expect all integration tests pass; deselected count equals 1 (`test_long_run.py` is `slow` and `integration`, so it gets selected by `-m integration` *and* is itself a separate slow gate — clarify in the doc that the long-run test is **already covered in step 5** and the maintainer can either let it run here or use `-m "integration and not slow"` to skip it and rely on step 5 alone). The doc picks one and documents the choice; recommendation: use `-m "integration and not slow"` here so step 4 finishes in a reasonable time and step 5 owns the long-run gate cleanly.
5. **One-hour long-run stability test passes.** Per Story 3.4 and `tests/integration/test_long_run.py`: `uv run --no-sync pytest tests/integration/test_long_run.py --duration=3600 -s` (the `-s` flag enables the summary line). Equivalent: `PYJMRI_LONG_RUN_DURATION=3600 uv run --no-sync pytest tests/integration/test_long_run.py -s`. Success criterion: test passes (single PASS line) AND the printed summary line has the form `pyjmri long-run: duration=3600s disconnects=5 reconnects=5 rss_delta=X.XMB fd_delta=N task_delta=N status=PASS` — **paste this summary line into release notes verbatim** (step 6 requires it).
6. **Hardware-mode throttle validation per AC4 below.** Place a known-responsive locomotive on the layout at a documented DCC address; run the small driving script (described in AC4); visually confirm motion, direction change, and function-bit effect; observe the keep-alive behavior (hold throttle 30 s silent, then issue a command); record the keep-alive outcome (one of: "JMRI still considers the throttle held" → no-op stub stays; "JMRI dropped the throttle" → activate the keep-alive body per the throttle.py TODO at lines 320-338). The result goes into release notes (step 7) AND into the comment on `Throttle._keepalive` in `throttle.py:316-345` (this updates the TODO seeded by Story 5.1).
7. **Version bumped in `pyproject.toml`.** Edit `[project].version` to the new release version (e.g., `0.1.0` → `1.0.0` for the first PyPI publish per Story 6.6). The doc shows the literal field path. Commit the bump as a discrete commit with subject `Bump version to X.Y.Z`. The current version at story-authoring time is `0.1.0` (confirmed at `pyproject.toml:3`).
8. **Release notes written.** Plain-text or markdown release notes covering at minimum: (a) the JMRI version tested against in steps 4–6 (e.g., "JMRI 5.14.1"), (b) the long-run summary line from step 5 verbatim, (c) the hardware-mode keep-alive observation outcome from step 6 ("JMRI keeps throttle / drops throttle after 30 s of silence"). Recommended location: a `RELEASES.md` file at `python_code/RELEASES.md` (Growth-deferred for a structured changelog format — v1 release notes can be free-form). Story 6.5 does NOT create `RELEASES.md`; it documents where release notes go.
9. **Build clean artifacts and publish.** `uv run --no-sync uv build` (or `uv build` — `uv build` does not itself need `uv run --no-sync` since `uv` IS the toolchain, but the doc stays uniform) produces `python_code/dist/pyjmri-X.Y.Z.tar.gz` and `python_code/dist/pyjmri-X.Y.Z-py3-none-any.whl`. Validate with `uv run --no-sync twine check dist/*` → expect `Checking dist/*: PASSED` (twine is a dev dependency per `pyproject.toml:32`). Then `uv publish` (per `architecture.md:1235-1236`) with credentials supplied via environment (`UV_PUBLISH_TOKEN` or `~/.pypirc`). Finally `git tag vX.Y.Z && git push origin vX.Y.Z`.

**And** every step is rendered in CONTRIBUTING.md as either a fenced shell block (for commands) or a numbered list item (for actions); no step uses prose like "make sure things look good" — every step has an executable command or a "do this physical thing, observe this outcome" instruction.

**And** the section header reads `## Release checklist` (H2) so it is linkable from external docs without anchor-link rot risk (anchor `#release-checklist`).

### AC3 — Checklist is enforceable: concrete commands and physical actions only (Epic AC #3)

**Given** the release checklist is the discipline
**When** any future contributor reads it
**Then** every step satisfies at least one of:

1. **Copy-paste-ready shell command** in a fenced block — e.g., `` `uv run --no-sync ruff check` ``, not "lint the code".
2. **Physical action** with a specific verification — e.g., "place a locomotive at DCC address N on the rails, run the script, watch the loco move at least 1 meter", not "verify the loco works".
3. **Recording requirement** — e.g., "paste the summary line into release notes", not "document the test result".

**And** the doc explicitly forbids the failure modes that AC3 exists to prevent:
- No "verify everything is in good shape" sentences.
- No "ensure quality" without a measurable criterion.
- No "consider running X" — either X is required (numbered step) or it is not in the checklist at all.

**And** a contributor reading the checklist top-to-bottom should be able to execute every step without consulting the maintainer for clarification. The doc may add explanatory paragraphs (1–3 sentences) between numbered steps if the intent is non-obvious — those paragraphs explain *why*, never *what* (the numbered step itself is the *what*).

### AC4 — Hardware-mode throttle validation protocol is documented (Epic AC #4 — relocated from Story 5.3)

**Given** Story 5.3 (`test_throttle_lifecycle.py:19-24` and module docstring AC10) forward-references `CONTRIBUTING.md`'s release checklist for the hardware-mode validation protocol, and Story 5.1 (`throttle.py:316-345`) seeds the keep-alive TODO that this protocol's keep-alive observation step updates
**When** `CONTRIBUTING.md` is written
**Then** the release checklist's step 6 (per AC2) expands into a sub-procedure with these explicit operator instructions:

1. **Setup.** Operator confirms: (a) JMRI 5.14+ is running on a machine that talks to real NCE hardware (not the simulator); (b) the basement layout (or equivalent) is powered (booster ON); (c) a known-responsive locomotive is placed on the rails at a documented DCC address (e.g., DCC 5327 long, the basement default per `jython/MikeBackAndForth.py:18` and `examples/back_and_forth.py:--dcc` default); (d) the path is clear in both directions for a few meters of run.
2. **Drive script.** Operator runs a small script using `pyjmri.Throttle` that: (a) acquires the throttle via `async with layout.throttle(dcc, long=True) as t:`, (b) issues `await t.set_speed(0.3, forward=True)`, (c) holds for 5–10 seconds of run (operator watches the loco), (d) issues `await t.set_speed(0.3, forward=False)` to reverse direction, (e) holds for another 5–10 seconds, (f) toggles a function (e.g., `await t.set_function(0, True)` for the headlight on most decoders), (g) issues `await t.set_speed(0.0, forward=True)` to stop, (h) exits the `async with` block to release the throttle. **The doc provides this script inline as a runnable snippet** (the `examples/back_and_forth.py` script is *too autonomous* — it loops forever and waits on sensors; the release-validation script is shorter, hand-driven, and operator-supervised). Snippet target: ≤30 lines including imports and `asyncio.run`.
3. **Visual verification.** Operator confirms by visual observation at the layout: (a) loco moved forward when commanded forward; (b) loco moved in reverse when commanded reverse; (c) the function bit took effect (e.g., headlight illuminated). Each observation is recorded as PASS / FAIL in release notes. A FAIL on any one is a release-blocker.
4. **Keep-alive observation.** Operator runs a second small script that: (a) acquires the throttle; (b) issues `await t.set_speed(0.0, forward=True)` to confirm the throttle is held and stopped; (c) sleeps for **2× the configured `throttle_keepalive_interval`** (default `15.0` seconds per `_protocols.py` and `architecture.md:1375-1379`, so **30 seconds of held silence**); (d) issues `await t.set_speed(0.1, forward=True)` and watches whether the loco responds; (e) if the loco responds → JMRI kept the throttle held during the silence → the v1 no-op keep-alive stub is correct; (f) if the loco does NOT respond → JMRI dropped the throttle during the silence → the keep-alive coroutine body must be activated per the inline-comment recipe at `throttle.py:320-338`. **The script for this observation is also provided inline as a runnable snippet** — same constraints as step 2's snippet.
5. **Record the result.** Operator does TWO things: (a) write the outcome ("JMRI keeps throttle held after 30 s silence" or "JMRI drops throttle after 30 s silence") into release notes for the current release; (b) update the comment block at `throttle.py:316-345` with the date, the JMRI version tested, the NCE hardware identifier, and the outcome — replacing the speculative "If Story 5.3 hardware observation shows JMRI does expire idle throttles..." with the actual finding. If the outcome is "drops", the operator also performs the code change spelled out in the same comment (`while True: await asyncio.sleep(...); await self._handle.throttle_heartbeat(...)`) and runs the quality gates again before continuing the release. This second step IS a code change but it happens at *release time*, not at Story 6.5 implementation time — Story 6.5 documents the procedure; the maintainer executes it.

**And** the protocol explicitly notes the two cross-references it satisfies:
- It is the procedure `test_throttle_lifecycle.py:19-24` forward-references.
- It is the data point that resolves the TODO at `throttle.py:316-345` (seeded by Story 5.1 per its AC2 and AC8).

**And** the protocol explicitly notes its scope limits:
- It validates throttle + decoder responsiveness on real hardware, NOT turnout/sensor/route hardware behavior — those are covered by the integration tests in step 4 of the checklist (which run on the simulator for v1 and are deferred to maintainer judgment for hardware validation).
- It is performed once per release, not on every CI run — Headless-JMRI CI is Growth-deferred per `architecture.md:360-361`.

### AC5 — Doc cross-references existing files correctly and does NOT duplicate their content

**Given** `python_code/README.md` (Quickstart + Limitations + Migration table, owned by Stories 6.1/6.2/6.3), `python_code/examples/` (three example scripts owned by Story 6.4), `python_code/src/pyjmri/throttle.py` (keep-alive TODO at lines 316-345 owned by Story 5.1), `python_code/tests/integration/test_long_run.py` (long-run gate owned by Story 3.4), `python_code/tests/integration/test_throttle_lifecycle.py` (cross-reference at lines 19-24 owned by Story 5.3), `python_code/pyproject.toml` (version field, dev dependencies, pytest markers)
**When** `CONTRIBUTING.md` references any of these
**Then** the reference uses a conceptual phrase like "see the Quickstart in `README.md`" or "the comment block at `throttle.py:316-345`", NOT a markdown anchor link like `[Quickstart](README.md#quickstart)` (anchor-link discipline from Story 6.3).

**And** content already canonical elsewhere is NOT re-stated:
- The Quickstart script is in `README.md` — CONTRIBUTING.md does not duplicate it.
- The Limitations content is in `README.md` — CONTRIBUTING.md may reference it ("see Limitations in `README.md` for the open-loop caveat that applies to the hardware validation step") but does not restate the limitations.
- The Jython migration table is in `README.md` — CONTRIBUTING.md does not reference it (irrelevant to maintainer / release).
- The simulator-vs-hardware caveat is documented in `examples/back_and_forth.py` and `examples/multi_train_session.py` docstrings — CONTRIBUTING.md notes "the example docstrings cover the simulator/hardware split for example-script users" and does not repeat it.

**And** the doc DOES reproduce one thing that is also in pyproject.toml: the list of `[project].dependencies` and `[dependency-groups].dev` is mentioned in passing in the developer-setup section (one-paragraph "the runtime deps are `httpx` and `websockets`; dev adds `mypy`, `ruff`, `pytest`, `pytest-asyncio`, `psutil`, `twine`, `ipykernel`") — this is a developer-onboarding hint, not a contract; `pyproject.toml` remains the source of truth.

### AC6 — Markdownlint-clean and polish discipline (carries Stories 6.1/6.2/6.3/6.4 polish discipline)

**Given** memory `feedback_polish_matters.md` and the markdownlint-style self-scan that Stories 6.1, 6.2, 6.3, and 6.4 all applied
**When** `CONTRIBUTING.md` is written
**Then**:

1. **Heading levels increment cleanly.** H1 (the doc title) → H2 (the four main sections + Release checklist) → H3 (sub-sections within Release checklist or within the hardware-mode protocol) → H4 (any `Why X?` explanatory blocks). Never jump from H2 to H4.
2. **No `**Why X?**` italics-as-heading lines.** Use `#### Why X?` H4 headings (the pattern Story 6.3 and 6.4's Dev Notes established). Markdownlint rule MD036.
3. **No trailing whitespace** on any line. No tab characters. No double spaces between sentences (single-space convention).
4. **Fenced code blocks have language tags** where the language matters: `bash` for shell commands, `python` for Python snippets, `toml` for TOML, `text` for plain output. Markdownlint rule MD040.
5. **Lists use consistent markers.** `-` for unordered (the convention in this repo's existing markdown — confirm by inspection of `README.md`), `1.` / `2.` etc. for ordered. No mixed `*` / `-` within the same list.
6. **No placeholder lines.** No `*(fill in later)*`, no `TODO`, no `TBD` in the final doc — every section is complete at story-done time. The hardware-mode protocol's "if the operator finds X, then do Y" branches are documented in full (both branches), not deferred.
7. **Self-scan THIS story file** before declaring done — same MD036 etc. scan applied to the story file itself.

### AC7 — Acceptance check: a contributor and a maintainer each get what they need

**Given** the doc is read by two different audiences
**When** the document is reviewed
**Then**:

1. **A new contributor** (someone who has never opened the repo before) can: (a) install dependencies with `uv sync`, (b) run unit tests with the documented command, (c) understand why integration tests are not on CI and what their PR responsibility is, (d) file a useful issue or PR.
2. **The maintainer (Mikey, or a future maintainer)** can: (a) read the release checklist top-to-bottom and execute every step without ambiguity, (b) know exactly what to record in release notes, (c) perform the hardware-mode validation and know how to update the throttle.py keep-alive TODO based on the observation, (d) publish to PyPI and push the git tag.

**And** if either audience would have to ask "what does X mean?" or "where is Y?" — that is a doc bug to fix before declaring done. (The dev agent obviously can't ask these questions itself; the test is the dev re-reading the doc with each persona in mind. A self-scan, same rigor as the markdownlint scan.)

## Tasks / Subtasks

- [x] **Task 1 — Verify the state of the world before authoring** (AC: 1, 2, 4, 5)
  - [x] Confirm `python_code/CONTRIBUTING.md` does not yet exist: `test -f python_code/CONTRIBUTING.md && echo EXISTS || echo MISSING` → expect `MISSING`.
  - [x] Re-read the current `python_code/README.md` (lines 1-128) to confirm exact section headings ("Quickstart", "Limitations", "Migrating from Jython") and avoid restating their content.
  - [x] Re-read `python_code/pyproject.toml` to confirm the dependency-group listing, `[tool.pytest.ini_options].markers` (which should include `integration` and `slow`), and current `[project].version` (expected `0.1.0` at story-authoring time).
  - [x] Open `python_code/src/pyjmri/throttle.py:316-345` and confirm the inline comment block describing the no-op stub and the activation recipe. CONTRIBUTING.md's AC4 references this comment by file path and line range.
  - [x] Open `python_code/tests/integration/test_long_run.py:1-40, 90-115, 178-220` and confirm: the `--duration=3600` option, the `PYJMRI_LONG_RUN_DURATION` env-var equivalent, the summary-line format printed on success (`pyjmri long-run: duration=Ns disconnects=N reconnects=N rss_delta=X.XMB fd_delta=N task_delta=N status=PASS`). CONTRIBUTING.md's release checklist step 5 quotes this format.
  - [x] Open `python_code/tests/integration/test_throttle_lifecycle.py:1-30` and confirm the module docstring forward-references CONTRIBUTING.md's hardware-mode protocol. AC4 satisfies this forward-reference.
  - [x] Verify the CI workflow lives at `.github/workflows/ci.yml` (repo root, NOT under python_code/) and runs the matrix `[ubuntu-latest, macos-latest] × ['3.11', '3.12', '3.13']` with `paths: ['python_code/**', '.github/workflows/ci.yml']`. CONTRIBUTING.md's "integration-tests-local-only" section reflects this exact scope.
  - [x] Confirm `twine` IS in `[dependency-groups].dev` (used in release checklist step 9). It is at `pyproject.toml:32` (actually `pyproject.toml:28` in the current file — minor drift; non-blocking).

- [x] **Task 2 — Draft the developer-setup, integration-policy, and how-to-run-integration sections** (AC: 1, 5, 6)
  - [x] Write the H1 title `# Contributing to pyjmri` and the one-paragraph intro (≤4 sentences) positioning the doc as maintainer-focused with a pointer to README for end-users.
  - [x] Write H2 `## Developer setup` covering: `uv sync`, Python version verification, the four quality-gate commands (each in its own fenced `bash` block), and the post-Story-6.4 unit-test baseline (411 passed, 22 deselected).
  - [x] Write H2 `## Testing policy: integration tests are local-only` explaining the v1 policy, citing the CI workflow's `pytest -m "not integration"` invocation, naming Headless-JMRI CI as Growth-deferred, and stating the PR responsibility (contributor runs unit tests; maintainer runs integration tests at release time).
  - [x] Write H2 `## Running integration tests locally` with the pre-conditions (JMRI 5.14+ at `localhost:12080`, basement-or-equivalent layout, conftest's skip-on-absence) and the three invocation forms (`pytest tests/integration/`, `pytest -m integration`, `pytest -m "integration and not slow"`). DO NOT include the long-run invocation here; that's release-checklist step 5.
  - [x] Cross-link to README for end-user docs ("End users should read `README.md`'s Quickstart and Limitations sections; this doc assumes you are maintaining or contributing to the library, not using it."). No markdown anchor links.

- [x] **Task 3 — Draft the release checklist H2 section with the 9 numbered steps** (AC: 2, 3, 5, 6)
  - [x] Write H2 `## Release checklist` with a one-paragraph preamble explaining: this is the pre-release discipline; every step must produce evidence (command output or physical observation); steps run in order; a failure at any step halts the release until fixed.
  - [x] For each of the 9 steps (per AC2), use the format: `N. **Short title** — purpose.` followed by a fenced `bash` block of the copy-paste command, then an `Expected: ...` / `Failure mode: ...` line. For physical-action steps (step 6), the fenced block is replaced with a forward-reference to the dedicated H2 section.
  - [x] Step 1: ruff check + ruff format --check, separate fenced blocks for each command, expected outputs as observed in Story 6.4 completion notes (`All checks passed!` and `N files already formatted`).
  - [x] Step 2: mypy --strict src/pyjmri and mypy --strict examples/ — separate blocks; baseline counts (20 source files, 3 source files) from Story 6.4.
  - [x] Step 3: pytest -m "not integration" with the 411/22 baseline.
  - [x] Step 4: integration suite invocation. Recommendation per AC2: use `pytest -m "integration and not slow"` here so step 5 owns the long-run gate; explain the choice in 1-2 sentences.
  - [x] Step 5: long-run test with `--duration=3600 -s` flag. Quote the summary-line format verbatim. Note the env-var alternative (`PYJMRI_LONG_RUN_DURATION=3600`).
  - [x] Step 6: forward-reference to the hardware-mode sub-section (AC4 / Task 4). The numbered step itself is one line that says "Perform the hardware-mode throttle validation procedure (see the next section)."
  - [x] Step 7: version bump in pyproject.toml. Show the literal field path `[project].version`, plus the commit-subject convention `Bump version to X.Y.Z`.
  - [x] Step 8: release notes — content list (JMRI version, long-run summary, keep-alive outcome). Recommend `python_code/RELEASES.md` as the location but do NOT create it; note that v1 release notes can be free-form.
  - [x] Step 9: `uv build`, `uv run --no-sync twine check dist/*`, `uv publish`, `git tag vX.Y.Z && git push origin vX.Y.Z`. Each command in its own fenced block.
  - [x] After step 9, write a 3–5 sentence "After publish" paragraph: confirm `https://pypi.org/project/pyjmri/` shows the new version; smoke-install in a fresh venv (`uv add pyjmri` in a scratch directory) and re-run the Quickstart; close out the release notes with a "Published 20YY-MM-DD" line.

- [x] **Task 4 — Draft the Hardware-mode throttle validation H2/H3 sub-section** (AC: 4, 5, 6)
  - [x] Write H2 `## Hardware-mode throttle validation` immediately after the release checklist section. Open with a one-paragraph preamble explaining: this is the procedure that release-checklist step 6 references; it runs against real NCE hardware (not the simulator); Story 5.3's simulator tests cover library plumbing only.
  - [x] H3 `### Setup` — operator pre-conditions (JMRI 5.14+ talking to real NCE, layout powered, known-responsive loco on rails at documented DCC address, clear path in both directions).
  - [x] H3 `### Drive script` — the inline runnable Python snippet for AC4 step 2 (acquire → forward → reverse → function toggle → stop → release). The snippet is fenced as `python`, ≤30 lines including imports and `asyncio.run`. Snippet uses CLI args for `--dcc` and `--url` (with basement defaults) so the operator can adapt without editing the file.
  - [x] H3 `### Visual verification` — the three PASS/FAIL observations (forward motion, reverse motion, function-bit effect). Rendered as a bulleted list of observations to record.
  - [x] H3 `### Keep-alive observation` — the second inline runnable snippet for AC4 step 4 (acquire → stop → sleep 30 s → command → observe). Also ≤30 lines. Snippet uses the 30 s default but documents the formula (2× `throttle_keepalive_interval`, currently 15 s default per `_protocols.py`).
  - [x] H3 `### Recording the result` — the two recording actions (release notes; throttle.py:316-345 comment). For the throttle.py comment update, document the format of the new comment ("Confirmed [necessary/unnecessary] on JMRI X.Y / NCE [hardware identifier] / 20YY-MM-DD by [maintainer]."). For the "if drops, activate the body" branch, point at the inline-comment recipe at throttle.py:329-336 and require re-running the four quality gates.
  - [x] H3 `### Scope` — what this procedure covers (throttle + decoder responsiveness) and what it does NOT cover (turnout/sensor/route hardware validation — those are the maintainer's judgment call per release).

- [x] **Task 5 — Quality gates + render-check + final read-through** (AC: 6, 7)
  - [x] Markdownlint scan of `CONTRIBUTING.md` (MD036, MD040, MD001, no trailing whitespace, no tabs, no double spaces) — clean.
  - [x] Markdownlint scan of THIS story file — clean.
  - [x] Two-persona read-through completed (new contributor / maintainer at release time); no ambiguity gaps surfaced.
  - [x] No `(fill in later)`, `TODO`, `TBD`, or placeholder text in the doc (the two "TODO" hits are references to the throttle.py comment block by name, not placeholders in CONTRIBUTING.md).
  - [x] Every tool invocation in the doc uses `uv run --no-sync`; `uv build`, `uv sync`, `uv publish`, `uv add` correctly stand alone.
  - [x] No markdown anchor links into other docs; only conceptual phrases.

- [x] **Task 6 — File List + Completion Notes + Status update** (AC: 1, 2, 4, 7)
  - [x] Update File List: 1 new file (`python_code/CONTRIBUTING.md`), 1 modified story file, 1 modified `sprint-status.yaml`.
  - [x] Completion Notes updated below.
  - [x] Change Log entry added.
  - [x] Status set to `review`.
  - [x] Final-gate quality checks re-run; unchanged baseline (`ruff check` clean, `ruff format --check` clean, `mypy --strict src/pyjmri` 20 files clean, `mypy --strict examples/` 3 files clean, `pytest -m "not integration"` 411 passed / 22 deselected).

### Senior Developer Review (AI)

**Review date:** 2026-05-25
**Review outcome:** Changes Requested
**Model:** Claude Sonnet 4.6 (different from implementing model Opus 4.7 ✓)
**Layers:** Blind Hunter · Edge Case Hunter · Acceptance Auditor

### Review Findings

**Patch items — must be resolved before `done`:**

- [x] [Review][Patch] release_drive.py: direction reversal at full speed — no zero-speed waypoint between forward and reverse legs; some decoders fault or stall on mid-motion direction change, physical risk of runaway at direction transition. Add `await t.set_speed(0.0, forward=True)` + brief `asyncio.sleep(2)` before the reverse leg, OR add a prose warning about momentum CV 3/4. [source: blind+edge] [`python_code/CONTRIBUTING.md`, Drive script section] — **Fixed: inserted `set_speed(0.0)` + `sleep(3)` stop between forward and reverse legs.**
- [x] [Review][Patch] release_drive.py: F0 left ON (True) when script exits — headlight stays on after validation run; if headlight was already on before the test, `set_function(0, True)` produces no visible change and makes the "function-bit effect" observation meaningless. Add `await t.set_function(0, False)` before the final `set_speed(0.0)` call, or add a pre-condition note "ensure headlight is OFF before running this script." [source: blind] [`python_code/CONTRIBUTING.md`, Drive script section] — **Fixed: added `set_function(0, False)` before final stop.**
- [x] [Review][Patch] Step 9: `dist/` not cleared before `uv build` — stale artifacts from prior builds stay in `dist/`; `twine check dist/*` passes on old clean wheels even if a new malformed wheel exists alongside them. Add `rm -rf dist/` (or instruct "delete any existing `dist/` contents") before the `uv build` command. [source: blind] [`python_code/CONTRIBUTING.md`, Release checklist step 9] — **Fixed: added `rm -rf dist/` before `uv build`.**
- [x] [Review][Patch] Keep-alive observation: no warning against Ctrl-C during the 30-second hold — interrupting the script mid-sleep drops the throttle session, producing a "loco does not respond" false negative that looks like a JMRI expiry. Add a prose note: "Do not interrupt the script during the 30-second wait — a cancelled script releases the throttle and produces a false 'JMRI dropped' result." [source: edge] [`python_code/CONTRIBUTING.md`, Keep-alive observation section] — **Fixed: warning sentence added after the `Run it:` block.**
- [x] [Review][Patch] Hardware validation: no sequencing guidance between release_drive.py and release_keepalive.py — if the second script is run immediately after the first, JMRI may reject the new throttle acquire on the same DCC address while the previous session's WS release is still in flight. Add a brief note: "Wait a few seconds after release_drive.py finishes before running release_keepalive.py." [source: edge] [`python_code/CONTRIBUTING.md`, Hardware-mode throttle validation] — **Fixed: sequencing note added at top of Keep-alive observation section.**
- [x] [Review][Patch] AC1: Reporting-issues content has no visible label — the paragraph is invisible to a contributor scanning document headings or structure; spec names it "Reporting issues" / "Filing a PR." Add a bold prefix label `**Reporting issues and filing PRs:**` as the paragraph opener (no new heading needed — keeps hierarchy clean). [source: auditor] [`python_code/CONTRIBUTING.md`, line 5] — **Fixed: bold label added.**
- [x] [Review][Patch] AC4: Scope section cross-reference to test_throttle_lifecycle.py omits line range `:19-24` — spec explicitly requires the line range. Change reference from bare filename to `test_throttle_lifecycle.py:19-24`. [source: auditor] [`python_code/CONTRIBUTING.md`, Scope section] — **Fixed: `:19-24` added to reference.**

**Deferred items:**

- [x] [Review][Defer] throttle_heartbeat raises NotImplementedError in keep-alive activation recipe [`python_code/src/pyjmri/throttle.py:329-336`, `client.py:575`] — deferred, pre-existing: the unimplemented method exists in throttle.py's comment recipe independently of this story; Story 6.5 references the recipe but does not own its correctness. A future story should either implement `throttle_heartbeat` or remove it from the recipe.
- [x] [Review][Defer] No TestPyPI gate before production publish [`python_code/CONTRIBUTING.md`, step 9] — deferred, editorial choice: first-publish risk is acknowledged; "yank the broken version" is documented as remediation. Story 6.6 may add a TestPyPI step.
- [x] [Review][Defer] 30s keep-alive hold may be insufficient on NCE PowerCab with longer idle-throttle timeout [`python_code/CONTRIBUTING.md`, Keep-alive observation] — deferred, design decision: 2× default interval is the specified rule; hardware-specific variance is out of scope for v1.
- [x] [Review][Defer] test_throttle_lifecycle.py line 21 "currently backlog" qualifier is stale [`python_code/tests/integration/test_throttle_lifecycle.py:21`] — deferred, pre-existing: explicitly deferred in Story 6.5 Dev Notes; cleanup is a future polish pass, out of scope for Story 6.5.
- [x] [Review][Defer] uv publish credentials not pre-validated before build step [`python_code/CONTRIBUTING.md`, step 9] — deferred, editorial: standard publish flow; missing-credential failure is late but not silent. Story 6.6 may add a credential check.

## Dev Notes

### Authoritative current state (verified 2026-05-25, post-Story-6.4-done)

Line numbers below reference state at the time this story was authored.

| Path | Status for Story 6.5 |
| --- | --- |
| `python_code/CONTRIBUTING.md` | **NEW** — verified absent at story-authoring time; dev creates fresh |
| `python_code/README.md` | UNCHANGED — Stories 6.1 (Quickstart), 6.2 (Limitations), 6.3 (Migration) own README content; Story 6.5 does NOT edit README |
| `python_code/pyproject.toml` | UNCHANGED — version stays at 0.1.0 (Story 6.6 bumps to 1.0.0 as part of release-checklist step 7); markers and dependencies unchanged |
| `python_code/src/pyjmri/` | UNCHANGED — including `throttle.py:316-345` keep-alive comment (release-time updates per AC4 step 5 are a maintainer responsibility executed when running the checklist, not part of this story's implementation) |
| `python_code/tests/` | UNCHANGED — no test additions or modifications |
| `python_code/examples/` | UNCHANGED — Story 6.4 owns this directory |
| `.github/workflows/ci.yml` | UNCHANGED — referenced by CONTRIBUTING.md's integration-policy section but not edited |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | MODIFIED — story 6-5 transitions `backlog` → `ready-for-dev` → `in-progress` → `review` |

### Cross-story dependencies and forward-references

| Story | Status | What it owns | How Story 6.5 uses it |
| --- | --- | --- | --- |
| Story 3.4 | done | `tests/integration/test_long_run.py` with `--duration=3600` and `PYJMRI_LONG_RUN_DURATION` env var; summary-line format `pyjmri long-run: duration=Ns disconnects=N reconnects=N rss_delta=X.XMB fd_delta=N task_delta=N status=PASS` | Release checklist step 5 quotes the invocation AND the summary-line format verbatim |
| Story 5.1 | done | `Throttle._keepalive` no-op stub at `throttle.py:339-344`; the inline comment block at `throttle.py:316-338` seeding the TODO with the activation recipe; `ClientConfig.throttle_keepalive_interval = 15.0` default | AC4 step 5 documents the procedure for updating this comment when an operator runs the keep-alive observation step. The 30 s held silence = 2× the 15 s default. |
| Story 5.3 | done | `test_throttle_lifecycle.py:19-24` forward-references CONTRIBUTING.md's release checklist for hardware-mode validation; module docstring at lines 1-30 documents the simulator/hardware split | AC4 produces the procedure those forward-references point at. After Story 6.5 lands, the forward-reference is no longer "currently backlog" — the dev should NOT edit those references (they live in test_throttle_lifecycle.py which Story 6.5 does not touch), but a future spot-check or comment-cleanup pass can drop the "currently backlog" parenthetical. That cleanup is OUT OF SCOPE for this story. |
| Story 6.1 | done | README Quickstart at `README.md:5-72` | CONTRIBUTING.md says "End users should read `README.md`'s Quickstart" — does NOT restate it |
| Story 6.2 | done | README Limitations at `README.md:74-100` | CONTRIBUTING.md may reference Limitations in passing for the hardware-validation honesty context; does NOT restate |
| Story 6.3 | done | README Migration table at `README.md:102-128` | Not referenced by CONTRIBUTING.md (irrelevant to maintainer/release) |
| Story 6.4 | done | `examples/hello_jmri.py`, `examples/back_and_forth.py`, `examples/multi_train_session.py` | CONTRIBUTING.md may note that the example docstrings cover the simulator-vs-hardware split for end users; AC4's release-validation script is a NEW, smaller, hand-driven snippet (NOT one of the shipped examples, which loop forever) |
| Story 6.6 | backlog | The actual PyPI publish | CONTRIBUTING.md's release checklist is the procedure Story 6.6 will follow top-to-bottom |

### Authoritative API and tool references (verified 2026-05-25)

| Item | Source | Notes |
| --- | --- | --- |
| `uv sync` | `uv` docs + project convention | Creates `.venv/` with runtime + dev deps; editable install via src layout per `architecture.md:1237-1239` |
| `pytest -m "not integration"` | `pyproject.toml:50` markers + CI workflow | Standard CI invocation; post-Story-6.4 baseline 411 passed, 22 deselected |
| `pytest -m integration` | `pyproject.toml:50` markers | Runs all integration tests INCLUDING long-run (which is also `slow`) |
| `pytest -m "integration and not slow"` | marker boolean | Recommended for release-checklist step 4 to avoid duplicating step 5's long-run gate |
| `pytest tests/integration/test_long_run.py --duration=3600 -s` | `tests/integration/test_long_run.py:97-112` (custom option) | The pre-release one-hour gate; `-s` enables the summary print |
| `PYJMRI_LONG_RUN_DURATION=3600` | `tests/integration/test_long_run.py:100` | Env-var equivalent to `--duration=3600` |
| Long-run summary line | `tests/integration/test_long_run.py:316-317` (`print(...)`) | Format: `pyjmri long-run: duration=Ns disconnects=N reconnects=N rss_delta=X.XMB fd_delta=N task_delta=N status=PASS` |
| `ruff check` | `pyproject.toml:32-40` ruff config | Lint gate |
| `ruff format --check` | `pyproject.toml:32-40` ruff config | Format gate |
| `mypy --strict src/pyjmri` | `pyproject.toml:42-46` mypy config | Source type-check gate; post-6.4 baseline 20 files, 0 issues |
| `mypy --strict examples/` | new with Story 6.4 | Examples type-check gate; post-6.4 baseline 3 files, 0 issues |
| `uv build` | `architecture.md:1233-1234` | Produces sdist + wheel into `dist/` |
| `uv run --no-sync twine check dist/*` | `pyproject.toml:32` (twine in dev deps) | PyPI metadata pre-check |
| `uv publish` | `architecture.md:1235-1236` | v1 publish path; PyPI credentials via `UV_PUBLISH_TOKEN` env or `~/.pypirc` |
| `git tag vX.Y.Z` | git convention | Tag matches `[project].version` per Story 6.6 AC4 (`epics.md:1083-1086`) |
| Throttle keep-alive TODO | `python_code/src/pyjmri/throttle.py:316-345` | Multi-line comment block above `_keepalive`; the speculative "If Story 5.3 hardware observation shows..." block at lines 325-338 is the part the hardware-mode procedure replaces with the actual observation result |
| `ClientConfig.throttle_keepalive_interval` | `architecture.md:1375-1379`, `_protocols.py` default | Default 15.0 s; AC4 step 4 sleeps 2× this = 30 s |
| `Throttle.__aenter__` / `__aexit__` | `throttle.py:74-132` | Acquire/release lifecycle; AC4's drive script and keep-alive script both use `async with layout.throttle(...) as t:` |
| `Throttle.set_speed(value: float, *, forward: bool)` | `throttle.py:146` | Atomic speed + direction; `forward` keyword-only AND required |
| `Throttle.set_function(n: int, on: bool)` | `throttle.py:201` | Both positional |
| `Layout.throttle(dcc_address, *, long)` | `layout.py:240` | `long` keyword-only |
| `Client()` default URL | `client.py` Client.__init__ | `http://localhost:12080` |
| `JMRI 5.14+` requirement | `architecture.md:83`, `README.md:12` | The minimum supported JMRI version |

### Why the release-validation script is a NEW snippet (not `examples/back_and_forth.py`)

The shipped examples (Story 6.4) are autonomous — `back_and_forth.py` and `multi_train_session.py` loop forever, waiting on sensors to fire the next iteration. They are designed for "set it and forget it" demonstration runs. The release-validation script is the opposite: short, hand-driven, operator-supervised — start the loco, watch it for a few seconds, command direction change, watch it again, toggle a function, stop, release. The operator is supposed to watch the loco between commands; a `while True:` loop would not give the operator a controlled moment to record the PASS/FAIL observation.

The AC4 drive script is therefore inline in CONTRIBUTING.md as a runnable code block, not a reference to `examples/`. It is short enough (≤30 lines) to read at a glance and copy into a scratch file. This is consistent with the README's Quickstart pattern (Story 6.1) — short, inlined, copy-paste — rather than the `examples/` pattern (substantive, runnable as-is, autonomous).

### Why the release checklist's step 4 recommends `-m "integration and not slow"` over `-m integration`

The `slow` marker is intentionally separate from `integration` per Story 3.4's scope note (`test_long_run.py` carries both markers). `-m integration` selects both — which means `test_long_run.py` runs at its default 300 s duration (5-minute mode) as part of step 4, AND again at 3600 s in step 5. That's wasteful and noisy.

`-m "integration and not slow"` runs the full integration suite minus the long-run test. Step 5 then owns the long-run gate cleanly at the 1-hour duration. The maintainer who finishes step 5 has covered all integration tests at their appropriate cadence.

The doc explains this choice in one sentence below step 4 so a future maintainer who sees the marker boolean doesn't wonder why it isn't just `-m integration`.

### Why the hardware-mode procedure lives in CONTRIBUTING.md, not in a separate document

Three reasons:

1. **The protocol is release discipline, not test-suite documentation.** It is performed once per release by the maintainer, not on every CI run, not by contributors with their PRs. CONTRIBUTING.md is the maintainer's reference; the release checklist is its core. The hardware-mode procedure IS one step of that checklist (step 6) plus a supporting H2 sub-section.
2. **Story 5.3's forward-reference points here, not elsewhere.** `test_throttle_lifecycle.py:19-24` and `test_throttle_lifecycle.py:188` say "documented in `CONTRIBUTING.md`'s release checklist." Spawning a separate `HARDWARE-VALIDATION.md` would force changing that forward-reference (which Story 6.5 does not edit).
3. **Single-source release discipline.** A maintainer running the checklist should not need to context-switch into a second document for one step. The hardware-mode H2 sub-section is right below the checklist, in the same file, in scope.

### Why `RELEASES.md` is not created by this story

Release notes are a Story 6.6 (and Growth-deferred for the structured-changelog format) concern. Story 6.5 documents WHERE release notes go ("a `RELEASES.md` file at `python_code/RELEASES.md`, free-form for v1") and WHAT content goes in them (JMRI version tested, long-run summary line, keep-alive outcome) — but does not create the file. Creating the file before there is content to put in it would be a `(fill in later)` placeholder, which AC6 explicitly forbids. Story 6.6's release notes are the file's first content.

### Why `--no-sync` on every `uv run` invocation

Per memory `feedback_use_uv.md`: "Always use `uv run --no-sync <tool>` for pytest/mypy/ruff/python inside python_code/; never invoke tools directly." The `--no-sync` flag avoids `uv` re-resolving the lockfile on every tool invocation (which is slow and unnecessary once `uv sync` has been run once). The convention is uniform across the doc to avoid the reader-confusion of "sometimes with `--no-sync`, sometimes without — when do I use which?".

The exception is `uv build`, `uv sync`, `uv publish`, and `uv add` — these are themselves `uv` commands operating on the project state; they are not "run a tool" invocations. The doc shows them as `uv build`, `uv sync`, etc. — no `run --no-sync`.

### Architecture rules carried forward (apply verbatim)

- **Public-facing documentation discipline** per `architecture.md:918-934`: docstrings on public surface; tone "what + when to use it". CONTRIBUTING.md is maintainer-facing, not public-API-facing, so the docstring rule doesn't apply directly — but the "what + when to use it" tone applies to the release checklist's step descriptions ("when to run X, what success looks like").
- **No reinvention.** The four quality-gate commands, the long-run invocation, the throttle keep-alive interval, the integration-tests-local-only policy, the basement DCC defaults — every one of these is already documented somewhere in the codebase or the planning artifacts. CONTRIBUTING.md cites them; does not redefine them.
- **Forward-reference discipline.** Stories 5.1 (throttle.py TODO) and 5.3 (test_throttle_lifecycle.py docstring) wrote forward-references to "CONTRIBUTING.md's release checklist (Story 6.5, currently backlog)". Story 6.5 makes those references real. The dev does NOT need to update either of those source files — they continue to forward-reference the (now existing) CONTRIBUTING.md correctly, with the trivial cosmetic addition of a "(currently backlog)" parenthetical that became stale. Cleaning that parenthetical is OUT OF SCOPE for Story 6.5; deferred to a future polish pass.
- **`uv run --no-sync` everywhere** per memory `feedback_use_uv.md`. Every tool invocation in CONTRIBUTING.md uses this prefix.
- **Writable-paths discipline** per memory `feedback_writable_paths.md`: Story 6.5 writes only to `python_code/CONTRIBUTING.md` and `_bmad-output/`. No edits to `.jmri/` profiles, `jython/` scripts, `roster/`.

### Carry-forward learnings from Stories 6.1, 6.2, 6.3, 6.4

- **Scope discipline.** Each prior Epic-6 story owned exactly one slice of user-facing documentation. Story 6.5 owns `CONTRIBUTING.md` only. No edits to README, examples/, tests/, src/, pyproject.toml, or any other artifact's content.
- **Markdownlint discipline.** Pre-dev self-scan of THIS story file; post-author self-scan of `CONTRIBUTING.md`. Use `#### Why X?` H4 headings (this story's "Why ..." Dev Notes blocks demonstrate the pattern), not `**Why X?**` italics. Fenced blocks always have language tags.
- **No anchor-link rot.** Stories 6.1, 6.2, 6.3 all wrote cross-references using conceptual phrases rather than markdown anchor links. Same discipline here: "see the Quickstart in `README.md`", never `[Quickstart](README.md#quickstart)`.
- **Polish before declaring done** (memory `feedback_polish_matters.md`). Stories 6.3 and 6.4 each made small post-implementation polish edits surfaced by markdownlint scan. Plan time for the same pass here.
- **PRD-vs-real-code drift discipline** (Story 6.3 and 6.4 each found drift). Story 6.5 references commands and file paths that the dev should re-verify at Task 1 — drift between this story's claims and the real repo state is a story-file bug, not a dev-execution surprise.
- **Quality-gate baseline.** Post-Story-6.4 baseline is **411 unit tests passed, 22 deselected**; `ruff check`, `ruff format --check`, `mypy --strict src/pyjmri`, `mypy --strict examples/` all clean. Story 6.5 confirms unchanged at Task 6 final-gate check because there are no Python file changes.
- **`uv run --no-sync` discipline** (memory `feedback_use_uv.md`). Every documented command in CONTRIBUTING.md uses this prefix for tool invocations (pytest/mypy/ruff/twine/python).

### Risks and mitigations

- **R1: Dev restates content already in README (Quickstart, Limitations, Migration table) inside CONTRIBUTING.md, creating drift between the two docs.** Mitigation: AC5 explicitly forbids restating; Task 2 says "cross-link to README"; Dev Notes "Cross-story dependencies" table lists what each prior Epic-6 story owns so the dev knows what to NOT touch.
- **R2: Release checklist contains aspirational prose ("ensure everything is in good shape") instead of concrete commands.** Mitigation: AC3 explicitly forbids this pattern and gives the three acceptable forms (shell command / physical action / recording requirement); Task 3 templates each step as `**Short title** — purpose / fenced block / expected / failure mode`.
- **R3: Hardware-mode procedure is too vague for an operator to execute without re-deriving steps.** Mitigation: AC4 spells out 5 numbered operator instructions; Task 4 produces inline runnable Python snippets for both the drive script and the keep-alive observation script; the H3 sub-headings within "Hardware-mode throttle validation" give the operator a top-to-bottom procedure with no judgment calls except the documented PASS/FAIL observations.
- **R4: Dev creates `python_code/RELEASES.md` as a placeholder.** Mitigation: explicitly forbidden by AC6 (no placeholders) and by the "Why `RELEASES.md` is not created" Dev Notes block. Step 8 of the checklist names the file path but the file itself is created at first release (Story 6.6).
- **R5: Dev edits `throttle.py:316-345` keep-alive comment as part of Story 6.5.** Mitigation: AC4 step 5 is explicit that the comment update is an OPERATOR action at RELEASE TIME, not a dev action at story time. The Authoritative state table at the top of Dev Notes also lists `python_code/src/pyjmri/` as UNCHANGED.
- **R6: Dev edits `test_throttle_lifecycle.py:19-24` to remove the "currently backlog" parenthetical from the Story 5.3 forward-reference.** Mitigation: "Forward-reference discipline" Dev Notes block explicitly defers this to a future polish pass; the parenthetical staleness is cosmetic and not blocking; Story 6.5's scope is CONTRIBUTING.md only.
- **R7: Dev forgets `uv run --no-sync` on a documented command (uses bare `pytest` or `mypy` instead).** Mitigation: AC2 explicitly requires the prefix; Task 5 includes a verification step ("Verify every command in the doc uses `uv run --no-sync` for tool invocations"); memory `feedback_use_uv.md` is the canonical rule.
- **R8: Dev wires `pytest -m integration` for step 4 instead of `pytest -m "integration and not slow"`, causing the long-run test to run twice (at 5 min in step 4, at 1 hr in step 5).** Mitigation: AC2 step 4 recommends the marker-boolean form; "Why the release checklist's step 4 recommends..." Dev Notes block explains the rationale; if the dev makes a different choice it gets documented in Completion Notes per Task 6.

### References

- `_bmad-output/planning-artifacts/epics.md:1033-1057` — Epic 6 Story 6.5 acceptance criteria (this story's source).
- `_bmad-output/planning-artifacts/epics.md:926-928` — Epic 6 intro framing.
- `_bmad-output/planning-artifacts/prd.md:816-822` — FR38–FR44 (distribution/docs/tooling); Story 6.5 directly addresses the integration-tests-local-only stance and the release-discipline FR-equivalents.
- `_bmad-output/planning-artifacts/architecture.md:142` — single-line CONTRIBUTING.md description.
- `_bmad-output/planning-artifacts/architecture.md:243` — documentation deliverables note.
- `_bmad-output/planning-artifacts/architecture.md:360-361` — Headless-JMRI CI deferred to Growth.
- `_bmad-output/planning-artifacts/architecture.md:540-558` — Concurrency Model; keep-alive coroutine architecture context.
- `_bmad-output/planning-artifacts/architecture.md:691-707` — Test Strategy: integration tests local-only, long-run test as separate pre-release target.
- `_bmad-output/planning-artifacts/architecture.md:701` — `CONTRIBUTING.md` (Epic 6) will reference the long-run test as part of the release checklist.
- `_bmad-output/planning-artifacts/architecture.md:918-934` — Documentation Patterns (docstring tone applies analogously to maintainer docs).
- `_bmad-output/planning-artifacts/architecture.md:924` — `CONTRIBUTING.md` keep-alive cross-reference.
- `_bmad-output/planning-artifacts/architecture.md:970-985` — Project structure showing `CONTRIBUTING.md` at `python_code/CONTRIBUTING.md`.
- `_bmad-output/planning-artifacts/architecture.md:1144-1158` — Distribution/Docs/Tooling cross-reference.
- `_bmad-output/planning-artifacts/architecture.md:1230-1244` — Build & Distribution; `uv build` / `uv publish` / `uv sync` canonical.
- `_bmad-output/planning-artifacts/architecture.md:1373-1389` — Throttle keep-alive default interval (15.0 s); the rationale for the 30-s held-silence wait.
- `_bmad-output/implementation-artifacts/3-4-parameterized-unattended-stability-test-5-min-default-1-hour-optional-pre-release.md` — Done. Source for `--duration=3600`, `PYJMRI_LONG_RUN_DURATION` env var, summary-line format.
- `_bmad-output/implementation-artifacts/5-1-throttle-async-context-manager-acquire-release-lifecycle-keep-alive-supervision.md` — Done. Source for the keep-alive TODO seed at `throttle.py:316-345` and the `ClientConfig.throttle_keepalive_interval = 15.0` default.
- `_bmad-output/implementation-artifacts/5-3-multi-throttle-integration-test-plumbing-on-simulator-physical-correctness-on-hardware.md` — Done. Source for the forward-reference at `test_throttle_lifecycle.py:19-24` that Story 6.5 satisfies.
- `_bmad-output/implementation-artifacts/6-1-readme-5-minute-quickstart.md` — Done. Source for the README Quickstart that CONTRIBUTING.md points end-users at.
- `_bmad-output/implementation-artifacts/6-2-readme-limitations-section.md` — Done. Source for the README Limitations CONTRIBUTING.md references in the hardware-validation honesty context.
- `_bmad-output/implementation-artifacts/6-3-readme-jython-to-pyjmri-migration-table.md` — Done. Source for the anchor-link-free cross-reference discipline.
- `_bmad-output/implementation-artifacts/6-4-three-shipped-examples-hello-jmri-py-back-and-forth-py-multi-train-session-py.md` — Done. Source for the quality-gate baselines (411 unit / 22 deselected / 20 mypy source / 3 mypy examples). Also the explanation of why the release-validation script is a NEW inline snippet rather than reusing the autonomous-loop examples.
- `python_code/README.md` — Current state (post-Story-6.4 done). Quickstart at lines 5-72; Limitations at lines 74-100; Migration table at lines 102-128. Story 6.5 does NOT edit any of these.
- `python_code/pyproject.toml` — Build config. Version `0.1.0`. Markers `integration` and `slow` at `[tool.pytest.ini_options].markers`. `twine` in `[dependency-groups].dev`. Story 6.5 does NOT edit.
- `python_code/src/pyjmri/throttle.py:316-345` — Keep-alive TODO comment block. AC4 step 5 documents the procedure for updating this at release time; Story 6.5 does NOT edit it.
- `python_code/tests/integration/test_long_run.py:1-40, 97-115, 178-220, 316-317` — Long-run test invocation, duration parameter, summary-line format.
- `python_code/tests/integration/test_throttle_lifecycle.py:1-30` — Module docstring forward-referencing CONTRIBUTING.md's release checklist (currently backlog at the time it was written; Story 6.5 makes the reference live).
- `.github/workflows/ci.yml` — CI matrix and `paths` scoping; CONTRIBUTING.md's integration-tests-local-only section mirrors this exactly.
- Memory: `feedback_use_uv.md` — `uv run --no-sync` for all tool invocations.
- Memory: `feedback_polish_matters.md` — markdownlint self-scan before declaring done; `#### Why X?` H4 headings, not `**Why X?**` italics.
- Memory: `feedback_writable_paths.md` — only `python_code/` and `_bmad-output/` writable.
- Memory: `feedback_github_actions_help.md` — Mikey is new to GitHub Actions; the integration-policy section should be unambiguous about WHY integration tests are excluded from CI and what the CI matrix actually covers.
- Memory: `project_throttle_simulator_blindspot.md` — NCE simulator has no virtual loco; the hardware-mode procedure exists because of this gap.
- Memory: `project_nce_open_loop.md` — NCE is open-loop; the hardware-mode procedure's "visual verification" step exists because there is no electronic signal to assert against.
- Memory: `project_jmri_state_model.md` — JMRI reports last-commanded, not observed; reinforces the visual-confirmation discipline in the hardware-mode procedure.
- Memory: `project_pyjmri_status.md` — implementation status snapshot (post-Story-6.4); confirms Epics 1–5 done and Epic 6 in-progress.
- Memory: `project_pyjmri_architecture.md` — canonical pyjmri architecture lives in `_bmad-output/planning-artifacts/architecture.md` (the references above resolve there).

### Project Structure Notes

- ALL changes live in `python_code/CONTRIBUTING.md` (one new file) and `_bmad-output/implementation-artifacts/` (this story file + sprint-status.yaml).
- NO Python file changes (no `src/`, no `tests/`, no `examples/`).
- NO `pyproject.toml`, `README.md`, or `LICENSE` changes.
- NO `.github/workflows/` changes.
- NO changes to `.jmri/` profiles, `jython/` scripts, `roster/` directory, or `roster.xml` (memory `feedback_writable_paths.md`).
- The cross-references in `python_code/src/pyjmri/throttle.py:316-345` and `python_code/tests/integration/test_throttle_lifecycle.py:19-24` will remain forward-references with a now-stale "(currently backlog)" parenthetical. Cleaning the parenthetical is OUT OF SCOPE for Story 6.5 and is deferred to a future polish pass.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (1M context)

### Debug Log References

None — documentation-only story; no debugging required.

### Completion Notes List

- **Single-file delivery.** Created `python_code/CONTRIBUTING.md` (330 lines after edits, within the 250–400 line target). No other content changes; no `src/`, no `tests/`, no `examples/`, no `pyproject.toml`, no `README.md` edits. Matches Story 6.5's documentation-only scope.
- **AC1 satisfied.** Four required sections present in order: Developer setup (line 7), Testing policy: integration tests are local-only (line 47), Running integration tests locally (line 62), Release checklist (line 88). Intro paragraph and Reporting-issues paragraph both at the top of the doc (the Reporting-issues paragraph is rendered without its own heading to avoid an H1→H3 jump; AC1 only required the paragraph to exist, not to have a sub-heading).
- **AC2 satisfied.** Release checklist has the 9 specified steps in order, each with copy-paste-ready shell commands in fenced `bash` blocks, expected outputs, and failure-mode descriptions. Step 6 forward-references the Hardware-mode section per the recommended template. Step 4 uses `pytest -m "integration and not slow"` per the recommendation (avoids double-running the long-run test in steps 4 and 5).
- **AC3 satisfied.** Every step is either a copy-paste shell command, a physical action with a recording requirement, or a forward-reference to a procedure that itself satisfies the rule. No "verify everything is in good shape" prose anywhere.
- **AC4 satisfied.** Hardware-mode throttle validation is its own H2 section with 5 H3 sub-sections (Setup, Drive script, Visual verification, Keep-alive observation, Recording the result, plus Scope). Two inline runnable Python snippets are provided (`release_drive.py` 22 lines, `release_keepalive.py` 19 lines) — both ≤30 lines including imports and `asyncio.run`. Snippets use argparse for `--dcc` and `--url` with basement defaults. The recording step documents both the release-notes line format and the throttle.py:316-345 comment-update format ("Confirmed [necessary/unnecessary] on JMRI X.Y / NCE [hardware identifier] / 20YY-MM-DD by [maintainer]."). The "if JMRI drops the throttle" branch points at the inline-comment recipe at throttle.py:329-336 and requires re-running the four quality gates before continuing.
- **AC5 satisfied.** No restated Quickstart, Limitations, or Migration content. References to README, throttle.py, test_long_run.py, test_throttle_lifecycle.py, and pyproject.toml are conceptual ("see the Quickstart in `README.md`", "the comment block at `throttle.py:316-345`") — no markdown anchor links. The dev-deps list is mentioned in passing in the Developer-setup section as onboarding context; pyproject.toml remains the source of truth.
- **AC6 satisfied.** Markdownlint scan clean on both `CONTRIBUTING.md` and this story file: no MD036 (bold-as-heading), no MD040 (every opening fence has a language tag), no MD001 (heading levels increment cleanly H1→H2→H3, no H4 in the final doc since the one would-be H4 "Why --no-sync" block was inlined as prose to keep the hierarchy clean). No trailing whitespace, no tabs, no double spaces, no `TODO`/`TBD`/`(fill in later)` placeholders. The two "TODO" string matches in the doc are deliberate references to the throttle.py comment block by name (not unresolved placeholders in CONTRIBUTING.md itself).
- **AC7 satisfied.** Two-persona read-through completed:
  - *New contributor* path: `uv sync` → `uv run --no-sync python --version` → four quality-gate commands → "Reporting issues" paragraph for GitHub Issues URL and PR expectations. No ambiguity gaps.
  - *Maintainer at release time* path: nine numbered steps with copy-paste commands; step 6 cleanly forward-references the Hardware-mode procedure; the procedure's 5 sub-steps walk an operator from setup through recording without judgment calls beyond the documented PASS/FAIL observations.
- **Polish discipline applied.** Self-scan against this story file's AC6 rules and memory `feedback_polish_matters.md`. Fixed two issues during draft review: (a) an H1→H3 heading jump caused by an over-eager "Reporting issues" sub-heading (inlined as prose under the intro); (b) a broken argparse pattern in the drive-script snippet (`p.dcc if hasattr(p, "dcc") else p.parse_args().dcc` was nonsense — replaced with the standard `args = p.parse_args(); ... main(args.dcc, args.url)` form).
- **Deviations from story recommendation.** None of substance. One reasonable judgment call: AC2 step 4 expected wording was "deselected count equals 1" but the actual deselected count under `pytest -m "integration and not slow"` is 412 (411 unit tests + 1 long-run test). Rewrote that expectation as "every selected integration test passes. The one `slow` integration test (`test_long_run.py`) is excluded by the `and not slow` clause and runs separately in step 5." This is more accurate for a maintainer reading the output and avoids a surprise about the actual deselected count.
- **Forward-references left as-is.** Per Story 6.5's Dev Notes, the "(currently backlog)" parenthetical at `test_throttle_lifecycle.py:21` is now stale (Story 6.5 made the reference live) but cleaning it is OUT OF SCOPE for this story. Deferred to a future polish pass.
- **Final-gate quality check.** All five gates green at unchanged baseline: `ruff check` clean, `ruff format --check` 56 files already formatted, `mypy --strict src/pyjmri` 20 source files clean, `mypy --strict examples/` 3 source files clean, `pytest -m "not integration"` 411 passed / 22 deselected.

### File List

**New files:**

- `python_code/CONTRIBUTING.md` (330 lines)

**Modified files:**

- `_bmad-output/implementation-artifacts/6-5-contributing-md-with-release-checklist.md` (story file — Tasks/Subtasks checkboxes, Dev Agent Record, File List, Change Log, Status)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (story 6-5 transitioned `ready-for-dev` → `in-progress` → `review`)

## Change Log

| Date | Author | Summary |
| --- | --- | --- |
| 2026-05-25 | Mikey + dev agent (Claude Opus 4.7) | Implemented Story 6.5: created `python_code/CONTRIBUTING.md` with developer-setup, integration-tests-local-only policy, integration-test invocations, the 9-step release checklist, and the hardware-mode throttle validation procedure (including the two inline operator snippets that resolve the keep-alive TODO at `throttle.py:316-345`). No Python file changes; quality gates unchanged at post-Story-6.4 baseline (411 passed / 22 deselected, ruff clean, mypy strict clean on src and examples). Status: review. |

