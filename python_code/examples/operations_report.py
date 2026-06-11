"""PRD Journey 5: a "where is every car" report from a JMRI Operations session.

Connects to a running JMRI web server, calls ``discover_operations()``, and
prints the *operational* picture as plain typed Python: every location, each
train and where it is along its route, and each car with its current location
and train assignment. This is the operationally-active subset actually deployed
on the layout — distinct from the roster (the DecoderPro catalog of *every*
engine you ever programmed). A layout with ~45 roster engines may have only a
handful on the layout tonight; Operations is what's running.

Operations is **read-only** in this increment: there is no build-train,
move/assign-car, or generate-manifest surface — those are deferred to a future
command increment. This example only reads.

Run it
------

Default (JMRI at ``localhost:12080``)::

    uv run --no-sync python examples/operations_report.py

Against a JMRI on a different host or port::

    uv run --no-sync python examples/operations_report.py --url 192.168.1.159:12080

Graceful degradation
--------------------

- If JMRI has no Operations data configured, the four collections come back
  empty (a valid result, not an error); the script says so and exits cleanly.
- If JMRI is unreachable or returns a malformed response, the script prints a
  short explanation instead of a traceback.

Simulator note
--------------

Operations is a pure data subsystem (cars/engines/locations/trains are records
JMRI serves over JSON regardless of hardware), so this report is fully testable
on the NCE simulator with Operations data loaded — no physical layout required.
"""

from __future__ import annotations

import argparse
import asyncio

from pyjmri import Client, JMRIError, Operations, Placement


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


def print_report(ops: Operations) -> None:
    """Print the Journey-5 report, or an explanatory message if there is no data."""
    total = len(ops.locations) + len(ops.trains) + len(ops.cars) + len(ops.engines)
    if total == 0:
        print("No Operations data is configured in this JMRI profile — nothing to report.")
        print(
            "Configure JMRI's Operations module (locations, trains, cars, engines) "
            "to populate this report."
        )
        return

    print(
        f"Operations session: {len(ops.locations)} locations, "
        f"{len(ops.trains)} trains, {len(ops.cars)} cars, "
        f"{len(ops.engines)} engines deployed."
    )
    print(
        "(These are the operationally-active records — distinct from the roster, "
        "which catalogs every engine ever programmed in DecoderPro.)"
    )

    print("\nLocations:")
    for loc in ops.locations.values():
        tracks = ", ".join(_fmt(t.user_name, t.name) for t in loc.tracks) or "—"
        print(f"  {_fmt(loc.user_name, loc.name)}  (tracks: {tracks})")

    print("\nTrains — where is each one:")
    for train in ops.trains.values():
        print(
            f"  {_fmt(train.user_name, train.name)} → at {_fmt(train.current_location)}"
            f"  [route: {_fmt(train.route)}, status: {_fmt(train.status)}]"
        )

    print("\nCars — where is every car:")
    for car in ops.cars.values():
        print(
            f"  {car.name:<10} at {_fmt_placement(car.location)}"
            f"  on train {_fmt(car.train)}"
            f"  → {_fmt_placement(car.destination)}"
        )


async def main(args: argparse.Namespace) -> None:
    url: str | None = args.url
    client = Client(url) if url is not None else Client()
    try:
        async with client as jmri:
            # Journey 5 calls discover() first, then discover_operations().
            await jmri.discover()
            ops = await jmri.discover_operations()
            print_report(ops)
    # discover_operations() fetches the four types in an asyncio.TaskGroup, so a
    # failure arrives wrapped in an ExceptionGroup; a connection failure on open
    # arrives bare. `except*` handles both (it matches a naked exception too).
    except* JMRIError as eg:
        reasons = "; ".join(str(exc) for exc in eg.exceptions)
        print(f"Could not read Operations from JMRI: {reasons}")
        print(f"Is JMRI running with the web server enabled at {url or 'localhost:12080'}?")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print a read-only 'where is every car' report from JMRI Operations."
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
