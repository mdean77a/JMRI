"""Drive several locomotives concurrently on a single JMRI client.

PRD Journey 2: a multi-train evening session. One :class:`pyjmri.Client`
connection, one :meth:`discover` call, one :func:`asyncio.gather` of
per-locomotive coroutines — each acquires its own throttle and oscillates
between its own pair of block sensors. Adding or removing locomotives is
a config change, not a code change.

Run it
------

Default (two basement-layout locomotives, NCE simulator)::

    uv run --no-sync python examples/multi_train_session.py

Custom roster via a JSON file::

    uv run --no-sync python examples/multi_train_session.py --config my_locos.json

Config file shape (a JSON list of loco objects)::

    [
      {
        "dcc": 5327,
        "long": true,
        "forward_sensor": "Block 1",
        "reverse_sensor": "Block 6",
        "speed": 0.4
      },
      {
        "dcc": 1029,
        "long": true,
        "forward_sensor": "Block 7",
        "reverse_sensor": "Block 12",
        "speed": 0.35
      }
    ]

Defaults
--------

- ``--url`` — JMRI URL; ``None`` means ``localhost:12080``.
- ``--config`` — path to a JSON file with the shape shown above. If omitted,
  the two basement-layout locomotives below are used: loco 5327 (long)
  between "Block 1" / "Block 6" at speed 0.4 — matching
  ``jython/MikeBackAndForthTwoEngines.py``'s first loco — and loco 1029
  (long, the "1029 NW2 Switcher" from the basement roster) between
  "Block 7" / "Block 12" at speed 0.35.

Simulator vs hardware
---------------------

The NCE simulator accepts throttle commands but has no virtual
locomotives, so this example exercises the orchestration layer — concurrent
throttle acquires, parallel wait-fanout across many sensors, clean
shutdown of N throttles on ``Ctrl-C`` — without driving any physical
train. To see the per-loco loops actually progress on the simulator, tap
each loco's sensors in the JMRI UI by hand. To see physical motion, run
against a JMRI connected to NCE hardware with responsive decoders at the
configured DCC addresses.

Reconnect resilience
--------------------

This example relies on pyjmri's built-in WebSocket reconnect: if JMRI's
web server restarts or the network blinks while the script is running,
the per-loco ``await sensor.wait_active()`` calls survive the interruption
and resume when JMRI is reachable again. To observe this, stop JMRI's web
server briefly while the script is running (or pull the network cable),
then restart it — the loops should pick up where they left off. The
example does not catch :class:`pyjmri.JMRIConnectionError` because doing
so would mask the resilience and also turn a terminal reconnect failure
into something silent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from pyjmri import Client, Layout


@dataclass(frozen=True)
class LocoConfig:
    """A single locomotive's identity and route for this session."""

    dcc: int
    long: bool
    forward_sensor: str
    reverse_sensor: str
    speed: float


DEFAULT_LOCOS: list[LocoConfig] = [
    LocoConfig(dcc=5327, long=True, forward_sensor="Block 1", reverse_sensor="Block 6", speed=0.4),
    LocoConfig(
        dcc=1029, long=True, forward_sensor="Block 7", reverse_sensor="Block 12", speed=0.35
    ),
]


def _load_config(path: Path) -> list[LocoConfig]:
    """Read a JSON file describing the locomotives to drive."""
    with path.open() as fh:
        raw = json.load(fh)
    if not isinstance(raw, list):
        raise ValueError(f"{path}: top-level JSON must be a list of loco objects")
    locos: list[LocoConfig] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: each loco entry must be a JSON object")
        locos.append(
            LocoConfig(
                dcc=int(entry["dcc"]),
                long=bool(entry["long"]),
                forward_sensor=str(entry["forward_sensor"]),
                reverse_sensor=str(entry["reverse_sensor"]),
                speed=float(entry["speed"]),
            )
        )
    return locos


async def drive_loco(layout: Layout, cfg: LocoConfig) -> None:
    """Oscillate one locomotive between its forward and reverse sensors."""
    forward_sensor = layout.sensors[cfg.forward_sensor]
    reverse_sensor = layout.sensors[cfg.reverse_sensor]
    async with layout.throttle(cfg.dcc, long=cfg.long) as t:
        while True:
            await t.set_speed(cfg.speed, forward=True)
            await forward_sensor.wait_active()
            await t.set_speed(cfg.speed, forward=False)
            await forward_sensor.wait_inactive()
            await reverse_sensor.wait_active()


async def main(args: argparse.Namespace) -> None:
    locos: list[LocoConfig]
    if args.config is not None:
        locos = _load_config(Path(args.config))
    else:
        locos = DEFAULT_LOCOS

    print(f"Driving {len(locos)} locomotive(s):")
    for cfg in locos:
        addressing = "long" if cfg.long else "short"
        print(
            f"  DCC {cfg.dcc} ({addressing})  "
            f"{cfg.forward_sensor!r} <-> {cfg.reverse_sensor!r}  "
            f"speed={cfg.speed}"
        )

    url: str | None = args.url
    client = Client(url) if url is not None else Client()
    async with client as jmri:
        layout = await jmri.discover()
        await asyncio.gather(*(drive_loco(layout, cfg) for cfg in locos))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Drive multiple locomotives concurrently against a single JMRI.",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="JMRI URL (host:port). Defaults to localhost:12080.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to a JSON file listing locomotives to drive. "
        "Omit to use the basement-layout default.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_parse_args()))
