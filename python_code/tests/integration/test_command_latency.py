"""NFR3 microbenchmark: pyjmri command-path overhead.

Asserts that the median per-command library overhead (the time
``Turnout.throw()`` / ``Turnout.close()`` spends outside the underlying
JMRI HTTP roundtrip) is under 20 ms.

Methodology
-----------
JMRI's raw HTTP response time is measured in a separate warm-up phase
(``_WARMUP`` plain POSTs via raw ``httpx.AsyncClient``) *before* the
timed library-call phase.  The median of those warm-up samples is used as
``jmri_http_baseline_ms``; each trial's overhead is then
``call_total_ms - jmri_http_baseline_ms``.

Sequencing the raw POST immediately after the library call (as some
benchmarks do) would command the turnout a second time under post-command
JMRI load, producing overhead samples that can be negative and that
measure nothing meaningful.  The warm-up approach keeps the two
measurement phases independent.

Marked ``integration`` AND ``slow`` so it stays out of the default
``integration and not slow`` selector that CI runs locally; this test is
release-prep only.
"""

from __future__ import annotations

import statistics
import time
from urllib.parse import quote

import httpx
import pytest

from pyjmri import Client, TurnoutState

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_TRIALS = 20
_WARMUP = 20
_OVERHEAD_BUDGET_MS = 20.0


async def test_turnout_command_overhead_median_under_20ms(jmri_available: None) -> None:
    async with Client() as jmri:
        layout = await jmri.discover()
        turnouts = list(layout.turnouts.values())
        if not turnouts:
            pytest.skip("layout has no turnouts — cannot measure command latency")
        turnout = turnouts[0]

        original = await turnout.get_state()
        if original not in {TurnoutState.CLOSED, TurnoutState.THROWN}:
            pytest.skip(f"turnout {turnout.name} in non-binary state {original.name}")

        url = f"http://localhost:12080/json/v5/turnout/{quote(turnout.name, safe='')}"

        try:
            async with httpx.AsyncClient() as raw_http:
                # Warm-up phase: measure JMRI's raw HTTP response time
                # independently of the library calls.  Alternating codes
                # so JMRI processes a real state change each time.
                warmup_ms: list[float] = []
                for i in range(_WARMUP):
                    code = 4 if i % 2 == 0 else 2
                    body = {"type": "turnout", "data": {"name": turnout.name, "state": code}}
                    t = time.monotonic()
                    r = await raw_http.post(url, json=body)
                    warmup_ms.append((time.monotonic() - t) * 1000.0)
                    assert r.status_code == 200, r.text

                jmri_http_baseline_ms = statistics.median(warmup_ms)

                # Timed phase: measure library-call total time.
                call_totals_ms: list[float] = []
                for i in range(_TRIALS):
                    target = TurnoutState.THROWN if i % 2 == 0 else TurnoutState.CLOSED
                    t0 = time.monotonic()
                    await turnout.set_state(target)
                    call_totals_ms.append((time.monotonic() - t0) * 1000.0)

        finally:
            try:
                await turnout.set_state(original)
            except Exception:
                pass

        overheads_ms = [c - jmri_http_baseline_ms for c in call_totals_ms]
        median_overhead_ms = statistics.median(overheads_ms)
        print(
            f"pyjmri command latency: median_overhead={median_overhead_ms:.3f}ms "
            f"jmri_baseline={jmri_http_baseline_ms:.3f}ms "
            f"n={_TRIALS} status="
            f"{'PASS' if median_overhead_ms < _OVERHEAD_BUDGET_MS else 'FAIL'}"
        )
        assert median_overhead_ms < _OVERHEAD_BUDGET_MS, (
            f"NFR3 violation: median library overhead {median_overhead_ms:.3f}ms "
            f">= budget {_OVERHEAD_BUDGET_MS}ms. "
            f"JMRI baseline: {jmri_http_baseline_ms:.3f}ms (median of {_WARMUP} warm-up POSTs). "
            f"Call totals (ms): {[round(x, 3) for x in call_totals_ms]}. "
            f"Overhead samples (ms): {[round(x, 3) for x in overheads_ms]}"
        )
