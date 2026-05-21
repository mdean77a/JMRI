"""Throttle async context manager + acquire/release lifecycle + keep-alive.

Architecture sec. Public API Surface: ``async with layout.throttle(addr, long=True) as loco:``.

Story 5.1 Task 0 spike (2026-05-21) found JMRI's throttle API is WebSocket-only and JMRI's
WS-level heartbeat keeps held throttles alive without per-throttle application heartbeats.
The keep-alive coroutine therefore ships as a no-op structural stub; Story 5.3 hardware
observation flips the body if needed.
"""

from __future__ import annotations

import asyncio
import logging
from types import TracebackType
from typing import TYPE_CHECKING, Self

from pyjmri.exceptions import (
    JMRIConnectionError,
    JMRIRequestTimeout,
    ThrottleAcquireFailed,
    ThrottleReleased,
)

if TYPE_CHECKING:
    from pyjmri._protocols import ClientHandle

__all__ = ["Throttle"]

logger = logging.getLogger("pyjmri.throttle")


class Throttle:
    """Async context manager for a JMRI throttle session.

    A ``Throttle`` represents an acquired DCC decoder address on JMRI. The
    lifecycle is:

    1. ``layout.throttle(addr, long=True)`` (or ``client.throttle(...)``)
       constructs an unacquired ``Throttle``.
    2. ``async with throttle as loco:`` issues the WS acquire and spawns
       a supervised keep-alive coroutine.
    3. On exit (clean or exceptional), the keep-alive is cancelled and a
       WS release envelope is sent.

    **FR28 open-loop honesty.** A successful acquire means only that JMRI
    accepted the throttle session — it does NOT imply a locomotive at this
    DCC address is physically on the layout or responsive. NCE is open-loop
    with no DCC-bus feedback; pyjmri cannot detect "ghost throttle" (a held
    session for an absent locomotive). Control commands sent to a throttle
    for an absent address are silently accepted by JMRI and the booster.

    Args:
        handle: The :class:`pyjmri._protocols.ClientHandle` (typically a
            :class:`pyjmri.Client`) that owns the underlying WS connection.
        dcc_address: DCC decoder address (1..10293 typical).
        long: ``True`` for long (4-digit) addressing, ``False`` for short.
    """

    def __init__(
        self,
        handle: ClientHandle,
        *,
        dcc_address: int,
        long: bool,
    ) -> None:
        self._handle = handle
        self.dcc_address = dcc_address
        self.long = long
        self._throttle_id: str | None = None
        self._released: bool = False
        self._keepalive_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> Self:
        """Acquire the throttle via WS and spawn the supervised keep-alive.

        Successful acquire only means JMRI accepted the throttle; it does not
        imply a locomotive at this DCC address is physically on the layout or
        responsive — NCE is open-loop with no DCC-bus feedback (FR28).

        Raises:
            ThrottleReleased: when this ``Throttle`` was already released.
            RuntimeError: when this ``Throttle`` is already acquired (i.e.,
                ``__aenter__`` was called while a prior ``async with`` is
                still active on the same instance).
            ThrottleAcquireFailed: when JMRI rejects the acquire (e.g.,
                invalid address).
            JMRIConnectionError, JMRIRequestTimeout: surfaced from the WS
                transport.
        """
        if self._released:
            raise ThrottleReleased(
                "throttle already released; cannot re-acquire",
                dcc_address=self.dcc_address,
            )
        if self._throttle_id is not None:
            raise RuntimeError(
                f"Throttle for DCC address {self.dcc_address} is already acquired; "
                "exit the current 'async with' block before re-entering"
            )
        try:
            self._throttle_id = await self._handle.throttle_acquire(
                self.dcc_address, long=self.long
            )
        except (JMRIConnectionError, JMRIRequestTimeout):
            raise
        except ThrottleAcquireFailed:
            raise
        self._keepalive_task = self._handle.spawn_supervised(
            self._keepalive(),
            name=f"pyjmri-throttle-keepalive-{self.dcc_address}",
        )
        logger.info(
            "throttle acquired",
            extra={
                "dcc_address": self.dcc_address,
                "throttle_id": self._throttle_id,
                "long": self.long,
            },
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        body_raised = exc is not None
        if not self._released:
            await self._release_impl(suppress_errors=body_raised)
        # Return None: do not swallow the body exception.

    async def release(self) -> None:
        """Cancel the keep-alive and send the WS release envelope.

        After ``release()``, all control methods (in v1: ``__aenter__``,
        any Story 5.2 control methods) raise :class:`ThrottleReleased`.
        Release is idempotent — a second call returns without re-issuing
        the WS envelope.
        """
        if self._released:
            return
        await self._release_impl(suppress_errors=False)

    async def _release_impl(self, *, suppress_errors: bool) -> None:
        """Shared teardown: cancel keep-alive, send WS release, mark released.

        Args:
            suppress_errors: When ``True`` (called from ``__aexit__`` while
                a body exception is propagating), log + swallow any WS
                release failure so the body exception keeps priority. When
                ``False`` (called from explicit ``release()``), let release
                errors propagate to the caller.
        """
        # Cancel the keep-alive first so it can't fight us during release.
        if self._keepalive_task is not None and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            # Python's task machinery re-raises CancelledError when awaiting
            # a cancelled task even if the coroutine caught it internally
            # (asyncio sets Task._must_cancel; the StopIteration path then
            # calls super().cancel() before super().set_result()).
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(
                    "keepalive task raised during shutdown (swallowed)",
                    extra={
                        "dcc_address": self.dcc_address,
                        "throttle_id": self._throttle_id,
                        "error_type": type(e).__name__,
                    },
                )
        self._keepalive_task = None
        # Send the release. Fire-and-forget per AC4 — JMRI's release-echo is
        # consumed by the WS dispatcher but not awaited.
        if self._throttle_id is not None:
            try:
                await self._handle.throttle_release(self._throttle_id)
            except Exception as e:
                if suppress_errors:
                    logger.warning(
                        "throttle release failed during exception-driven teardown (swallowed)",
                        extra={
                            "dcc_address": self.dcc_address,
                            "throttle_id": self._throttle_id,
                            "error_type": type(e).__name__,
                        },
                    )
                else:
                    self._released = True
                    logger.info(
                        "throttle released (WS release errored)",
                        extra={
                            "dcc_address": self.dcc_address,
                            "throttle_id": self._throttle_id,
                        },
                    )
                    raise
        self._released = True
        logger.info(
            "throttle released",
            extra={
                "dcc_address": self.dcc_address,
                "throttle_id": self._throttle_id,
            },
        )

    # Story 5.3 hookpoint: the keep-alive body is a no-op stub.
    #
    # Confirmed unnecessary on JMRI 5.14 simulator / 2026-05-21 — JMRI's
    # WS-level heartbeat (server-advertised 13500 ms; pyjmri transport's
    # 10 s ping_interval) keeps the WS connection alive, which in turn
    # keeps all held throttles alive. The supervised task here exists
    # structurally per architecture sec. Concurrency Model (line 543-547):
    # "Per-throttle keep-alive coroutine, one per active Throttle".
    #
    # If Story 5.3 hardware observation shows JMRI does expire idle
    # throttles on hardware-mode (which the simulator doesn't), populate
    # the body with:
    #
    #     while True:
    #         await asyncio.sleep(self._handle.throttle_keepalive_interval)
    #         assert self._throttle_id is not None
    #         try:
    #             await self._handle.throttle_heartbeat(self._throttle_id)
    #         except Exception as e:
    #             logger.warning("heartbeat failed; retry next iteration", ...)
    #
    # and record the verification: "Confirmed necessary on JMRI X.Y / NCE /
    # 20YY-MM-DD".
    async def _keepalive(self) -> None:
        """No-op supervised stub; cancels cleanly on release."""
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return
