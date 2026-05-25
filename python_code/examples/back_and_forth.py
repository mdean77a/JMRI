"""Drive a locomotive back and forth between two sensors.

This is the pyjmri port of ``jython/MikeBackAndForth.py``: pick a locomotive
by DCC address and two sensors by name; drive forward until the forward
sensor trips; reverse; wait for the forward sensor to clear (so the
loco fully leaves the overlap); drive until the reverse sensor trips; loop.

``Ctrl-C`` exits cleanly — the ``async with`` blocks for the :class:`Client`
and the :class:`Throttle` handle their own teardown (WebSocket close,
throttle release).

Run it
------

Default (basement layout, NCE simulator)::

    uv run --no-sync python examples/back_and_forth.py

Against a different layout or locomotive::

    uv run --no-sync python examples/back_and_forth.py \\
        --dcc 1029 --forward-sensor "Block 7" --reverse-sensor "Block 12"

Short-address locomotive::

    uv run --no-sync python examples/back_and_forth.py --dcc 41 --short

Defaults
--------

- ``--url`` — JMRI URL; ``None`` means ``localhost:12080`` (the Client default).
- ``--dcc 5327`` — the loco from ``jython/MikeBackAndForth.py``.
- ``--long`` / ``--short`` — long (4-digit) DCC addressing is the default;
  pass ``--short`` for short (1-127) addressing.
- ``--forward-sensor "Block 1"`` — the sensor that trips when the loco
  reaches the forward end of its run (basement-layout user name).
- ``--reverse-sensor "Block 11"`` — the sensor that trips at the reverse end.
- ``--speed 0.4`` — throttle setting in [0.0, 1.0]. 0.4 matches the Jython
  source's documented speed.

Simulator vs hardware
---------------------

The NCE simulator accepts throttle commands and does not raise, but it has
no virtual locomotive — no train moves and no block sensor fires on its
own. To see this script's oscillation actually run on the simulator, tap
the forward and reverse sensors in JMRI's Sensor Table UI to fire
``wait_active`` / ``wait_inactive`` by hand. To see it run for real, point
this at a JMRI connected to NCE hardware with a responsive decoder at the
configured DCC address; physical motion will trip the block sensors and
the loop progresses on its own.
"""

from __future__ import annotations

import argparse
import asyncio

from pyjmri import Client


async def main(args: argparse.Namespace) -> None:
    url: str | None = args.url
    speed: float = args.speed
    client = Client(url) if url is not None else Client()
    async with client as jmri:
        layout = await jmri.discover()
        forward_sensor = layout.sensors[args.forward_sensor]
        reverse_sensor = layout.sensors[args.reverse_sensor]
        async with layout.throttle(args.dcc, long=args.long) as t:
            while True:
                await t.set_speed(speed, forward=True)
                await forward_sensor.wait_active()
                await t.set_speed(speed, forward=False)
                await forward_sensor.wait_inactive()
                await reverse_sensor.wait_active()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Drive a locomotive back and forth between two sensors.",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="JMRI URL (host:port). Defaults to localhost:12080.",
    )
    parser.add_argument("--dcc", type=int, default=5327, help="DCC decoder address.")
    addressing = parser.add_mutually_exclusive_group()
    addressing.add_argument(
        "--long",
        dest="long",
        action="store_true",
        help="Use long (4-digit) DCC addressing (default).",
    )
    addressing.add_argument(
        "--short",
        dest="long",
        action="store_false",
        help="Use short (1-127) DCC addressing.",
    )
    parser.set_defaults(long=True)
    parser.add_argument(
        "--forward-sensor",
        type=str,
        default="Block 1",
        help="Sensor name (user-name or system-name) tripped at the forward end.",
    )
    parser.add_argument(
        "--reverse-sensor",
        type=str,
        default="Block 11",
        help="Sensor name (user-name or system-name) tripped at the reverse end.",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=0.4,
        help="Throttle setting in [0.0, 1.0].",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_parse_args()))
