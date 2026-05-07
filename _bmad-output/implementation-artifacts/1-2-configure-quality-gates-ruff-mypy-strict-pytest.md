# Story 1.2: Configure quality gates (ruff, mypy strict, pytest)

Status: review

## Story

As a library developer,
I want `ruff`, `mypy --strict`, and `pytest` configured in `python_code/pyproject.toml` plus a `tests/unit/` and `tests/integration/` directory split,
so that every push runs through the same quality gates locally and in CI, and unit vs. integration tests are physically separable from the start.

## Acceptance Criteria

1. **Ruff lint + format clean on empty scaffold.** Given the package skeleton from Story 1.1, when `[tool.ruff]` configuration is added to `python_code/pyproject.toml` enabling rule sets `E, W, F, I, B, UP, ASYNC, RUF` plus the formatter, then `uv run ruff check src/ tests/` exits with status 0 and `uv run ruff format --check src/ tests/` exits with status 0.
2. **Mypy strict clean on empty scaffold.** Given `[tool.mypy]` is configured with `strict = true` in `pyproject.toml`, when `uv run mypy src/pyjmri` runs, then it exits with status 0 (no errors) against the empty package.
3. **Pytest discovers and runs cleanly.** Given `[tool.pytest.ini_options]` is configured with `asyncio_mode = "auto"`, when `pytest-asyncio` is added as a dev dependency via `uv add --dev pytest-asyncio`, then `uv run pytest tests/` discovers no tests and exits with the "no tests collected" status (pytest exit code 5) without crashing.
4. **Tests directory split + integration marker registered.** Given `tests/unit/` and `tests/integration/` directories exist with empty `conftest.py` placeholders, when a developer registers the custom `integration` marker in `[tool.pytest.ini_options]`, then `uv run pytest -m "not integration"` runs without warnings about unregistered markers.

## Tasks / Subtasks

- [x] **Task 1: Add dev dependencies** (AC: #1, #2, #3)
  - [x] In `python_code/`, run `uv add --dev ruff mypy pytest pytest-asyncio` to add the four tools as dev dependencies and refresh `uv.lock`.
  - [x] Verify `pyproject.toml` `[dependency-groups]` (or `[tool.uv]` dev block, whichever uv produces in 0.7.x) lists all four; do **not** move them into `[project] dependencies` — they are dev-only.
  - [x] Commit `uv.lock` after the add (the pinned versions are part of the contract).

- [x] **Task 2: Configure `[tool.ruff]`** (AC: #1)
  - [x] Add a `[tool.ruff]` table with `line-length = 100` and `target-version = "py311"` (matches `requires-python = ">=3.11"` so ruff rewrites pre-3.11 syntax under the `UP` ruleset).
  - [x] Add `[tool.ruff.lint]` with `select = ["E", "W", "F", "I", "B", "UP", "ASYNC", "RUF"]`. Do **not** add `D` (docstring) or `ANN` (annotations) rulesets in this story — those are out of scope for AC #1 and would fail later modules; Epic-2+ stories may layer them on.
  - [x] Add `[tool.ruff.format]` (empty table is fine; defaults match the project's style: double-quote strings, 4-space indent, trailing commas where multi-line). Do **not** override `quote-style` or `indent-style` — defaults are correct.
  - [x] Verify `uv run ruff check src/ tests/` exits 0 and `uv run ruff format --check src/ tests/` exits 0.

- [x] **Task 3: Configure `[tool.mypy]` strict** (AC: #2)
  - [x] Add `[tool.mypy]` with `strict = true`, `python_version = "3.11"`, and `mypy_path = "src"`. The `mypy_path` line teaches mypy to find `pyjmri` under `src/` without requiring an editable install resolution dance.
  - [x] Confirm `src/pyjmri/py.typed` already exists (it does — created by Story 1.1) so users importing pyjmri also get strict types via FR44.
  - [x] Verify `uv run mypy src/pyjmri` exits 0 against the empty package. The current `__init__.py` (one logging import + `addHandler` call) is already typed cleanly under strict; nothing additional needed.
  - [x] Do **not** add per-module overrides (`[[tool.mypy.overrides]]`) in this story. Architecture forbids `Any` in the public surface (§Type Annotation Conventions) — overrides that loosen strictness would erode that contract.

- [x] **Task 4: Configure `[tool.pytest.ini_options]`** (AC: #3, #4)
  - [x] Add `[tool.pytest.ini_options]` with: `asyncio_mode = "auto"`, `testpaths = ["tests"]`, and `markers = ["integration: requires a real JMRI instance on localhost:12080; excluded from CI"]`.
  - [x] The marker description string is the source of truth for *what* the marker means; CI's `pytest -m "not integration"` invocation (Story 1.3) reads this registration to suppress unknown-marker warnings.
  - [x] Verify `uv run pytest tests/` against the empty tree exits with code 5 ("no tests collected") — this is the documented success state for AC #3, not a failure.
  - [x] Verify `uv run pytest -m "not integration"` runs without `PytestUnknownMarkWarning`.

- [x] **Task 5: Create the unit/integration directory split** (AC: #4)
  - [x] Create `python_code/tests/unit/` and `python_code/tests/integration/` directories.
  - [x] Create empty `python_code/tests/unit/conftest.py` (zero bytes is fine — placeholder for future fixture loaders per architecture §Testing Patterns).
  - [x] Create empty `python_code/tests/integration/conftest.py` (zero bytes is fine — placeholder for the JMRI-probe skip-on-absence session fixture introduced in Epic 2).
  - [x] **Do not** create `__init__.py` files inside `tests/`, `tests/unit/`, or `tests/integration/`. Pytest's rootdir-based collection works without them and the architecture's test tree (§Project Structure) shows none.
  - [x] **Do not** create `tests/unit/fixtures/` or any test files in this story — those are Epic 2's territory (§Testing Patterns shows `fixtures/*.json` arriving with the parsing tests).

- [x] **Task 6: Verify all four AC commands locally** (AC: #1, #2, #3, #4)
  - [x] Run all four commands from `python_code/` and confirm exit codes:
    - `uv run ruff check src/ tests/` → 0 ✅
    - `uv run ruff format --check src/ tests/` → 0 ✅ (3 files already formatted)
    - `uv run mypy src/pyjmri` → 0 ✅ ("Success: no issues found in 1 source file")
    - `uv run pytest tests/` → 5 ✅ ("no tests ran in 0.00s")
    - `uv run pytest -m "not integration"` → 5 ✅, no `PytestUnknownMarkWarning`
  - [x] If any command produces unexpected output, fix the configuration before marking the story done — these five invocations are the contract Story 1.3 will lift verbatim into CI.

## Dev Notes

### Source of all changes

- **Files modified:** `python_code/pyproject.toml`, `python_code/uv.lock`
- **Files created:** `python_code/tests/unit/conftest.py`, `python_code/tests/integration/conftest.py`
- **Files NOT touched:** `python_code/src/pyjmri/__init__.py`, `python_code/src/pyjmri/py.typed`, `python_code/.python-version`, `python_code/README.md` — all owned by other Epic-1 stories.

### Current state (post-Story-1.1)

`python_code/` already contains the `uv init --lib` scaffold:

```
python_code/
├── .python-version          # "3.11"
├── pyproject.toml           # bare [project] + [build-system]; no tool tables yet
├── uv.lock                  # generated by `uv sync`
├── README.md                # empty (Story 1.4)
├── .venv/                   # local; gitignored
└── src/pyjmri/
    ├── __init__.py          # logging.NullHandler installed on "pyjmri" root
    └── py.typed             # empty marker file (FR44)
```

The current `pyproject.toml` (read it before editing):

```toml
[project]
name = "pyjmri"
version = "0.1.0"
description = "Async Python client for the JMRI web server"
readme = "README.md"
authors = [{ name = "Mike Dean", email = "miketraindoc@gmail.com" }]
requires-python = ">=3.11"
dependencies = []

[build-system]
requires = ["uv_build>=0.7.6,<0.8"]
build-backend = "uv_build"
```

This story adds tool tables and dev dependencies; do not modify `[project]` or `[build-system]`.

### Why these specific ruff rule sets

Each set in `E, W, F, I, B, UP, ASYNC, RUF` does work the project needs:

- **E, W, F** — pycodestyle errors/warnings + pyflakes (unused imports, undefined names). The baseline.
- **I** — isort. Architecture §Public API Discipline demands `__all__` discipline; ordered imports are part of consistent module headers.
- **B** — flake8-bugbear. Catches `except:` without exception type, mutable default args — both forbidden by architecture §Error Handling Discipline and §Async Patterns.
- **UP** — pyupgrade. Architecture §Type Annotation Conventions mandates PEP 604 unions (`X | None`) and `from __future__ import annotations`; UP rewrites the legacy forms automatically.
- **ASYNC** — flake8-async. Architecture §Async Patterns forbids blocking I/O in `async def`; ASYNC catches `time.sleep` in coroutines, sync HTTP calls, etc.
- **RUF** — ruff-native rules. Catches `asyncio.gather` patterns and `__all__` typing issues that bite later epics.

Sets the architecture mentions but Story 1.2 *does not* enable: `D` (docstrings) and `ANN` (annotations). Both will fail loudly against any module that lacks docstrings or annotations, and the empty scaffold has neither — enabling them now would either fail AC #1 or require silencing rules. Architecture §Documentation Patterns mentions `D` enforcement; that is a future-story concern, not Story 1.2's scope.

### Why `target-version = "py311"` matters

The `UP` ruleset uses the target version to decide which rewrites are safe. Setting `py311` lets ruff convert `Optional[X]` → `X | None` and `Union[X, Y]` → `X | Y` automatically — which is exactly what architecture §Type Annotation Conventions requires the codebase to use. If left unset, ruff defaults to the lowest version `requires-python` allows, which is fine here, but explicit > implicit.

### Why `mypy_path = "src"` and not `packages`

The `src/` layout puts the importable package one directory below the project root. `mypy src/pyjmri` works only if mypy can resolve `pyjmri` as a top-level package; setting `mypy_path = "src"` is the canonical way under PEP 518 / `pyproject.toml`. Alternatives (`packages = ["pyjmri"]`, `files = ["src/pyjmri"]`) work too but are more brittle to file-tree changes. `mypy_path` matches what the wider Python tooling ecosystem (FastAPI, httpx, anthropic-sdk-python) does for src layouts.

### Why `asyncio_mode = "auto"`

Architecture §Testing Patterns: "`async def test_*`. Pytest config sets `asyncio_mode = "auto"`, so the `@pytest.mark.asyncio` decorator is not needed." Setting auto here is the explicit decision recorded in the architecture; do not switch to `"strict"` even though pytest-asyncio docs sometimes recommend it.

### Why the integration marker description matters

Story 1.3 (CI) lifts `uv run pytest -m "not integration"` verbatim into the workflow file. The marker description in `[tool.pytest.ini_options].markers` is not just decorative — `pytest --strict-markers` (which Story 1.3 may add) requires registered markers to have descriptions to suppress warnings. Make the description specific and accurate so a future reader of the workflow file understands why CI excludes that marker.

### Architecture compliance checklist

| Architecture rule | Story 1.2 alignment |
|---|---|
| §Test Harness — `tests/unit/` and `tests/integration/` dirs | Created in Task 5 |
| §Test Harness — `pytest.mark.integration` marker | Registered in Task 4 |
| §Test Harness — `asyncio_mode = "auto"` | Set in Task 4 |
| §Project Structure — no `__init__.py` in `tests/` subtrees | Enforced in Task 5 (do-not list) |
| §Type Annotation Conventions — PEP 604 unions, `from __future__ import annotations` | Enforced by ruff `UP` ruleset (Task 2) |
| §Async Patterns — no blocking I/O in `async def` | Enforced by ruff `ASYNC` ruleset (Task 2) |
| §Public API Discipline — `__all__` in every public module | Enabled by ruff `RUF` + `F` rulesets (Task 2); test surface arrives in Epic 2 |
| §Error Handling Discipline — concrete exception types only | Enforced by ruff `B` ruleset (Task 2) |
| §Enforcement — "Run `ruff format`, `ruff check`, and `mypy --strict` before treating any change as complete" | This story makes those commands runnable for the first time |
| §Decision Impact Analysis Step 1 — "Project init … plus the project-specific configuration layered on top (ruff, mypy strict, pytest + pytest-asyncio, tests directory split, …)" | This story is exactly the "layered on top" portion |

### Anti-patterns to avoid

- **Do not** copy ruff/mypy config from another project. The arch document is opinionated; foreign configs typically include `D`, `ANN`, or per-module mypy overrides that conflict with §Type Annotation Conventions or §Documentation Patterns timing.
- **Do not** add `# type: ignore` or `# noqa` comments to make checks pass. The empty scaffold is clean; if either tool flags something, the config is wrong, not the code.
- **Do not** install ruff/mypy/pytest globally or via pipx. Use `uv add --dev` so the versions are locked in `uv.lock` and reproducible across machines (the JMRI repo is cloned to multiple hosts including a Raspberry Pi per CLAUDE.md).
- **Do not** add a separate `ruff.toml` or `mypy.ini` file. `pyproject.toml` is the single source of truth per architecture §Selected Starter "single source of truth for metadata, deps, and tool configs."
- **Do not** create `tests/__init__.py`. Pytest discovers `tests/` via `testpaths` without it; an `__init__.py` would force importable test packages, which complicates fixture scoping later.
- **Do not** add a `conftest.py` at `tests/` root in this story. Each subtree gets its own; shared fixtures arrive in later stories where there's something to share.

### Reference: previous story context

Story 1.1 (`uv init --lib --name pyjmri`) is implemented on disk (`python_code/` contains the scaffold) but **not yet recorded as a story file** in `_bmad-output/implementation-artifacts/`. There is no Story 1.1 dev-notes record to draw from. The state on disk *is* the contract: do not assume any other Story 1.1 outputs exist beyond what's listed in §Current state above.

Note: `_bmad-output/implementation-artifacts/sprint-status.yaml` may still mark `1-1-initialize-package-skeleton-with-uv-init-lib` as `backlog`. That is a sprint-status drift, not a blocker for Story 1.2 — the prerequisite scaffold is on disk. Inform the user if they want sprint-status reconciled.

### Source references

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.2: Configure quality gates (ruff, mypy strict, pytest)] — full BDD acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md#Project-Specific Configuration to Layer On] — ruff/mypy/pytest layering plan
- [Source: _bmad-output/planning-artifacts/architecture.md#Test Harness] — directory split, marker, asyncio_mode decision
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules] — Type Annotation, Async, Error Handling, Logging, Public API, Testing patterns the linter must enforce
- [Source: _bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure] — final tests/ tree shape
- [Source: _bmad-output/planning-artifacts/architecture.md#Enforcement] — local-clean-before-push rule that this story makes physically possible
- [Source: _bmad-output/planning-artifacts/prd.md FR44] — `py.typed` marker (already present)
- [Source: _bmad-output/planning-artifacts/prd.md NFR7] — Python 3.11+ floor (matches `target-version = "py311"`)
- [Source: _bmad-output/planning-artifacts/prd.md Technical Success criteria] — "`mypy --strict`, `ruff` clean, `py.typed`"

### Latest tool versions (knowledge cutoff: January 2026)

- **ruff** — let `uv add --dev ruff` resolve the latest stable. Ruff has been on a fast minor cadence; >=0.8 has the `ASYNC` ruleset stable. `target-version = "py311"` is supported back to 0.5.x, so any recent release is fine.
- **mypy** — let `uv add --dev mypy` resolve the latest stable. >=1.13 is recommended for stable 3.13 support; `strict = true` semantics have been stable since 1.0.
- **pytest** — latest 8.x stream. Pytest 8 introduced stricter type-checking on its own internals which interacts well with mypy strict.
- **pytest-asyncio** — latest 0.x stream. `asyncio_mode = "auto"` has been stable since 0.21; >=0.24 has the cleanest interaction with pytest 8.

`uv.lock` will pin exact versions when `uv add --dev` runs; that lockfile is the durable record. Do not over-pin in `pyproject.toml` `[dependency-groups]` — let uv resolve and lock.

### Project Structure Notes

After this story, `python_code/` will look like:

```
python_code/
├── .python-version                # unchanged
├── pyproject.toml                 # MODIFIED: + [tool.ruff], [tool.mypy], [tool.pytest.ini_options], + dev deps
├── uv.lock                        # MODIFIED: refreshed by `uv add --dev`
├── README.md                      # unchanged (Story 1.4)
├── src/pyjmri/                    # unchanged (Story 1.1)
│   ├── __init__.py
│   └── py.typed
└── tests/                         # NEW
    ├── unit/
    │   └── conftest.py            # NEW (empty placeholder)
    └── integration/
        └── conftest.py            # NEW (empty placeholder)
```

This matches the architecture §Complete Project Directory Structure subset that exists at end-of-Epic-1; the per-entity test files arrive with their corresponding modules in Epic 2+.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Opus 4.7, 1M context)

### Debug Log References

Implementation date: 2026-05-07. uv at version 0.7.6.

Resolved tool versions (pinned in `uv.lock`):
- ruff 0.15.12
- mypy 2.0.0
- pytest 9.0.3
- pytest-asyncio 1.3.0

### Completion Notes List

- All four ACs satisfied; all five verification commands produced the expected exit codes on first run with zero rework.
- Note on tool versions: the architecture document (drafted earlier in the project) and the story dev notes anticipated mypy 1.x and pytest 8.x, but `uv add --dev` resolved to mypy 2.0.0 and pytest 9.0.3 as the current latest stable on PyPI. Both run cleanly with `strict = true` and `asyncio_mode = "auto"` against the empty scaffold; no config changes were required to accommodate the major-version bumps. Flagging here so a future story is not surprised by the difference between the architecture's prose and the actual `uv.lock` pins.
- The shell `cd` into `python_code/` was performed by the Bash tool's persistent cwd, not by an explicit `cd` step. All commands executed from `python_code/`.
- `uv run ruff check` triggered an editable rebuild of `pyjmri` on first invocation (uv noticed the `pyproject.toml` changed). Subsequent runs are no-ops. This is expected uv behavior, not a story regression.

### File List

Modified:
- `python_code/pyproject.toml` — added `[dependency-groups] dev`, `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.format]`, `[tool.mypy]`, `[tool.pytest.ini_options]` tables.
- `python_code/uv.lock` — refreshed by `uv add --dev` (added 13 transitive packages; pyjmri rebuilt).

Created:
- `python_code/tests/unit/conftest.py` — empty placeholder.
- `python_code/tests/integration/conftest.py` — empty placeholder.

Sprint tracking:
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `1-2-configure-quality-gates-ruff-mypy-strict-pytest` flipped `ready-for-dev → in-progress → review`.

## Change Log

- 2026-05-07 — Story 1.2 implemented. Quality gates (ruff, mypy --strict, pytest + pytest-asyncio) configured in `python_code/pyproject.toml`; `tests/unit/` and `tests/integration/` created with empty `conftest.py` placeholders; `integration` pytest marker registered. All four ACs and the five-command verification contract pass. Ready for code review.
