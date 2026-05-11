"""Layout container and EntityCollection with dual-name lookup.

Architecture sec. Layout Container & Dual-Name Lookup.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator, Mapping
from typing import Generic, Protocol, TypeVar

from pyjmri.block import Block
from pyjmri.exceptions import LayoutEntityNotFound
from pyjmri.light import Light
from pyjmri.memory import Memory
from pyjmri.route import Route
from pyjmri.sensor import Sensor
from pyjmri.signal import SignalHead, SignalMast
from pyjmri.turnout import Turnout

logger = logging.getLogger(__name__)

__all__ = ["EntityCollection", "Layout"]


class _NamedEntity(Protocol):
    name: str
    user_name: str | None


T = TypeVar("T", bound=_NamedEntity)


class EntityCollection(Mapping[str, T], Generic[T]):
    """Read-only ``Mapping[str, T]`` keyed by entity user-or-system name.

    A discovered layout maps each entity type to one ``EntityCollection``
    (see :class:`Layout`). Lookup is dual-keyed: ``collection[key]`` first
    tries the user-name index, then falls back to the system-name index.
    Iteration yields system names in insertion order.

    Collision rule:
        If a string is registered as both a *user* name on entity X and
        a *system* name on entity Y, the user-name index wins —
        ``collection[key]`` returns entity X. Entity Y remains reachable
        via :meth:`by_system_name`. This is a documented quirk of dual
        indexing; in practice collisions are vanishingly rare because
        users rarely choose names that look like system names (``NT400``,
        ``IS:AUTO:0001``, etc.).

    ``__contains__`` (``key in collection``) returns ``True`` if ``key``
    is present in **either** index. ``.values()``, ``.keys()``, and
    ``.items()`` follow the standard :class:`collections.abc.Mapping`
    contract over the system-name index.

    Args:
        entities: Iterable of entity instances; each must expose ``name``
            (system name, required) and ``user_name`` (optional). Order
            is preserved for iteration.
        entity_type: JMRI entity-type string (``"turnout"``, ``"sensor"``,
            ``"signalHead"``, ``"signalMast"``, etc.). Surfaced in
            :class:`pyjmri.LayoutEntityNotFound` context so missing-name
            errors are diagnosable.

    Example:
        Dual-name lookup with a collision::

            x = Turnout(name="NT1", user_name="Foo", ...)
            y = Turnout(name="Foo", user_name=None, ...)
            collection: EntityCollection[Turnout] = EntityCollection(
                [x, y], entity_type="turnout"
            )
            assert collection["Foo"] is x                # user name wins
            assert collection.by_system_name("Foo") is y # explicit override
    """

    def __init__(self, entities: Iterable[T], *, entity_type: str) -> None:
        by_system: dict[str, T] = {}
        by_user: dict[str, T] = {}
        for entity in entities:
            by_system[entity.name] = entity
            if entity.user_name is not None:
                by_user[entity.user_name] = entity
        self._by_system_name: dict[str, T] = by_system
        self._by_user_name: dict[str, T] = by_user
        self._entity_type: str = entity_type

    def __getitem__(self, key: str) -> T:
        """Return the entity whose user OR system name equals ``key``.

        User-name lookup wins on collision; falls back to system-name
        lookup on miss.

        Raises:
            LayoutEntityNotFound: if ``key`` is in neither index. The
                exception's ``context`` carries ``entity_type`` and
                ``key`` for diagnostics.
        """
        entity = self._by_user_name.get(key)
        if entity is not None:
            return entity
        entity = self._by_system_name.get(key)
        if entity is not None:
            return entity
        raise LayoutEntityNotFound(entity_type=self._entity_type, key=key)

    def __iter__(self) -> Iterator[str]:
        """Iterate system names in insertion order."""
        return iter(self._by_system_name)

    def __len__(self) -> int:
        """Return the number of entities in the collection."""
        return len(self._by_system_name)

    def __contains__(self, key: object) -> bool:
        """Return ``True`` if ``key`` is a user OR system name in this collection."""
        return key in self._by_user_name or key in self._by_system_name

    def by_user_name(self, name: str) -> T:
        """Return the entity whose user name equals ``name``.

        Unlike :meth:`__getitem__`, this method does **not** fall back to
        the system-name index — pass an unknown user name and you get
        :class:`pyjmri.LayoutEntityNotFound`.

        Raises:
            LayoutEntityNotFound: if no entity in this collection has the
                given user name.
        """
        entity = self._by_user_name.get(name)
        if entity is None:
            raise LayoutEntityNotFound(entity_type=self._entity_type, key=name)
        return entity

    def by_system_name(self, name: str) -> T:
        """Return the entity whose system name equals ``name``.

        Unlike :meth:`__getitem__`, this method does **not** consult the
        user-name index — pass an unknown system name and you get
        :class:`pyjmri.LayoutEntityNotFound`.

        Raises:
            LayoutEntityNotFound: if no entity in this collection has the
                given system name.
        """
        entity = self._by_system_name.get(name)
        if entity is None:
            raise LayoutEntityNotFound(entity_type=self._entity_type, key=name)
        return entity


class Layout:
    """Typed snapshot of a JMRI layout's discoverable entities.

    Returned by :meth:`pyjmri.Client.discover` (Story 2.5). Holds one
    :class:`EntityCollection` per supported entity type. The snapshot is
    not auto-refreshed — each entity's cached state reflects the value
    captured at discovery (or at the last explicit refresh). To re-read
    a single entity, call its ``get_state()`` or ``get_value()`` method;
    to wait for state changes, use Epic 3's ``wait_*`` primitives.

    Any constructor parameter omitted defaults to an empty
    :class:`EntityCollection` with the matching ``entity_type``, so
    ``Layout()`` is a valid empty snapshot.

    Args:
        turnouts: Pre-built turnout collection, or ``None`` for empty.
        sensors: Pre-built sensor collection, or ``None`` for empty.
        blocks: Pre-built block collection, or ``None`` for empty.
        lights: Pre-built light collection, or ``None`` for empty.
        memories: Pre-built memory collection, or ``None`` for empty.
        routes: Pre-built route collection, or ``None`` for empty.
        signal_heads: Pre-built signal-head collection, or ``None`` for
            empty.
        signal_masts: Pre-built signal-mast collection, or ``None`` for
            empty.

    Example:
        Construct empty (e.g., for tests or before discovery)::

            layout = Layout()
            assert len(layout.turnouts) == 0

        Used internally by :meth:`pyjmri.Client.discover` (Story 2.5)::

            layout = Layout(
                turnouts=EntityCollection(turnouts, entity_type="turnout"),
                sensors=EntityCollection(sensors, entity_type="sensor"),
                # ... one collection per entity type
            )
    """

    def __init__(
        self,
        *,
        turnouts: EntityCollection[Turnout] | None = None,
        sensors: EntityCollection[Sensor] | None = None,
        blocks: EntityCollection[Block] | None = None,
        lights: EntityCollection[Light] | None = None,
        memories: EntityCollection[Memory] | None = None,
        routes: EntityCollection[Route] | None = None,
        signal_heads: EntityCollection[SignalHead] | None = None,
        signal_masts: EntityCollection[SignalMast] | None = None,
    ) -> None:
        self.turnouts: EntityCollection[Turnout] = (
            turnouts if turnouts is not None else EntityCollection([], entity_type="turnout")
        )
        self.sensors: EntityCollection[Sensor] = (
            sensors if sensors is not None else EntityCollection([], entity_type="sensor")
        )
        self.blocks: EntityCollection[Block] = (
            blocks if blocks is not None else EntityCollection([], entity_type="block")
        )
        self.lights: EntityCollection[Light] = (
            lights if lights is not None else EntityCollection([], entity_type="light")
        )
        self.memories: EntityCollection[Memory] = (
            memories if memories is not None else EntityCollection([], entity_type="memory")
        )
        self.routes: EntityCollection[Route] = (
            routes if routes is not None else EntityCollection([], entity_type="route")
        )
        self.signal_heads: EntityCollection[SignalHead] = (
            signal_heads
            if signal_heads is not None
            else EntityCollection([], entity_type="signalHead")
        )
        self.signal_masts: EntityCollection[SignalMast] = (
            signal_masts
            if signal_masts is not None
            else EntityCollection([], entity_type="signalMast")
        )
