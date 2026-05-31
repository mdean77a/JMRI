"""Shared wait-for-state helpers for entity ``wait_state`` / ``wait_change``.

The pre-register-wait pattern (architecture sec. Command / Event
Correlation) is identical across :class:`~pyjmri.Sensor`,
:class:`~pyjmri.Turnout`, :class:`~pyjmri.Light`, :class:`~pyjmri.Block`,
:class:`~pyjmri.SignalHead`, and :class:`~pyjmri.SignalMast` — only the
JMRI entity-type string, the primary-state attribute, and the state
enum type differ. These helpers hold the common skeleton so the
per-entity wrappers stay terse.

The current-state read is supplied as a ``Callable[[], StateT]`` rather
than a string attribute name: it keeps the helper fully typed under
mypy strict, and lets each wrapper close over its own primary attribute
(``self.state`` / ``self.appearance`` / ``self.aspect``) without a
runtime ``getattr``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from enum import Enum
from typing import TYPE_CHECKING, TypeVar

from pyjmri.exceptions import WaitTimeout

if TYPE_CHECKING:
    from pyjmri._protocols import ClientHandle
    from pyjmri._waiters import WaiterList

StateT = TypeVar("StateT", bound=Enum)

__all__ = ["command_then_wait", "wait_for_change", "wait_for_target"]


async def wait_for_target(
    *,
    handle: ClientHandle,
    entity_type: str,
    name: str,
    waiters: WaiterList[StateT],
    read_state: Callable[[], StateT],
    target: StateT,
    timeout: float | None,  # noqa: ASYNC109
) -> StateT:
    """Common body of every entity's ``wait_state`` (FR31).

    Early-returns when the cached state already equals ``target``,
    re-checks after :meth:`ClientHandle.ensure_subscription` (the
    subscribe await may let the WS dispatcher update the cache
    mid-flight), then registers a one-shot waiter and awaits it.
    :class:`WaitTimeout` is raised on timeout; cleanup is unconditional
    via ``finally``.
    """
    current = read_state()
    if current == target:
        return current
    await handle.ensure_subscription(entity_type, name)
    current = read_state()
    if current == target:
        return current
    future = waiters.register(lambda s: s == target)
    try:
        if timeout is None:
            return await future
        async with asyncio.timeout(timeout):
            return await future
    except TimeoutError as e:
        raise WaitTimeout(
            entity_type=entity_type,
            name=name,
            target=target.name,
        ) from e
    finally:
        waiters.remove(future)


async def wait_for_change(
    *,
    handle: ClientHandle,
    entity_type: str,
    name: str,
    waiters: WaiterList[StateT],
    read_state: Callable[[], StateT],
    timeout: float | None,  # noqa: ASYNC109
) -> StateT:
    """Common body of every entity's ``wait_change`` (FR32).

    Captures ``starting`` after ensuring the subscription is live so
    an event arriving during the subscribe await cannot invalidate the
    reference. Returns when JMRI reports any state other than
    ``starting``.
    """
    await handle.ensure_subscription(entity_type, name)
    starting = read_state()
    future = waiters.register(lambda s: s != starting)
    try:
        if timeout is None:
            return await future
        async with asyncio.timeout(timeout):
            return await future
    except TimeoutError as e:
        raise WaitTimeout(
            entity_type=entity_type,
            name=name,
            from_state=starting.name,
        ) from e
    finally:
        waiters.remove(future)


async def command_then_wait(
    *,
    handle: ClientHandle,
    entity_type: str,
    name: str,
    waiters: WaiterList[StateT],
    state: StateT,
    outbound_map: Mapping[StateT, int],
    wait_for_jmri_state: bool,
) -> None:
    """Common body of Turnout/Light ``set_state`` (FR17, FR19, FR21, FR22).

    Validates ``state`` against ``outbound_map`` and raises
    :class:`ValueError` for non-commandable members (e.g. ``UNKNOWN``,
    ``INCONSISTENT``). With ``wait_for_jmri_state=False`` issues the
    HTTP command fire-and-forget. With ``wait_for_jmri_state=True``
    uses the pre-register-wait pattern: ensure the subscription is
    live, register a waiter, send the command under
    :func:`asyncio.shield` (so a caller-side cancel cannot abort an
    in-flight HTTP command and leave JMRI uncertain whether the command
    was received), then await the waiter future. On any exception —
    including :class:`asyncio.CancelledError` — the waiter is removed
    from the WaiterList; on success the future is already pruned by
    fanout.
    """
    if state not in outbound_map:
        raise ValueError(
            f"{state!r} is not a commandable {entity_type} state; "
            f"use {sorted(s.name for s in outbound_map)!r}"
        )
    payload = {"state": outbound_map[state]}
    if not wait_for_jmri_state:
        await handle.command(entity_type, name, payload)
        return
    await handle.ensure_subscription(entity_type, name)
    future = waiters.register(lambda s: s == state)
    try:
        await asyncio.shield(handle.command(entity_type, name, payload))
        await future
    except BaseException:
        waiters.remove(future)
        raise
