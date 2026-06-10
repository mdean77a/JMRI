"""Operations subsystem read-only entity classes and nested value objects.

JMRI's Operations module (locations, trains, cars, engines) is a data
subsystem distinct from the layout model and from the roster. pyjmri
exposes it **read-only**: every type in this module is a frozen,
handle-free snapshot with no command, set, or wait surface (FR49). To
refresh, re-run discovery (Story 8.2's ``Client.discover_operations()``).

Architecture sec. "Operations Subsystem (Read-Only)". Parsing of JMRI's
JSON into these objects lives in :mod:`pyjmri._parsing`
(``parse_location`` / ``parse_train`` / ``parse_car`` / ``parse_engine``).
"""

from __future__ import annotations

from dataclasses import dataclass

from pyjmri.layout import EntityCollection

__all__ = [
    "Car",
    "Engine",
    "Location",
    "Operations",
    "Placement",
    "RouteStop",
    "Track",
    "Train",
]


@dataclass(frozen=True, kw_only=True, slots=True)
class Track:
    """A track within an Operations location (e.g. a staging or yard track).

    Read-only snapshot. ``name`` is JMRI's system id (e.g. ``"2s1"``);
    ``user_name`` is the human label (e.g. ``"NW_Track_1"``).
    """

    name: str
    user_name: str | None


@dataclass(frozen=True, kw_only=True, slots=True)
class Placement:
    """A location reference attached to a car or engine.

    Models JMRI's nested ``location`` / ``destination`` object: the
    location the rolling stock is at (or bound for) plus, when JMRI
    reports it, the specific :class:`Track`. ``track`` is ``None`` when
    JMRI omits it. The whole placement is ``None`` (not an empty
    ``Placement``) when the stock is unplaced/unassigned — see
    :attr:`Car.location` / :attr:`Car.destination`.
    """

    name: str
    user_name: str | None
    track: Track | None


@dataclass(frozen=True, kw_only=True, slots=True)
class RouteStop:
    """One stop on a train's route, from JMRI's ``train.locations[]``.

    Read-only snapshot. ``sequence_id`` is the stop's order along the
    route (1-based); stops are exposed in :attr:`Train.route_stops`
    ordered by it.
    """

    name: str
    user_name: str | None
    sequence_id: int
    train_direction: str


@dataclass(frozen=True, kw_only=True, slots=True)
class Location:
    """An Operations location (a yard, interchange, or staging area).

    Read-only snapshot. Carries both a system :attr:`name` (e.g. ``"2"``)
    and a :attr:`user_name` (e.g. ``"NW_Staging_Yard"``), so it supports
    dual-name lookup in the Story 8.2 ``Operations`` container.
    """

    name: str
    user_name: str | None
    length: int
    comment: str | None
    tracks: tuple[Track, ...] = ()


@dataclass(frozen=True, kw_only=True, slots=True)
class Car:
    """An Operations car (rolling stock) — read-only operational snapshot.

    Identified by :attr:`name` = road+number (e.g. ``"AA123"``); JMRI
    gives cars no separate user name, so :attr:`user_name` is always
    ``None``. The value-add over the roster is the operational state:
    :attr:`location` (where it is now), :attr:`train` (the name of the
    train it is assigned to), and :attr:`destination`. Each is ``None``
    when JMRI reports the car as unplaced/unassigned — a valid state,
    parsed without error (FR48).
    """

    name: str
    user_name: str | None = None
    road: str
    number: str
    car_type: str
    length: int
    location: Placement | None
    train: str | None
    destination: Placement | None


@dataclass(frozen=True, kw_only=True, slots=True)
class Engine:
    """An Operations engine — read-only operational snapshot.

    Identified by :attr:`name` = road+number (e.g. ``"UP2570"``); JMRI
    gives engines no separate user name, so :attr:`user_name` is always
    ``None``.

    Distinct from the roster (FR48): the roster (DecoderPro catalog)
    lists *every* engine the user has programmed, whereas an
    :class:`Engine` is the operationally-active subset actually deployed
    on the layout. The two are intentionally separate types and are not
    conflated — an :class:`Engine` is never a roster entry.

    :attr:`location` is where the engine is now; :attr:`train` is the
    name of the train it is assigned to (``None`` when unassigned — both
    assigned and unassigned engines occur in practice, FR48).
    """

    name: str
    user_name: str | None = None
    road: str
    number: str
    model: str | None
    engine_type: str
    length: int
    location: Placement | None
    train: str | None
    destination: Placement | None


@dataclass(frozen=True, kw_only=True, slots=True)
class Train:
    """An Operations train — read-only operational snapshot.

    Carries both a system :attr:`name` (e.g. ``"1"``) and a
    :attr:`user_name` (e.g. ``"TestTrainOne"``). The operational
    value-add: :attr:`route` (the assigned route's name),
    :attr:`current_location` (the user name of the location the train is
    currently at, ``None`` before it departs), :attr:`status` (JMRI's
    freeform status text, e.g. ``"Partial 3/27 cars"`` — a raw string in
    v1.1, not an enum) and :attr:`status_code`.

    The consist and route are exposed as nested read-only snapshots:
    :attr:`route_stops` (ordered by :attr:`RouteStop.sequence_id`), and
    :attr:`engines` / :attr:`cars` (the rolling stock currently in the
    train, as full :class:`Engine` / :class:`Car` objects).

    Note on :attr:`lead_engine`: JMRI stores this as a display string in
    "road number" form (e.g. ``"UP 8997"`` with a space separator), which
    differs from :attr:`Engine.name` (road concatenated with number,
    e.g. ``"UP8997"``). The two cannot be compared by simple equality;
    use the consist :attr:`engines` tuple to look up the leading engine
    programmatically.
    """

    name: str
    user_name: str | None
    route: str | None
    current_location: str | None
    status: str
    status_code: int
    lead_engine: str | None
    route_stops: tuple[RouteStop, ...] = ()
    engines: tuple[Engine, ...] = ()
    cars: tuple[Car, ...] = ()


class Operations:
    """Read-only snapshot of a JMRI Operations session.

    Returned by :meth:`pyjmri.Client.discover_operations`. Holds one
    :class:`~pyjmri.EntityCollection` per Operations type — ``locations``,
    ``trains``, ``cars``, ``engines`` — reusing the same dual-name
    container that :class:`~pyjmri.Layout` uses.

    This is a distinct subsystem from :class:`~pyjmri.Layout`: Operations
    entities are pure data records (where a car is, what train it is on),
    not commandable layout hardware. The container is therefore
    **read-only and handle-free** — it exposes no command, set, wait, or
    throttle method, only the four collection attributes (FR49).

    The snapshot is point-in-time and is **not** WebSocket-subscribed; to
    refresh, call :meth:`pyjmri.Client.discover_operations` again.

    Locations and trains carry both a user name and a system name, so
    dual-name lookup works (``ops.locations["NW_Staging_Yard"]`` and
    ``ops.locations["2"]``). Cars and engines have no user name and are
    keyed by road+number (``ops.cars["AA123"]``). A missing key raises
    :class:`~pyjmri.LayoutEntityNotFound`.

    Any constructor parameter omitted defaults to an empty
    :class:`~pyjmri.EntityCollection` with the matching ``entity_type``,
    so ``Operations()`` is a valid empty snapshot (FR50).

    Args:
        locations: Pre-built location collection, or ``None`` for empty.
        trains: Pre-built train collection, or ``None`` for empty.
        cars: Pre-built car collection, or ``None`` for empty.
        engines: Pre-built engine collection, or ``None`` for empty.
    """

    def __init__(
        self,
        *,
        locations: EntityCollection[Location] | None = None,
        trains: EntityCollection[Train] | None = None,
        cars: EntityCollection[Car] | None = None,
        engines: EntityCollection[Engine] | None = None,
    ) -> None:
        self.locations: EntityCollection[Location] = (
            locations if locations is not None else EntityCollection([], entity_type="location")
        )
        self.trains: EntityCollection[Train] = (
            trains if trains is not None else EntityCollection([], entity_type="train")
        )
        self.cars: EntityCollection[Car] = (
            cars if cars is not None else EntityCollection([], entity_type="car")
        )
        self.engines: EntityCollection[Engine] = (
            engines if engines is not None else EntityCollection([], entity_type="engine")
        )
