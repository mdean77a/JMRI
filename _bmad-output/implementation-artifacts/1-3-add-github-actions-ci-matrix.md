# Story 1.3: Add GitHub Actions CI matrix

Status: ready-for-dev

## Story

As a library developer,
I want a GitHub Actions workflow that runs `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest -m "not integration"` on every push across macOS and Linux × Python 3.11/3.12/3.13, scoped to `python_code/**` changes,
so that regressions are caught before merge and routine commits to JMRI panel XML, roster, or Jython files do not trigger CI churn.

## Acceptance Criteria

1. **Matrix produces six parallel jobs.** Given the quality gates from Story 1.2, when `.github/workflows/ci.yml` is committed at the JMRI repo root with a matrix of `os: [macos-latest, ubuntu-latest]` × `python-version: ['3.11', '3.12', '3.13']`, then every qualifying push triggers six parallel CI jobs.
2. **All four quality-gate steps pass against the current scaffold.** Given a CI job is running, when the workflow installs `uv`, runs `uv sync` inside `python_code/`, then sequentially runs `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src/pyjmri`, and `uv run pytest -m "not integration"`, then all four steps complete with exit status 0.
3. **Windows is absent from the matrix (NFR9).** Given the workflow definition, when a reviewer inspects the matrix, then Windows is not present.
4. **Path-scoped triggers.** Given the workflow lives at the JMRI repo root but pyjmri sources live only under `python_code/`, when the workflow's `on:` triggers are configured, then the workflow runs only on commits that touch `python_code/**` or `.github/workflows/ci.yml` itself, and routine commits to JMRI panel XML (`*.jmri/`), `roster.xml`, `roster/`, or `jython/` files do not trigger CI.
5. **Strict-violation regressions surface on the PR.** Given a future commit introduces a `mypy --strict` violation in `src/pyjmri/`, when CI runs, then the affected jobs fail and the failure is surfaced on the PR.

## Tasks / Subtasks

- [x] **Task 1: Create the workflow file at the JMRI repo root** (AC: #1, #2, #3, #4)
  - [x] Create directory `.github/workflows/` at the **JMRI repo root** (`/Users/jmichaeldean/JMRI/.github/workflows/`), **not** under `python_code/`. The workflow file lives at the repo root because GitHub Actions only reads `.github/workflows/*` from the repository's top-level directory.
  - [x] Create `.github/workflows/ci.yml` using the canonical content shown in §"Workflow file content (canonical)" below.
  - [x] Verify the YAML parses (locally validated via Ruby's `psych`; structural inspection confirmed 6 matrix combinations, 7 steps, both path triggers correct, `fail-fast: false`).

- [x] **Task 2: Configure the `on:` triggers with path scoping** (AC: #4)
  - [x] Trigger on both `push` and `pull_request`. The AC text emphasizes "push" but the last AC says "failure is surfaced on the PR" — both are needed.
  - [x] On both events, use a `paths:` filter listing exactly two patterns: `python_code/**` and `.github/workflows/ci.yml`. Anything else (panel XML, roster files, Jython scripts, README at repo root, etc.) must NOT trigger the workflow.
  - [x] Do **not** add `paths-ignore:` patterns for the JMRI assets — `paths:` is allowlist-style and already excludes everything not listed. Mixing the two on the same event is a YAML error.

- [x] **Task 3: Configure the matrix and runners** (AC: #1, #3)
  - [x] Set `strategy.matrix.os: [ubuntu-latest, macos-latest]` and `strategy.matrix.python-version: ['3.11', '3.12', '3.13']`. Six combinations × one job each = six parallel jobs.
  - [x] Set `strategy.fail-fast: false`. Default is `true`, which cancels the whole matrix on the first failure. We want full visibility of which OS/Python combos pass and which fail.
  - [x] Quote the Python versions as strings (`'3.11'`, not `3.11`). YAML coerces unquoted `3.10` → `3.1` (silently dropping the trailing zero); quoting future-proofs the matrix.
  - [x] Do **not** add `windows-latest` to the OS list — NFR9 explicitly excludes Windows from CI for v1.

- [x] **Task 4: Configure uv + Python install via `astral-sh/setup-uv`** (AC: #2)
  - [x] Use `astral-sh/setup-uv@v4` (Astral's first-party action, current stable as of 2026). Pin to `@v4` (major version), not `@main` (unpinned drift) and not `@v4.x.y` (over-pinning forces manual updates for security patches).
  - [x] Pass `python-version: ${{ matrix.python-version }}` to setup-uv. The action installs uv AND the requested Python version in one step; do NOT use `actions/setup-python@v5` separately.
  - [x] Enable cache: `enable-cache: true` and `cache-dependency-glob: "python_code/uv.lock"`. This caches `~/.cache/uv` keyed on the lockfile, so subsequent runs reuse downloads when the lockfile is unchanged.

- [x] **Task 5: Set the working directory** (AC: #2)
  - [x] Set `defaults.run.working-directory: python_code` at the workflow level (or at the job level — workflow level is fine since this is the only job). All `run:` steps execute inside `python_code/` without needing per-step `cd`.
  - [x] **Action steps** (`uses:`) are not affected by `defaults.run.working-directory` — they run from the repo root. This is fine for `actions/checkout` and `astral-sh/setup-uv`; the cache-dependency-glob path therefore must be `python_code/uv.lock` (repo-relative), not just `uv.lock`.

- [x] **Task 6: Add the four quality-gate steps** (AC: #2)
  - [x] Step 1: `uv sync` — installs runtime + dev dependencies from `uv.lock`. uv resolves them deterministically since the lockfile is committed.
  - [x] Step 2: `uv run ruff check` — no path args; ruff scans `python_code/` (the working dir). Matches AC #2 verbatim.
  - [x] Step 3: `uv run ruff format --check` — no path args; same scoping. Distinct step (not chained with `&&`) so failures pinpoint which check broke.
  - [x] Step 4: `uv run mypy src/pyjmri` — explicit path; matches Story 1.2's local invocation contract.
  - [x] Step 5: `uv run pytest -m "not integration"` — relies on the marker registered in `pyproject.toml` and `testpaths = ["tests"]` for collection. Wrapped with the `|| ([ $? = 5 ] && echo "...")` exit-5 guard so the empty test tree doesn't fail CI on first push (auto-removes once Story 2.1+ lands real tests).
  - [x] Each step gets a `name:` field for readable logs.

- [ ] **Task 7: Push and verify on GitHub** (AC: #1, #2, #5)
  - [ ] Commit and push `.github/workflows/ci.yml` to a branch (or to `master`).
  - [ ] On GitHub Actions tab, confirm exactly six jobs appear in the workflow run.
  - [ ] Confirm all six jobs go green within a few minutes (cold cache run will be slowest; expect 1–3 min per job).
  - [ ] Verify path scoping: make a no-op edit to a JMRI panel XML or `roster.xml`, push, confirm CI does NOT trigger. Make a no-op edit under `python_code/` (e.g., add a trailing newline to `python_code/README.md`), push, confirm CI DOES trigger.
  - [ ] Verify regression detection (AC #5) by either: (a) deliberately introducing a transient mypy error in a feature branch (e.g., add a single `def f(x): return x` to `__init__.py` — missing annotations fail under strict mode), confirming the workflow fails, then reverting; or (b) trusting the green-on-clean run as sufficient evidence and noting AC #5 as verified-by-construction.

## Dev Notes

### Workflow file content (canonical)

This is the exact content to commit at `.github/workflows/ci.yml`. Copy verbatim — every line below is intentional. The annotations after each section explain *why* for a developer new to GitHub Actions.

```yaml
name: CI

on:
  push:
    paths:
      - 'python_code/**'
      - '.github/workflows/ci.yml'
  pull_request:
    paths:
      - 'python_code/**'
      - '.github/workflows/ci.yml'

defaults:
  run:
    working-directory: python_code

jobs:
  test:
    name: ${{ matrix.os }} / Python ${{ matrix.python-version }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ['3.11', '3.12', '3.13']
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Install uv and Python ${{ matrix.python-version }}
        uses: astral-sh/setup-uv@v4
        with:
          python-version: ${{ matrix.python-version }}
          enable-cache: true
          cache-dependency-glob: "python_code/uv.lock"

      - name: Install dependencies (uv sync)
        run: uv sync

      - name: Lint (ruff check)
        run: uv run ruff check

      - name: Format check (ruff format --check)
        run: uv run ruff format --check

      - name: Type check (mypy --strict)
        run: uv run mypy src/pyjmri

      - name: Unit tests (pytest -m "not integration")
        run: uv run pytest -m "not integration"
```

### Annotated walkthrough (for someone new to GitHub Actions)

| Line / block | What it does | Why this exact form |
|---|---|---|
| `name: CI` | Display name shown in the Actions tab. | Short and recognizable; appears on PR check runs. |
| `on: push: paths: [...]` and `on: pull_request: paths: [...]` | Restricts when the workflow fires. **Allowlist semantics**: only commits that change at least one file matching one of the listed patterns trigger the workflow. | AC #4. JMRI panel XML, roster, and Jython commits live elsewhere in the repo and would otherwise burn CI minutes for no reason. |
| `python_code/**` | Glob: any file under `python_code/`, any depth. | Catches `pyproject.toml`, `uv.lock`, `src/**`, `tests/**`, future additions. |
| `.github/workflows/ci.yml` | The workflow file itself. | Standard practice — editing the workflow re-runs it so the new logic actually takes effect. |
| `defaults.run.working-directory: python_code` | Every `run:` step starts in `python_code/`. | Saves repeating `cd python_code` on every step. Does not affect `uses:` steps; those still run from repo root. |
| `runs-on: ${{ matrix.os }}` | The VM image. `ubuntu-latest` and `macos-latest` are GitHub-hosted runners. | NFR9: macOS and Linux are first-class. |
| `strategy.fail-fast: false` | One failing job does not cancel the others. | Better diagnostics: see all six results, not just the first failure. |
| `strategy.matrix.python-version: ['3.11', '3.12', '3.13']` | Three Python versions. The values are quoted strings. | AC #1. Quoting prevents the YAML parser silently truncating `3.10` → `3.1` if a future maintainer adds it. |
| `actions/checkout@v4` | Clones the repo into the runner. | Required first step. v4 is the current stable; v3 is end-of-life. |
| `astral-sh/setup-uv@v4` | Astral's first-party action. Installs `uv`, then installs the requested Python via uv. | Replaces the older `setup-python` + `pip install uv` two-step. With `python-version` set, uv handles the Python install too — one tool, no version drift between the runner's Python and the project's Python. |
| `enable-cache: true` + `cache-dependency-glob` | Caches `~/.cache/uv` keyed on the lockfile hash. | Cold runs are the same speed; subsequent runs (lockfile unchanged) skip downloads. |
| `uv sync` | Installs runtime + dev deps from `uv.lock`. With `[dependency-groups] dev` (PEP 735), the dev group is included by default. | No `--frozen` flag needed; `uv sync` is already deterministic when `uv.lock` is committed. |
| Each quality-gate step is a separate `run:` | One check per step. | Failures pinpoint which gate broke (rather than `&& && && &&` chain that fails opaquely on whichever check fired first). |

### Architecture compliance checklist

| Architecture / PRD rule | Story 1.3 alignment |
|---|---|
| §Test Harness "Unit tests run in CI matrix: macOS-latest + ubuntu-latest × Python 3.11/3.12/3.13. Every push." | Six-job matrix in Task 3; triggers in Task 2 |
| §Test Harness "Integration tests run locally only for v1." | `pytest -m "not integration"` in Task 6 step 5 |
| §Test Harness "Headless-JMRI CI is a Growth-phase spike, not in scope here." | Workflow has no JMRI bootstrap step |
| §Project Structure shows `.github/workflows/ci.yml` at the `python_code/` root in the *project structure diagram* | **Diagram is wrong-by-design here** — see §"Architecture diagram caveat" below. The repo-root location is mandated by AC #4 (path scoping) and the GH Actions runtime requirement. |
| §Enforcement "CI is the backstop, not the primary gate — local-clean before push." | Workflow is non-blocking on local dev; mirrors Story 1.2's local commands |
| NFR9 "macOS and Linux as first-class development targets, gated by automated CI on each release. Windows has no CI gate." | Matrix excludes Windows in Task 3 |
| PRD FR44 / `py.typed` | Mypy --strict step proves the package's public types resolve cleanly under strict |

### Architecture diagram caveat

The architecture document's §"Complete Project Directory Structure" (lines 935–1006) shows:

```
python_code/
├── .github/
│   └── workflows/
│       └── ci.yml
```

That placement is **inconsistent with AC #4 of this story** and inconsistent with how GitHub Actions actually works:

1. GitHub Actions only reads `.github/workflows/*` from the **repository root**. A `.github/workflows/ci.yml` at `python_code/.github/workflows/ci.yml` would be ignored entirely.
2. AC #4 explicitly says "the workflow lives at the JMRI repo root but pyjmri sources live only under `python_code/`."
3. The Story 1.3 user story sentence says "scoped to `python_code/**` changes" — only meaningful if the workflow itself is at the repo root looking inward at `python_code/`.

**Resolution:** put the workflow at `/Users/jmichaeldean/JMRI/.github/workflows/ci.yml` (the JMRI repo root). The architecture diagram's placement is a documentation defect, not a directive. Do not move or duplicate the workflow under `python_code/`.

### Path-scoping verification matrix

After deploying the workflow, the path filter MUST behave as follows:

| Commit touches… | Triggers CI? | Reason |
|---|---|---|
| `python_code/src/pyjmri/__init__.py` | ✅ Yes | matches `python_code/**` |
| `python_code/pyproject.toml` | ✅ Yes | matches `python_code/**` |
| `python_code/tests/unit/test_foo.py` | ✅ Yes | matches `python_code/**` |
| `.github/workflows/ci.yml` | ✅ Yes | exact match |
| `.github/workflows/release.yml` (future) | ❌ No | not listed; would need its own filter |
| `Basement_Revised_2024.jmri/March2026Settings.xml` | ❌ No | not under `python_code/` |
| `roster.xml` | ❌ No | not under `python_code/` |
| `roster/Mike9912.xml` | ❌ No | not under `python_code/` |
| `jython/MikeStartATrain.py` | ❌ No | not under `python_code/` |
| `CLAUDE.md` (repo root) | ❌ No | not under `python_code/` |
| `README.md` (repo root, if it ever exists separately) | ❌ No | not under `python_code/` |

Test at least one ✅ row and one ❌ row before considering Task 7 complete (`python_code/README.md` edit + a no-op edit to a panel XML or roster file are easy candidates that revert cleanly).

### Key gotchas to avoid

- **Workflow location:** `.github/workflows/ci.yml` at JMRI repo root, NOT `python_code/.github/workflows/ci.yml`. This is the single biggest mistake to avoid; a misplaced workflow file is silently ignored — no error, no log, just no CI runs.
- **Action version pinning:** Pin to major version (`@v4`), not `@main` (drift risk) and not full SHA pins (overkill for first-party Astral/GitHub actions). Mid-major bumps go through GitHub's deprecation notice.
- **Path-filter syntax:** GH Actions uses `paths:` (allowlist) and `paths-ignore:` (denylist). They cannot coexist on the same event trigger — using both produces a YAML schema error. We use only `paths:`.
- **Quoted Python versions:** `'3.11'` (string), not `3.11` (float). The YAML parser is fine with `3.11` for now, but as a habit quote them so `'3.10'` doesn't bite a future maintainer.
- **Don't run integration tests in CI:** `pytest -m "not integration"` is mandatory. Architecture §Test Harness explicitly excludes integration tests from CI for v1 (no JMRI server in CI). Drop the `-m` flag and the integration-test fixtures will try to probe `localhost:12080`, fail, and either skip-flood or fail-flood the run.
- **Don't add `cache: 'pip'` to setup-python:** Common GH Actions pattern — irrelevant here. setup-uv has its own cache; setup-python is not in this workflow at all.
- **Don't run with `--frozen` or `--locked` on `uv sync`:** `uv sync` already respects the committed `uv.lock` deterministically. Adding `--locked` is harmless but redundant; `--frozen` would skip lock updates which is also harmless here, but neither is needed.
- **Don't pin runner OS versions:** Use `ubuntu-latest`, not `ubuntu-22.04`. GitHub bumps `-latest` aliases on a slow cadence with deprecation notices; pinning specific versions creates manual upgrade work for no benefit.
- **Don't add Windows even "just to see if it works":** NFR9 is an explicit project decision. If a contributor wants a Windows job, that's a separate scope discussion, not a Story 1.3 deviation.
- **Don't add `permissions:` block yet:** GH Actions runs with default `contents: read` for forked PRs — fine for read-only CI. A `permissions:` block becomes necessary only when the workflow needs to push tags, comment on PRs, etc. (Story 6.6 / release workflow concern, not here).

### Verifying AC #5 (regression surfacing)

AC #5 says a future mypy violation must fail CI and surface on the PR. There are two acceptable ways to verify:

**Option A — Live verification (recommended for confidence):**
1. After deploying the workflow, create a branch like `test/ci-regression`.
2. Add `def broken(x): return x` (no annotations — fails `disallow_untyped_defs` from `strict = true`) to `python_code/src/pyjmri/__init__.py`.
3. Push the branch. Open a draft PR.
4. Confirm the workflow fails on the mypy step with a clear error.
5. Confirm the failure appears as a red ❌ on the PR's Checks panel.
6. Close the PR without merging; delete the branch.

**Option B — Construction proof:**
- The workflow runs `uv run mypy src/pyjmri` as a separate step with default `continue-on-error: false`.
- Any non-zero exit on that step fails the job; any failed job fails the workflow; any failed workflow surfaces a ❌ on the associated PR.
- Story 1.2 already verified the command produces non-zero exit on mypy errors locally.
- This combination is sufficient evidence to mark AC #5 satisfied without the live test.

Either is acceptable. Option A is more concrete; Option B is faster.

### Reference: previous story context

**Story 1.2 (just completed, status `review`):** Configured `[tool.ruff]`, `[tool.mypy] strict = true`, `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` and `markers = ["integration: ..."]`, dev deps (`ruff 0.15.12`, `mypy 2.0.0`, `pytest 9.0.3`, `pytest-asyncio 1.3.0`), and created `tests/unit/conftest.py` and `tests/integration/conftest.py` placeholders. The five verification commands all pass locally:

```
uv run ruff check src/ tests/        # exit 0
uv run ruff format --check src/ tests/   # exit 0
uv run mypy src/pyjmri               # exit 0
uv run pytest tests/                 # exit 5 (no tests)
uv run pytest -m "not integration"   # exit 5 (no tests)
```

Story 1.3 lifts the latter four into CI (the `pytest tests/` invocation is subsumed by `pytest -m "not integration"`). The exit code 5 ("no tests collected") **will fail CI** if not handled — pytest treats it as a non-zero exit. See §"Pytest exit code 5 in CI" below.

### Pytest exit code 5 in CI — important

Pytest returns exit code 5 when no tests are collected. Locally this looked benign in Story 1.2 because we read the message and shrugged. In CI, exit code 5 fails the step.

**At Story 1.3 deployment, `tests/unit/` and `tests/integration/` contain only empty `conftest.py` files. There are zero tests.** So the `pytest -m "not integration"` step will exit 5 and fail CI on the first push.

**Two options to handle this:**

**Option A — Don't fail on exit 5 (recommended for Story 1.3 only):**
Change the pytest step to:
```yaml
- name: Unit tests (pytest -m "not integration")
  run: uv run pytest -m "not integration" || ([ $? = 5 ] && echo "No tests collected — passing.")
```
This treats exit 5 as success (no-tests) but still fails on actual test failures (exit 1) or collection errors (exit 2/3/4). Once Story 2.1+ lands real tests, the `|| ([ $? = 5 ] && ...)` guard becomes a no-op (exit 0 short-circuits the `||`).

**Option B — Use pytest's `--exitfirst`-style flag:**
pytest 9.x supports `--no-tests-ok` (or in older versions, you set `empty_parameter_set_mark = "skip"`). The cleanest in pytest 9 is:
```yaml
- name: Unit tests (pytest -m "not integration")
  run: uv run pytest -m "not integration" --co --quiet || true  # collect-only first
  # then a real run that won't be exit-5-empty by Story 2.1
```
This is more brittle. Prefer Option A.

**Option C — Defer:** If you're comfortable knowing CI will fail on Story 1.3 until Story 2.1 lands a test, accept the failure as a known transient and move on. The matrix and workflow are still correct; CI will turn green automatically once tests exist. This is *not* recommended because AC #2 says all four steps must complete with exit status 0 against the current scaffold.

**Implementation:** use Option A. It satisfies AC #2 (exit 0 against current scaffold) and self-removes once tests arrive.

### File List (planned)

Created:
- `.github/workflows/ci.yml` (at JMRI repo root)

No other files modified.

### Source references

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.3: Add GitHub Actions CI matrix]
- [Source: _bmad-output/planning-artifacts/architecture.md#Test Harness] — CI matrix spec, integration-tests-local-only, headless-JMRI-CI deferred
- [Source: _bmad-output/planning-artifacts/architecture.md#Project-Specific Configuration to Layer On] — "GitHub Actions CI matrix workflow: macOS-latest + ubuntu-latest × Python 3.11 / 3.12 / 3.13, running ruff check, mypy, and pytest tests/unit/ on every push (NFR9)"
- [Source: _bmad-output/planning-artifacts/architecture.md#Enforcement] — "CI is the backstop, not the primary gate"
- [Source: _bmad-output/planning-artifacts/prd.md NFR9] — macOS+Linux first-class CI; Windows excluded
- [Source: _bmad-output/implementation-artifacts/1-2-configure-quality-gates-ruff-mypy-strict-pytest.md] — local invocation contract this CI lifts

### Latest GitHub Actions / uv specifics (knowledge cutoff: January 2026)

- **`actions/checkout@v4`** — current stable; v3 is EOL since 2024.
- **`astral-sh/setup-uv@v4`** — current stable as of 2026. Supports `python-version` input (installs Python via uv) and `enable-cache: true` (caches `~/.cache/uv` keyed on `cache-dependency-glob`). Replaces the older "setup-python + pip install uv" two-step.
- **`ubuntu-latest`** — currently aliases `ubuntu-24.04`. Will roll forward.
- **`macos-latest`** — currently aliases `macos-14` (ARM64). Bash and Python both work natively; no Rosetta concerns for our toolchain.
- **uv `[dependency-groups]` (PEP 735)** — `uv sync` includes the `dev` group by default. No flag needed to install dev deps.
- **GitHub Actions path filters** — allowlist (`paths:`) and denylist (`paths-ignore:`) are mutually exclusive on the same event trigger. We use only `paths:`.

### Project Structure Notes

After this story, the JMRI repo gains:

```
JMRI/
├── .github/                       # NEW (only this story creates it)
│   └── workflows/
│       └── ci.yml                 # NEW
├── python_code/                   # unchanged
│   └── ...
└── (rest of JMRI repo)            # unchanged
```

This is the **first** introduction of `.github/` to the JMRI repo. Earlier JMRI commits (panel XML, roster, Jython) never needed it. The `.github/` directory at the repo root may eventually grow other entries (issue templates, CODEOWNERS, dependabot config) but Story 1.3 only creates `workflows/ci.yml`.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Opus 4.7, 1M context)

### Debug Log References

Implementation date: 2026-05-07.

YAML structural validation (via Ruby `psych`):
- Top-level keys: `name`, `on`, `defaults`, `jobs` (Note: Ruby's psych uses YAML 1.1 spec which parses bare `on` as boolean `true` — informational only; GitHub Actions uses YAML 1.2 + its own schema and parses `on:` correctly as the trigger key. Modern `pyyaml` in 1.2 mode keeps it as the string `on` too.)
- Triggers: `push`, `pull_request`
- Push paths: `["python_code/**", ".github/workflows/ci.yml"]`
- PR paths: `["python_code/**", ".github/workflows/ci.yml"]`
- Default working-directory: `python_code`
- Matrix OS: `["ubuntu-latest", "macos-latest"]`
- Matrix Python: `["3.11", "3.12", "3.13"]`
- Matrix combinations: 6
- fail-fast: false
- Steps: 7 (Checkout, setup-uv, uv sync, ruff check, ruff format --check, mypy, pytest with exit-5 guard)

### Completion Notes List

- Tasks 1–6 complete. Workflow file written to `/Users/jmichaeldean/JMRI/.github/workflows/ci.yml` and structurally validated locally.
- **Task 7 (push and verify on GitHub) is intentionally unchecked.** Per user instruction, Mikey will perform the `git add / commit / push` himself and observe the live CI run on github.com — this is the appropriate division of labor since pushing is a "shared state" action visible to anyone watching the repo. Once the live verification confirms 6 jobs run green, mark Task 7 complete and flip Status to `review`.
- ACs satisfied by file content (verifiable now): #1 (six-job matrix shape), #3 (no Windows in matrix), #4 (path filters limit triggers to `python_code/**` and the workflow file).
- ACs deferred to live verification: #2 (all four steps green against current scaffold) and #5 (regression detection). AC #5 can be construction-proven once #2 passes — see story §"Verifying AC #5 (regression surfacing)" Option B.
- Pytest exit-5 guard implemented as `|| ([ $? = 5 ] && echo "No tests collected — passing.")`. Once Story 2.1 lands the first real unit test, this becomes a no-op (pytest exits 0 → `||` short-circuits → guard never fires). When that happens, the guard can stay as defensive programming or be removed in cleanup; both are fine.

### Push instructions for Mikey

From the JMRI repo root, the exact sequence:

```bash
cd /Users/jmichaeldean/JMRI
git status                                        # see the new file is untracked
git add .github/workflows/ci.yml                  # stage just this file
git status                                        # confirm only ci.yml staged
git commit -m "Add GitHub Actions CI matrix (story 1.3)"
git push                                          # pushes to origin/master (or current branch)
```

Then open `https://github.com/mdean77a/JMRI/actions` in a browser. You should see a workflow run named "CI" appear within ~10 seconds. Click into it to see the six job tiles spin up. First-run cold-cache time is ~2–3 min per job; all six run in parallel, so total wall-clock is ~3 min.

If anything goes red, click the failed job to see the log, then come back and we'll fix it.

### File List

Created:
- `.github/workflows/ci.yml` — GitHub Actions CI workflow at JMRI repo root.

No other files modified.

## Change Log

- 2026-05-07 — Story 1.3 implementation: GitHub Actions CI workflow created at `.github/workflows/ci.yml`. Six-job matrix (ubuntu-latest + macos-latest × Python 3.11/3.12/3.13), path-scoped to `python_code/**` and the workflow file itself, runs ruff lint + format-check + mypy strict + pytest. Local YAML validation passed; live verification on GitHub deferred to user (Task 7).
