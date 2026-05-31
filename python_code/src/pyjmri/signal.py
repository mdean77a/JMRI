"""Signal head and signal mast entity classes and state enums.

``SignalHeadAppearance`` is integer-coded by JMRI (translated through
``_codes.py``). ``SignalMastAspect`` is string-coded by JMRI (translated
via Python's value-based enum lookup; see ``_parsing.parse_signal_mast``).

pyjmri v1 binds to JMRI's "basic" signaling system only. Layouts using
AAR-1946, NORAC, or custom signaling will see ``JMRIProtocolError`` on
signal-mast read. Story 6.2 (README Limitations) must surface this.

``wait_*`` primitives operate on the primary state attribute only —
``appearance`` for :class:`SignalHead`, ``aspect`` for
:class:`SignalMast`. The ``held`` and ``lit`` flags are read via
:meth:`get_state` but are not modeled as waitable events in v1.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import TYPE_CHECKING

from pyjmri._waiters import WaiterList
from pyjmri.exceptions import WaitTimeout

if TYPE_CHECKING:
    from pyjmri._protocols import ClientHandle

__all__ = ["SignalHead", "SignalHeadAppearance", "SignalMast", "SignalMastAspect"]


class SignalHeadAppearance(Enum):
    DARK = "dark"
    RED = "red"
    FLASHRED = "flashred"
    YELLOW = "yellow"
    FLASHYELLOW = "flashyellow"
    GREEN = "green"
    FLASHGREEN = "flashgreen"
    LUNAR = "lunar"
    FLASHLUNAR = "flashlunar"


class SignalMastAspect(Enum):
    """JMRI 'basic' signaling-system aspects.

    Member values are the exact JMRI aspect strings — Python's value-based
    enum lookup (``SignalMastAspect("Clear")``) is the translation
    primitive, so the strings MUST match JMRI verbatim.
    """

    CLEAR = "Clear"
    APPROACH = "Approach"
    APPROACH_MEDIUM = "Approach Medium"
    ADVANCE_APPROACH = "Advance Approach"
    APPROACH_SLOW = "Approach Slow"
    SLOW_APPROACH = "Slow Approach"
    MEDIUM_APPROACH = "Medium Approach"
    RESTRICTING = "Restricting"
    PERMISSIVE = "Permissive"
    SLOW = "Slow"
    MEDIUM = "Medium"
    STOP = "Stop"
    DARK = "Dark"
    HELD = "Held"
    UNKNOWN = "Unknown"


class SignalHead:
    """A JMRI signal head with its current appearance.

    Read-only in pyjmri v1: there are no command methods on
    :class:`SignalHead`; appearances are driven by JMRI's CTC / signal
    logic, not by direct API writes. See README §Limitations.

    Args:
        name: JMRI system name.
        user_name: Optional JMRI user name.
        appearance: Initial cached :class:`SignalHeadAppearance`.
        held: Initial cached "held" flag (when ``True``, JMRI has forced
            the head to its most-restrictive appearance).
        lit: Initial cached "lit" flag (when ``False``, JMRI has blanked
            the head).
        _handle: Internal :class:`~pyjmri._protocols.ClientHandle`.

    Example:
        Wait for the head to display ``GREEN``::

            await head.wait_state(SignalHeadAppearance.GREEN, timeout=10.0)
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
        appearance: SignalHeadAppearance,
        held: bool,
        lit: bool,
        _handle: ClientHandle,
    ) -> None:
        self.name = name
        self.user_name = user_name
        self.appearance = appearance
        self.held = held
        self.lit = lit
        self._handle = _handle
        self._waiters: WaiterList[SignalHeadAppearance] = WaiterList()

    async def get_state(self) -> SignalHeadAppearance:
        """Refresh and return the cached :class:`SignalHeadAppearance`.

        Updates :attr:`appearance`, :attr:`held`, and :attr:`lit` atomically
        on success. :attr:`name` and :attr:`user_name` are identity fields
        and are never refreshed.
        """
        from pyjmri._parsing import parse_signal_head

        envelope = await self._handle.get_entity("signalHead", self.name)
        parsed = parse_signal_head(envelope)
        self.appearance = parsed.appearance
        self.held = parsed.held
        self.lit = parsed.lit
        return parsed.appearance

    def _on_event(self, new_appearance: SignalHeadAppearance) -> None:
        """Update cached :attr:`appearance` and resolve matching waiters.

        Only the primary state attribute (``appearance``) is updated by
        ``_on_event``; the ``held`` and ``lit`` flags are not modeled
        as waitable events in v1. Call :meth:`get_state` to refresh
        them explicitly.
        """
        self.appearance = new_appearance
        self._waiters.fanout(new_appearance)

    async def wait_state(
        self,
        target: SignalHeadAppearance,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> SignalHeadAppearance:
        """Await the head reaching ``target`` appearance (FR31).

        Raises:
            WaitTimeout: if ``timeout`` elapses before the target appearance.
            RuntimeError: if the owning :class:`~pyjmri.Client` is closed
                while this call is suspended inside ``ensure_subscription``.
        """
        if self.appearance == target:
            return self.appearance
        await self._handle.ensure_subscription("signalHead", self.name)
        if self.appearance == target:
            return self.appearance
        future = self._waiters.register(lambda a: a == target)
        try:
            if timeout is None:
                return await future
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as e:
            raise WaitTimeout(
                entity_type="signalHead",
                name=self.name,
                target=target.name,
            ) from e
        finally:
            self._waiters.remove(future)

    async def wait_change(
        self,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> SignalHeadAppearance:
        """Await the next appearance change (FR32).

        Captures :attr:`appearance` after ensuring the subscription is
        live, so the "starting" reference cannot be invalidated by an
        event that arrives during the subscribe await.

        Raises:
            WaitTimeout: if ``timeout`` elapses before any appearance change.
            RuntimeError: if the owning :class:`~pyjmri.Client` is closed
                while this call is suspended inside ``ensure_subscription``.
        """
        await self._handle.ensure_subscription("signalHead", self.name)
        starting = self.appearance
        future = self._waiters.register(lambda a: a != starting)
        try:
            if timeout is None:
                return await future
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as e:
            raise WaitTimeout(
                entity_type="signalHead",
                name=self.name,
                from_state=starting.name,
            ) from e
        finally:
            self._waiters.remove(future)


class SignalMast:
    """A JMRI signal mast with its current aspect.

    Read-only in pyjmri v1: there are no command methods on
    :class:`SignalMast`; aspects are driven by JMRI's signaling logic,
    not by direct API writes. See README §Limitations.

    pyjmri v1 binds to the JMRI "basic" signaling system only; aspects
    outside that system raise :class:`~pyjmri.JMRIProtocolError` on read.
    See README Limitations (Story 6.2).

    Args:
        name: JMRI system name.
        user_name: Optional JMRI user name.
        aspect: Initial cached :class:`SignalMastAspect`.
        held: Initial cached "held" flag.
        lit: Initial cached "lit" flag.
        _handle: Internal :class:`~pyjmri._protocols.ClientHandle`.

    Example:
        Wait for the mast to display ``CLEAR``::

            await mast.wait_state(SignalMastAspect.CLEAR, timeout=10.0)
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
        aspect: SignalMastAspect,
        held: bool,
        lit: bool,
        _handle: ClientHandle,
    ) -> None:
        self.name = name
        self.user_name = user_name
        self.aspect = aspect
        self.held = held
        self.lit = lit
        self._handle = _handle
        self._waiters: WaiterList[SignalMastAspect] = WaiterList()

    async def get_state(self) -> SignalMastAspect:
        """Refresh and return the cached :class:`SignalMastAspect`.

        Updates :attr:`aspect`, :attr:`held`, and :attr:`lit` atomically
        on success. :attr:`name` and :attr:`user_name` are identity fields
        and are never refreshed.
        """
        from pyjmri._parsing import parse_signal_mast

        envelope = await self._handle.get_entity("signalMast", self.name)
        parsed = parse_signal_mast(envelope)
        self.aspect = parsed.aspect
        self.held = parsed.held
        self.lit = parsed.lit
        return parsed.aspect

    def _on_event(self, new_aspect: SignalMastAspect) -> None:
        """Update cached :attr:`aspect` and resolve matching waiters.

        Only the primary state attribute (``aspect``) is updated by
        ``_on_event``; the ``held`` and ``lit`` flags are not modeled
        as waitable events in v1.
        """
        self.aspect = new_aspect
        self._waiters.fanout(new_aspect)

    async def wait_state(
        self,
        target: SignalMastAspect,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> SignalMastAspect:
        """Await the mast reaching ``target`` aspect (FR31).

        Raises:
            WaitTimeout: if ``timeout`` elapses before the target aspect.
            RuntimeError: if the owning :class:`~pyjmri.Client` is closed
                while this call is suspended inside ``ensure_subscription``.
        """
        if self.aspect == target:
            return self.aspect
        await self._handle.ensure_subscription("signalMast", self.name)
        if self.aspect == target:
            return self.aspect
        future = self._waiters.register(lambda a: a == target)
        try:
            if timeout is None:
                return await future
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as e:
            raise WaitTimeout(
                entity_type="signalMast",
                name=self.name,
                target=target.name,
            ) from e
        finally:
            self._waiters.remove(future)

    async def wait_change(
        self,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> SignalMastAspect:
        """Await the next aspect change (FR32).

        Raises:
            WaitTimeout: if ``timeout`` elapses before any aspect change.
            RuntimeError: if the owning :class:`~pyjmri.Client` is closed
                while this call is suspended inside ``ensure_subscription``.

        Captures :attr:`aspect` after ensuring the subscription is live,
        so the "starting" reference cannot be invalidated by an event
        that arrives during the subscribe await.
        """
        await self._handle.ensure_subscription("signalMast", self.name)
        starting = self.aspect
        future = self._waiters.register(lambda a: a != starting)
        try:
            if timeout is None:
                return await future
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as e:
            raise WaitTimeout(
                entity_type="signalMast",
                name=self.name,
                from_state=starting.name,
            ) from e
        finally:
            self._waiters.remove(future)
