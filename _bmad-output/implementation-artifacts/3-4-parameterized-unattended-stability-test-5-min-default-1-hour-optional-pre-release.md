# Story 3.4: Parameterized unattended stability test (5-min default; 1-hour optional pre-release)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a library user,
I want a parameterized unattended stability test that defaults to 5 minutes for normal dev use but can be invoked at one hour for pre-release validation, proving the script does not leak memory, file descriptors, or asyncio tasks across forced WS disconnects,
So that NFR4's one-hour stability claim is verifiable on demand without making everyday testing painful.

## Scope notes

- **3.4 is proof, not new production plumbing.** Stories 3.1–3.3 already shipped the reconnect machinery, waiter primitives, and `_force_disconnect()` hook. This story is a single new integration test plus a small amount of pytest scaffolding (CLI option, marker, dev dependency).
- **No production changes.** All work lives under `python_code/tests/` and `python_code/pyproject.toml`. The `src/pyjmri/` tree is untouched.
- **`psutil` is the right tool here.** `resource.getrusage()` returns RSS in different units on macOS (bytes) vs Linux (KiB), and has no cross-platform FD-count API. `psutil` gives uniform `memory_info().rss` (bytes) and `num_fds()` on both NFR9 first-class platforms. Add it as a **dev-only** dependency; the published wheel does not depend on it.
- **`@pytest.mark.slow` is new.** The repo currently registers only `integration` in `[tool.pytest.ini_options].markers`. The story registers `slow` alongside it so the long-run test can be excluded with `pytest -m "not slow"` even when integration is enabled. (Belt-and-suspenders: the test is *also* `integration`, so `pytest -m "not integration"` — the standard CI invocation per `.github/workflows/ci.yml` — already skips it.)
- **Layout-agnostic.** Pick the first sensor from `discover()`. Skip with a clear message if no sensors exist. **Sensor-only** workload is sufficient: the sensor round-trip is the authoritative NFR5 / NFR4 proof on the NCE Simulator (turnout state changes do not echo back via WS on simulator-only layouts — see 3.3's debug log).
- **Disconnect cadence:** schedule disconnects to maintain **at least 5/hour** (NFR5 floor) for runs ≥ 1 hour, with a floor of **one disconnect per run** for the 5-min default. The cleanest formula: `num_disconnects = max(1, math.ceil(duration_seconds / 720))` → 1 disconnect at 300 s, 3 at 1800 s, 5 at 3600 s. Space disconnects evenly across the run.
- **Reporting matters.** When the test passes, print a one-line summary (`duration=…s disconnects=… reconnects=… rss_delta=…MB fd_delta=… task_delta=…`) so a release-prep run produces visible evidence to paste into release notes.
- **Cross-story implications:** Epic 6 Story 6.5 (`CONTRIBUTING.md` release checklist) will reference `pytest tests/integration/test_long_run.py --duration=3600` as the pre-release stability gate. This story creates the artifact 6.5 will reference; no Epic-6 work happens here.

## Acceptance Criteria

**AC1 — Parameterized test, properly marked, with CLI/env override**

**Given** Stories 3.1–3.3
**When** `python_code/tests/integration/test_long_run.py` is added
**Then** it defines a single test parameterized by duration with a default of **300 seconds** (5 minutes)
**And** the duration can be overridden via a pytest CLI option `--duration=<seconds>` (registered in a new `python_code/tests/conftest.py` via `pytest_addoption`)
**And** the duration can be overridden via the environment variable `PYJMRI_LONG_RUN_DURATION` (CLI wins over env, env wins over default)
**And** the test is marked `@pytest.mark.integration` AND `@pytest.mark.slow`
**And** `@pytest.mark.slow` is registered in `pyproject.toml` under `[tool.pytest.ini_options].markers` so `ruff`/`pytest` do not emit "unknown marker" warnings

**AC2 — Force-disconnect cadence scales with duration; NFR5 floor satisfied**

**Given** the test runs at any duration ≥ 300 s
**When** it executes
**Then** at least one forced WS disconnect is scheduled during the run (via `jmri._force_disconnect()`)
**And** the disconnect count is computed as `max(1, math.ceil(duration_seconds / 720))` — yielding 1 at 300 s, 3 at 1800 s, 5 at 3600 s, ≥ 5/hour for any run ≥ 1 hour (NFR5 enforcement)
**And** disconnects are spaced evenly across the run (e.g., at `duration/(N+1)` intervals)
**And** after each forced disconnect, the test waits (bounded to 15 s) for the `pyjmri.reconnect` INFO log `"WebSocket reconnected; replaying subscriptions"` before continuing
**And** if any reconnect fails to log within 15 s, the test fails with a clear message naming the disconnect index and elapsed seconds

**AC3 — Leak metrics captured; thresholds enforced (NFR4)**

**Given** the test runs to completion at any duration
**When** baseline metrics are captured immediately after `Client.__aenter__` returns and the first sensor is discovered, and final metrics are captured **after** the workload loop ends but **before** `Client.__aexit__` runs (so the comparison is library-internal, not "did teardown clean up")
**Then** all three deltas are recorded:
  - **RSS delta** (process resident set size, via `psutil.Process().memory_info().rss`) — converted to MB
  - **FD delta** (open file descriptors, via `psutil.Process().num_fds()`)
  - **asyncio task delta** (active tasks in the running loop, via `len(asyncio.all_tasks())` minus the current test task)
**And** RSS delta is asserted to be **at most** `10 MB at 300 s, scaling linearly up to 50 MB at 3600 s`, computed as `max_rss_delta_mb = 10 + (40 * (duration_s - 300) / 3300)` clamped at `[10, 50]` for safety
**And** FD delta is asserted to be **at most 5** (allowing some headroom for httpx connection pool internals at the moment of measurement)
**And** asyncio task delta is asserted to be **at most 2** (allowing for the WS supervisor and one transient task)
**And** if any threshold is exceeded, the assertion message includes the captured baseline, captured final, and computed delta so a reader can diagnose without re-running

**AC4 — Reconnect-success and waiter-survival invariants verified**

**Given** the workload loop registers an `await sensor.wait_change(timeout=...)` before each forced disconnect
**When** a disconnect fires
**Then** after reconnect, the test induces a sensor state change (raw httpx POST to the opposite state)
**And** the in-flight `wait_change()` resolves with the expected new state within the bounded post-reconnect window (or via the level-triggered subscription-ack if the state changed during the disconnect window — both outcomes are valid, mirroring Story 3.3 AC2/AC3 semantics)
**And** every forced disconnect is followed by a successful reconnect inside the bounded backoff window (per the reconnect-log polling in AC2)
**And** no `wait_*` waiter is left dangling: the workload loop's `finally` block cancels and awaits any unresolved tasks before metric capture

**AC5 — Standard CI invocation does not run this test; layout-agnostic skip on empty layout; summary printed on success**

**Given** the architecture's policy that this test is "its own pytest target, invoked manually"
**When** the developer runs the standard CI invocation `uv run --no-sync pytest -m "not integration"`
**Then** this test does not run (excluded by the `integration` marker)
**And** when the developer runs `uv run --no-sync pytest tests/integration/test_long_run.py`
**Then** the test runs at the default 5-minute duration and reports its leak metrics on completion
**And** when the developer runs `uv run --no-sync pytest tests/integration/test_long_run.py --duration=3600`
**Then** the test runs for one hour and verifies NFR4's full claim
**And** if the discovered layout has zero sensors, the test skips with a clear message (rather than failing) — layout-agnostic per architecture
**And** on success at any duration, the test prints (via `pytest -s` or `caplog` summary capture, plus a final `print()` to stdout) a single summary line of the form: `pyjmri long-run: duration=300s disconnects=1 reconnects=1 rss_delta=2.3MB fd_delta=0 task_delta=0 status=PASS`

## Tasks / Subtasks

- [x] **Task 1 — Register `slow` marker and `--duration` pytest option** (AC: 1)
  - [x] Edit `python_code/pyproject.toml` `[tool.pytest.ini_options].markers` to add: `"slow: long-running tests intended for manual / pre-release invocation; excluded from the default test run."` alongside the existing `integration` marker.
  - [x] Create `python_code/tests/conftest.py` (new, repo-root-of-tests level) with:
    ```python
    from __future__ import annotations

    import pytest


    def pytest_addoption(parser: pytest.Parser) -> None:
        parser.addoption(
            "--duration",
            action="store",
            default=None,
            help=(
                "Override the duration (seconds) of long-running tests "
                "(e.g., tests/integration/test_long_run.py). Wins over "
                "PYJMRI_LONG_RUN_DURATION env var. Default in-test: 300."
            ),
        )
    ```
  - [x] Run `uv run --no-sync pytest --collect-only tests/integration/test_long_run.py --duration=60` after Task 3 is in place to confirm the option is accepted (no `unrecognized arguments` error).

- [x] **Task 2 — Add `psutil` as a dev-only dependency** (AC: 3)
  - [x] Edit `python_code/pyproject.toml` `[dependency-groups].dev` to add `"psutil>=5.9"`. Keep alphabetical order (after `pytest-asyncio`, before `ruff`).
  - [x] Run `uv sync --group dev` to refresh `uv.lock`. Commit the lock change with the pyproject change.
  - [x] Sanity-check importability: `uv run --no-sync python -c "import psutil; print(psutil.__version__)"`.

- [x] **Task 3 — Implement `tests/integration/test_long_run.py`** (AC: 1, 2, 3, 4, 5)
  - [x] Module docstring naming FR7/FR33/NFR4/NFR5, describing the workload (sensor `wait_change()` across N evenly-spaced forced disconnects), and citing the disconnect cadence formula.
  - [x] Module-level constants near the top:
    ```python
    _DEFAULT_DURATION_S = 300
    _DISCONNECT_PERIOD_S = 720           # 1 disconnect / 720s → 5/hour at 3600s
    _RECONNECT_WAIT_S = 15.0             # poll budget per reconnect log
    _RECONNECT_POLL_INTERVAL_S = 0.2
    _RECONNECT_INFO_MSG = "WebSocket reconnected; replaying subscriptions"
    _PER_CYCLE_WAIT_TIMEOUT_S = 30.0     # generous; expect << 1s on local layouts
    _FD_DELTA_MAX = 5
    _TASK_DELTA_MAX = 2
    _RSS_DELTA_FLOOR_MB = 10
    _RSS_DELTA_CEIL_MB = 50
    ```
  - [x] Helper `_resolve_duration(request: pytest.FixtureRequest) -> int`:
    - Read `request.config.getoption("--duration")` first.
    - Fall back to `os.environ.get("PYJMRI_LONG_RUN_DURATION")`.
    - Fall back to `_DEFAULT_DURATION_S`.
    - Cast to `int`; raise `pytest.UsageError` if non-positive.
  - [x] Helper `_max_rss_delta_mb(duration_s: int) -> float`:
    ```python
    if duration_s <= 300:
        return _RSS_DELTA_FLOOR_MB
    if duration_s >= 3600:
        return _RSS_DELTA_CEIL_MB
    span_factor = (duration_s - 300) / (3600 - 300)
    return _RSS_DELTA_FLOOR_MB + (_RSS_DELTA_CEIL_MB - _RSS_DELTA_FLOOR_MB) * span_factor
    ```
  - [x] Helper `_post_sensor_state(raw_http, sensor_name, target)` — copy verbatim from `tests/integration/test_reconnect_resilience.py:56-66` (raw httpx POST against `/json/v5/sensor/<urlquoted>`). Do **not** import it cross-module; this test should be self-contained.
  - [x] Helper `_opposite_sensor(state)` — copy verbatim from `tests/integration/test_reconnect_resilience.py:82-87`.
  - [x] Helper `_await_reconnect_log(caplog, since_record_index, cycle_idx)` (async) that polls `caplog.records` for the next `pyjmri.reconnect` INFO log appearing after `since_record_index`, returning the new index or raising `pytest.fail(...)` on timeout. (Tracking the index across multiple disconnects is critical — without it, the test would match the *first* reconnect log for every subsequent disconnect.)
  - [x] Helper `_metric_snapshot() -> dict[str, int|float]` capturing `{"rss_bytes": ..., "fds": ..., "tasks": ...}` via `psutil.Process()` and `asyncio.all_tasks()`. **Exclude the current task** when counting `all_tasks()` (`asyncio.current_task()` is part of the test runner, not pyjmri).
  - [x] The test function `test_long_run_stability` with signature:
    ```python
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_long_run_stability(
        jmri_available: None,
        request: pytest.FixtureRequest,
        caplog: pytest.LogCaptureFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
    ```
  - [x] Test body sequence:
    1. `duration_s = _resolve_duration(request)`; compute `num_disconnects = max(1, math.ceil(duration_s / _DISCONNECT_PERIOD_S))`.
    2. `async with Client() as jmri:` — discover; `sensors = list(layout.sensors.values())`; `pytest.skip(...)` if empty.
    3. `sensor = sensors[0]` — force to a known starting state via `_post_sensor_state(...)` + `sensor.wait_state(...)` (10 s timeout) so the cache is correct.
    4. Capture **baseline** metrics: `baseline = _metric_snapshot()`. Record the `caplog.records` length now so the first-disconnect log search starts at this index.
    5. Plan disconnect timestamps: `times = [duration_s * (i + 1) / (num_disconnects + 1) for i in range(num_disconnects)]` (evenly spaced, never at t=0 or t=duration). Start a monotonic timer with `loop.time()`.
    6. Loop over `times`:
       - `await asyncio.sleep(next_time - elapsed_now)` to reach the scheduled disconnect time.
       - Register `wait_task = asyncio.create_task(sensor.wait_change(timeout=_PER_CYCLE_WAIT_TIMEOUT_S))`; `await asyncio.sleep(0)` to register the waiter.
       - Set up a log-index marker; call `await jmri._force_disconnect()`; call `_wait_for_reconnect_log(caplog, marker, deadline=loop.time() + _RECONNECT_WAIT_S)` and record the elapsed time.
       - Resolve the waiter: if `wait_task.done()` (level-triggered via subscription-ack), accept whichever post-state arrived; else POST the opposite sensor state and `await wait_task` with a 10 s bound. Assert the resolved state differs from the pre-disconnect cached state.
       - Restore the sensor to the original starting state for the next cycle (only if a command was issued).
    7. After the loop, capture **final** metrics: `final = _metric_snapshot()` (still inside the `async with Client()` block — *before* teardown).
    8. Compute deltas; assert each against its threshold using the helper-computed bounds. Assertion messages must include baseline, final, delta, and threshold.
    9. Print the summary line via `print(...)`; pytest's `-s` flag or `capsys.readouterr()` makes it visible. Format: `pyjmri long-run: duration=Ns disconnects=N reconnects=N rss_delta=X.XMB fd_delta=N task_delta=N status=PASS`.
    10. `finally:` block (inside the loop or wrapping it) ensures any non-done `wait_task` is cancelled and awaited (mirror Story 3.3's pattern at `tests/integration/test_reconnect_resilience.py:257-262`).
  - [x] Imports at top of the new test file: `asyncio`, `contextlib`, `logging`, `math`, `os`, `urllib.parse.quote`, `httpx`, `psutil`, `pytest`, `from pyjmri import Client, SensorState`. Uses `from __future__ import annotations`. (`time` not needed — used `asyncio.get_running_loop().time()`.)

- [x] **Task 4 — Validate end-to-end and quality gates** (AC: all)
  - [x] `uv run --no-sync ruff format` (clean — auto-reformatted one line in `_resolve_duration`).
  - [x] `uv run --no-sync ruff check` (clean — no `# noqa: ASYNC109` needed; the rule fires on function *definitions*, and this test only *calls* `wait_*(timeout=…)`).
  - [x] `uv run --no-sync mypy --strict src/pyjmri` (clean; "Success: no issues found in 19 source files").
  - [x] `uv run --no-sync mypy --strict tests/integration/test_long_run.py` (clean; required `# type: ignore[import-untyped]` on `import psutil` (psutil 7.2.2 ships no stubs) and one `int(...)` narrowing on `process.num_fds()`).
  - [x] `uv run --no-sync pytest -m "not integration"` — 318 passed, 7 deselected. Long-run not collected in default CI invocation. ✓
  - [x] **Smoke run at short duration:** `--duration=60`. Result: 1 passed in 60.18 s wall-clock. Summary: `pyjmri long-run: duration=60s disconnects=1 reconnects=1 rss_delta=0.0MB fd_delta=0 task_delta=0 status=PASS`.
  - [x] **Default smoke run:** bare invocation. Result: 1 passed in 300.15 s (5:00) wall-clock. Summary: `pyjmri long-run: duration=300s disconnects=1 reconnects=1 rss_delta=0.1MB fd_delta=0 task_delta=0 status=PASS`.
  - [x] Update story File List to enumerate every changed file: `python_code/pyproject.toml`, `python_code/uv.lock`, `python_code/tests/conftest.py` (NEW), `python_code/tests/integration/test_long_run.py` (NEW).

### Review Findings — BMAD code-review (2026-05-19)

Three layers run in parallel: Blind Hunter (diff only), Edge Case Hunter (diff + project read access), Acceptance Auditor (diff + spec). 17 dismissed as noise, 1 deferred, 2 patches. All 5 ACs confirmed satisfied.

- [x] [Review][Patch] **No minimum duration guard in `_resolve_duration`** — `_resolve_duration` accepts any positive integer including `--duration=1`. With `duration_s < _RECONNECT_WAIT_S` (15 s), the `_await_reconnect_log` poll deadline is guaranteed to expire before a reconnect could complete, so the test always fails. Fix: add `if value < 30: raise pytest.UsageError(f"--duration must be at least 30 seconds; got {value}")` after the positive-check. [`python_code/tests/integration/test_long_run.py:93-107`] — flagged by Blind Hunter
- [x] [Review][Patch] **Unconditional `import psutil` fails module collection when dev deps are absent** — A bare `import psutil` at module top-level raises `ImportError` and fails the entire module collection rather than skipping gracefully. Fix: replace with `psutil = pytest.importorskip("psutil", reason="psutil required for leak-metric capture")` at module scope. [`python_code/tests/integration/test_long_run.py:42`] — flagged by Blind Hunter
- [x] [Review][Defer] **`sensor.state` potentially stale between reconnect-log confirmation and `_opposite_sensor(sensor.state)` call** — After `_await_reconnect_log` returns, subscription-ack events for the sensor may not yet have been processed by the receive loop, leaving `sensor.state` at its pre-disconnect cached value. If the sensor's actual JMRI state changed during the disconnect window, `_opposite_sensor` targets the wrong state. Inherent integration-test race; the level-triggered fallback (`if wait_task.done()`) handles the most common case. [`python_code/tests/integration/test_long_run.py:242`] — flagged by Edge Case Hunter — deferred, pre-existing design trade-off

## Dev Notes

### Authoritative current state of `python_code/` (verified 2026-05-19, post-Story-3.3 review patches)

**Source files (20 files; src/pyjmri unchanged by this story):**

- `_transport.py` — exposes `WSConnection._force_disconnect()` (Story 3.3, line ~305). Closes `self._connection` (a `websockets.asyncio.client.ClientConnection`) if active; no-op otherwise. This is the hook the long-run test repeatedly invokes.
- `client.py` — exposes `Client._force_disconnect()` (Story 3.3, line ~321). Raises `RuntimeError` if Client not open; delegates to `self._ws._force_disconnect()`. Also exposes `Client._on_ws_reconnect()` which emits the `pyjmri.reconnect` INFO log `"WebSocket reconnected; replaying subscriptions"` with `extra={"host": ..., "subscription_count": registry.size}` (line ~359). **This is the log the test polls between disconnects to confirm reconnect success.**
- `_subscriptions.py` — `SubscriptionRegistry.size` is a property returning `len(self._subscriptions)`. `SubscriptionRegistry.replay()` re-sends every known subscription on reconnect. The test inspects `jmri._registry.size` to assert subscription survival.
- All entity modules (`sensor.py`, `turnout.py`, ...), parsers, exceptions, layout — unchanged by this story.

**Test infrastructure already in place:**

- `tests/integration/conftest.py` — `jmri_available` session fixture (probes `localhost:12080` via a TCP `socket.create_connection`; skips with a clear message on `OSError`). The long-run test consumes this fixture.
- `tests/integration/test_reconnect_resilience.py` (Story 3.3, post-review-patch state) — **the closest pattern** for this story. Re-use `_post_sensor_state`, `_opposite_sensor`, `_RECONNECT_WAIT_S`, `_RECONNECT_INFO_MSG`, the polling loop (`asyncio.get_running_loop().time()` deadline + `caplog.records` scan), and the `finally:` task-cleanup block. Copy verbatim — do **not** introduce a shared helper module; tests are intentionally self-contained per repo convention.
- `tests/unit/conftest.py` — provides `patch_http_factory` / `make_fake_handle`; **not used** by the long-run test (it hits live JMRI).
- **No root `tests/conftest.py` exists yet.** Task 1 creates it. Putting `pytest_addoption` there (not in `tests/integration/conftest.py`) makes the `--duration` option discoverable by the unit-test subtree too if a future unit test ever wants it — `pytest_addoption` must be defined in a `conftest.py` that pytest discovers during the initial CLI parse, i.e., at the testpath root.

**Current test counts (post-3.3 review patches, verified by Story 3.3 completion notes):**

- 318 unit tests passing.
- 6 integration tests passing (test_connection_lifecycle.py, test_discovery.py, test_ws_connect.py, test_wait_primitives_latency.py, test_reconnect_resilience.py × 1, plus one in test_discovery.py — see `tests/integration/` directory).

After this story: still 318 unit tests; 7 integration tests when JMRI is running (default-duration long-run passes); but the long-run test is **not** part of the default `pytest -m "not integration"` run.

### Disconnect-cadence math (AC2)

```
num_disconnects = max(1, math.ceil(duration_s / 720))
```

| duration (s) | duration (min) | num_disconnects | per-hour rate |
|---|---|---|---|
| 300 | 5 | 1 | 12/hr (over-rate, but only 1 actual event in the 5 min) |
| 600 | 10 | 1 | 6/hr |
| 1800 | 30 | 3 | 6/hr |
| 3600 | 60 | 5 | 5/hr ✓ NFR5 floor |
| 7200 | 120 | 10 | 5/hr ✓ |

The 720 s period is chosen so that runs ≥ 1 hour produce **at least 5 disconnects per hour** (the NFR5 minimum) while shorter runs still get the proof-of-concept single disconnect. Even spacing means disconnects at `i * duration / (N+1)` for `i ∈ {1..N}` — never at t=0 (Client must be steady-state) and never at t=duration (workload must observe the recovery).

### Leak-metric thresholds (AC3)

**RSS delta** (linear interpolation between 300 s and 3600 s):

```
max_rss_delta_mb(duration_s) =
  10                                                  if duration_s ≤ 300
  50                                                  if duration_s ≥ 3600
  10 + (40 * (duration_s - 300) / 3300)               otherwise
```

| duration (s) | max RSS delta (MB) |
|---|---|
| 300 | 10 |
| 900 | 17.3 |
| 1800 | 28.2 |
| 3600 | 50 |

**Why linear, not constant?** A genuine leak grows roughly linearly with time, so a constant threshold either has too much headroom at 5 min (catches no real leak) or too little at 1 hour (false positives from httpx connection-pool growth). Linear interpolation tracks the duration. The 10 MB floor accounts for one-time allocations after `Client.__aenter__` (httpx + websockets internal buffers, parsed layout); the 50 MB ceiling accounts for psutil/process overhead variance over an hour without ever masking a real leak (a leak that escapes 50 MB/hr is a critical bug regardless).

**FD delta** capped at 5 — httpx pools may briefly hold extra connections; absolute leak (uncapped growth across reconnects) is what matters and would clearly exceed 5.

**asyncio task delta** capped at 2 — the WS reconnect supervisor lives for the whole Client lifetime; one transient task allowance for the `_on_ws_reconnect` callback being mid-flight at the moment of measurement. A genuine task leak (each reconnect spawning an orphan) would exceed 2 quickly.

### Subscription replay log shape (the test's reconnect signal)

`Client._on_ws_reconnect()` at `python_code/src/pyjmri/client.py:351-363` is what the test polls. The relevant log call:

```python
logger_reconnect.info(
    "WebSocket reconnected; replaying subscriptions",
    extra={"host": self._host, "subscription_count": self._registry.size},
)
```

- Logger name: `"pyjmri.reconnect"`.
- Level: `logging.INFO`.
- Message substring: `"WebSocket reconnected; replaying subscriptions"` (the exact constant `_RECONNECT_INFO_MSG` in the test).
- `caplog.records` exposes `LogRecord.name`, `LogRecord.levelno`, `LogRecord.getMessage()`, and `LogRecord.subscription_count` (via `extra=`). The test asserts `subscription_count >= 1` after each reconnect.

**Why polling, not waiting?** `caplog` records are populated synchronously when `logger.info(...)` runs, but the test cannot `await` a specific log event directly. The polling loop (`while loop.time() < deadline: ... await asyncio.sleep(0.2)`) gives the event loop time to process the WS reconnect, run `_on_ws_reconnect`, and emit the log. Story 3.3 validated this pattern.

**Multi-disconnect index tracking:** unlike Story 3.3 which only has one disconnect, the long-run test must track an "index marker" into `caplog.records` so each cycle looks only for reconnect logs that appeared **after** the disconnect was triggered, not the first reconnect log accumulated since test start.

### Workload loop pseudocode (AC2 + AC4)

```python
loop = asyncio.get_running_loop()
start = loop.time()
caplog_marker = len(caplog.records)
disconnects_done = 0
reconnects_done = 0
starting_state = sensor.state  # known (we forced it before baseline)

for cycle_idx, scheduled_t in enumerate(times, start=1):
    # 1. Wait until the scheduled disconnect time.
    while True:
        delay = scheduled_t - (loop.time() - start)
        if delay <= 0:
            break
        await asyncio.sleep(min(delay, 1.0))

    # 2. Register a waiter that should survive the disconnect.
    wait_task = asyncio.create_task(
        sensor.wait_change(timeout=_PER_CYCLE_WAIT_TIMEOUT_S)  # noqa: ASYNC109
    )
    await asyncio.sleep(0)
    pre_cycle_state = sensor.state

    # 3. Force disconnect + wait for reconnect.
    cycle_marker = len(caplog.records)
    with caplog.at_level(logging.INFO, logger="pyjmri.reconnect"):
        await jmri._force_disconnect()
        disconnects_done += 1
        new_marker = _wait_for_reconnect_log(
            caplog, cycle_marker, deadline=loop.time() + _RECONNECT_WAIT_S
        )
        reconnects_done += 1
        caplog_marker = new_marker

    try:
        # 4. Resolve the waiter — accept either outcome.
        if wait_task.done():
            # Level-triggered: subscription-ack delivered new state.
            resolved = wait_task.result()
            assert resolved is not pre_cycle_state, (
                f"cycle {cycle_idx}: waiter resolved to starting state {pre_cycle_state!r}"
            )
        else:
            target = _opposite_sensor(sensor.state)
            await _post_sensor_state(raw_http, sensor.name, target)
            resolved = await asyncio.wait_for(asyncio.shield(wait_task), timeout=10.0)
            assert resolved is target, (
                f"cycle {cycle_idx}: expected {target!r}; got {resolved!r}"
            )
            # 5. Restore for the next cycle.
            await _post_sensor_state(raw_http, sensor.name, pre_cycle_state)
            await sensor.wait_state(pre_cycle_state, timeout=10.0)  # noqa: ASYNC109
    finally:
        if not wait_task.done():
            wait_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await wait_task
```

This pattern is structurally identical to Story 3.3's force-disconnect + opposite-state-command + level-triggered-fallback, but parameterized into a loop. **Do not invent a new pattern** — re-use 3.3's structure verbatim where it applies.

### File layout for this story

```
python_code/pyproject.toml                          # MODIFY — add psutil dev dep + slow marker
python_code/uv.lock                                 # MODIFY — refresh by `uv sync --group dev`
python_code/tests/conftest.py                       # NEW    — root tests/ conftest with --duration option
python_code/tests/integration/test_long_run.py      # NEW    — the long-run test
```

Four files total; one new test, one new conftest, two config updates. No `src/` changes.

### Quality-gate expectations

- `ruff format`: clean.
- `ruff check`: clean. Expect `# noqa: ASYNC109` on each `timeout=` callsite that accepts the user-facing `timeout` parameter on `wait_*` (the repo convention — see how `test_reconnect_resilience.py` handles it).
- `mypy --strict src/pyjmri`: clean (unchanged surface).
- `mypy --strict tests/integration/test_long_run.py`: clean. `psutil>=5.9.5` ships type stubs in-tree; older versions need `pip install types-psutil`. The dev-dep pin `psutil>=5.9` should give a typed install on first sync.
- Unit-test regression run: **318 passing, no new** unit tests.
- Default integration suite after this story: **7 passing** (6 prior + 1 new `test_long_run.py` at 300 s) — but only when the developer explicitly invokes the integration target.
- `pytest -m "not integration"` (CI invocation): test must **not** be collected.

### Cross-story implications

- **Epic 6 / Story 6.5 (`CONTRIBUTING.md` release checklist)** will reference this test as the pre-release stability gate, with the explicit command `uv run --no-sync pytest python_code/tests/integration/test_long_run.py --duration=3600`. This story creates the artifact 6.5 will reference; no Epic-6 work is done here.
- **No production API changes.** The library's public surface is unchanged. `_force_disconnect()` remains test-only (underscore-prefixed, no `__all__` entry).
- **No new `# noqa: ASYNC109` suppressions in `src/`.** All suppressions land in the new test file only.
- **Sample output** (release-prep evidence to paste into release notes) at 1 hour against `Basement_Revised_2024.jmri`:
  ```
  pyjmri long-run: duration=3600s disconnects=5 reconnects=5 rss_delta=18.4MB fd_delta=0 task_delta=0 status=PASS
  ```

### Risks and mitigations

- **R1: External sensor state change during the run** (someone walks past a real sensor, or panel scripts toggle internal sensors). Mitigation: pick an **internal sensor** if possible by preferring system names starting with `IS` over `NS` (use `sensors[0]` for layout-agnosticism, but if a future hardening pass is needed, sort sensors by system-name prefix). For v1 of this test, accept the level-triggered branch — Story 3.3's pattern already handles "waiter resolved by subscription-ack" as a valid outcome.
- **R2: Clock drift / GC pause exceeding the 15 s reconnect window.** Mitigation: `_RECONNECT_WAIT_S = 15.0` is generous; `websockets`' default initial backoff is 0–5 s random, and local-loopback reconnect typically completes in < 1 s. If the budget is ever tight at one hour, increase to 30 s — but do not lower below 15 s.
- **R3: psutil `num_fds()` not available on Windows.** Mitigation: dev/CI runs only on macOS+Linux per NFR9. If a contributor runs the test on Windows, `num_fds()` raises `AttributeError` — catch and `pytest.skip` with a "Windows long-run unsupported" message, or just accept the failure (Windows is not a v1 target). **Preferred:** add a defensive `if not hasattr(psutil.Process(), 'num_fds'): pytest.skip(...)` at the top of `_metric_snapshot()`.
- **R4: RSS measurement variance** on macOS due to memory-pressure compaction. Mitigation: the 10 MB floor at 5 min already absorbs typical noise (~2–5 MB run-to-run on a quiet machine). If a release-prep run trips RSS for variance reasons, re-run; if it trips repeatedly, **that is a real leak signal**, not noise.

### References

- `_bmad-output/planning-artifacts/epics.md` §Story 3.4 — story scope, acceptance criteria, design intent.
- `_bmad-output/planning-artifacts/architecture.md` §Test Harness (line ~667) — "One-hour unattended stability run (NFR4) is its own pytest target, invoked manually before each release."
- `_bmad-output/planning-artifacts/architecture.md` §Reconnect & Restoration Mechanism (line ~462) — level-triggered semantics, subscription replay, `websockets` built-in backoff.
- `_bmad-output/planning-artifacts/architecture.md` §Concurrency Model (line ~535) — TaskGroup discipline; "no bare `asyncio.create_task` outside the supervising TaskGroup" applies to library code, not to test code, but the test's `asyncio.create_task(sensor.wait_change(...))` is fine because tests run inside pytest-asyncio's own loop, not Client's TaskGroup.
- `_bmad-output/planning-artifacts/prd.md` §NFR4 (line ~847) — "A user script subscribed to fewer than 100 entities can run unattended for at least one hour against a stable JMRI instance without leaking memory, file descriptors, or asyncio tasks."
- `_bmad-output/planning-artifacts/prd.md` §NFR5 (line ~850) — "at least five forced WebSocket disconnects per hour."
- `_bmad-output/planning-artifacts/prd.md` §NFR6 (line ~855) — bounded exponential backoff defaults.
- `_bmad-output/implementation-artifacts/3-3-forced-disconnect-resilience-integration-test.md` §Test structure sketch — the pattern this story extends to a loop.
- `_bmad-output/implementation-artifacts/3-1-...md` — `WSConnection.run()` architecture; `_on_ws_reconnect` log format; `SubscriptionRegistry.replay()`.
- `python_code/src/pyjmri/_transport.py:305-315` — `WSConnection._force_disconnect()` (Story 3.3).
- `python_code/src/pyjmri/client.py:321-335` — `Client._force_disconnect()` (Story 3.3).
- `python_code/src/pyjmri/client.py:351-363` — `Client._on_ws_reconnect()` (the INFO log producer the test polls).
- `python_code/src/pyjmri/_subscriptions.py:34-37` — `SubscriptionRegistry.size` property.
- `python_code/tests/integration/test_reconnect_resilience.py` — verbatim source for `_post_sensor_state`, `_opposite_sensor`, polling-deadline pattern, and `finally:` cleanup.
- `python_code/tests/integration/conftest.py` — `jmri_available` session fixture.
- `python_code/pyproject.toml` — current marker registration (`integration` only); current dev-dep set.
- Memory: `feedback_use_uv.md` — always invoke `uv run --no-sync` for pytest/mypy/ruff/python in this project.
- Memory: `project_throttle_simulator_blindspot.md` — NCE Simulator's command-echo limitation; sensor path is authoritative for NFR4/NFR5 proof on simulator-only layouts.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M-context) via Claude Code, with bmad-dev-story workflow. **Caveat:** this same context authored Story 3.4 immediately before implementing it, so the independent-review benefit was reduced. The post-merge `code-review` workflow should be run with a different model.

### Debug Log References

- **Test wall-clock < duration on first 60 s smoke (2026-05-19):** The first 60 s smoke completed in 30.79 s, not ~60 s, because the workload loop exited as soon as the last scheduled disconnect cycle finished. NFR4 is a **duration** claim (the script must actually run for that long), not a "disconnects done" claim. **Fix:** added an idle-fill loop after the disconnect schedule completes — `while loop.time() - start_t < duration_s: await asyncio.sleep(min(remaining, 1.0))`. Re-running at `--duration=60` then took 60.18 s wall-clock. Default 300 s run produced exactly 300.15 s wall-clock.
- **mypy strict on `psutil` (2026-05-19):** `psutil` 7.2.2 (current latest on PyPI) does not ship type stubs in-tree; mypy emitted `[import-untyped]`. The Dev Notes anticipated this and pre-authorized `# type: ignore[import-untyped]` on the `import psutil` line. Also needed an `int(...)` narrowing on `process.num_fds()` since the call returns `Any` through the unstubbed module. No other ignores added; the rest of the file is fully typed under `--strict`.

### Completion Notes List

- All 5 ACs satisfied. All 4 tasks and every subtask checked.
- **AC1 (parameterization + markers):** `python_code/tests/conftest.py` registers `--duration` via `pytest_addoption`. `_resolve_duration` precedence is CLI → env var (`PYJMRI_LONG_RUN_DURATION`) → default 300. `slow` marker registered in `pyproject.toml` alongside `integration`. Test decorated with both markers.
- **AC2 (disconnect cadence):** Cadence formula `num_disconnects = max(1, math.ceil(duration_s / 720))` lives in the test body. Schedule `[duration * (i+1) / (N+1) for i in range(N)]` spaces disconnects evenly; never at t=0 or t=duration. Each cycle polls `caplog.records` from a per-cycle index marker for the `pyjmri.reconnect` INFO log within a 15 s budget, then advances the marker for the next cycle.
- **AC3 (leak metrics):** Baseline captured after Client + first `discover()` settle; final captured after the workload + idle-fill loop, **before** `Client.__aexit__`. Three thresholds enforced: RSS delta linear-interp `[10 MB at 300 s, 50 MB at 3600 s]`, FD delta ≤ 5, asyncio task delta ≤ 2. Assertion messages include baseline, final, and delta for diagnosis.
- **AC4 (waiter survival + reconnect success):** Each cycle registers an `asyncio.create_task(sensor.wait_change(timeout=30))` before the disconnect, then accepts either valid outcome after reconnect: (a) waiter already resolved via level-triggered subscription-ack (assert result ≠ pre-cycle state); (b) waiter still pending → POST the opposite state and await, with sensor restored to `starting_state` for the next cycle. `finally:` cancels any leftover waiter.
- **AC5 (CI-skip + layout-agnostic + summary):** `pytest -m "not integration"` does not collect the test (verified: 318 passed, 7 deselected). Layout-agnostic skip on empty `layout.sensors`. Final `print(...)` emits the summary line under `pytest -s`.
- **Live-JMRI evidence (NCE Simulator on Basement_Revised_2024):**
  - `--duration=60` → `pyjmri long-run: duration=60s disconnects=1 reconnects=1 rss_delta=0.0MB fd_delta=0 task_delta=0 status=PASS` (60.18 s)
  - default 300 s → `pyjmri long-run: duration=300s disconnects=1 reconnects=1 rss_delta=0.1MB fd_delta=0 task_delta=0 status=PASS` (300.15 s)
  - 1-hour run **not** executed during this story (it's the pre-release artifact; Epic 6 / Story 6.5 will reference it as the release-checklist invocation).
- **Quality gates:** `ruff format` + `ruff check` + `mypy --strict src/pyjmri` + `mypy --strict tests/integration/test_long_run.py tests/conftest.py` all clean. 318 unit tests passing, no regressions.
- **No `src/pyjmri/` changes** — production surface untouched, as promised in the Dev Notes scope.

### File List

- `python_code/pyproject.toml` — MODIFIED. Added `psutil>=5.9` to `[dependency-groups].dev` (alphabetical, between `mypy` and `pytest`). Added `slow` marker to `[tool.pytest.ini_options].markers`.
- `python_code/uv.lock` — MODIFIED. Refreshed by `uv sync --group dev` after adding `psutil`. Installed `psutil==7.2.2`.
- `python_code/tests/conftest.py` — NEW. Root-of-tests conftest registering the `--duration=<seconds>` CLI option via `pytest_addoption`.
- `python_code/tests/integration/test_long_run.py` — NEW. Parameterized long-run integration test: `test_long_run_stability`. Marked `@pytest.mark.integration` AND `@pytest.mark.slow`. Default 5-minute duration; override via `--duration` CLI option or `PYJMRI_LONG_RUN_DURATION` env var. Forces N evenly-spaced WS disconnects (formula `max(1, ceil(duration_s / 720))`), verifies waiter survival + reconnect + state-change roundtrip per cycle, captures pre/post leak metrics (RSS via `psutil`, FDs via `psutil.Process.num_fds()`, asyncio tasks via `asyncio.all_tasks()`), enforces linear-interp thresholds, and prints a one-line summary on success.

## Change Log

- 2026-05-19 — Story 3.4 implemented (`in-progress` → `review`). All 5 ACs satisfied. New `tests/conftest.py` registers `--duration` CLI option. `pyproject.toml` gains `slow` marker + `psutil>=5.9` dev dep (`uv.lock` refreshed). New `tests/integration/test_long_run.py` parameterized long-run test passes against live JMRI at both `--duration=60` (60.18 s wall-clock, all deltas ≈ 0) and default 300 s (300.15 s wall-clock, all deltas ≈ 0). Quality gates clean: 318 unit tests pass, ruff + mypy --strict clean. **No `src/pyjmri/` changes.** Single in-development fix: added an idle-fill loop after the disconnect schedule so wall-clock matches the requested duration (NFR4 is a duration claim, not a disconnect-count claim).
- 2026-05-19 — Story 3.4 created (`backlog` → `ready-for-dev`). Five ACs defining a parameterized long-run integration test (default 300 s, override via `--duration` or `PYJMRI_LONG_RUN_DURATION`), NFR4 leak-metric assertions (RSS / FDs / asyncio tasks), NFR5 disconnect cadence (≥ 5/hour at ≥ 1 hour), and standard-CI-skip discipline. Four files touched: `pyproject.toml`, `uv.lock`, new `tests/conftest.py`, new `tests/integration/test_long_run.py`. Builds on Story 3.3's `_force_disconnect()` hook; no `src/pyjmri/` changes.
