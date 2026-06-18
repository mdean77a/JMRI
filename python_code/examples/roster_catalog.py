"""PRD Journey 6: a fleet-catalog reference sheet from JMRI's roster.

Connects to a running JMRI web server, calls ``discover_roster()``, and prints
a printable maintenance/reference sheet of the whole fleet: per locomotive its
road number, model, decoder family/model, owner, DCC address, and comment —
followed by a decoder-family/model rollup (how many entries use each decoder).

This is the **complete DecoderPro catalog** — every engine you have ever
programmed — distinct from Operations (the operationally-active subset actually
deployed on the layout) and from the live `Layout` model. A layout with ~45
roster engines may have only a handful running tonight; the catalog lists them
all.

The roster is **read-only** in this increment: there is no decoder-programming
or CV-write surface — editing a locomotive stays in DecoderPro. This example
only reads.

Run it
------

Default (JMRI at ``localhost:12080``)::

    uv run --no-sync python examples/roster_catalog.py

Against a JMRI on a different host or port::

    uv run --no-sync python examples/roster_catalog.py --url 192.168.1.159:12080

Graceful degradation
--------------------

- If JMRI has no roster configured, the collection comes back empty (a valid
  result, not an error); the script says so and exits cleanly.
- If JMRI is unreachable or returns a malformed response, the script prints a
  short explanation instead of a traceback and exits with a non-zero status.
- An invalid ``--url`` value is reported with a one-line message (exit code 2).

Simulator note
--------------

The roster is a pure data subsystem (entries are records JMRI serves over JSON
regardless of hardware), so this catalog is fully testable on the NCE simulator
with a populated roster — no physical layout required.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter

from pyjmri import Client, JMRIError, Roster


def _fmt(value: str | None, fallback: str = "—") -> str:
    """Render an optional string, using a dash for None/empty."""
    return value if value else fallback


def _leaf_messages(exc: BaseException) -> list[str]:
    """Flatten an exception (or nested ExceptionGroup) into its leaf messages."""
    if isinstance(exc, BaseExceptionGroup):
        return [msg for sub in exc.exceptions for msg in _leaf_messages(sub)]
    return [str(exc)]


def _decoder_label(family: str | None, model: str | None) -> str:
    """Combine decoder family/model into one rollup key (identity, not capability)."""
    if family and model:
        return f"{family} / {model}"
    return family or model or "—"


def print_catalog(roster: Roster) -> None:
    """Print the Journey-6 fleet catalog, or an explanatory message if empty."""
    if len(roster) == 0:
        print("No roster entries are configured in this JMRI profile — nothing to catalog.")
        print("Program some locomotives in DecoderPro to populate the roster.")
        return

    print(f"Roster catalog: {len(roster)} locomotive(s).")
    print(
        "(The full DecoderPro catalog — distinct from Operations, the "
        "operationally-active subset deployed on the layout.)"
    )

    for entry in roster.values():
        addressing = "long" if entry.long_address else "short"
        label = _fmt(entry.road_number, entry.name)
        print(f"\n  {label}  —  DCC {entry.dcc_address} ({addressing})")
        print(f"    model:   {_fmt(entry.model)}")
        print(f"    decoder: {_decoder_label(entry.decoder_family, entry.decoder_model)}")
        print(f"    owner:   {_fmt(entry.owner)}")
        print(f"    comment: {_fmt(entry.comment)}")

    rollup: Counter[str] = Counter(
        _decoder_label(entry.decoder_family, entry.decoder_model) for entry in roster.values()
    )
    print("\nDecoder rollup (entries per decoder family/model):")
    for label, count in sorted(rollup.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {count:>3} x  {label}")


async def main(args: argparse.Namespace) -> None:
    url: str | None = args.url
    try:
        client = Client(url) if url is not None else Client()
    # An invalid --url (missing/bad port, unsupported scheme) raises ValueError
    # from Client() before any connection is attempted.
    except ValueError as exc:
        print(f"Invalid --url {url!r}: {exc}")
        raise SystemExit(2) from None
    exit_code = 0
    try:
        async with client as jmri:
            # The roster is a standalone read-only subsystem: discover_roster()
            # does its own version check, so there is no need to discover() first.
            roster = await jmri.discover_roster()
            print_catalog(roster)
    # discover_roster() degrades an empty/failed fetch to an empty Roster, but a
    # connection failure on open (or the version-check probe) still raises; a
    # bare exception and an ExceptionGroup are both matched by `except*`.
    except* JMRIError as eg:
        print(f"Could not read the roster from JMRI: {'; '.join(_leaf_messages(eg))}")
        print(f"Is JMRI running with the web server enabled at {url or 'localhost:12080'}?")
        exit_code = 1
    # `return` is a syntax error inside an except* block, and a raise there can be
    # re-grouped with unhandled siblings, so the exit code is carried out and
    # raised here instead.
    if exit_code:
        raise SystemExit(exit_code)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print a read-only fleet-catalog reference sheet from the JMRI roster."
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
