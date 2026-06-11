# pyjmri

Async Python client for the JMRI web server.

## Quickstart

`pyjmri` is an async Python client for the JMRI web server. It lets you drive a JMRI-controlled model railroad — turnouts, sensors, lights, throttles — from Python scripts using `async`/`await`, instead of JMRI's bundled Jython. In the next five minutes, you'll install the library, connect to a running JMRI instance, discover the layout, and flip a turnout.

### Prerequisites

- Python 3.11 or newer.
- JMRI 5.14 or later, running with its web server enabled at `http://localhost:12080`.
- A panel file open in JMRI with at least one turnout defined.

To verify JMRI's web server is up, open `http://localhost:12080/json/v5/version` in a browser — you should see a JSON envelope reporting the JSON API version.

### Install

[uv](https://docs.astral.sh/uv/) is recommended (it's the modern Python toolchain `pyjmri` is developed against); pip works as a universal fallback:

```bash
uv add pyjmri
```

```bash
pip install pyjmri
```

### Your first script

Save this as `quickstart.py` and run `python quickstart.py`:

```python
import asyncio
from pyjmri import Client, TurnoutState


async def main() -> None:
    async with Client() as jmri:
        layout = await jmri.discover()
        turnout = next(iter(layout.turnouts.values()))
        print(f"name={turnout.name} user_name={turnout.user_name} initial state={turnout.state.name}")
        target = TurnoutState.THROWN if turnout.state is TurnoutState.CLOSED else TurnoutState.CLOSED
        await turnout.set_state(target)
        print(f"final state={target.name}")


asyncio.run(main())  # in a Jupyter notebook, use: await main()
```

### What you should see

Two lines, with the exact values depending on your panel file:

```text
name=NT400 user_name=North Yard Lead initial state=CLOSED
final state=THROWN
```

The two states are intentionally opposite — the script reads the current state, then commands the opposite. Run it again and the values will swap. The `final state` line means JMRI accepted the command — see the Limitations section below for what "accepted" does and does not imply at the layout. If `initial state=UNKNOWN` appears instead of `CLOSED` or `THROWN`, that is normal — JMRI reports `UNKNOWN` for any turnout not yet commanded in the current session.

### Try it in a notebook

The repo includes `explorepyjmri.ipynb`, a Jupyter notebook that walks through the same quickstart broken into separate cells — imports, logging setup, client creation, and the turnout flip. It's a convenient sandbox for poking at JMRI interactively without restarting a script every time.

To use it:

1. Open `explorepyjmri.ipynb` in Jupyter, VS Code, Cursor, or any other notebook-capable editor.
2. Select a kernel that has `pyjmri` installed (e.g., the `.venv` from `uv sync` in this directory).
3. Run the cells top-to-bottom. The logging-setup cell writes DEBUG output to `pyjmri.log` in the working directory; that file is gitignored.

Re-running the `await main()` cell will flip the same turnout back and forth, since the script always commands the opposite of the currently reported state.

## Limitations

`pyjmri` is honest about what it does and does not know. DCC itself is an open-loop control protocol: the command station broadcasts packets onto the rails, but accessory and locomotive decoders do not push anything back. Virtually every DCC system in common use behaves this way. Layouts that add auxiliary feedback hardware — block-occupancy detectors, transponding receivers — regain a real upstream signal for the entities those sensors cover, and `pyjmri` surfaces that signal through `Sensor`s (see "Sensors are the real feedback path" below). For everything else, `pyjmri` faithfully relays what JMRI reports, which is in turn what DCC tells JMRI.

Read this section before writing code that assumes a returned `await` implies a moved turnout, a powered locomotive, or a confirmed route.

### Hardware scope

`pyjmri` talks to JMRI's JSON web server, not to any specific DCC hardware. Anything JMRI can drive, `pyjmri` should be able to drive. v1 has been tested only against the maintainer's layout, which uses an NCE command station (USB and simulator); the rest of the limitations in this section are DCC-protocol properties that apply to any JMRI-supported DCC system, not NCE-specific quirks. If you exercise `pyjmri` against different DCC hardware, please open a GitHub issue with what worked and what didn't so the tested-hardware footprint can grow.

### DCC is open-loop — JMRI reports last-commanded, not observed

There is no DCC-bus feedback from a commanded accessory (turnout, route, light) or locomotive decoder back to the command station: the rails carry packets outbound but not inbound. JMRI knows what it *commanded*, not what physically happened — the state it reports for a turnout, light, or route is the last-commanded state, not an observed one. This is a DCC protocol property, not a JMRI or `pyjmri` choice. `pyjmri` does not raise an exception when reported state diverges from physical reality; it has no second signal to compare against. Visual confirmation at the layout, or an auxiliary sensor (next subsection), is the only ground truth.

### "Command acknowledged" means JMRI accepted the command, not that the layout moved

When `await turnout.set_state(TurnoutState.THROWN)` returns, the library has confirmed that JMRI's JSON web server accepted the request and updated its internal model. The DCC bus may not have delivered the packet; the turnout coil may have failed; the decoder may be unpowered. `pyjmri` does not raise for any of these — it has no signal to detect a turnout that physically failed to move. This holds against a JMRI simulator and against any real DCC hardware alike. A successful `await` confirms intent reached JMRI, nothing more.

### Layout power is hardware-controlled — `pyjmri` exposes read-only `power_state()`

The booster's physical power switch is the source of truth for whether the rails are energized. JMRI can *observe* the booster's power state, and `pyjmri` surfaces that observation via `jmri.power_state()`, which returns `PowerState.ON`, `PowerState.OFF`, or `PowerState.UNKNOWN`. `pyjmri` does not expose a power-write method by design — the library will not synthesize a software `power_on()` that could mislead a script into believing it controls layout energization. `pyjmri` does not raise if a script keeps commanding entities while the layout is unpowered.

### Throttle acquire is best-effort — it reserves a slot, not a locomotive

Entering `async with jmri.throttle(dcc_address=N, long=True) as loco:` successfully means JMRI accepted the acquire request and reserved a throttle slot. It does NOT mean a locomotive at DCC address `N` is on the rails, powered, or responsive — the decoder may be unaddressed, asleep, or absent. `set_speed` and `set_function` send DCC packets toward that address whether or not a decoder is listening. `pyjmri` does not raise an exception for a missing locomotive on the rails. In practice: don't gate downstream logic on a successful `async with jmri.throttle(...)` entry — gate it on a sensor detecting train motion to confirm the decoder is actually responding.

### Sensors are the real feedback path

Block-occupancy detectors and other sensors wired through JMRI hardware DO carry a true upstream signal — they report what the *physical* world is doing. `await sensor.wait_state(SensorState.ACTIVE)` is therefore a meaningful event-driven primitive: it waits for an actual electrical change at the layout, not for a software echo. When event-driven correctness matters — waiting for a train to reach a block, confirming a route cleared — drive the wait off a sensor, never off a turnout or route state. `pyjmri` does not raise when a broken sensor never fires; a `wait_state` call without a `timeout=` argument will simply wait forever.

### No library-side authentication — JMRI's web server is unauthenticated by design

`pyjmri` does not add an authentication layer. JMRI's JSON web server is unauthenticated and intended for use on a trusted network — typically the same machine as JMRI itself, or the same LAN as the layout. `pyjmri` does not raise an exception when an untrusted client also reaches that server; there is no auth check to fail. Do not expose JMRI's web server to the public internet; keep it on localhost or behind your home firewall and let `pyjmri` talk to it from there.

## Migrating from Jython

`pyjmri` does not replace JMRI's bundled Jython — Jython continues to work, and `pyjmri` is for users who prefer modern async Python. This table maps common Jython idioms to their `pyjmri` equivalents for users porting existing scripts.

The biggest structural shift is from `AbstractAutomaton`'s synchronous `init()` / `handle()` polling loop to a top-level `async def` function wrapped in `asyncio.run(...)`. Long waits become `await` points: instead of returning `True` from `handle()` to keep polling, you continue past an `await sensor.wait_active()` line.

| Jython | `pyjmri` |
| --- | --- |
| `sensors.provideSensor("Block 1")` | `layout.sensors["Block 1"]` |
| `turnouts.getTurnout("NT400")` | `layout.turnouts["NT400"]` |
| `routes.getRoute("Crossover")` | `layout.routes["Crossover"]` |
| `memories.provideMemory(name).getValue()` | `await layout.memories[name].get_value()` |
| `self.getThrottle(5327, True)` | `async with layout.throttle(5327, long=True) as t:` (see note (b)) |
| `throttle.setSpeedSetting(0.4)` | `await t.set_speed(0.4, forward=True)` (see note (a)) |
| `throttle.setIsForward(True)` | `await t.set_speed(current_speed, forward=True)` (see note (a)) |
| `throttle.setF2(True)` | `await t.set_function(2, True)` |
| `self.waitSensorActive(s)` | `await s.wait_active()` |
| `self.waitSensorInactive(s)` | `await s.wait_inactive()` |
| `self.waitMsec(ms)` | `await asyncio.sleep(ms / 1000)` (see note (c)) |
| `AbstractAutomaton init() / handle()` | top-level `async def` + `asyncio.run(...)` (see note (d)) |
| `TrainManager.getTrainsByIdList()` | `(await jmri.discover_operations()).trains` (see note (e)) |
| `CarManager.getByIdList()` | `(await jmri.discover_operations()).cars` (see note (e)) |

### Notes

- **(a) Speed and direction are atomic in `pyjmri`.** `set_speed(value, *, forward)` sets both in one call. The Jython pair `setSpeedSetting(v)` + `setIsForward(d)` collapses into `await t.set_speed(v, forward=d)`. `forward` is keyword-only AND required — bare `t.set_speed(0.4)` raises `TypeError`. To change only direction, re-emit the current speed with the new direction; to change only speed, re-emit the current direction with the new speed.
- **(b) Throttle lifecycle is the async context manager.** `async with layout.throttle(addr, long=True) as t:` acquires on entry and releases on exit, including exception paths. No explicit `t.release()` call is needed; the Jython end-of-script release pattern goes away. (A `.release()` method exists for advanced cases — ordinary scripts don't need it.)
- **(c) `asyncio.sleep` takes seconds, not milliseconds.** Add `import asyncio` at the top of the script (Jython's `waitMsec` was a method on `AbstractAutomaton`), and convert with `/ 1000` — `waitMsec(500)` becomes `await asyncio.sleep(0.5)`.
- **(d) No `init` / `handle` analog.** `pyjmri` is event-driven, not polling: instead of returning `True` from `handle()` to keep looping, you `await` sensor events. The top-level structure is one `async def main()` wrapped in `asyncio.run(main())` — no base class to subclass.
- **(e) Operations discovery is read-only and returns a snapshot.** `await jmri.discover_operations()` returns an `Operations` container with `.locations` / `.trains` / `.cars` / `.engines`, each looked up by name like a `Layout` collection. It is a point-in-time read — re-call to refresh. See the [Operations](#operations-read-only) section below.

## Operations (read-only)

JMRI's Operations module models an operating session: locations (yards, towns, staging), the cars and engines on the layout, and trains with assigned routes. `pyjmri` exposes it through a separate entry point:

```python
async with Client() as jmri:
    ops = await jmri.discover_operations()
    print(f"{len(ops.locations)} locations, {len(ops.trains)} trains, "
          f"{len(ops.cars)} cars, {len(ops.engines)} engines")
    for train in ops.trains.values():
        print(train.user_name, "→", train.current_location)
    for car in ops.cars.values():
        print(car.name, "at", car.location, "on train", car.train)
```

`discover_operations()` returns an `Operations` container — distinct from the `Layout` returned by `discover()`. Locations and trains are looked up by both system and user name; cars and engines by road+number. A worked "where is every car" report is in [`examples/operations_report.py`](examples/operations_report.py).

### Operations is not the roster

The roster (DecoderPro's catalog) lists *every* engine you have ever programmed. Operations engines are the **operationally-active subset actually deployed** on the layout — you may have ~45 roster engines but only a handful running tonight. The two are intentionally separate: an Operations `Engine` is never a roster entry, and Operations tells you a car's current location and train assignment, which the roster cannot.

### Fully simulator-testable

Operations is a pure data subsystem — cars, engines, locations, and trains are records JMRI serves over JSON regardless of hardware. Unlike throttles and sensors (see [Limitations](#limitations)), Operations discovery is **not** subject to the open-loop blind spot, so it is fully exercisable on the NCE simulator with Operations data loaded.

### Read-only in this release

Operations discovery is **read-only**. There is no build-train, move/assign-car, or generate-manifest surface in `pyjmri` yet — those mutating operations are deferred to a future command increment. Today you can inspect the whole operating session as typed Python; you cannot change it.
