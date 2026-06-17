"""Standalone out-and-back runner for engine 8997.

Run from the command line:

    cd /Users/jmichaeldean/JMRI/python_code
    .venv/bin/python examples/train_out_and_back.py

The train departs NW Track 6. Press Enter at any time to signal
come-home; the script then drives the train back and parks it.
"""

import asyncio
import logging
import sys
from datetime import datetime

from pyjmri import Client

HOST = "localhost:12080"
DCC = 8997
STAGING_TRACK = "NW Track 6"
RETURN_TRACK = "NW Track 6"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    filename="pyjmri.log",
    force=True,
)


async def horn(t, *, duration: float = 1.2, pause: float = 0.5, times: int = 3) -> None:
    for _ in range(times):
        await t.set_function(2, True)
        await asyncio.sleep(duration)
        await t.set_function(2, False)
        await asyncio.sleep(pause)


async def wait_edge(sensor) -> None:
    print(f"Waiting for {sensor} to be active")
    await sensor.wait_active()
    print(f"{sensor} is active")
    print(f"Waiting for {sensor} to become inactive")
    await sensor.wait_inactive()
    print(f"{sensor} is now inactive")


async def slow_through(layout, t, schedule):
    for sensor_name, speed in schedule:
        await layout.sensors[sensor_name].wait_active()
        await t.set_speed(speed, forward=True)


async def count_laps(throat) -> None:
    """Print one line per lap while the train is on the mainline."""
    lap = 0
    while True:
        await throat.wait_active()
        lap += 1
        print(f"Lap {lap} at {datetime.now():%H:%M:%S}")
        await throat.wait_inactive()


async def run_train(layout, dcc, staging_track, return_track, come_home):
    print(f"[{dcc}] preparing to depart {staging_track}")
    throat = layout.sensors["West / SW"]
    await layout.routes[staging_track].activate()

    try:
        async with layout.throttle(dcc, long=True) as t:
            await t.set_function(0, True)
            await t.set_speed(0.2, forward=True)
            print(f"[{dcc}] departing {staging_track}")
            # await t.set_speed(0.2)
            await wait_edge(throat)
            await layout.routes["NW Staging Close"].activate()
            await t.set_speed(0.8)
            print("When you want the train to return home, press the Enter key.")
            lap_task = asyncio.create_task(count_laps(throat))
            try:
                await come_home.wait()
                print("come_home.wait() returned cleanly")
            except BaseException as e:
                print(f"come_home.wait() raised: {type(e).__name__}: {e}")
                raise
            finally:
                lap_task.cancel()
                try:
                    await lap_task
                except asyncio.CancelledError:
                    pass
            print(f"{dcc} has been commanded to return to staging")
            await slow_through(
                layout,
                t,
                [
                    ("North Zone 9", 0.30),
                    ("West / SW", 0.25),
                ],
            )
            await throat.wait_inactive()
            await t.set_speed(0)
            print("Train stopping, ready to reverse")
            await asyncio.sleep(10)
            await layout.routes[return_track].activate()
            await t.set_function(1, True)
            await t.set_speed(0.15, forward=False)
            await wait_edge(throat)
            await t.set_speed(0.10, forward=False)
            await asyncio.sleep(28)
            await t.set_speed(0)
            await t.set_function(1, False)
            await t.set_function(0, False)
            await layout.routes["NW Staging Close"].activate()
            print(f"{dcc} returned and parked in {return_track}")
    except BaseException as e:
        print(f"run_train exiting with: {type(e).__name__}: {e}")
        raise


async def wait_for_enter() -> None:
    """Block until the user presses Enter. `input()` runs in a worker
    thread so the asyncio loop keeps driving the train task."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, input, "")


async def main() -> None:
    async with Client(HOST) as jmri:
        layout = await jmri.discover()
        print(
            f"discovered: {len(layout.turnouts)} turnouts, "
            f"{len(layout.sensors)} sensors, "
            f"{len(layout.routes)} routes, "
            f"{len(layout.blocks)} blocks"
        )

        come_home = asyncio.Event()
        train_task = asyncio.create_task(
            run_train(layout, DCC, STAGING_TRACK, RETURN_TRACK, come_home)
        )

        print()
        print(">>> Train is running. Press Enter to send come-home. <<<")
        print()

        try:
            await wait_for_enter()
        except (KeyboardInterrupt, EOFError):
            print("Interrupt received — sending come-home anyway")

        come_home.set()
        print("Come-home signal sent. Waiting for train to park...")

        await train_task
        print("Done.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Aborted by user")
        sys.exit(1)
