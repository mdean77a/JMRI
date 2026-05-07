# Story 1.4: Add MIT LICENSE and README scaffold

Status: review

## Story

As a library publisher,
I want a MIT `LICENSE` file at `python_code/LICENSE` and a `README.md` seeded with the placeholder sections required by FR40/FR41/FR42,
so that the wheel built from `python_code/` is self-contained and PyPI-ready, with the documentation surface stubbed for later epics to fill.

## Acceptance Criteria

1. **MIT LICENSE wired into wheel METADATA.** Given the package skeleton from Story 1.1, when `python_code/LICENSE` is added containing the MIT License text with the author's copyright line AND `python_code/pyproject.toml` `[project]` metadata declares `license = "MIT"` and references `LICENSE`, then `uv build` produces an sdist and wheel under `python_code/dist/` whose `METADATA` reflects the MIT license.
2. **README scaffold passes `twine check`.** Given `python_code/README.md` exists with placeholder sections titled "Quickstart" (for FR40), "Migrating from Jython" (for FR41), and "Limitations" (for FR42), when `pyproject.toml` `[project]` metadata declares `readme = "README.md"`, then the built wheel's METADATA includes the README content and `twine check dist/*` (or equivalent METADATA inspection) passes.
3. **Stub markers prevent confusion.** Given the README scaffold, when a reviewer reads the placeholder sections, then each section is clearly marked as a stub to be filled in Epic 6 (e.g., a `TODO` comment or an explicit "(filled in Epic 6)" note), so no Epic-1 reader mistakes the placeholder for the final content.

## Tasks / Subtasks

- [x] **Task 1: Add `dist/` to repo-root `.gitignore`** (defensive, supports AC #1)
  - [x] Append `**/dist/` to `/Users/jmichaeldean/JMRI/.gitignore`. This prevents `uv build`'s output (`python_code/dist/`) from being accidentally committed. The existing `.gitignore` already covers `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`; `dist/` is the missing peer.
  - [x] Do this **before** `uv build` runs, otherwise `git status` will spam wheel/sdist filenames as untracked.

- [x] **Task 2: Create `python_code/LICENSE`** (AC: #1)
  - [x] Create `python_code/LICENSE` containing the standard MIT License text with copyright line `Copyright (c) 2026 Mike Dean`. Use the canonical text from §"MIT LICENSE text (canonical)" below — it is the exact form OSI publishes; do not modify it.
  - [x] The file lives at `python_code/LICENSE`, **not** at the JMRI repo root. Per architecture §"Project-Specific Configuration to Layer On": "the surrounding JMRI repository has its own license posture; the pyjmri license is scoped to `python_code/`."
  - [x] No file extension (`LICENSE`, not `LICENSE.md` or `LICENSE.txt`). PyPI's automated parsing prefers the bare name; setuptools / hatchling / uv_build all match it that way.

- [x] **Task 3: Add `license` declaration to `pyproject.toml`** (AC: #1)
  - [x] Add two lines to the `[project]` table (immediately after the `authors` line is fine):
    ```toml
    license = "MIT"
    license-files = ["LICENSE"]
    ```
  - [x] Use the **SPDX-string form** (`license = "MIT"`), NOT the legacy `license = { file = "LICENSE" }` or `license = { text = "MIT" }` forms. PEP 639 (finalized 2024) standardized SPDX strings as the modern syntax; uv_build, setuptools 77+, and hatchling all support it. The legacy `{file = ...}` form is deprecated and emits warnings on modern toolchains.
  - [x] `license-files = ["LICENSE"]` is what causes the file itself to be packaged into the wheel's `dist-info/licenses/` directory (per PEP 639 §"License files"). Without it, the wheel's METADATA has the SPDX string but the LICENSE file isn't bundled — PyPI accepts this but Linux distributions packaging from sdist would lose the license text.

- [x] **Task 4: Create the `README.md` scaffold** (AC: #2, #3)
  - [x] Replace the empty `python_code/README.md` with the canonical content shown in §"README scaffold (canonical)" below. The structure is: H1 title + one-line description, followed by H2 sections in this order: Quickstart, Migrating from Jython, Limitations.
  - [x] Each H2 stub section MUST contain an explicit "(filled in Epic 6)" marker so a reader cannot mistake the placeholder for finished prose. AC #3 is specific about this — a bare "TODO" in code comments is invisible to a reader; the marker must appear in the rendered Markdown.
  - [x] Do **not** include code examples, install instructions, or Limitations details yet. Those are Epic 6's territory (Stories 6.1, 6.2, 6.3). This story creates *placeholders only*.

- [x] **Task 5: Add `twine` as a dev dependency** (AC: #2)
  - [x] From `python_code/`, run `uv add --dev twine`. This refreshes `uv.lock` with twine and its small dependency closure.
  - [x] Twine is needed by AC #2's `twine check dist/*` invocation. It is also the canonical PyPI upload tool, which Story 6.6 will use for the first PyPI publication — adding it now means it's locked and available for both stories.
  - [x] Confirm `twine --version` runs via `uv run twine --version` — `twine version 6.2.0`.

- [x] **Task 6: Build sdist + wheel** (AC: #1)
  - [x] From `python_code/`, run `uv build`. Produced `dist/pyjmri-0.1.0.tar.gz` (1925 B) and `dist/pyjmri-0.1.0-py3-none-any.whl` (2771 B). uv_build accepted PEP 639 SPDX form without complaint; fallback not needed.
  - [x] Confirm `python_code/dist/` contains exactly two artifact files plus an auto-generated `.gitignore` (uv_build's standard convention — already covered by repo-root `**/dist/` ignore).

- [x] **Task 7: Verify METADATA content** (AC: #1, #2)
  - [x] **Method 1 (canonical, per AC #2):** `uv run twine check dist/*` → both PASSED.
  - [x] **Method 2 (manual METADATA inspection):** Wheel METADATA confirmed to contain `License-Expression: MIT`, `License-File: LICENSE`, full README body, `Description-Content-Type: text/markdown`, `Metadata-Version: 2.4`.
  - [x] **License file bundled in wheel:** Confirmed `pyjmri-0.1.0.dist-info/licenses/LICENSE` (1066 B) is in the wheel zipfile listing — `license-files` directive worked.

- [x] **Task 8: Verify CI still passes** (AC: implicit — don't break Stories 1.2 & 1.3)
  - [x] Local quality gates re-run from `python_code/`:
    - `uv run ruff check` → 0 ✅
    - `uv run ruff format --check` → 0 ✅ (3 files already formatted)
    - `uv run mypy src/pyjmri` → 0 ✅
    - `uv run pytest -m "not integration"` → exit 5 (no tests collected; expected) ✅
  - [x] None of Story 1.4's changes touched Python source under `src/pyjmri/`, so all four passed unchanged.
  - [ ] **Live CI verification deferred to Mikey post-push.** Once committed and pushed, the workflow at `.github/workflows/ci.yml` will trigger (path filter matches `python_code/**`). All six matrix jobs are expected to go green; the new `license = "MIT"` + `license-files = ["LICENSE"]` block runs through `uv sync` cleanly on Linux + macOS × Python 3.11/3.12/3.13.

## Dev Notes

### MIT LICENSE text (canonical)

Use this exact text — it is the OSI-published form. Replace nothing except the year, which is `2026`.

```
MIT License

Copyright (c) 2026 Mike Dean

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

The "Mike Dean" attribution matches the author line already in `pyproject.toml` (`{ name = "Mike Dean", email = "miketraindoc@gmail.com" }`). The year is `2026` because this is the calendar year of first publication; future years roll forward as `2026-2027`, `2026-2028`, etc., when meaningful new work is added.

### README scaffold (canonical)

Replace the empty `python_code/README.md` with this:

```markdown
# pyjmri

Async Python client for the JMRI web server.

## Quickstart

*(filled in Epic 6 — Story 6.1)*

A 5-minute getting-started guide that takes a developer from `uv add pyjmri` to a successful turnout flip will go here. See PRD FR40.

## Migrating from Jython

*(filled in Epic 6 — Story 6.3)*

A table mapping common JMRI Jython idioms to their pyjmri equivalents will go here. See PRD FR41.

## Limitations

*(filled in Epic 6 — Story 6.2)*

A clear explanation of what the library can and cannot detect — open-loop NCE, no DCC feedback, no power control on this hardware — will go here. See PRD FR42.
```

**Why this exact shape:**

- **H1 title + one-line description**: matches what every PyPI project page renders at the top. The description string ("Async Python client for the JMRI web server") matches the `description` field already in `pyproject.toml` so the two stay aligned.
- **Section order matches FR mapping**: Quickstart (FR40) → Migrating (FR41) → Limitations (FR42). Architecture §Documentation Patterns says "Limitations section is mandatory README content" — we satisfy that by listing it explicitly as a placeholder, not as omitted content.
- **"(filled in Epic 6 — Story 6.X)" annotation**: This is how AC #3 is satisfied. The annotation appears in the rendered Markdown (so a github.com viewer sees it), not as an HTML comment (which would hide it). It also names the specific Story that finishes each section, so a future maintainer doesn't have to grep the epics file to find what's owed.
- **No Installation section**: Tempting to add one (`uv add pyjmri` is two words), but Story 6.1 explicitly owns the Quickstart, which includes install. Adding it here means Story 6.1 has to either delete or merge our content. Cleaner to leave the whole getting-started arc to Epic 6.
- **No badges (CI, PyPI, etc.)**: same reasoning. Epic 6 owns README polish.

### `pyproject.toml` final form (after Task 3)

The `[project]` table after Task 3 should look like:

```toml
[project]
name = "pyjmri"
version = "0.1.0"
description = "Async Python client for the JMRI web server"
readme = "README.md"
authors = [
    { name = "Mike Dean", email = "miketraindoc@gmail.com" }
]
license = "MIT"
license-files = ["LICENSE"]
requires-python = ">=3.11"
dependencies = []
```

Two new lines (`license` + `license-files`); everything else unchanged. The order within `[project]` matters only for human readability, not for tooling — group the metadata fields together so a reader sees `name`/`version`/`description`/`readme`/`authors`/`license`/`license-files`/`requires-python`/`dependencies` in a logical narrative.

### Architecture compliance checklist

| Architecture / PRD rule | Story 1.4 alignment |
|---|---|
| §Project-Specific Configuration to Layer On — "MIT LICENSE file at `python_code/LICENSE`" | Task 2 |
| §Project-Specific Configuration to Layer On — "the pyjmri license is scoped to `python_code/`" | Task 2 (NOT at JMRI repo root) |
| §Documentation Patterns — "README-first documentation. The 5-minute getting-started (FR40) is the front door." | Quickstart section in Task 4 |
| §Documentation Patterns — "Limitations section is mandatory README content (FR42), not buried elsewhere." | Limitations section listed (as stub) in Task 4 |
| §Project Structure — README placement, LICENSE placement under `python_code/` | Tasks 2, 4 |
| §Build & Distribution — "uv build produces sdist + wheel into dist/" | Task 6 |
| PRD FR40 (Quickstart) | Task 4 — placeholder section reserves the slot |
| PRD FR41 (Jython migration table) | Task 4 — placeholder section reserves the slot |
| PRD FR42 (Limitations) | Task 4 — placeholder section reserves the slot |
| Business Success — "MIT license; PyPI distribution `pyjmri`" | Tasks 2, 3, 6 |

### Why PEP 639 / SPDX form (and not the legacy `{file = ...}` form)

Three reasons stacked:

1. **It's the documented modern form as of late 2024.** PEP 639 was accepted in 2024; setuptools 77 (2024-Q4), hatchling 1.27 (2024-Q4), and uv_build all adopted SPDX expressions as the canonical input. Legacy forms still parse but emit deprecation warnings on the toolchains we use.
2. **`twine check` validates it.** With SPDX form, twine inspects the `License-Expression` METADATA field against the SPDX license list and verifies "MIT" is a real identifier. Legacy `{text = "..."}` produces an unstructured `License:` field that twine accepts blindly — a typo in the license text would slip through. SPDX gets us a real check.
3. **PyPI uses it for badges and search.** PyPI's project page renders an "MIT License" badge derived from the SPDX expression. The legacy free-text form gives no badge.

If `uv_build` ever objects to SPDX (very unlikely with uv 0.7.6+), Task 6's fallback note tells you exactly what to do.

### Why we add `twine` now (vs. leaving it for Story 6.6)

Two reasons:

1. **AC #2 names it explicitly.** "twine check dist/*" is the documented validator. Substituting our own METADATA inspection is allowed ("or equivalent") but adds work; using twine is one `uv add --dev` line.
2. **It's coming back in Story 6.6.** Story 6.6 (first PyPI publication) needs `twine upload`. Pinning twine in `uv.lock` now means both stories use the same exact version — no surprise behavior between metadata-validation in 1.4 and upload in 6.6.

Twine is a pure-Python tool; the install is small (twine + cryptography + a few helpers, all already common transitive deps). It will not slow down CI's `uv sync` step in any noticeable way.

### Reference: previous story context

**Story 1.3 (just completed, status `review`):** Created `.github/workflows/ci.yml` at JMRI repo root. CI is path-scoped to `python_code/**` and `.github/workflows/ci.yml`. Six-job matrix runs ruff/mypy/pytest. Story 1.4's edits to `python_code/pyproject.toml`, `python_code/uv.lock`, `python_code/LICENSE`, and `python_code/README.md` will all trigger CI on push — that's the desired behavior (CI re-validates after we add the license declaration).

**Story 1.2 (status `review`):** Established the local quality-gate contract — `uv run ruff check`, `ruff format --check`, `mypy src/pyjmri`, `pytest -m "not integration"`. Story 1.4 must not break any of them.

**Story 1.1 (status `done`):** Created the `uv init --lib --name pyjmri` scaffold. The empty `README.md` it produced is what we replace in Task 4; the empty `[project]` license slot is what we fill in Task 3.

### Verification matrix (after all tasks complete)

After Task 8, this is the expected end-state:

| Check | Expected outcome |
|---|---|
| `python_code/LICENSE` exists, MIT text, year 2026, "Mike Dean" copyright line | ✅ |
| `python_code/pyproject.toml` `[project]` has `license = "MIT"` and `license-files = ["LICENSE"]` | ✅ |
| `python_code/README.md` has H1 + 3 stub H2 sections (Quickstart, Migrating from Jython, Limitations), each with "(filled in Epic 6 — Story 6.X)" marker | ✅ |
| `python_code/dist/pyjmri-0.1.0.tar.gz` exists | ✅ |
| `python_code/dist/pyjmri-0.1.0-py3-none-any.whl` exists | ✅ |
| `uv run twine check dist/*` → both PASSED | ✅ |
| Wheel METADATA contains `License-Expression: MIT` and `License-File: LICENSE` | ✅ |
| Wheel zipfile listing contains `pyjmri-0.1.0.dist-info/licenses/LICENSE` | ✅ |
| `uv run ruff check` → 0 | ✅ (no Python source changes) |
| `uv run mypy src/pyjmri` → 0 | ✅ (no Python source changes) |
| `**/dist/` is gitignored | ✅ (Task 1) |
| GitHub Actions CI workflow goes green on push | ✅ (path filter triggers; quality gates unchanged) |

### File List (planned)

Created:
- `python_code/LICENSE` — MIT license text
- `python_code/dist/pyjmri-0.1.0.tar.gz` — built sdist (gitignored, but present on disk for verification)
- `python_code/dist/pyjmri-0.1.0-py3-none-any.whl` — built wheel (gitignored, but present on disk for verification)

Modified:
- `python_code/README.md` — replaced empty file with H1 + 3 placeholder H2 sections
- `python_code/pyproject.toml` — added `license = "MIT"` and `license-files = ["LICENSE"]` to `[project]`; added `twine` to `[dependency-groups] dev`
- `python_code/uv.lock` — refreshed by `uv add --dev twine`
- `.gitignore` (JMRI repo root) — append `**/dist/`

### Latest tool specifics (knowledge cutoff: January 2026)

- **PEP 639** (SPDX license expressions in `pyproject.toml`): Accepted in 2024; supported by setuptools 77+, hatchling 1.27+, uv_build (all versions Mikey has access to via uv 0.7.6).
- **twine 5.x / 6.x**: Validates SPDX expressions against the spdx-license-list. `twine check` operates on built distributions; it does not require PyPI credentials (those are needed only for `twine upload` later).
- **PyPI's License-Expression rendering**: As of mid-2024, PyPI displays the SPDX badge directly on the project page when `License-Expression` is set. Legacy `License:` field still works but produces unstyled text.

### Source references

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.4: Add MIT LICENSE and README scaffold]
- [Source: _bmad-output/planning-artifacts/architecture.md#Project-Specific Configuration to Layer On] — MIT LICENSE at python_code/LICENSE; README.md scope
- [Source: _bmad-output/planning-artifacts/architecture.md#Documentation Patterns] — README-first; Limitations mandatory
- [Source: _bmad-output/planning-artifacts/architecture.md#Build & Distribution] — `uv build` produces sdist + wheel into dist/
- [Source: _bmad-output/planning-artifacts/prd.md FR40] — 5-minute Quickstart
- [Source: _bmad-output/planning-artifacts/prd.md FR41] — Jython migration table
- [Source: _bmad-output/planning-artifacts/prd.md FR42] — Limitations section

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Opus 4.7, 1M context)

### Debug Log References

Implementation date: 2026-05-07.

Build verification — wheel METADATA (extracted from `dist/pyjmri-0.1.0-py3-none-any.whl`):

```
Metadata-Version: 2.4
Name: pyjmri
Version: 0.1.0
Summary: Async Python client for the JMRI web server
Author: Mike Dean
Author-email: Mike Dean <miketraindoc@gmail.com>
License-Expression: MIT
License-File: LICENSE
Requires-Python: >=3.11
Description-Content-Type: text/markdown
[+ full README body inlined as long-description]
```

Wheel zipfile listing:

```
pyjmri/__init__.py                              78 B
pyjmri/py.typed                                  0 B
pyjmri-0.1.0.dist-info/licenses/LICENSE       1066 B
pyjmri-0.1.0.dist-info/WHEEL                    79 B
pyjmri-0.1.0.dist-info/METADATA                900 B
pyjmri-0.1.0.dist-info/RECORD                  545 B
```

`twine check`:
```
Checking dist/pyjmri-0.1.0-py3-none-any.whl: PASSED
Checking dist/pyjmri-0.1.0.tar.gz: PASSED
```

Resolved tool versions: `twine==6.2.0`. Twine pulled in 17 transitive deps (rich, keyring, requests, etc.) — all pinned in `uv.lock`.

### Completion Notes List

- All three ACs satisfied locally. AC #1: LICENSE present + `license = "MIT"` + `license-files = ["LICENSE"]` in pyproject.toml + uv build produces sdist + wheel under `python_code/dist/` with `License-Expression: MIT` in METADATA. AC #2: README scaffold passes `twine check`; both wheel and sdist verified. AC #3: Each H2 stub has explicit "(filled in Epic 6 — Story 6.X)" marker visible in rendered Markdown.
- **Live CI verification on GitHub deferred** — Mikey will push and observe the run, same pattern as Story 1.3.
- **PEP 639 SPDX form worked on first try.** uv_build (via uv 0.7.6) accepted `license = "MIT"` + `license-files = ["LICENSE"]` cleanly; the wheel's METADATA emits the modern `License-Expression: MIT` field (not the legacy free-text `License:` field). Fallback to legacy form was prepped but not needed.
- **Twine pulled in 17 transitive deps** including `cryptography`, `keyring`, `rich`, `markdown-it-py`, `nh3`, `readme-renderer`, etc. All pinned in `uv.lock`. Slightly larger dev-environment footprint, but architecturally clean — twine is the canonical PyPI tool that Story 6.6 will use for upload.
- **`dist/` directory:** uv_build also wrote a tiny `dist/.gitignore` (single `*` line) that uv generates by convention. Repo-root `**/dist/` already ignores the whole directory tree, so this auto-generated file is double-covered (harmless).
- **Build artifact size sanity check:** wheel is 2.8 KB, sdist is 1.9 KB. Tiny because the package is currently just `__init__.py` (NullHandler installer) + `py.typed` (empty marker). Will grow as Epic 2+ lands real modules.

### Push instructions for Mikey

From the JMRI repo root, the exact sequence:

```bash
cd /Users/jmichaeldean/JMRI
git status                                                  # eyeball what's about to land
git add .gitignore python_code/LICENSE python_code/README.md \
        python_code/pyproject.toml python_code/uv.lock      # if you want to scope; or just `git add .`
git status                                                  # confirm dist/ is NOT staged (the new gitignore should handle it)
git commit -m "Add MIT LICENSE and README scaffold (story 1.4)"
git push
```

`dist/` should NOT show as untracked because Task 1 added `**/dist/` to the repo-root `.gitignore`. If it appears anyway, double-check the `.gitignore` line is uncommented and saved.

After push, watch `https://github.com/mdean77a/JMRI/actions` for the new workflow run. Path filter triggers (you touched `python_code/**`); expect 6 jobs, all green.

### File List

Created:
- `python_code/LICENSE` — MIT License text (1066 B), copyright Mike Dean 2026.

Modified:
- `python_code/pyproject.toml` — added `license = "MIT"` and `license-files = ["LICENSE"]` to `[project]`; added `twine>=6.2.0` to `[dependency-groups] dev`.
- `python_code/uv.lock` — refreshed by `uv add --dev twine` (17 packages added).
- `python_code/README.md` — replaced empty file with H1 + 3 placeholder H2 sections (Quickstart, Migrating from Jython, Limitations), each with an "(filled in Epic 6 — Story 6.X)" marker.
- `.gitignore` (JMRI repo root) — appended `**/dist/`.

Sprint tracking:
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `1-4-add-mit-license-and-readme-scaffold` flipped `ready-for-dev → in-progress → review`.

Build artifacts (gitignored, present on disk for verification):
- `python_code/dist/pyjmri-0.1.0.tar.gz`
- `python_code/dist/pyjmri-0.1.0-py3-none-any.whl`

## Change Log

- 2026-05-07 — Story 1.4 implementation: `python_code/LICENSE` (MIT) created; `pyproject.toml` `[project]` declares `license = "MIT"` + `license-files = ["LICENSE"]` (PEP 639 SPDX form); `python_code/README.md` replaced with three H2 placeholder sections (Quickstart, Migrating from Jython, Limitations), each marked "(filled in Epic 6)"; twine added as dev dep. `uv build` produces sdist + wheel; `twine check dist/*` passes; wheel METADATA confirmed to contain `License-Expression: MIT`, `License-File: LICENSE`, and full README body. All four local quality gates from Story 1.2 still pass. Story Status moved to `review`; live CI verification deferred to user push.
