# pyjmri v1.0.0 hardware-mode validation — operator instructions

This directory lives at `python_code/release-check/` in the JMRI repo. It contains
two scripts (`release_drive.py`, `release_keepalive.py`) and these instructions.
It is **operator-only validation** for the pyjmri v1.0.0 pre-publish release
checklist — not part of the published `pyjmri` wheel, not under `examples/`.

You are running this on a machine connected (directly or over LAN) to JMRI
which is connected to **real NCE hardware** powering the basement layout. The
simulator cannot validate this step — it has no virtual decoder.

---

## Prerequisites on the other machine

- The JMRI repo cloned (you presumably already have it).
- Python 3.11 or later.
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh` if missing).
- Network access to JMRI (`localhost:12080` if JMRI is on this machine, or
  `192.168.1.159:12080` if JMRI is on the basement layout machine over LAN).

## Setup on the other machine

```bash
cd /path/to/JMRI
git pull
cd python_code
uv sync
```

`uv sync` creates / updates the local `.venv` with pyjmri (dev-tree, matches
the v1.0.0 source) and its dependencies.

## Layout precondition checklist

Confirm each before running anything:

- [ ] JMRI 5.14 or later is running and connected to real NCE hardware
      (NCE USB or NCE PowerCab over serial).
- [ ] Basement layout (or equivalent NCE layout) is powered — booster ON,
      track power live.
- [ ] A known-responsive locomotive is on the rails at a documented DCC
      address. Basement default is DCC `5327` long.
- [ ] The loco has at least a few meters of clear track in both directions.

Note the **JMRI version** and **NCE hardware identifier** (e.g., "NCE USB")
somewhere — you'll need both when reporting results.

---

## Step 1 — Drive test

From `python_code/`:

```bash
uv run --no-sync python release-check/release_drive.py --dcc 5327 --url http://localhost:12080
```

Adjust `--dcc` to your test loco; adjust `--url` if JMRI is on a different
machine (`http://192.168.1.159:12080` for the basement machine over LAN).

**Watch the locomotive.** Record PASS or FAIL for each of these three
observations, with the loco ID and rough distance traveled:

| # | Observation | PASS / FAIL |
|---|---|---|
| 1 | Forward motion — loco moved forward during the first 8 s window | |
| 2 | Reverse motion — loco changed direction and moved in reverse during the second 8 s window | |
| 3 | Function-bit effect — function 0 toggled (typically headlight on, then off) | |

**Any FAIL is a release blocker.** Diagnose (decoder consist conflict, wrong
DCC address, dirty wheels/track, decoder reset needed) and re-run before
continuing.

A successful `await` in pyjmri only confirms the command reached JMRI — visual
confirmation at the layout is the only ground truth for whether the layout
moved.

---

## Step 2 — Keep-alive observation

Wait a few seconds after the drive script finishes so JMRI fully releases the
previous throttle session on the same DCC address.

```bash
uv run --no-sync python release-check/release_keepalive.py --dcc 5327 --url http://localhost:12080
```

The script does:

1. Acquire the throttle, set speed 0 forward.
2. **Hold silent for 30 seconds.** Do NOT press Ctrl-C during this hold —
   that releases the throttle session early and creates a false "drop" result.
3. Send `set_speed(0.1, forward=True)` and watch the loco for 5 seconds.
4. Stop and release.

The 30 s hold is 2× pyjmri's default keep-alive interval (15.0 s). The point
is: if JMRI silently expires idle throttle sessions, the `set_speed(0.1)`
after the silence will hit a dropped session and the loco will not move.

**Record one of two outcomes:**

| Observation | Outcome to record |
|---|---|
| Loco responds to `set_speed(0.1)` — moves briefly forward | **"JMRI keeps throttle held after 30 s silence"** |
| Loco does NOT respond — stays still | **"JMRI drops throttle after 30 s silence"** |

The "keeps" outcome means the v1 no-op keep-alive stub in `throttle.py` is
correct as-is.

The "drops" outcome means the keep-alive coroutine body must be activated.
This is a source-code change (replace the no-op stub at `throttle.py:329-336`
with a four-line `while True: await asyncio.sleep(...); throttle_heartbeat(...)`
loop) — the release procedure will handle that if it comes up, including
re-running the quality gates and rebuilding the v1.0.0 wheel.

---

## Reporting back

Send back a short message with:

1. **JMRI version** — e.g., `JMRI 5.14.1`.
2. **NCE hardware identifier** — e.g., `NCE USB` or `NCE PowerCab`.
3. **Date** — today's date.
4. **DCC address used** — e.g., `5327`.
5. **Drive results** — PASS/FAIL on Forward, Reverse, Function-bit.
6. **Keep-alive outcome** — `keeps` or `drops`.

Example report:

```
JMRI 5.14.1, NCE USB, 2026-05-26, DCC 5327
Drive: Forward PASS (~2m), Reverse PASS (~2m), Function-bit PASS (headlight on/off)
Keep-alive: keeps
```

If anything failed, also include what you observed and any diagnostic notes.

---

## Scope of what this validates

- ✅ Throttle command path reaches a real NCE decoder.
- ✅ Forward / reverse / function-bit commands take effect on a physical loco.
- ✅ Keep-alive behavior on this JMRI version × NCE hardware combination.

What this does NOT validate (covered by other gates in the release checklist):

- ❌ Turnout, sensor, route, light, or memory hardware behavior — those run
  against the simulator in the integration test suite (NCE is open-loop;
  there is no electronic confirmation a turnout physically moved).
- ❌ Long-run stability — the 1-hour long-run test runs against the simulator
  on a separate machine, in parallel with this validation.
