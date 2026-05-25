"""First-contact pyjmri example: connect, discover, summarize the layout.

Connects to a running JMRI web server, runs :meth:`pyjmri.Client.discover` to
enumerate the layout, prints counts of every entity collection JMRI exposes,
and prints the first five turnouts' name / user name / state.

Run it
------

Default (JMRI at ``localhost:12080``)::

    uv run --no-sync python examples/hello_jmri.py

Against a JMRI on a different host or port::

    uv run --no-sync python examples/hello_jmri.py --url 192.168.1.50:12080

Defaults
--------

- ``--url`` — ``localhost:12080`` (the JMRI default). Pass any host:port,
  ``http://host:port``, or ``ws://host:port`` form accepted by
  :class:`pyjmri.Client`.

Roster note
-----------

pyjmri v1 does not yet expose JMRI's locomotive roster as a typed
:class:`Layout` collection; ``roster.py`` is a stub deferred to post-MVP.
The counts below are the eight collections that v1 does surface (turnouts,
sensors, blocks, lights, memories, routes, signal heads, signal masts).
"""

from __future__ import annotations

import argparse
import asyncio

from pyjmri import Client


async def main(args: argparse.Namespace) -> None:
    url: str | None = args.url
    client = Client(url) if url is not None else Client()
    async with client as jmri:
        layout = await jmri.discover()

        print("Layout summary:")
        print(f"  turnouts:     {len(layout.turnouts)}")
        print(f"  sensors:      {len(layout.sensors)}")
        print(f"  blocks:       {len(layout.blocks)}")
        print(f"  lights:       {len(layout.lights)}")
        print(f"  memories:     {len(layout.memories)}")
        print(f"  routes:       {len(layout.routes)}")
        print(f"  signal heads: {len(layout.signal_heads)}")
        print(f"  signal masts: {len(layout.signal_masts)}")

        turnouts = list(layout.turnouts.values())[:5]
        if not turnouts:
            print("\nNo turnouts on this layout.")
            return

        print(f"\nFirst {len(turnouts)} turnout(s):")
        for t in turnouts:
            user_name = t.user_name if t.user_name is not None else "<no user name>"
            print(f"  name={t.name}  user_name={user_name}  state={t.state.name}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Connect to JMRI, discover the layout, and print a summary."
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
