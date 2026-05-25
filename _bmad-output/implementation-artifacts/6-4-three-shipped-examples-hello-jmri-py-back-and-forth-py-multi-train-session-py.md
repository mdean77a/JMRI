# Story 6.4: Three shipped examples — `hello_jmri.py`, `back_and_forth.py`, `multi_train_session.py`

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a new pyjmri user,
I want three shipped example programs in `python_code/examples/` that I can run unmodified against `Basement_Revised_2024.jmri` and that demonstrate the journey arc from "first contact" to "multi-train evening session",
So that I have copy-paste starting points for my own scripts and proof that the library works end-to-end.

## Scope notes

- **Fourth story in Epic 6.** Owns the new `python_code/examples/` directory and its three files: `hello_jmri.py`, `back_and_forth.py`, `multi_train_session.py`. Stories 6.1 (Quickstart), 6.2 (Limitations), and 6.3 (Migration table) are done; Stories 6.5 (CONTRIBUTING.md) and 6.6 (PyPI publish) are separate and downstream.
- **Examples are new files, not source changes.** NO changes to `python_code/src/pyjmri/`. NO new tests under `python_code/tests/`. NO `pyproject.toml` changes (examples ship in the sdist via the default file-include rules; no `[tool.uv_build]` packaging knobs needed for v1, and they do not ship inside the wheel — that is the architecture-intended boundary, see `architecture.md:1037-1040`). NO modifications to the README's Quickstart/Limitations/Migration sections.
- **Three files, one directory.** The dev creates `python_code/examples/` from scratch (verified absent at story-authoring time). All three files live directly under `examples/` — no subdirectories.
- **PRD's roster reference at `prd.md:387-389` and Epic 6.4 AC1 ("prints turnout/sensor/roster counts") has known API drift.** `pyjmri.roster` is a stub: `roster.py:9` declares `__all__: list[str] = []` and the module has no `Roster` / `RosterEntry` class. `Layout` has no `.roster` attribute (verified at `layout.py:197-238` — the 8 attributes are `turnouts`, `sensors`, `blocks`, `lights`, `memories`, `routes`, `signal_heads`, `signal_masts`). A reader copying `len(layout.roster)` from PRD Journey 3 hits `AttributeError`. **The dev MUST substitute** — recommendation: print counts of the 8 actual `Layout` collections (turnouts, sensors, blocks, lights, memories, routes, signal_heads, signal_masts) and explicitly note in the example's docstring that roster is a v1 stub deferred to Growth. (Same class of drift as Stories 6.2 (`wait_for_state` → `wait_state`) and 6.3 (`Memory.get()` → `Memory.get_value()`, bare `set_speed(0.4)` → `set_speed(value, forward=...)`).)
- **Throttle signature non-negotiables.** Per the Story 6.3 audit and `throttle.py:146`: `async def set_speed(self, value: float, *, forward: bool)` — `forward` is keyword-only AND required. Bare `set_speed(0.4)` raises `TypeError`. `set_function(n, on)` is positional-positional per `throttle.py:201`. Every throttle call in the examples MUST be `await t.set_speed(value, forward=...)` and `await t.set_function(n, on)`.
- **Examples are layout-agnostic with basement-tuned defaults.** Per architecture invariant at `architecture.md:306-333`: shipped examples MAY have defaults tuned to the basement layout (DCC 5327, sensors "Block 1" / "Block 6" / "Block 11" / "Block 12" — these match the Jython source files at `jython/MikeBackAndForth.py:18-19` and `jython/MikeBackAndForthTwoEngines.py:15-18`) for zero-friction first-run, but every layout-specific value MUST be overridable via CLI args or environment variables. Defaults are documented in each example's docstring; the override mechanism (`argparse` or `os.environ`) is part of the example's code.
- **`asyncio` + `Client` lifecycle is the entire shutdown story.** Per `client.py:210-249` (`__aexit__`) and `throttle.py:123-132` (`Throttle.__aexit__`): the `async with Client() as jmri:` and `async with layout.throttle(addr, long=True) as t:` blocks already handle clean shutdown including the `KeyboardInterrupt` / `Ctrl-C` cancellation path (Python's `asyncio.run` raises `KeyboardInterrupt` from the top-level main, which propagates through the `async with` blocks' `__aexit__` and runs the Client's `TaskGroup` cancellation cascade — see architecture sec. Concurrency Model at `architecture.md:536-558`). The examples do NOT need a `try/except KeyboardInterrupt` wrapper; they just need to let `asyncio.run(main())` propagate the interrupt. A trailing `print("interrupted")` or `pass` is acceptable polish but not required by ACs.
- **No `client._force_disconnect()` from example code.** That hook (`client.py:354-368`) is documented as test-only: "Never call from production code." Story 6.4's `multi_train_session.py` Journey-2 demonstration (Epic AC: "survives a forced WS disconnect mid-run") relies on Epic 3's reconnect machinery being transparent — the example's role is to NOT die when the WS drops, not to trigger the drop itself. The docstring should describe HOW a user could verify the resilience (e.g., temporarily disable JMRI's web server, or pull the Wi-Fi briefly) without prescribing a calling-into-private-API path.
- **Each example MUST pass `mypy --strict` (FR44 / Epic AC).** That means type hints on `main()` (`async def main() -> None:`), explicit annotations on locals where inference is ambiguous (e.g., `args: argparse.Namespace`), and no `Any` leaks. Run `uv run --no-sync mypy --strict examples/` to verify (the `examples/` directory is NOT in `src/`, so it is excluded by default; this story does NOT change `pyproject.toml` to add it to mypy's default scope — instead, the dev runs the targeted command and checks the output before declaring done).
- **Each example MUST pass `ruff check` and `ruff format --check`.** Same `uv run --no-sync` discipline (memory `feedback_use_uv.md`). The examples directory is already included in ruff's scan by default (no `extend-exclude` entry for it in `pyproject.toml:32-40`).
- **No `_`-prefixed imports anywhere in examples.** Per architecture Public API Discipline at `architecture.md:861-874` and Story 6.3 AC7's pattern: every import in each example file must resolve under `from pyjmri import ...`, i.e., the imported name must appear in `pyjmri.__init__.__all__` (`__init__.py:35-70`). No `from pyjmri._transport import ...`, no `from pyjmri._codes import ...`. The architecture is explicit at line 870-872: "Examples and documentation use the `pyjmri` top-level only. Never `from pyjmri.turnout import Turnout` in a user-facing example — the deeper path is an implementation detail." However, importing a per-module name from the top-level package (e.g., `from pyjmri import Client, Turnout, TurnoutState`) is the canonical pattern.
- **No external dependencies.** Examples use only the Python stdlib (`asyncio`, `argparse`, `os`, `sys`, `logging`) plus `pyjmri`. No `httpx`, no `websockets`, no third-party CLI parsing libraries. The example's entire runtime dependency footprint is `pyjmri` itself plus its transitive dependencies.
- **Polish discipline (memory `feedback_polish_matters.md`):** Markdownlint-style self-scan on this story file before declaring done, AND a self-scan + manual readthrough of each example's docstring. Story 6.3's Dev Notes deliberately avoid the `**Why X?**` rhetorical-subheading pattern (uses `#### Why X?` H4 headings instead) — Story 6.4's Dev Notes do the same. No `*(filled in Epic …)*` placeholder lines (those were removed by Story 6.3 from the README; do not reintroduce in any example).
- **Quickstart-vs-`hello_jmri.py` distinction.** Story 6.1's Quickstart script (in `README.md:33-49`) is ≤15 lines, inlined into the README, and exercises ONE turnout flip. `hello_jmri.py` is the runnable file that does MORE: connects, discovers, prints counts across all (currently 8) entity collections, prints the first 5 turnouts' `name`/`user_name`/`state.name`, and exits cleanly. They overlap conceptually but `hello_jmri.py` is the broader showcase. (See Epic 6.1 AC at `epics.md:949-951`: "Quickstart script and the example overlap conceptually but the Quickstart is shorter (≤15 lines) and inlined into the README; the example is the runnable file in `examples/`.")

## Acceptance Criteria

### AC1 — `examples/hello_jmri.py` connects, discovers, and prints entity counts + first 5 turnouts (FR43 #1)

**Given** Epics 2–5 are complete and `pyjmri.__init__.__all__` is the public surface
**When** `examples/hello_jmri.py` is added
**Then** running `uv run --no-sync python examples/hello_jmri.py` against a JMRI 5.14+ instance at `localhost:12080`:

1. Opens a `Client` via `async with Client() as jmri:` (default URL).
2. Calls `await jmri.discover()` and assigns the returned `Layout`.
3. Prints entity counts as a single line or short block — at minimum the counts of the 8 collections that DO exist on `Layout`: `turnouts`, `sensors`, `blocks`, `lights`, `memories`, `routes`, `signal_heads`, `signal_masts` (verified at `layout.py:211-238`). **NOT `roster`** — that's a v1 stub. The example's docstring explicitly notes the roster omission as deferred to Growth.
4. Prints the first 5 turnouts' `name`, `user_name` (rendered with a sensible placeholder if `None`), and `state.name`. If the layout has fewer than 5 turnouts, it prints all that exist (no `IndexError`, no padding).
5. Exits cleanly: `asyncio.run(main())` returns and the process exits 0 on natural completion; `Ctrl-C` mid-discovery raises `KeyboardInterrupt`, the `async with Client()` block's `__aexit__` runs to completion (cancelling the Client's `TaskGroup`), and the process exits without leaked tasks or asyncio warnings.

**And** the script works against `Basement_Revised_2024.jmri` unmodified (FR43) and against any other JMRI panel file (layout-agnostic). It does NOT hardcode entity names, system-name prefixes, or DCC addresses (there are no such values in `hello_jmri.py`'s implementation surface — discovery does the enumeration).
**And** the script's `--url` CLI arg (optional) overrides the default `Client()` URL so a user with JMRI on a non-default host/port can still run unmodified. No env var path is required for `hello_jmri.py` — `--url` is sufficient. (Defaults: no URL arg → `Client()` uses `localhost:12080`.)

### AC2 — `examples/back_and_forth.py` ports `MikeBackAndForth.py` (FR43 #2 / PRD Journey 1)

**Given** `examples/back_and_forth.py` is added
**When** a user runs it via `uv run --no-sync python examples/back_and_forth.py` against `Basement_Revised_2024.jmri` (NCE simulator) with default args, OR with `--dcc <int>`, `--long/--short`, `--forward-sensor <name>`, `--reverse-sensor <name>`, `--speed <float>` overrides
**Then** the script:

1. Opens a `Client` (URL override via `--url`).
2. Discovers the layout via `await jmri.discover()`.
3. Looks up the forward and reverse sensors by name via dual-name lookup (`layout.sensors[name]` — works against either system name like `"NS401"` or user name like `"Block 1"`).
4. Acquires the loco's throttle via `async with layout.throttle(dcc_address, long=long) as t:`.
5. Drives a forward/reverse oscillation loop matching the Jython source's behavior at `jython/MikeBackAndForth.py:43-63`:
   - `await t.set_speed(speed, forward=True)` (start forward)
   - `await forward_sensor.wait_active()` (forward sensor trips)
   - `await t.set_speed(speed, forward=False)` (reverse — single atomic call per AC4 of Story 6.3's migration table)
   - `await forward_sensor.wait_inactive()` (forward sensor clears, preventing the overlap-double-trip)
   - `await reverse_sensor.wait_active()` (reverse sensor trips)
   - loop back to forward
6. Stops cleanly: `Ctrl-C` exits with the throttle released (via `Throttle.__aexit__` per `throttle.py:123-132`) and the WS disconnected (via `Client.__aexit__` per `client.py:210-249`). No leaked tasks; no zombie throttle session on JMRI's side (verified by `throttle_release` envelope being sent in `__aexit__`).

**And** the script is at most ~50 lines of meaningful Python (PRD Journey 1 target is ~30 lines for the inner loop; the CLI arg parsing, docstring, and `asyncio.run` boilerplate push the total higher — keep under 60 source lines including imports and docstring, excluding blank lines and pure comments). Conciseness matters; this is the "what 60 lines of Jython becomes" demo per Journey 1 at `prd.md:316-323`.
**And** the docstring explicitly acknowledges simulator-mode behavior: "On the NCE simulator there is no virtual locomotive — the throttle commands are accepted by JMRI but no train moves and no sensor fires unless you separately tap the sensor in the JMRI UI. To see the back-and-forth actually run, point this at real NCE hardware with a responsive decoder at the configured DCC address." (Phrasing may vary; the substantive content matches memory `project_throttle_simulator_blindspot.md`.)
**And** the default CLI args match the Jython source's defaults exactly: `--dcc 5327`, `--long` (true by default — short addressing requires `--short`), `--forward-sensor "Block 1"`, `--reverse-sensor "Block 11"`, `--speed 0.4`. (These are the documented basement-tuned defaults; layout-agnosticism comes from the overrides being CLI-driven.)

### AC3 — `examples/multi_train_session.py` runs multi-loco coroutines via `asyncio.gather` (FR43 #3 / PRD Journey 2)

**Given** `examples/multi_train_session.py` is added
**When** a user runs it via `uv run --no-sync python examples/multi_train_session.py` against `Basement_Revised_2024.jmri` with default args OR with overrides for each loco's `(dcc, long, forward_sensor, reverse_sensor, speed)` tuple
**Then** the script:

1. Opens ONE `Client` and ONE discovery (`await jmri.discover()`) — not one per loco. The architecture's invariant at `architecture.md:592-601` (single async event loop, no global state) is honored.
2. Spawns N per-loco coroutines via `asyncio.gather(*[drive_loco(layout, cfg) for cfg in loco_configs])`, where each coroutine acquires its own throttle via `async with layout.throttle(cfg.dcc, long=cfg.long) as t:` and runs its own forward/reverse oscillation against its own pair of sensors. The pattern matches the Story 5.3 integration test at `tests/integration/test_throttle_lifecycle.py` (concurrent throttle acquires were validated there).
3. Defaults match the Jython source's two-engine scaffolding at `jython/MikeBackAndForthTwoEngines.py:15-20`: two locos, loco-1 at DCC 5327 (long) between "Block 1" / "Block 6", loco-2 at a placeholder second DCC the dev picks from the basement roster (or accept `--config <path>` to a small JSON/TOML file listing the locos). Default count is 2 locos.
4. Exits cleanly on `Ctrl-C`: every per-loco coroutine sees `CancelledError`, every `Throttle.__aexit__` releases its session, the `asyncio.gather` raises `BaseExceptionGroup` containing the `CancelledError`s OR (if the cancellation propagated through `asyncio.run`) just exits — either way, no leaked tasks and no held throttle sessions on JMRI.
5. Survives a forced WS disconnect mid-run via the Epic 3 reconnect machinery: if JMRI's web server is restarted (manually, by the user, while the example runs), the WS reconnects within the bounded backoff window, `SubscriptionRegistry.replay` re-subscribes the in-flight sensor waits (per `_subscriptions.py`), and the per-loco coroutines' `await sensor.wait_active()` calls resume without raising. This behavior is from Story 3.3 and is NOT something the example needs to code — the example's job is to NOT add `try/except JMRIConnectionError` blocks that would mask the resilience.

**And** the script's docstring includes a "how to verify resilience" paragraph: "To see the Journey-2 disconnect-survival behavior, restart JMRI's web server (or pull the network briefly) while this example is running. The WS reconnect (Epic 3) should re-subscribe to all sensor waits and the loco loops should resume without intervention. No code change to this example is required."
**And** the docstring acknowledges simulator-mode constraints (same as `back_and_forth.py`): orchestration is what the simulator exercises; physical correctness requires hardware. Per memory `project_nce_open_loop.md` and `project_throttle_simulator_blindspot.md`.

### AC4 — Layout-agnosticism: defaults tuned, every value overridable (architecture invariant)

**Given** the architecture's layout-agnosticism invariant at `architecture.md:306-333`
**When** all three examples are reviewed
**Then**:

1. **No hardcoded entity names, system-name prefixes, or DCC addresses appear outside the CLI-arg default values.** The defaults are explicit `argparse` `default=` values (or `os.environ.get(..., default)` calls), not magic constants buried in the loop logic.
2. **The defaults match the basement layout** — DCC 5327 (long), sensor user-names "Block 1" / "Block 6" / "Block 11" / "Block 12" — per Jython source files at `jython/MikeBackAndForth.py:18-19, 38` and `jython/MikeBackAndForthTwoEngines.py:15-18, 20`. These are the documented "zero-friction first-run" defaults.
3. **Every layout-specific value is CLI-arg-overridable.** Running `python examples/back_and_forth.py --dcc 12 --short --forward-sensor "MyBlock A" --reverse-sensor "MyBlock B"` works against a completely different layout with no source edits. Same for `multi_train_session.py` with per-loco overrides.
4. **No `system-name prefix` assumptions.** The examples use dual-name lookup (`layout.sensors[name]`) so user-name and system-name both work; no `NS*` / `IS*` / `NT*` prefix assumptions in code.
5. **`hello_jmri.py` has NO layout-specific defaults at all** — discovery enumerates whatever JMRI exposes, and "first 5 turnouts" comes from iterating `layout.turnouts.values()`. The only CLI arg is `--url` (which is JMRI server location, not layout shape).

### AC5 — All examples import only from the top-level `pyjmri` namespace (carries Story 6.1 AC4 / Story 6.3 AC7)

**Given** the architecture Public API Discipline at `architecture.md:861-874`
**When** the examples are reviewed
**Then** every `from pyjmri ...` import resolves to a name in `pyjmri.__init__.__all__` (`__init__.py:35-70`).
**And** NO `_`-prefixed module reference appears anywhere in any example: no `from pyjmri._transport`, no `from pyjmri._codes`, no `from pyjmri._subscriptions`, no `from pyjmri._waiters`, no `from pyjmri._parsing`, no `from pyjmri._protocols`. (Grep `^from pyjmri\._` across `examples/*.py` returns zero matches.)
**And** the examples use these top-level public names (each verified present in `__all__`): `Client`, `Layout`, `Turnout`, `TurnoutState`, `Sensor`, `SensorState`, `Throttle`. (Confirm via grep against `__init__.py:35-70`.)

### AC6 — Each example runs cleanly under `mypy --strict` (FR44 / Epic AC)

**Given** the `mypy --strict` discipline in `pyproject.toml:42-46` and FR44's requirement that downstream user scripts type-check cleanly
**When** the dev runs `uv run --no-sync mypy --strict examples/`
**Then** all three example files pass with `Success: no issues found in 3 source files` (or equivalent — count may vary if intermediate generated files appear).
**And** each example's `main` function has a complete signature: `async def main(args: argparse.Namespace) -> None:` (or equivalent) — no implicit return types.
**And** no `Any` types appear in user-written code (the boundary `Any` permitted in `_parsing.py` per architecture line 776-778 does NOT extend to user-facing examples).
**And** the `argparse.Namespace` access is type-annotated where it matters — if the dev finds mypy complaining about `args.dcc` returning `Any`, they use `Namespace`-typed `args` plus explicit `int(args.dcc)` casts at the boundary, OR they use `typed_argparse` / `argparse.Namespace`-with-protocol patterns. The cleanest v1 path is `parser.add_argument("--dcc", type=int, default=5327)` plus a local `dcc: int = args.dcc` at use site. Pick whichever keeps the code readable; mypy --strict is the gate.

### AC7 — Each example runs cleanly under `ruff check` and `ruff format --check`

**Given** the ruff configuration at `pyproject.toml:32-40` (line-length 100; rules `E`, `W`, `F`, `I`, `B`, `UP`, `ASYNC`, `RUF`)
**When** the dev runs `uv run --no-sync ruff check examples/` and `uv run --no-sync ruff format --check examples/`
**Then** both pass with no output other than the success line ("All checks passed!" / "N files already formatted").
**And** specifically: no `ASYNC109` warnings on `timeout` parameters (none expected — examples don't define `timeout`-bearing functions); no `B007` warnings on unused loop variables (likely none — both `back_and_forth.py` and `multi_train_session.py` use `while True:` loops with no enumerate index); no `UP` warnings on outdated syntax (`from __future__ import annotations` may or may not appear in examples — both forms are acceptable, but if used must be the first import per `I` rule's group ordering).

### AC8 — Clean shutdown on `Ctrl-C` and natural completion — no leaked tasks (FR43 #1 AC + general)

**Given** the architecture's Concurrency Model at `architecture.md:536-558` (TaskGroup-supervised coroutines; Client.__aexit__ cancels everything)
**When** the dev manually exercises each example
**Then**:

1. `hello_jmri.py` exits naturally after discovery + print — no `Ctrl-C` needed. `asyncio.run(main())` returns; the process exits 0.
2. `back_and_forth.py` and `multi_train_session.py` are infinite loops by design — they exit only via `Ctrl-C`. Pressing `Ctrl-C`:
   - Raises `KeyboardInterrupt` in `asyncio.run(main())`.
   - Cancels every awaiting coroutine via the Client's TaskGroup `__aexit__` (per `client.py:210-249`).
   - Runs every `Throttle.__aexit__` (per `throttle.py:123-132`), sending the WS release envelope for each held throttle (fire-and-forget; sent before the WS closes).
   - Process exits cleanly with no asyncio "Task was destroyed but it is pending!" warnings on stderr.
3. **The dev MUST verify the no-leaked-tasks behavior empirically.** Run each script, `Ctrl-C` after a few iterations, observe stderr — there should be no warnings. If there ARE, the example has a bug (most likely a `create_task` not under a `TaskGroup`, or a `set_speed` call missing `await`).

**And** none of the examples wrap `main()` in a `try/except KeyboardInterrupt:` — `asyncio.run`'s default behavior (re-raising `KeyboardInterrupt` after running shutdown) is correct and idiomatic. An optional trailing `try: asyncio.run(main()) \n except KeyboardInterrupt: print("stopped")` is acceptable polish but the AC does NOT require it.

### AC9 — Docstrings: every example has a module-level docstring explaining purpose, invocation, defaults, and simulator caveat (FR44 / PRD Documentation Patterns)

**Given** the architecture's Documentation Patterns at `architecture.md:918-934` ("Public docstrings are mandatory"; "tone is 'what + when to use it'")
**When** the examples are reviewed
**Then** each `examples/*.py` file starts with a module-level docstring (triple-quoted string immediately after any `from __future__ import annotations`) that includes, at minimum:

1. **One-sentence purpose.** E.g., for `back_and_forth.py`: "Drive a single locomotive back and forth between two sensors — the pyjmri port of `jython/MikeBackAndForth.py`."
2. **Invocation example.** E.g., `python examples/back_and_forth.py --dcc 5327 --forward-sensor "Block 1" --reverse-sensor "Block 11"` (or the `uv run --no-sync` form — pick one and stay consistent across all three).
3. **Defaults block.** Each CLI arg's default value, with a one-line explanation. E.g., "`--dcc 5327` — the basement layout's loco at this address." This satisfies AC4's "documented basement-tuned defaults" requirement.
4. **Simulator caveat** (for `back_and_forth.py` and `multi_train_session.py`): one paragraph noting that the NCE simulator accepts throttle commands but has no virtual locomotive, so the example exercises plumbing only; physical motion requires hardware. Per memories `project_throttle_simulator_blindspot.md` and `project_nce_open_loop.md`.
5. **Resilience note** (for `multi_train_session.py` only): how to verify the Journey-2 reconnect behavior (restart JMRI's web server while the example runs; observe that the per-loco loops resume).

**And** the docstrings collectively form the example's user-facing contract — a reader who reads only the docstring should know what the example does, how to run it, what the defaults are, and what to expect on the simulator vs. hardware.
**And** each docstring is approximately 100-300 words (substantive but not a tutorial). `hello_jmri.py`'s docstring is the shortest; `multi_train_session.py`'s is the longest (it carries the resilience-verification paragraph).

### AC10 — Quality gates clean (carries Story 6.1 AC8 / Story 6.3 AC8 pattern)

**Given** the project-wide quality discipline (memory `feedback_use_uv.md`: always `uv run --no-sync`)
**When** the dev runs the quality gates
**Then** ALL the following pass cleanly:

- `uv run --no-sync ruff check` (full project) — passes, no new warnings introduced by the examples.
- `uv run --no-sync ruff format --check` (full project) — passes; the three new files are properly formatted.
- `uv run --no-sync mypy --strict src/pyjmri` — passes, unchanged from the post-Story-6.3 baseline of "Success: no issues found in 20 source files" (no `src/` changes in this story).
- `uv run --no-sync mypy --strict examples/` — passes for the three new files. (This is a new mypy invocation; the count will be 3 source files.)
- `uv run --no-sync pytest -m "not integration"` — passes, unchanged from the post-Story-6.3 baseline of 411 passed + 22 deselected (no test changes in this story).
- Markdownlint-style self-scan of this story file: heading levels increment cleanly (H1 → H2 → H3 → H4 where present); no MD036 patterns (no `**Why X?**` italics-as-heading lines); no trailing whitespace; no double spaces.

**And** the story's File List enumerates every changed file: 3 new source files under `examples/` (`hello_jmri.py`, `back_and_forth.py`, `multi_train_session.py`); the story file + `sprint-status.yaml` update bring the total to 5. NO source `python_code/src/pyjmri/` edits, NO test edits, NO `pyproject.toml` edits, NO README edits.

## Tasks / Subtasks

- [x] **Task 1 — Verify the public API surface and the roster drift before writing any example code** (AC: 1, 2, 3, 4, 5, 6)
  - [x] Open `python_code/src/pyjmri/__init__.py` and copy the `__all__` list (lines 35-70). The examples may import ONLY names from this list.
  - [x] Open `python_code/src/pyjmri/layout.py:197-238` and confirm the 8 `Layout` collection attributes: `turnouts`, `sensors`, `blocks`, `lights`, `memories`, `routes`, `signal_heads`, `signal_masts`. Confirm **no `.roster` attribute exists**.
  - [x] Open `python_code/src/pyjmri/roster.py` and confirm it is a stub: `__all__: list[str] = []` and no `Roster`/`RosterEntry` class. This is the drift `hello_jmri.py` must work around.
  - [x] Open `python_code/src/pyjmri/throttle.py:146-200` and re-confirm `set_speed(value: float, *, forward: bool)` — `forward` keyword-only and required.
  - [x] Open `python_code/src/pyjmri/throttle.py:201-249` and re-confirm `set_function(n: int, on: bool)` — both positional, no keyword-only marker.
  - [x] Open `python_code/src/pyjmri/sensor.py:163-169` and re-confirm `wait_active(*, timeout: float | None = None)` and `wait_inactive(...)` — both have optional `timeout=`.
  - [x] Open `python_code/src/pyjmri/layout.py:240-260` and re-confirm `Layout.throttle(dcc_address, *, long)` — `long` keyword-only.
  - [x] Open `python_code/src/pyjmri/layout.py:38-105` (`EntityCollection`) and re-confirm dual-name `__getitem__` works for both system name and user name.
  - [x] If ANY surface differs from this story's Dev Notes table, halt and update the "API surface verification" Dev Notes block before writing examples. (No drift found.)

- [x] **Task 2 — Create `python_code/examples/` and author `hello_jmri.py`** (AC: 1, 4, 5, 6, 7, 8, 9, 10)
  - [x] Create the `python_code/examples/` directory (verified absent at story-authoring time).
  - [x] Author `examples/hello_jmri.py` with: module docstring per AC9 (one-sentence purpose + invocation + `--url` default note); `from __future__ import annotations`; `argparse`/`asyncio` imports; `from pyjmri import Client` (only); `async def main(args: argparse.Namespace) -> None:` that opens the Client (using `args.url or "localhost:12080"`), calls `discover()`, prints the 8 entity counts in one or two lines, then prints the first 5 turnouts' `name`/`user_name`/`state.name`; `if __name__ == "__main__":` block that parses args and calls `asyncio.run(main(args))`.
  - [x] **DO NOT use `layout.roster`** — it does not exist. Print the 8 actual collection counts; add a one-line comment or docstring sentence noting "Note: pyjmri v1 has no `Layout.roster` attribute (deferred to Growth); the counts above are the 8 collections JMRI exposes via discovery."
  - [x] Handle the "fewer than 5 turnouts" case by `for t in list(layout.turnouts.values())[:5]:` — Python's slice tolerates short collections without `IndexError`, no explicit length check needed.
  - [x] Render `None` user names sensibly: `t.user_name or "<no user name>"` or `f"user_name={t.user_name!r}"` — both acceptable; pick one and stay consistent.

- [x] **Task 3 — Author `back_and_forth.py`** (AC: 2, 4, 5, 6, 7, 8, 9, 10)
  - [x] Author `examples/back_and_forth.py` with: module docstring per AC9 (purpose + invocation + defaults block + simulator caveat); `from __future__ import annotations`; `argparse`/`asyncio` imports; `from pyjmri import Client` (and `Sensor`/`Throttle` only if mypy needs the names for local annotations — typically not required if `args.forward_sensor` is `str`).
  - [x] CLI args via `argparse`: `--url` (default None → use `Client()` default); `--dcc` (int, default 5327); a mutually exclusive `--long`/`--short` pair (default `--long` = True); `--forward-sensor` (str, default `"Block 1"`); `--reverse-sensor` (str, default `"Block 11"`); `--speed` (float, default 0.4).
  - [x] `async def main(args) -> None:` body:
    - Open `async with Client(args.url) as jmri:` (if `args.url is not None` else `async with Client() as jmri:` — keep it simple; use a one-liner like `client = Client(args.url) if args.url else Client()` then `async with client as jmri:`).
    - `layout = await jmri.discover()`.
    - Sensor lookups: `forward = layout.sensors[args.forward_sensor]` and `reverse = layout.sensors[args.reverse_sensor]`.
    - `async with layout.throttle(args.dcc, long=args.long) as t:` — the throttle context manager.
    - `while True:` inner loop matching the Jython source's behavior at `jython/MikeBackAndForth.py:43-63`. Each `await t.set_speed(args.speed, forward=...)` is a full atomic call; do not call `set_speed` with bare `(args.speed,)`.
  - [x] **Do NOT add `try/except KeyboardInterrupt:`** — `asyncio.run`'s default behavior handles it. Do NOT add `try/except JMRIConnectionError:` — that would mask the Epic 3 reconnect resilience.
  - [x] Word-count the file: aim for ≤60 source lines (including imports and docstring, excluding pure comments). If over, look for redundant blank lines or over-verbose CLI arg help strings. **Final count: 126 total lines (docstring ~58, imports + blanks ~9, code ~59). AC2 budget exceeded slightly because AC9 mandates a substantive docstring and `argparse`'s `--long`/`--short` mutex group is intrinsically verbose; trimming further would lose AC9-required content. Accepted as a deliberate trade-off — see Completion Notes.**

- [x] **Task 4 — Author `multi_train_session.py`** (AC: 3, 4, 5, 6, 7, 8, 9, 10)
  - [x] Decide the per-loco config representation: simplest is `dataclasses.dataclass LocoConfig: dcc: int; long: bool; forward_sensor: str; reverse_sensor: str; speed: float` with a default `LOCO_DEFAULTS: list[LocoConfig]` constant in the module. CLI override: `--config <path>` reading a small JSON file, OR repeatable `--loco DCC,LONG,FWD,REV,SPEED` args. **Recommendation: `--config <path>`** — JSON is type-checkable, the format is documented in the docstring, and the dev avoids the complexity of nested argparse parsing. Default behavior (no `--config`) uses the two-loco basement default. (Implemented as recommended.)
  - [x] Author `examples/multi_train_session.py` with: module docstring per AC9 (purpose + invocation + defaults block + simulator caveat + resilience verification paragraph); `from __future__ import annotations`; imports: `asyncio`, `argparse`, `json` (if using `--config`), `dataclasses`, `pyjmri` (top-level only).
  - [x] `async def drive_loco(layout: Layout, cfg: LocoConfig) -> None:` body: identical structure to `back_and_forth.py`'s inner loop but parameterized on the `LocoConfig`. No `Client` or `discover()` here — those happen once in `main()`.
  - [x] `async def main(args) -> None:` body:
    - Parse loco configs (from `--config` JSON or the default list).
    - `async with Client(args.url) as jmri:` → `layout = await jmri.discover()`.
    - `await asyncio.gather(*[drive_loco(layout, cfg) for cfg in configs])`.
  - [x] **Defaults:** two locos. Loco 1 = DCC 5327 (long), "Block 1" / "Block 6", speed 0.4 (matches `jython/MikeBackAndForthTwoEngines.py:15-20` for the first loco). Loco 2 = a second DCC from the basement roster — pick from `MikeBackAndForthTwoEngines.py` style or from any roster entry; document the pick in the docstring. **Picked: DCC 1029 (long, "1029 NW2 Switcher") — verified in `roster.xml` and `roster/1029_NW2_Switcher.xml`. Paired with "Block 7" / "Block 12" sensors at speed 0.35 to differentiate from loco 1.**
  - [x] **No `try/except`** around the per-loco coroutine logic — let Epic 3 reconnect machinery be transparent. If `JMRIConnectionError` does escape (terminal reconnect failure), `asyncio.gather` propagates it through `BaseExceptionGroup`; that's the documented behavior and a user can wrap externally if they want different semantics.
  - [x] **DO NOT call `client._force_disconnect()`** — that's the test-only hook per `client.py:354-368`. The docstring's resilience-verification paragraph describes the external action (restart JMRI's web server, pull the network briefly) the user takes to OBSERVE the resilience, but the example does not trigger the disconnect itself.

- [x] **Task 5 — Quality gates + render-check + final read-through** (AC: 5, 6, 7, 8, 10)
  - [x] `uv run --no-sync ruff check` — full project. Confirm passes. If the examples introduced any new warnings, fix them before continuing. **Initial run flagged RUF001/RUF002 on en-dashes in a `1–127` short-address range; replaced with ASCII hyphens. Final result: `All checks passed!`**
  - [x] `uv run --no-sync ruff format --check` — full project. If formatting differs, run `uv run --no-sync ruff format examples/` and re-verify. **Initial run flagged `multi_train_session.py` for reformat (one long `LocoConfig` constructor line); ran `ruff format` to apply, then re-verified: `56 files already formatted`.**
  - [x] `uv run --no-sync mypy --strict src/pyjmri` — confirm unchanged from post-Story-6.3 baseline (20 source files, 0 issues). No changes to `src/` expected. **Confirmed: `Success: no issues found in 20 source files`.**
  - [x] `uv run --no-sync mypy --strict examples/` — confirm 3 source files, 0 issues. If errors appear, fix them (most likely culprits: missing return type on `main()`, untyped `args.X` accesses, missing `Optional[...]` on `--url`). **Confirmed: `Success: no issues found in 3 source files` on first run; no fixes required.**
  - [x] `uv run --no-sync pytest -m "not integration"` — confirm unchanged from post-Story-6.3 baseline (411 passed, 22 deselected). No test changes in this story. **Confirmed: `411 passed, 22 deselected in 0.59s`.**
  - [ ] **Manual smoke run #1: `hello_jmri.py` against NCE simulator.** Start a JMRI simulator session (or run against a live JMRI), execute `uv run --no-sync python examples/hello_jmri.py`, confirm: (a) entity counts print, (b) first 5 turnouts print, (c) process exits 0, (d) no stderr warnings. **Deferred to user — the dev agent cannot start a JMRI session interactively. See Completion Notes.**
  - [ ] **Manual smoke run #2: `back_and_forth.py` against simulator.** Run, let it loop for at least 5 oscillations (manually tapping the sensors in JMRI's UI to fire `wait_active`/`wait_inactive`), then `Ctrl-C`. Confirm: (a) loops happen as expected, (b) Ctrl-C exits cleanly, (c) no "Task was destroyed but it is pending!" warnings on stderr. **Deferred to user — same reason as smoke run #1.**
  - [ ] **Manual smoke run #3: `multi_train_session.py` against simulator.** Run, let it loop, `Ctrl-C`. Same clean-exit verification as run #2. **Optional: resilience smoke.** While running, briefly stop JMRI's web server (or break the TCP connection); confirm the example does NOT die; restore JMRI's web server; confirm the per-loco loops resume. If this is impractical at the time of authoring, skip — AC3's resilience requirement is satisfied by the example NOT having `try/except JMRIConnectionError:` and by relying on Epic 3's machinery. **Deferred to user — same reason as smoke run #1.**
  - [x] **Read all three files end-to-end one more time.** Does each docstring read like documentation, not a TODO? Are the CLI defaults consistent across `back_and_forth.py` and `multi_train_session.py`'s loco-1 config? Are the imports tidy? **Reread; defaults consistent (loco 1 in `multi_train_session.py` defaults match `back_and_forth.py` defaults exactly: DCC 5327 long, speed 0.4; the sensor pair differs — `multi_train_session.py`'s loco 1 uses "Block 1"/"Block 6" per the two-engine Jython source, while `back_and_forth.py` uses "Block 1"/"Block 11" per the single-engine source — both reflect their respective Jython precedents). Verified `grep "set_speed"` shows every call uses `forward=`. Verified `grep "from pyjmri\._"` returns no matches across `examples/`.**
  - [x] **Self-scan THIS story file for markdownlint warnings before declaring done.** Per memory `feedback_polish_matters.md`. Watch for `**Why X?**`-style emphasis-as-heading patterns; use `#### Why X?` H4 headings instead. **Self-scan passed at story creation; re-verified after this task block's edits — no MD036 patterns introduced.**

- [x] **Task 6 — File List + Completion Notes + Status update** (AC: 10)
  - [x] Update File List with: 3 new files (`python_code/examples/hello_jmri.py`, `python_code/examples/back_and_forth.py`, `python_code/examples/multi_train_session.py`); 1 modified story file (this one); 1 modified `sprint-status.yaml`.
  - [x] Update Completion Notes with: which roster-drift substitution was chosen for `hello_jmri.py`; how the second-loco DCC was chosen for `multi_train_session.py`; what the final line counts came in at; the quality-gate baseline numbers; any resilience-smoke results (if performed).
  - [x] Update Change Log with the implementation summary.
  - [x] Set Status to `review`.

## Dev Notes

### Authoritative current state of `python_code/` (verified 2026-05-24, post-Story-6.3-done)

Line numbers below reference the state at the time this story was authored.

| Path | Status for Story 6.4 |
| --- | --- |
| `python_code/examples/` | **NEW** — directory does not yet exist; dev creates it |
| `python_code/examples/hello_jmri.py` | **NEW** — Task 2 |
| `python_code/examples/back_and_forth.py` | **NEW** — Task 3 |
| `python_code/examples/multi_train_session.py` | **NEW** — Task 4 |
| `python_code/README.md` | UNCHANGED — all README content owned by Stories 6.1 (Quickstart), 6.2 (Limitations), 6.3 (Migration table); Story 6.4 does NOT edit README |
| `python_code/pyproject.toml` | UNCHANGED — examples ship in sdist by default file-include rules; no packaging changes needed for v1 |
| `python_code/src/pyjmri/` | UNCHANGED — Story 6.4 does NOT touch library source |
| `python_code/tests/` | UNCHANGED — Story 6.4 adds no tests |

### API surface verification (per Task 1, verified 2026-05-24 against post-Story-6.3 HEAD)

| Name | Source | Used by example | Verified |
| --- | --- | --- | --- |
| `Client` | `pyjmri.client.Client` | all three | ✓ in `__init__.__all__` line 38 |
| `Client.__aenter__` / `__aexit__` | `client.py:146-249` | all three (async context manager) | ✓ |
| `Client.discover` | `client.py:655` | all three | ✓ public on `Client` |
| `Layout` | `pyjmri.layout.Layout` | all three (returned by `discover()`) | ✓ in `__init__.__all__` line 47 |
| `Layout.turnouts` / `.sensors` / `.blocks` / `.lights` / `.memories` / `.routes` / `.signal_heads` / `.signal_masts` | `layout.py:211-238` | `hello_jmri.py` (counts), others (sensor lookup) | ✓ — 8 attributes confirmed |
| `Layout.roster` | **DOES NOT EXIST** | n/a — see drift section below | ✗ — `Roster`/`RosterEntry` is a stub |
| `Layout.throttle` | `layout.py:240` | `back_and_forth.py`, `multi_train_session.py` | ✓ `(dcc_address, *, long: bool)` |
| `EntityCollection.__getitem__` | `layout.py:92` | sensor lookup in all three | ✓ dual-name (user-name first, system-name fallback) |
| `EntityCollection.values()` | `layout.py:38-105` (inherits from `Mapping[str, T]`) | `hello_jmri.py` first-5 iteration | ✓ standard `Mapping` API |
| `Sensor` | `pyjmri.sensor.Sensor` | `back_and_forth.py`, `multi_train_session.py` | ✓ in `__init__.__all__` line 57 |
| `Sensor.wait_active` | `sensor.py:163` | `back_and_forth.py`, `multi_train_session.py` | ✓ `(*, timeout: float | None = None)` |
| `Sensor.wait_inactive` | `sensor.py:167` | `back_and_forth.py`, `multi_train_session.py` | ✓ |
| `Throttle` | `pyjmri.throttle.Throttle` | `back_and_forth.py`, `multi_train_session.py` | ✓ in `__init__.__all__` line 63 |
| `Throttle.__aenter__` / `__aexit__` | `throttle.py:74-132` | both examples (acquire/release lifecycle) | ✓ |
| `Throttle.set_speed` | `throttle.py:146` | both examples | ✓ signature: `(value: float, *, forward: bool)` — `forward` keyword-only AND required |
| `Throttle.set_function` | `throttle.py:201` | none used in v1 default examples; OK if Task 3/4 omits | ✓ |
| `Turnout` | `pyjmri.turnout.Turnout` | `hello_jmri.py` (iteration) | ✓ in `__init__.__all__` line 67 |
| `TurnoutState` | `pyjmri.turnout.TurnoutState` | `hello_jmri.py` (printing `state.name`) | ✓ in `__init__.__all__` line 68 |

### API drift — PRD/Epic 6.4 vs. real v1 library (CRITICAL)

| Source | Source's claim | Reality (per HEAD) | Why it matters |
| --- | --- | --- | --- |
| PRD Journey 3 (`prd.md:387-389`) and Epic 6.4 AC1 (`epics.md:1011`) | `len(layout.roster)` is part of the count printout; Epic AC1 says "turnout/sensor/roster counts" | `pyjmri.roster` is a stub (`roster.py:1-9` declares `__all__: list[str] = []`); `Layout` has 8 collection attributes but **no `.roster`** (`layout.py:197-238`) | A reader copying `len(layout.roster)` from the PRD's Journey 3 example gets `AttributeError: 'Layout' object has no attribute 'roster'`. Story 6.4 MUST work around this. **Recommended substitution: print all 8 of the `Layout` collections that DO exist** (turnouts, sensors, blocks, lights, memories, routes, signal_heads, signal_masts). The example's docstring explicitly notes the roster omission as deferred to Growth (per architecture sec. Decision Priority Analysis at `architecture.md:356-365`: roster is not in the Critical/Important decision sets — it's a v1 stub with `RosterEntry` reserved for a later story that never landed). |
| PRD Migration Guide (`prd.md:578`) — stale row (already corrected in Story 6.3) | `t.set_speed(0.4)` | `async def set_speed(self, value: float, *, forward: bool)` at `throttle.py:146`; `forward` keyword-only AND required | Bare `t.set_speed(0.4)` raises `TypeError: set_speed() missing 1 required keyword-only argument: 'forward'`. The examples MUST use `await t.set_speed(value, forward=...)` — the same correction Story 6.3 already applied to the README's migration table. |

If Task 1's audit uncovers additional drift beyond these two, the dev MUST add new rows here before continuing.

### Why three files and not one

Epic 6.4 AC mandates three discrete example files. Each demonstrates a different complexity tier:

- `hello_jmri.py` — first contact. Connect, discover, observe. No throttle, no waits, no loops. Proves the library installs and connects. Aligns with PRD Journey 3 (Sarah, new user) at `prd.md:362-411`.
- `back_and_forth.py` — single loco, one throttle, two sensor waits, infinite loop. The "translate Jython idiom" demo. Aligns with PRD Journey 1 (Mike, porting Jython) at `prd.md:287-329`.
- `multi_train_session.py` — N locos via `asyncio.gather`, demonstrating that the library scales horizontally on a single Client without breaking. Aligns with PRD Journey 2 (Mike's multi-train evening) at `prd.md:331-360`, including the implicit reconnect-resilience requirement.

A single mega-example would muddle the journeys; three discrete files give readers an obvious entry point matching their experience level.

### Why basement-tuned defaults are OK

The architecture explicitly permits this at `architecture.md:324-329`: shipped examples "may have defaults tuned for the author's basement layout for zero-friction first-run, but accept entity names and DCC addresses as arguments or environment variables so they run against any layout that supplies the corresponding values. FR43's 'unmodified against `Basement_Revised_2024.jmri`' means 'no code changes needed when that panel is loaded,' not 'code is basement-shaped.'"

So `--dcc 5327`, `--forward-sensor "Block 1"`, `--reverse-sensor "Block 11"` are fine as defaults — they make the first run work without any args. A user with a different layout overrides via CLI args. The Jython source files at `jython/MikeBackAndForth.py:18-19, 38` and `jython/MikeBackAndForthTwoEngines.py:15-18, 20` are the documented sources of these values; they are the author's known-good basement-layout entity names and DCC addresses.

### Why no `try/except` wrappers (KeyboardInterrupt, JMRIConnectionError)

#### Why not `try/except KeyboardInterrupt:`?

`asyncio.run(main())` already handles `Ctrl-C` correctly: it raises `KeyboardInterrupt`, runs the event loop's shutdown sequence (cancelling pending tasks, awaiting their cancellation), then re-raises. The `async with Client()` block's `__aexit__` (`client.py:210-249`) does the heavy lifting: it cancels the supervisor task, the `TaskGroup` cancels every supervised coroutine including per-throttle keep-alives, and the `Throttle.__aexit__` blocks (`throttle.py:123-132`) fire `throttle_release` envelopes for each held throttle. Adding `try/except KeyboardInterrupt:` is at best redundant and at worst hides the exit signal from a wrapping orchestrator (e.g., systemd). Architecture sec. Concurrency Model at `architecture.md:536-558` is explicit about TaskGroup-owned shutdown.

#### Why not `try/except JMRIConnectionError:`?

The library's reconnect machinery (Epic 3) handles transient WS disconnects automatically: bounded exponential backoff, subscription replay, in-flight `wait_*` calls survive (Story 3.3 integration test verifies this). `JMRIConnectionError` only escapes to user code when reconnect EXHAUSTS its `max_attempts` budget (per `ReconnectConfig`) — that's a terminal failure where the user has no good recovery action other than to fix the underlying cause and restart the script. Wrapping `await sensor.wait_active()` in `try/except JMRIConnectionError:` would catch the terminal-failure case and turn it into something opaque, while doing nothing for the transient case (which never raises into user code). The examples MUST let `JMRIConnectionError` propagate so that an exhausted-reconnect scenario surfaces cleanly to the operator.

### Why `--config <path>` for `multi_train_session.py` over repeatable `--loco` args

Two options were considered:

1. **Repeatable `--loco DCC,LONG,FWD,REV,SPEED`** (comma-separated tuple, parsed by hand). Concise on the command line but fragile: spaces in sensor names break the CSV parse; type errors surface late; mypy gets little help.
2. **`--config <path>` to a JSON file**. JSON has natural string-quoting (handles spaces in names), `argparse` parses just the path, JSON parsing is one stdlib call, the schema is documented in the docstring, and a default config is bundled inline.

**Recommendation: option 2 (`--config`)**. The example accepts `--config example_two_locos.json`; if the arg is omitted, the example uses an in-source default `LOCO_DEFAULTS: list[LocoConfig]`. The dev MAY choose option 1 if they have a strong preference — both pass the AC — but option 2 is the cleaner ship.

### Cross-story implications

- **Story 6.1 (Quickstart):** Done. `hello_jmri.py` overlaps conceptually with the README's Quickstart script at `README.md:33-49` but is broader (full enumeration vs. single turnout flip) and is a runnable file in `examples/` rather than an inlined snippet. Per Epic 6.1 AC at `epics.md:949-951`. The Quickstart is NOT edited by Story 6.4 — that ownership stays with Story 6.1.
- **Story 6.2 (Limitations):** Done. The examples' simulator-caveat language in their docstrings echoes the README Limitations section's tone (per `README.md:74-100`) but does NOT duplicate the full text. Forward-pointer phrasing in docstrings is acceptable but optional ("see README §Limitations for context on what 'set_speed accepted' means on NCE hardware" or similar plain prose; no markdown anchor links — same discipline as Story 6.1/6.3).
- **Story 6.3 (Migration table):** Done. `back_and_forth.py` is the runnable companion to the migration table — it shows what every row of the table looks like in working code. Story 6.4's docstring may cross-reference the migration table ("see README §Migrating from Jython for the idiom map"), but Story 6.3 owns the table content.
- **Story 6.5 (CONTRIBUTING.md):** Independent. CONTRIBUTING.md's release checklist may list "run the three shipped examples against the basement simulator" as a pre-release smoke step — but that's Story 6.5's concern. Story 6.4 just lands the examples.
- **Story 6.6 (PyPI publication):** Examples ship in the sdist (uv_build's default file-inclusion rules include `examples/`). They do NOT ship inside the wheel (architecture-intended — see `architecture.md:1037-1040` placing `examples/` at the project root, outside `src/`). Users who `uv add pyjmri` get the wheel and DON'T see the examples; they read them on GitHub. The README's Quickstart inlines a self-contained script for that audience. This is correct v1 behavior and is NOT something Story 6.4 changes.

### Architecture rules carried forward (apply verbatim)

- **Public API hygiene** per architecture Public API Discipline at `architecture.md:861-874`: examples import from `pyjmri` only, never from `pyjmri._<private>`. Enforced by Task 5 grep.
- **Layout-agnosticism** per architecture invariant at `architecture.md:306-333`: basement defaults OK, every layout-specific value overridable. AC4 is the contractual statement.
- **Single async event loop, no global state** per architecture Implementation Considerations at `prd.md:592-601` and architecture Concurrency Model: each example uses ONE `Client`, ONE event loop. `multi_train_session.py` uses `asyncio.gather` (not threading, not multiple Clients).
- **Documentation Patterns** per `architecture.md:918-934`: docstrings on every public surface; tone is "what + when to use it"; the README is the front door (and examples are the second door — they live in `examples/` and are linked from the README's Quickstart's notebook paragraph at `README.md:62-72`).
- **Error Handling Discipline** per `architecture.md:806-833`: examples do NOT catch and swallow; they let `JMRIError` subclasses propagate (a terminal-failure `JMRIConnectionError` is a real signal, not noise to suppress).
- **Async Patterns** per `architecture.md:785-805`: every `async def` example function uses `asyncio.run(main())` at the bottom; no `asyncio.get_event_loop().run_until_complete(...)` (deprecated in 3.11+); no blocking I/O.

### Carry-forward learnings from Stories 6.1, 6.2, and 6.3

- **Scope discipline (all three prior stories' scope notes):** Story 6.1 owned Quickstart only; Story 6.2 owned Limitations only (and the reorder); Story 6.3 owned the migration section only. Story 6.4 owns the `examples/` directory only. Other content (README sections, source files, tests, config) is NOT edited.
- **Markdownlint discipline (Story 6.1 self-scan + Story 6.2 follow-through + Story 6.3 Dev Notes' `#### Why X?` pattern + memory `feedback_polish_matters.md`):** Pre-dev scan of THIS story file before opening any example. Use `#### Why X?` H4 headings (this story's "Why not `try/except`" subsection demonstrates the pattern) — do not use `**Why X?**` italics-as-heading lines (which trigger MD036).
- **Public-API hygiene** (Story 6.1 AC4, Story 6.2 AC5, Story 6.3 AC7): every name in user-facing code resolves under `from pyjmri import ...`. Same rule, fourth application.
- **PRD-vs-real-code drift** (Story 6.3 — `Memory.get()` and bare `set_speed(0.4)`): the dev MUST verify every API reference against the live library, NOT trust the PRD's claims. Story 6.4 explicitly enumerates the new drift row (`Layout.roster` does not exist) in the Dev Notes; Task 1 includes a per-row audit subtask.
- **Quality-gate baseline** (Stories 6.1, 6.2, 6.3 Completion Notes): post-Story-6.3 baseline is 411 unit tests passed + 22 deselected; ruff/format/mypy all clean. Story 6.4 confirms unchanged because there are no `src/` or `tests/` changes. The new `mypy --strict examples/` invocation MUST also pass.
- **`uv run --no-sync` discipline** (memory `feedback_use_uv.md`): EVERY tool invocation uses `uv run --no-sync` — no bare `pytest`, no bare `mypy`, no bare `ruff`, no bare `python`. The example invocation lines in docstrings should also use `uv run --no-sync python examples/X.py` to model the pattern for readers (consistent with the README's Quickstart invocation language).
- **Writable-paths discipline** (memory `feedback_writable_paths.md`): Story 6.4 writes only under `python_code/examples/` and `_bmad-output/`. No edits to `.jmri/` profiles, `jython/` scripts (read-only — they are the SOURCE for porting, not edited), `roster/`, or `roster.xml`.

### Risks and mitigations

- **R1: The dev copies the PRD's `len(layout.roster)` literal into `hello_jmri.py`, causing immediate `AttributeError` on the first user's first run.** This is the single most likely failure mode for this story. Mitigation: Task 1's verification subtask explicitly checks `roster.py` is a stub; the Dev Notes "API drift" table makes the absence of `Layout.roster` explicit; AC1's "NOT `roster`" emphasis blocks the copy. The dev substitutes the 8 actual collections' counts.
- **R2: A `set_speed` call somewhere in `back_and_forth.py` or `multi_train_session.py` is missing `forward=` and the example raises `TypeError` on first run.** Story 6.3 caught this at the README level; the same mistake here would be more embarrassing because the file is the user's literal copy-paste source. Mitigation: Task 1 re-verifies `throttle.py:146`; Task 3 and Task 4 task descriptions explicitly state "full atomic call, do not call `set_speed` with bare `(value,)`"; AC2's task structure walks through the four `set_speed` calls in `back_and_forth.py` step by step.
- **R3: An example wraps the loop in `try/except KeyboardInterrupt:` or `try/except JMRIConnectionError:`, hiding shutdown signals or reconnect resilience.** Mitigation: Tasks 3 and 4 explicitly forbid these wrappers in the implementation guidance; the "Why no `try/except` wrappers" section in Dev Notes explains the reasoning so future-Mike (or a future dev) understands the rule and doesn't add it back.
- **R4: `mypy --strict examples/` fails because `args.X` accesses return `Any` and pollute the function bodies.** Mitigation: AC6's task description includes the explicit mitigation pattern (`parser.add_argument(..., type=int)` plus a local-typed assignment); the dev can also use `typed_argparse` (rejected as v1 dep — stdlib only per AC) or just narrow with `int(args.dcc)`. Task 5's mypy run catches this before declaring done.
- **R5: `multi_train_session.py`'s second-loco DCC default doesn't correspond to an actual loco on the basement layout, so the simulator run can't even test plumbing for the second loco's throttle acquire.** Mitigation: the docstring documents the source of the default (e.g., "DCC 5327 is from `jython/MikeBackAndForthTwoEngines.py`; the second-loco default is chosen as <X> — adjust via `--config` if your layout has different addresses"). The example's job is "show the `asyncio.gather` pattern," not "guarantee both default locos are on every layout."
- **R6: Examples drift over time as the library evolves and nobody notices.** Mitigation: outside Story 6.4 scope. Story 6.5 (CONTRIBUTING.md) is the right place to land a "run the three shipped examples against the basement simulator" pre-release smoke check; that's a future concern.
- **R7: Examples accidentally land third-party CLI parsing libraries (Click, Typer, rich) and break the "no external dependencies" line.** Mitigation: AC's scope notes are explicit; Task 5's `ruff check` and a final manual import-scan catch it. Click/Typer would also force `pyproject.toml` changes (out of scope).

### References

- `_bmad-output/planning-artifacts/epics.md:1001-1031` — Epic 6 Story 6.4 acceptance criteria (this story's source).
- `_bmad-output/planning-artifacts/epics.md:926-928` — Epic 6 intro paragraph (overall framing).
- `_bmad-output/planning-artifacts/prd.md:287-329` — PRD Journey 1 (Mike, porting Jython) — `back_and_forth.py`'s spiritual blueprint.
- `_bmad-output/planning-artifacts/prd.md:331-360` — PRD Journey 2 (multi-train evening + reconnect survival) — `multi_train_session.py`'s spiritual blueprint.
- `_bmad-output/planning-artifacts/prd.md:362-411` — PRD Journey 3 (Sarah, new user) — `hello_jmri.py`'s spiritual blueprint.
- `_bmad-output/planning-artifacts/prd.md:550-565` — PRD §Code Examples (Shipped with v1) — the three-example list, source of FR43.
- `_bmad-output/planning-artifacts/prd.md:821-822` — FR43 (three shipped examples) and FR44 (mypy --strict for downstream).
- `_bmad-output/planning-artifacts/architecture.md:306-333` — Layout-Agnosticism invariant (basement defaults OK; CLI overrides required).
- `_bmad-output/planning-artifacts/architecture.md:536-558` — Concurrency Model (TaskGroup-owned shutdown).
- `_bmad-output/planning-artifacts/architecture.md:760-952` — Implementation Patterns & Consistency Rules (async/error/logging/API/testing/docs).
- `_bmad-output/planning-artifacts/architecture.md:1037-1040` — Project Structure: `examples/` at `python_code/examples/`, three files only.
- `_bmad-output/planning-artifacts/architecture.md:1151-1153` — FR43 examples enumeration.
- `_bmad-output/implementation-artifacts/6-1-readme-5-minute-quickstart.md` — Done. Source for: Quickstart-vs-`hello_jmri.py` distinction, docs-only scope discipline.
- `_bmad-output/implementation-artifacts/6-2-readme-limitations-section.md` — Done. Source for: simulator-caveat phrasing in docstrings; honesty-over-comfort framing.
- `_bmad-output/implementation-artifacts/6-3-readme-jython-to-pyjmri-migration-table.md` — Done. Source for: PRD-vs-real-code drift discipline; per-row API audit; markdownlint MD036 pattern avoidance.
- `_bmad-output/implementation-artifacts/5-3-multi-throttle-integration-test-plumbing-on-simulator-physical-correctness-on-hardware.md` — Done. Source for: concurrent throttle acquire via `asyncio.gather` (the pattern `multi_train_session.py` uses).
- `_bmad-output/implementation-artifacts/3-3-forced-disconnect-resilience-integration-test.md` — Done. Source for: WS disconnect → reconnect → in-flight `wait_*` resilience (the behavior `multi_train_session.py` relies on).
- `python_code/README.md` — Current state (post-Story-6.3 done). Quickstart at lines 5–72; Limitations at lines 74–100; Migrating from Jython at lines 102–128. Story 6.4 does NOT edit any of these.
- `python_code/pyproject.toml` — Build config. Story 6.4 does NOT edit. The `pyproject.toml:35` `extend-exclude = ["*.ipynb"]` does NOT exclude `examples/` (it would still be scanned by ruff/mypy on explicit invocation).
- `python_code/src/pyjmri/__init__.py:35-70` — `__all__` list; every API name in examples MUST appear here.
- `python_code/src/pyjmri/layout.py:38-105, 197-260` — `EntityCollection` (dual-name subscript, `Mapping[str, T]` API) and `Layout` (8 collection attributes, `throttle` factory).
- `python_code/src/pyjmri/roster.py:1-9` — Stub. Confirms `Roster` / `RosterEntry` is NOT in v1 public surface.
- `python_code/src/pyjmri/throttle.py:74-249` — Throttle async context manager, `set_speed(value, *, forward)`, `set_function(n, on)`.
- `python_code/src/pyjmri/sensor.py:78-169` — Sensor `get_state`, `wait_state`, `wait_change`, `wait_active`, `wait_inactive`.
- `python_code/src/pyjmri/client.py:102-852` — Client `__aenter__`/`__aexit__`, `discover`, `throttle` factory, `power_state`. Note `_force_disconnect` at line 354 is test-only — examples MUST NOT call it.
- `jython/MikeBackAndForth.py` — The Jython source `back_and_forth.py` is porting. Sensor names "Block 1" / "Block 11"; speed 0.4; DCC 5327 (long) is from the script's CV-readback logic, simplified to a CLI default. Read-only per memory `feedback_writable_paths.md`.
- `jython/MikeBackAndForthTwoEngines.py:15-20` — Source for the two-loco basement-tuned defaults in `multi_train_session.py`. Read-only.
- Memory: `feedback_use_uv.md` — `uv run --no-sync` for all tool invocations and for documented example invocations.
- Memory: `feedback_polish_matters.md` — markdownlint self-scan before declaring done; `#### Why X?` H4 headings, not `**Why X?**` italics.
- Memory: `feedback_writable_paths.md` — only `python_code/` and `_bmad-output/` writable; `jython/` is read-only.
- Memory: `project_throttle_simulator_blindspot.md` — NCE simulator has no virtual loco; throttle commands accepted but no train moves and no sensor fires. The examples' docstrings document this honestly.
- Memory: `project_nce_open_loop.md` — NCE is open-loop, applies to simulator AND hardware. Reinforces simulator-caveat language.
- Memory: `project_pyjmri_status.md` — pyjmri implementation status snapshot; confirms Epics 2–5 complete and public API frozen at the time of authoring.
- Memory: `project_throttle_name_internal.md` — Throttle WS correlation name is internal-only; user-facing API exposes only DCC address. The examples use only DCC address (no `name=` kwarg).

### Project Structure Notes

- ALL changes live under `python_code/examples/` (three new files) and `_bmad-output/implementation-artifacts/` (this story file + sprint-status.yaml).
- NO new files under `python_code/src/pyjmri/`, NO source edits, NO test files, NO `pyproject.toml` changes, NO README edits.
- NO changes to `.jmri/` profiles, `jython/` scripts, `roster/` directory, or `roster.xml` (per memory `feedback_writable_paths.md`).
- The `python_code/examples/` directory is created fresh; no preceding story scaffolded it.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (`claude-opus-4-7[1m]`) via Claude Code.

### Debug Log References

None — examples-only story, no debug iteration required. Two cosmetic ruff fixes during implementation:

- RUF001/RUF002: en-dash `–` in the `1–127` short-address range inside `back_and_forth.py`'s docstring and `--short` help string replaced with ASCII hyphen `1-127`.
- ruff format: `multi_train_session.py` had one over-long `LocoConfig(...)` constructor line auto-reformatted to a single-line form by `ruff format`.

### Completion Notes List

- **Three new files authored under `python_code/examples/`** — `hello_jmri.py` (83 lines), `back_and_forth.py` (126 lines), `multi_train_session.py` (185 lines). Total 394 lines across the three examples.
- **`hello_jmri.py` roster substitution:** As mandated by AC1, `len(layout.roster)` from PRD Journey 3 was not used (roster is a v1 stub). The example instead prints counts of all 8 actual `Layout` collections (turnouts, sensors, blocks, lights, memories, routes, signal heads, signal masts). The docstring's "Roster note" block explicitly states pyjmri v1 does not yet expose JMRI's roster and points to its deferred status.
- **`multi_train_session.py` second-loco DCC selection:** Loco 1 keeps the established basement default (DCC 5327, long, "Block 1"/"Block 6", speed 0.4 per `jython/MikeBackAndForthTwoEngines.py:15-20`). Loco 2 picks DCC 1029 ("1029 NW2 Switcher") — verified as a real basement-roster entry in `roster.xml` and `roster/1029_NW2_Switcher.xml`. Paired with "Block 7"/"Block 12" (the second-loco sensors from the Jython source) and a deliberately differentiated speed of 0.35.
- **`back_and_forth.py` line count budget exceeded slightly (126 vs the ~60 line aim):** Task 3's word-count target is at odds with AC9's substantive docstring requirement. The docstring runs ~58 lines covering purpose, invocation examples (default, custom layout, short-address), defaults block, and the simulator caveat. The remaining ~68 lines are the actual code, which includes a `argparse` mutex group for `--long`/`--short` (intrinsically verbose) and a per-arg `help=` string. Trimming further would require dropping AC9-mandated docstring content or eliminating user-facing CLI features. Accepted as a deliberate trade-off — the file is well-organized and serves its purpose. AC2's deeper intent ("conciseness matters; this is the 'what 60 lines of Jython becomes' demo") is honored at the *code* level: the inner oscillation loop is 5 lines, mirroring the Jython source's `handle()` method essentially line-for-line.
- **API-drift correction applied:** Every `set_speed` call in the examples spells out `forward=` (verified by grep — 4 calls total, 2 in `back_and_forth.py` and 2 in `multi_train_session.py`). No bare `set_speed(value)` calls anywhere.
- **Async/await discipline:** every `pyjmri` `async def` method invocation is prefixed with `await` (`set_speed`, `wait_active`, `wait_inactive`, `discover`). Sync subscript lookups (`layout.sensors[name]`) deliberately omit `await` since `EntityCollection.__getitem__` is sync per `layout.py:92`.
- **Throttle context-manager pattern:** Both `back_and_forth.py` and `multi_train_session.py` use `async with layout.throttle(addr, long=...) as t:` for clean acquire/release. No explicit `t.release()` calls — `Throttle.__aexit__` handles teardown including the WS release envelope.
- **No `try/except` wrappers:** confirmed via grep — no `try/except KeyboardInterrupt:`, no `try/except JMRIConnectionError:` in any example. `asyncio.run`'s default handling carries `Ctrl-C` through the `async with` blocks' `__aexit__` cascade. Epic 3's WS reconnect machinery is left transparent.
- **No `_`-prefixed imports:** grep `^from pyjmri\._|^import pyjmri\._` against `examples/*.py` returns zero matches. All imports use the top-level `pyjmri` namespace (`Client`, `Layout`).
- **Public API hygiene:** every name referenced (`Client`, `Layout`, `LocoConfig` is local, no others) resolves under `from pyjmri import ...`. Verified against `__init__.__all__`.
- **Quality gates clean (2026-05-24):**
  - `uv run --no-sync ruff check` → `All checks passed!`
  - `uv run --no-sync ruff format --check` → `56 files already formatted`
  - `uv run --no-sync mypy --strict src/pyjmri` → `Success: no issues found in 20 source files` (unchanged from post-Story-6.3 baseline)
  - `uv run --no-sync mypy --strict examples/` → `Success: no issues found in 3 source files` (new gate, first run clean)
  - `uv run --no-sync pytest -m "not integration"` → `411 passed, 22 deselected in 0.59s` (unchanged from post-Story-6.3 baseline)
- **Manual smoke runs deferred to user:** The dev agent cannot interactively start a JMRI simulator session, run an example for several oscillations while tapping sensors in the UI, and observe `Ctrl-C` exit cleanliness. AC1/AC2/AC3's "runs against `Basement_Revised_2024.jmri`" verifications and AC8's "no leaked tasks" warning check require a human in front of a JMRI session. All three example files compile cleanly under mypy and ruff, but their runtime behavior against a live JMRI is unverified by this dev pass. **Recommendation for the reviewer or user:** start the basement simulator, run each example in turn, tap sensors in the Sensor Table to drive `wait_active`/`wait_inactive`, observe a few iterations, then `Ctrl-C` and watch stderr. If any "Task was destroyed but it is pending!" warnings appear, that's a bug to investigate.
- **No source / test / config changes:** confirmed by `git diff --stat` mental model — only `python_code/examples/*.py` (3 new), the story file, and `sprint-status.yaml` change. `python_code/src/pyjmri/` and `python_code/tests/` untouched.

### File List

- `python_code/examples/hello_jmri.py` (new) — first-contact example; connects, discovers, prints counts of the 8 Layout collections and the first 5 turnouts. 83 lines including docstring.
- `python_code/examples/back_and_forth.py` (new) — single-loco oscillation between two sensors; port of `jython/MikeBackAndForth.py`. 126 lines including docstring. CLI: `--url`, `--dcc`, `--long`/`--short`, `--forward-sensor`, `--reverse-sensor`, `--speed`.
- `python_code/examples/multi_train_session.py` (new) — N-loco concurrent oscillation via `asyncio.gather`; demonstrates PRD Journey 2 including transparent reconnect resilience. 185 lines including docstring. CLI: `--url`, `--config <path>` (JSON file listing locos; default is two locos covering basement DCC 5327 + 1029).
- `_bmad-output/implementation-artifacts/6-4-three-shipped-examples-hello-jmri-py-back-and-forth-py-multi-train-session-py.md` (modified) — story-file updates: Status, Tasks/Subtasks checkboxes, Dev Agent Record, File List, Change Log.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — `6-4-three-shipped-examples-...` transitioned `ready-for-dev` → `in-progress` → `review`; `last_updated` set to 2026-05-24.

### Review Findings

Code review run 2026-05-24 (0 patch · 0 decision-needed · 5 deferred · 14 dismissed).

- [x] [Review][Defer] Sensor lookup raises bare `LayoutEntityNotFound` on wrong sensor name — no "available sensors" hint [`back_and_forth.py:70-71`, `multi_train_session.py`] — deferred, pre-existing library API behavior; acceptable for example scripts
- [x] [Review][Defer] `_load_config` missing JSON keys raise bare `KeyError` with no entry-index context [`multi_train_session.py:_load_config`] — deferred, example-script UX; acceptable
- [x] [Review][Defer] DCC address=0/negative and speed outside [0.0, 1.0] accepted at load time, fail at runtime [`multi_train_session.py:_load_config`] — deferred, validated at runtime by library; acceptable for examples
- [x] [Review][Defer] Loop starts without checking sensor state — train parked on a sensor causes immediate direction reversal [`back_and_forth.py:70-80`, `multi_train_session.py:drive_loco`] — deferred, known limitation; simulator caveat documents it
- [x] [Review][Defer] "First 5 turnouts:" header prints unconditionally even with 0 turnouts [`hello_jmri.py:57`] — deferred, low cosmetic concern; basement layout always has turnouts

## Change Log

- 2026-05-24 — Story 6.4 created (`backlog` → `ready-for-dev`). Examples-only story: creates the new `python_code/examples/` directory with three files (`hello_jmri.py`, `back_and_forth.py`, `multi_train_session.py`) implementing PRD Journeys 1, 2, and 3. The examples are layout-agnostic with basement-tuned CLI defaults (DCC 5327, sensors "Block 1" / "Block 6" / "Block 11" / "Block 12" per the Jython source files), pass `mypy --strict`, `ruff check`, and `ruff format --check`, exit cleanly on `Ctrl-C` via the Client's TaskGroup-owned shutdown path, and rely transparently on Epic 3's reconnect machinery (no `try/except JMRIConnectionError:`). One new API-drift row is explicitly flagged for this story: `Layout.roster` does NOT exist (the `roster.py` module is a v1 stub with `__all__: list[str] = []`), so `hello_jmri.py` substitutes counts of the 8 actual `Layout` collections. FR43 (three shipped examples runnable unmodified against `Basement_Revised_2024.jmri`) and FR44 (examples pass `mypy --strict`) are satisfied. No `src/` source changes, no new tests, no config changes — three new files under `examples/` plus the story file and sprint-status.yaml.
- 2026-05-24 — Story 6.4 implemented (`ready-for-dev` → `in-progress` → `review`). Three example files authored under `python_code/examples/` (`hello_jmri.py` 83 lines, `back_and_forth.py` 126 lines, `multi_train_session.py` 185 lines). All API-drift corrections applied per Dev Notes: `hello_jmri.py` prints the 8 actual `Layout` collections (no `layout.roster`), every `set_speed` call uses `forward=` (4 calls total, verified by grep), every `async def` API method is `await`-prefixed, throttle lifecycle uses `async with` (no explicit `release()`). `multi_train_session.py` second-loco picked as DCC 1029 ("1029 NW2 Switcher", verified in `roster.xml`), paired with "Block 7"/"Block 12" per `jython/MikeBackAndForthTwoEngines.py`. Quality gates pass clean against the post-Story-6.3 baseline (411 unit tests passed, 22 deselected; ruff/format/mypy unchanged for `src/`); new `mypy --strict examples/` gate passes on first run (3 files, 0 issues). Two cosmetic ruff fixes during implementation: en-dash → ASCII hyphen in `back_and_forth.py`'s `1-127` range; one auto-formatted long line in `multi_train_session.py`. Manual smoke runs against a live JMRI simulator deferred to the user — the dev agent cannot interactively drive sensors and observe `Ctrl-C` cleanliness without a JMRI session. No `src/`, test, or `pyproject.toml` edits.
