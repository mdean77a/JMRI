# Contributing to pyjmri

This file is for maintainers and contributors to `pyjmri`. End-users wanting the library should read `README.md` and the runnable scripts in `examples/`. The release checklist below is the discipline a maintainer follows before publishing a new version to PyPI; the hardware-mode throttle validation section is the procedure step 6 of that checklist references.

**Reporting issues and filing PRs:** Bugs and feature requests go to GitHub Issues at `https://github.com/mdean77a/JMRI`. Maintainer reviews are best-effort — `pyjmri` is a one-person project as of v1. A PR that includes passing unit tests against the simulator (and a note about hardware-mode behavior if the change touches throttles, turnouts, or routes) is much faster to merge than one without. There is no formal governance doc; talk to the maintainer in the issue thread before starting anything substantial.

## Developer setup

Clone the repo and work inside `python_code/`. Every command below assumes the working directory is `python_code/`.

Install runtime and dev dependencies with `uv`:

```bash
uv sync
```

`uv sync` creates `.venv/`, installs the runtime dependencies (`httpx`, `websockets`), installs the dev dependencies (`mypy`, `ruff`, `pytest`, `pytest-asyncio`, `psutil`, `twine`, `ipykernel`), and editable-installs `pyjmri` itself via the `src/` layout. After this, every tool invocation uses `uv run --no-sync` so the lockfile is not re-resolved on every call.

Confirm Python 3.11+ is in scope:

```bash
uv run --no-sync python --version
```

The four quality gates a contributor runs locally before opening a PR are:

```bash
uv run --no-sync ruff check
```

```bash
uv run --no-sync ruff format --check
```

```bash
uv run --no-sync mypy --strict src/pyjmri
```

```bash
uv run --no-sync pytest -m "not integration"
```

The post-Story-8.3 unit-test baseline is **610 passed, 25 deselected**. The 25 deselected tests are `@pytest.mark.integration` tests excluded from the default run; see the next section for what they cover and why they live locally.

`uv run` without `--no-sync` re-resolves the lockfile on every invocation, which is wasteful once `uv sync` has been run. The convention in this doc is uniform — every tool invocation takes `--no-sync` so a reader does not have to memorize which commands need the flag. The exception is `uv build`, `uv sync`, `uv publish`, and `uv add` — those are `uv` commands themselves, not "run a tool inside the venv" invocations, and they do not take `--no-sync`.

## Testing policy: integration tests are local-only

`pyjmri` ships two test suites:

- **Unit tests** (the 610 above) — no external dependencies, run in CI on every push and PR.
- **Integration tests** (the 25 deselected) — require a real JMRI 5.14+ instance at `localhost:12080` with a panel file loaded, and are **excluded from CI**.

The CI workflow at `.github/workflows/ci.yml` runs `pytest -m "not integration"` across `[ubuntu-latest, macos-latest] × ['3.11', '3.12', '3.13']`. No CI job spins up a JMRI instance. Headless-JMRI CI is Growth-deferred — not under consideration for v1.

The contributor-facing rule that falls out of this:

> No PR is blocked on missing integration coverage. Integration evidence is the maintainer's pre-release responsibility, not the contributor's per-PR responsibility.

If your PR changes library behavior that integration tests exercise, mention what hardware or simulator setup you used to validate it locally. If you cannot run integration tests at all, say so — the maintainer will validate at release time before publishing.

## Running integration tests locally

Pre-conditions:

- JMRI 5.14 or later is running on the same machine (or reachable on the LAN) with its web server enabled.
- A panel file is loaded. Most integration tests are layout-agnostic; `Basement_Revised_2024.jmri` or the NCE simulator profile both work.
- **For the Operations integration tests** (`tests/integration/test_operations_discovery.py`): the loaded profile must have JMRI Operations data configured. These tests are **not** layout-agnostic — they assert non-empty locations/trains/cars/engines. `Basement_Revised_2024.jmri` carries this data (3 locations / 4 engines / 3 cars / 1 train / 1 route); a bare NCE simulator profile without Operations data exercises only the empty-collection path and the rest skip. Operations is pure JSON data, so no hardware or physical layout is needed — the simulator with Operations data loaded is sufficient.
- `pyjmri` is installed in the active venv (i.e., you have run `uv sync`).

If JMRI is not reachable, the `conftest`'s skip-on-absence fixture skips the integration tests with a clear message rather than failing them — so it is safe to run the full suite from a state where JMRI may or may not be up.

Three invocation forms cover the integration suite:

```bash
uv run --no-sync pytest tests/integration/
```

```bash
uv run --no-sync pytest -m integration
```

```bash
uv run --no-sync pytest -m "integration and not slow"
```

The first two are equivalent and include the one-hour `test_long_run.py` at its default 5-minute duration. The third excludes the long-run test entirely; it is the form recommended for the release checklist's step 4, where step 5 owns the long-run gate at its full one-hour duration. The example docstrings in `examples/` cover the simulator-versus-hardware split for example-script users; this section is the integration-test equivalent for maintainers.

## Release checklist

This is the pre-release discipline a maintainer follows top-to-bottom before publishing a new version to PyPI. Every step produces evidence — either command output or a physical observation — and a failure at any step halts the release until the failure is fixed. Steps run in order; do not skip ahead.

Every command uses `uv run --no-sync` for tool invocations. The exceptions are `uv build`, `uv publish`, and `uv add` (and `uv sync`, if you need to re-sync), which are `uv` commands themselves.

1. **Linting and formatting clean locally.** Lint, then format-check, in separate invocations so a failure points at the right gate.

   ```bash
   uv run --no-sync ruff check
   ```

   ```bash
   uv run --no-sync ruff format --check
   ```

   Expected: `All checks passed!` from `ruff check`, and `N files already formatted` from `ruff format --check` (the count `N` is not the gate — the gate is "no files would be reformatted"). Failure mode: fix the lint or format issues and re-run; do not continue to step 2 with either gate red.

2. **Type-checking clean against source and examples.** Both the library source and the shipped examples are typed strictly.

   ```bash
   uv run --no-sync mypy --strict src/pyjmri
   ```

   ```bash
   uv run --no-sync mypy --strict examples/
   ```

   Expected: `Success: no issues found in 20 source files` for the library, and `Success: no issues found in 3 source files` for the examples (post-Story-6.4 baseline). The file counts may grow as the library or examples grow, but they must never *decrease* without an explicit story changing the source surface. Failure mode: fix the type errors and re-run; do not continue with mypy red.

3. **Unit tests clean.**

   ```bash
   uv run --no-sync pytest -m "not integration"
   ```

   Expected: `610 passed, 25 deselected` (post-Story-8.3 baseline). The passed count may grow as the library grows; the deselected count may grow as new `@pytest.mark.integration` tests are added. Any failure halts the release until the failing test is either fixed (regression) or explicitly de-scoped via story.

4. **Full integration suite passes against a real JMRI instance.** Start JMRI with `Basement_Revised_2024.jmri` (or an equivalent layout / the simulator), confirm the web server is up at `localhost:12080`, then run the integration suite minus the long-run test. Note: the Operations integration tests need Operations data loaded — `Basement_Revised_2024.jmri` has it; a bare simulator profile without Operations data is insufficient for that subset (see "Running integration tests locally" above):

   ```bash
   uv run --no-sync pytest -m "integration and not slow"
   ```

   Expected: every selected integration test passes. The one `slow` integration test (`test_long_run.py`) is excluded by the `and not slow` clause and runs separately in step 5. Failure mode: a failing integration test halts the release; investigate the failure on the actual layout before continuing.

   The marker boolean is intentional — the long-run test carries both `integration` and `slow` markers. Selecting `-m integration` would run it here at its default 5-minute duration *and* again at 1 hour in step 5. Using `-m "integration and not slow"` here lets step 5 own the long-run gate at its full duration without double-counting.

5. **One-hour long-run stability test passes.** This is the pre-release evidence that the reconnect machinery does not leak across an hour of forced disconnects.

   ```bash
   uv run --no-sync pytest tests/integration/test_long_run.py --duration=3600 -s
   ```

   The `-s` flag is required so the summary line prints to stdout. Equivalent form using the environment variable:

   ```bash
   PYJMRI_LONG_RUN_DURATION=3600 uv run --no-sync pytest tests/integration/test_long_run.py -s
   ```

   Expected: a single PASS line, and a printed summary line of the form

   ```text
   pyjmri long-run: duration=3600s disconnects=5 reconnects=5 rss_delta=X.XMB fd_delta=N task_delta=N status=PASS
   ```

   Paste this summary line verbatim into the release notes (step 8). Failure mode: a non-PASS outcome halts the release; the failure must be diagnosed before the next attempt (memory leak, FD leak, task leak, or reconnect-count mismatch are the four ways this gate fails).

6. **Hardware-mode throttle validation.** Perform the hardware-mode throttle validation procedure documented in the next section. The result of this step's keep-alive observation feeds two outputs: a line in the release notes (step 8), and an update to the comment block at `throttle.py:316-345` (see the recording step in the procedure).

7. **Version bumped in `pyproject.toml`.** Edit the `[project].version` field to the new release version. The current version at the time this checklist was authored is `0.1.0`; the first PyPI publish (per Story 6.6) bumps to `1.0.0`. Commit the bump as a discrete commit with the subject line `Bump version to X.Y.Z`. No other changes in that commit — version bumps are easier to revert and easier to read in `git log` when they are isolated.

8. **Release notes written.** Plain-text or markdown notes covering at minimum:

   - The JMRI version tested against in steps 4–6 (e.g., "JMRI 5.14.1").
   - The long-run summary line from step 5, pasted verbatim.
   - The hardware-mode keep-alive observation outcome from step 6 — one of "JMRI keeps throttle held after 30 s silence" or "JMRI drops throttle after 30 s silence".

   The recommended location is `python_code/RELEASES.md`. A structured changelog format (Keep-a-Changelog, conventional commits, etc.) is Growth-deferred — v1 release notes are free-form. The file does not exist yet; Story 6.6 creates it as part of the first publish.

9. **Build clean artifacts and publish.** Delete any stale build artifacts, then build the sdist and wheel:

   ```bash
   rm -rf dist/
   uv build
   ```

   This produces `python_code/dist/pyjmri-X.Y.Z.tar.gz` and `python_code/dist/pyjmri-X.Y.Z-py3-none-any.whl`. Validate the metadata:

   ```bash
   uv run --no-sync twine check dist/*
   ```

   Expected: `Checking dist/*: PASSED`. Publish to PyPI:

   ```bash
   uv publish
   ```

   Credentials are supplied via the `UV_PUBLISH_TOKEN` environment variable or `~/.pypirc`. Finally, tag the release and push the tag:

   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```

### After publish

Confirm `https://pypi.org/project/pyjmri/` shows the new version. In a scratch directory outside the repo, run `uv add pyjmri` in a fresh venv and re-run the Quickstart from `README.md` to confirm the installed wheel works as expected. Add a "Published 20YY-MM-DD" line at the bottom of the release notes for the version you just shipped. If the smoke install or smoke Quickstart fails, yank the broken version on PyPI before anyone downloads it and diagnose before re-publishing.

## Hardware-mode throttle validation

This section is the procedure referenced by step 6 of the release checklist. It runs against **real NCE hardware**, not the simulator — Story 5.3's simulator tests cover library plumbing only (acquire / release / set-speed / set-function envelopes round-trip cleanly), but the NCE simulator has no virtual decoder, so it cannot validate that a real locomotive responds to commands. This procedure is the only place real-hardware throttle behavior is validated, and it runs once per release.

### Setup

Operator confirms each of the following before continuing:

- JMRI 5.14 or later is running on a machine talking to real NCE hardware (NCE USB or NCE PowerCab connected via serial).
- The basement layout (or an equivalent NCE layout) is powered — booster ON, track power live.
- A known-responsive locomotive is on the rails at a documented DCC address. The basement default is DCC `5327` long (the same address used in `jython/MikeBackAndForth.py:18` and the `--dcc` default in `examples/back_and_forth.py`).
- The locomotive has clear track in both directions for at least a few meters of run.

### Drive script

Save the following as `release_drive.py` in a scratch directory outside the repo (not inside `examples/` — this is operator-only validation, not a shipped example):

```python
import argparse
import asyncio
from pyjmri import Client


async def main(dcc: int, url: str) -> None:
    async with Client(url) as jmri:
        layout = await jmri.discover()
        async with layout.throttle(dcc, long=True) as t:
            await t.set_speed(0.3, forward=True)
            await asyncio.sleep(8)
            await t.set_speed(0.0, forward=True)   # stop before reversing
            await asyncio.sleep(3)
            await t.set_speed(0.3, forward=False)
            await asyncio.sleep(8)
            await t.set_function(0, True)
            await asyncio.sleep(3)
            await t.set_function(0, False)  # restore headlight state
            await t.set_speed(0.0, forward=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dcc", type=int, default=5327)
    p.add_argument("--url", type=str, default="http://localhost:12080")
    args = p.parse_args()
    asyncio.run(main(args.dcc, args.url))
```

Run it:

```bash
uv run --no-sync python release_drive.py --dcc 5327
```

This is intentionally a smaller, hand-driven script than the autonomous `examples/back_and_forth.py` (which loops forever waiting on sensors). The operator is supposed to *watch the loco* between commands and observe each behavior in real time.

### Visual verification

Stand at the layout and observe each of the following. Record PASS or FAIL for each, with the locomotive ID and approximate distance traveled:

- **Forward motion.** The loco moved in the forward direction for the first 8-second window.
- **Reverse motion.** The loco changed direction and moved in reverse for the second 8-second window.
- **Function-bit effect.** The function bit took effect — for most decoders, function 0 toggles the headlight, so the headlight changed state.

A FAIL on any one observation is a release blocker. Diagnose the failure (decoder consist conflict, wrong DCC address, dirty wheels or track, decoder reset needed) and re-run before continuing. Per the Limitations section in `README.md`, a successful `await` only confirms the command reached JMRI — visual confirmation at the layout is the only ground truth for whether the layout moved.

### Keep-alive observation

Wait a few seconds after `release_drive.py` finishes before starting this script — JMRI needs a moment to fully release the previous throttle session on the same DCC address.

This is the step that resolves the speculative TODO at `throttle.py:316-345`. Save the following as `release_keepalive.py` in the same scratch directory:

```python
import argparse
import asyncio
from pyjmri import Client


async def main(dcc: int, url: str) -> None:
    async with Client(url) as jmri:
        layout = await jmri.discover()
        async with layout.throttle(dcc, long=True) as t:
            await t.set_speed(0.0, forward=True)
            await asyncio.sleep(30)
            await t.set_speed(0.1, forward=True)
            await asyncio.sleep(5)
            await t.set_speed(0.0, forward=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dcc", type=int, default=5327)
    p.add_argument("--url", type=str, default="http://localhost:12080")
    args = p.parse_args()
    asyncio.run(main(args.dcc, args.url))
```

Run it:

```bash
uv run --no-sync python release_keepalive.py --dcc 5327
```

Do not interrupt the script during the 30-second wait — a Ctrl-C mid-sleep releases the throttle session early and produces a false "JMRI dropped" result.

The 30-second silent hold is **2× `ClientConfig.throttle_keepalive_interval`** (default 15.0 seconds). If the keep-alive interval is changed in `_protocols.py`, recompute the hold to twice the new interval. The 30 s value is not magic — it is "long enough that any reasonable expiry would have fired by now."

Observe whether the loco responds to the `set_speed(0.1, ...)` command after the silent hold:

- **Loco responds → JMRI kept the throttle held during the 30 s silence → the v1 no-op keep-alive stub is correct.** Record this outcome.
- **Loco does NOT respond → JMRI dropped the throttle during the silence → the keep-alive coroutine body must be activated.** Record this outcome and follow the code change spelled out in the next sub-section.

### Recording the result

Two recording actions, in this order:

**(a) Release notes.** Add a line to the release notes (step 8 of the checklist) of the form:

```text
Hardware-mode keep-alive: JMRI keeps throttle held after 30 s silence on JMRI 5.14 / NCE USB / 2026-MM-DD.
```

Or the "JMRI drops throttle..." variant. Include the JMRI version, the NCE hardware identifier (NCE USB, NCE PowerCab, etc.), and the date.

**(b) Update the comment block at `throttle.py:316-345`.** The speculative paragraph starting "If Story 5.3 hardware observation shows JMRI does expire idle throttles..." is replaced with the actual finding. The replacement format is:

```text
Confirmed [necessary | unnecessary] on JMRI X.Y / NCE [hardware identifier] / 20YY-MM-DD by [maintainer].
```

If the outcome is "drops" (the body must be activated), make the code change recipe at `throttle.py:329-336` live — replace the no-op stub body with the four-line `while True: await asyncio.sleep(...); throttle_heartbeat(...)` loop. Because this is a source-code change, re-run the four quality gates (steps 1–3 of the checklist) before continuing the release. Steps 4–5 do not need to re-run unless the source change touches files the long-run test exercises (it usually doesn't).

### Scope

This procedure validates **throttle and decoder responsiveness** on real NCE hardware. It does NOT validate:

- **Turnout, sensor, route, light, or memory hardware behavior.** Those are covered by the integration tests in step 4 of the checklist (which run against the simulator for v1). Per the Limitations section in `README.md`, NCE is open-loop — there is no electronic signal confirming a turnout physically moved. The maintainer may choose to spot-check turnout commands against the real layout during a release, but this is a judgment call per release, not a required gate.
- **Long-run hardware stability.** The one-hour long-run test (step 5) runs against the simulator. Headless-JMRI hardware CI is Growth-deferred.

Two cross-references this procedure satisfies:

- `tests/integration/test_throttle_lifecycle.py:19-24` forward-references "the hardware-mode validation protocol in `CONTRIBUTING.md`'s release checklist" — this section is that protocol.
- The TODO at `throttle.py:316-345` (seeded by Story 5.1) is the data point this section's keep-alive observation step updates.
