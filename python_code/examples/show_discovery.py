"""Demo: discover and print both the Layout and the Operations subsystems.

Connects to a running JMRI web server, runs ``discover()`` (layout hardware)
and ``discover_operations()`` (the read-only Operations subsystem — locations,
trains, cars, engines), and prints a human-readable summary of each.

This is a demonstration script, distinct from the curated Story 8.3
``operations_report.py`` example. Run::

    uv run --no-sync python examples/show_discovery.py
    uv run --no-sync python examples/show_discovery.py --url 192.168.1.159:12080
"""

from __future__ import annotations

import argparse
import asyncio

from pyjmri import Client, Layout, Operations, Placement


def _fmt(value: str | None, fallback: str = "—") -> str:
    """Render an optional string, using a dash for None/empty."""
    return value if value else fallback


def _fmt_placement(placement: Placement | None) -> str:
    """One-line rendering of a car/engine location or destination."""
    if placement is None:
        return "—"
    where = _fmt(placement.user_name, placement.name)
    if placement.track is not None:
        track = _fmt(placement.track.user_name, placement.track.name)
        return f"{where} / {track}"
    return where


def print_layout(layout: Layout) -> None:
    print("=" * 60)
    print("LAYOUT (discover())")
    print("=" * 60)
    print(f"  turnouts:     {len(layout.turnouts)}")
    print(f"  sensors:      {len(layout.sensors)}")
    print(f"  blocks:       {len(layout.blocks)}")
    print(f"  lights:       {len(layout.lights)}")
    print(f"  memories:     {len(layout.memories)}")
    print(f"  routes:       {len(layout.routes)}")
    print(f"  signal heads: {len(layout.signal_heads)}")
    print(f"  signal masts: {len(layout.signal_masts)}")

    turnouts = list(layout.turnouts.values())[:5]
    if turnouts:
        print(f"\n  First {len(turnouts)} turnout(s):")
        for t in turnouts:
            print(f"    name={t.name}  user_name={_fmt(t.user_name)}  state={t.state.name}")


def print_operations(ops: Operations) -> None:
    print()
    print("=" * 60)
    print("OPERATIONS (discover_operations())")
    print("=" * 60)
    print(f"  locations: {len(ops.locations)}")
    print(f"  trains:    {len(ops.trains)}")
    print(f"  cars:      {len(ops.cars)}")
    print(f"  engines:   {len(ops.engines)}")

    print("\n  Locations:")
    for loc in ops.locations.values():
        tracks = ", ".join(_fmt(t.user_name, t.name) for t in loc.tracks) or "—"
        print(f"    [{loc.name}] {_fmt(loc.user_name)}  length={loc.length}  tracks: {tracks}")

    print("\n  Trains:")
    for train in ops.trains.values():
        print(f"    [{train.name}] {_fmt(train.user_name)}")
        print(f"        route:    {_fmt(train.route)}")
        print(f"        at:       {_fmt(train.current_location)}")
        print(f"        status:   {_fmt(train.status)} (code {train.status_code})")
        print(f"        lead:     {_fmt(train.lead_engine)}")
        print(
            f"        consist:  {len(train.engines)} engine(s), "
            f"{len(train.cars)} car(s), {len(train.route_stops)} route stop(s)"
        )

    print("\n  Engines:")
    for eng in ops.engines.values():
        print(
            f"    {eng.name:<10} {eng.engine_type:<8} model={_fmt(eng.model):<10} "
            f"train={_fmt(eng.train):<14} at={_fmt_placement(eng.location)}"
        )

    print("\n  Cars:")
    for car in ops.cars.values():
        print(
            f"    {car.name:<10} {car.car_type:<14} len={car.length:<4} "
            f"train={_fmt(car.train):<14} at={_fmt_placement(car.location)} "
            f"-> {_fmt_placement(car.destination)}"
        )


async def main(args: argparse.Namespace) -> None:
    url: str | None = args.url
    client = Client(url) if url is not None else Client()
    async with client as jmri:
        layout = await jmri.discover()
        ops = await jmri.discover_operations()

    print_layout(layout)
    print_operations(ops)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover and print the JMRI Layout and Operations subsystems."
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="JMRI URL (host:port or http://host:port). Defaults to localhost:12080.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_parse_args()))
