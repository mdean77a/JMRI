"""Plumbing test for the capability-aware startup command set (Story 9.3).

The capability-aware startup fires ``set_function(n, on=True)`` for each
function in ``firable_startup_functions(classify_capability(entry))``. This
test asserts the **exact set** of throttle WS updates that startup issues for
given fixture roster data — verifiable on the NCE simulator — and explicitly
does NOT assert physical movement (the simulator has no virtual locomotive,
per memory ``project_throttle_simulator_blindspot``). Physical "visibly
correct startup" is hardware-only and manual.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from pyjmri import (
    Capability,
    FunctionLabel,
    Throttle,
    classify_capability,
    firable_startup_functions,
)
from pyjmri._parsing import parse_roster_entry
from pyjmri._protocols import ClientHandle


async def _fire_startup(handle: Any, capability: Capability, *, dcc_address: int) -> Throttle:
    """Drive the startup the example performs and return the throttle.

    Mirrors ``examples/capability_aware_startup.py``: assert each firable
    startup function on the acquired throttle.
    """
    throttle = Throttle(cast(ClientHandle, handle), dcc_address=dcc_address, long=True)
    async with throttle as t:
        for num in firable_startup_functions(capability):
            await t.set_function(num, on=True)
    return throttle


async def test_sound_loco_fires_exactly_its_firable_functions(
    load_fixture: Callable[[str], list[dict[str, Any]]],
    make_fake_handle: Any,
) -> None:
    entries = [parse_roster_entry(env) for env in load_fixture("roster")]
    sound = next(
        e
        for e in entries
        if any(fl.label is not None and "horn" in fl.label.lower() for fl in e.function_labels)
    )
    capability = classify_capability(sound)
    expected = firable_startup_functions(capability)
    assert expected  # the chosen entry really does have firable sound functions

    handle = make_fake_handle(lambda _t, _n: {})
    await _fire_startup(handle, capability, dcc_address=sound.dcc_address)

    # Each set_function(n, on=True) becomes a {"F<n>": True} WS update; the
    # recorded payloads must be exactly the firable functions, in order.
    fired = [payload for (_id, payload) in handle.throttle_update_calls]
    assert fired == [{f"F{n}": True} for n in expected]


async def test_motor_only_loco_fires_no_functions(
    load_fixture: Callable[[str], list[dict[str, Any]]],
    make_fake_handle: Any,
) -> None:
    entries = [parse_roster_entry(env) for env in load_fixture("roster")]
    motor_only = next(
        e
        for e in entries
        if e.function_labels and all(fl.label is None for fl in e.function_labels)
    )
    capability = classify_capability(motor_only)

    handle = make_fake_handle(lambda _t, _n: {})
    await _fire_startup(handle, capability, dcc_address=motor_only.dcc_address)

    assert handle.throttle_update_calls == []


async def test_sound_label_above_f28_is_not_commanded(make_fake_handle: Any) -> None:
    # A sound label on F30 is classified but cannot be commanded by
    # set_function (F0-F28 only) — startup must NOT attempt it.
    capability = Capability(
        sound=True,
        sound_functions=(FunctionLabel(num=30, label="Sound", lockable=True),),
    )
    handle = make_fake_handle(lambda _t, _n: {})
    await _fire_startup(handle, capability, dcc_address=3)
    assert handle.throttle_update_calls == []
