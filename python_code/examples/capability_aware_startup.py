"""PRD Journey 6: a capability-aware startup that adapts to each locomotive.

Connects to a running JMRI web server, calls ``discover_roster()``, looks up a
locomotive by DCC address, prints its identity and decoder, classifies its
capabilities from its roster function *labels* (not the decoder family string),
fires only the startup functions that classification calls for, and drives.

The point: the **same script, unmodified**, handles three cases —

- a **sound** loco (labelled "Startup"/"Horn"/"Bell"/... functions) — its
  sound functions are asserted before it moves;
- a **motor-only** loco (blank function labels) — it just drives;
- an **address absent from the roster** — ``throttle_for_entry`` logs a
  motor-only WARNING and drives best-effort, so a brand-new, un-catalogued
  loco is never blocked (FR55).

Run it
------

Default (basement layout, NCE simulator)::

    uv run --no-sync python examples/capability_aware_startup.py

Pick a locomotive by DCC address::

    uv run --no-sync python examples/capability_aware_startup.py --dcc 5327

Against a different layout, short address, slower::

    uv run --no-sync python examples/capability_aware_startup.py \\
        --url 192.168.1.159:12080 --dcc 41 --short --speed 0.25 --seconds 8

Defaults
--------

- ``--url`` — JMRI URL; ``None`` means ``localhost:12080`` (the Client default).
- ``--dcc 5327`` — the loco to start (overridable; nothing is hardcoded in the library).
- ``--long`` / ``--short`` — addressing override. When the loco is in the roster,
  addressing is derived from the entry and this flag is unnecessary; for an
  un-catalogued address it overrides the ``address > 127`` ⇒ long convention.
- ``--speed 0.4`` — throttle setting in [0.0, 1.0] after startup.
- ``--seconds 5.0`` — how long to hold speed before releasing.

Success criterion (split)
-------------------------

This example's *plumbing* — which ``set_function`` commands fire for a given
loco — is verified on the NCE simulator (see ``tests/unit/test_capability_startup.py``).
Physical "visibly correct startup" (the sound actually plays, the loco actually
moves) is hardware-only and manual: the NCE simulator accepts throttle commands
but has no virtual locomotive, so nothing physically moves on the sim. Point this
at JMRI connected to NCE hardware with a responsive decoder to see it for real.
"""

from __future__ import annotations

import argparse
import asyncio

from pyjmri import (
    Capability,
    Client,
    JMRIError,
    RosterEntry,
    classify_capability,
    firable_startup_functions,
)


def _fmt(value: str | None, fallback: str = "—") -> str:
    """Render an optional string, using a dash for None/empty."""
    return value if value else fallback


def _leaf_messages(exc: BaseException) -> list[str]:
    """Flatten an exception (or nested ExceptionGroup) into its leaf messages."""
    if isinstance(exc, BaseExceptionGroup):
        return [msg for sub in exc.exceptions for msg in _leaf_messages(sub)]
    return [str(exc)]


def describe(entry: RosterEntry | None, dcc: int) -> str:
    """One-line identity/decoder description for the chosen loco."""
    if entry is None:
        return f"DCC {dcc}: (not in roster — driving motor-only)"
    decoder = " / ".join(p for p in (entry.decoder_family, entry.decoder_model) if p) or "—"
    return (
        f"DCC {entry.dcc_address}: {_fmt(entry.road_name)} #{_fmt(entry.road_number)} "
        f"'{entry.name}' — model {_fmt(entry.model)}, decoder {decoder}"
    )


async def run_startup(
    jmri: Client,
    dcc: int,
    *,
    long: bool | None,
    speed: float,
    seconds: float,
) -> None:
    """Discover the roster, classify the loco, fire its startup, and drive."""
    roster = await jmri.discover_roster()
    entry = roster.by_address(dcc)
    print(describe(entry, dcc))

    capability = (
        classify_capability(entry)
        if entry is not None
        else Capability(sound=False, sound_functions=())
    )
    if capability.motor_only:
        print("Classified motor-only — no sound functions to fire.")
    else:
        labels = ", ".join(f"F{fl.num}:{_fmt(fl.label)}" for fl in capability.sound_functions)
        print(f"Classified sound-capable — labelled functions: {labels}")
        skipped = [fl.num for fl in capability.sound_functions if fl.num > 28]
        if skipped:
            print(
                f"Note: function(s) {skipped} are above F28 and cannot be commanded "
                "by set_function — skipped."
            )

    # throttle_for_entry derives long/short from the matched entry; for an
    # un-catalogued address it warns and drives best-effort (FR55).
    target: RosterEntry | int = entry if entry is not None else dcc
    async with jmri.throttle_for_entry(target, long=long) as t:
        for num in firable_startup_functions(capability):
            print(f"  startup: set F{num} on")
            await t.set_function(num, on=True)
        print(f"Driving at speed {speed} for {seconds}s.")
        await t.set_speed(speed, forward=True)
        await asyncio.sleep(seconds)
    print("Released throttle. Done.")


async def main(args: argparse.Namespace) -> None:
    url: str | None = args.url
    try:
        client = Client(url) if url is not None else Client()
    except ValueError as exc:
        print(f"Invalid --url {url!r}: {exc}")
        raise SystemExit(2) from None
    exit_code = 0
    try:
        async with client as jmri:
            await run_startup(
                jmri,
                args.dcc,
                long=args.long,
                speed=args.speed,
                seconds=args.seconds,
            )
    except* JMRIError as eg:
        print(f"Could not run capability-aware startup: {'; '.join(_leaf_messages(eg))}")
        print(f"Is JMRI running with the web server enabled at {url or 'localhost:12080'}?")
        exit_code = 1
    if exit_code:
        raise SystemExit(exit_code)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capability-aware startup: adapt a loco's startup to its function labels."
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="JMRI URL (host:port). Defaults to localhost:12080.",
    )
    parser.add_argument("--dcc", type=int, default=5327, help="DCC decoder address to start.")
    addressing = parser.add_mutually_exclusive_group()
    addressing.add_argument(
        "--long",
        dest="long",
        action="store_true",
        default=None,
        help="Force long (4-digit) DCC addressing (override).",
    )
    addressing.add_argument(
        "--short",
        dest="long",
        action="store_false",
        help="Force short (1-127) DCC addressing (override).",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=0.4,
        help="Throttle setting in [0.0, 1.0] after startup.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=5.0,
        help="How long to hold speed before releasing.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_parse_args()))
