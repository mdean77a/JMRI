"""Roster read-only entity classes (capability-aware).

JMRI's roster is the full DecoderPro catalog of every locomotive the user
has programmed. pyjmri exposes it **read-only**: every type here is a
frozen, handle-free snapshot with no command, set, or wait surface
(FR56). To refresh, re-run discovery.

The roster is distinct from the Operations subsystem
(:mod:`pyjmri.operations`), whose :class:`~pyjmri.Engine` models only the
operationally-active subset deployed on the layout. The two are separate
types and are not conflated.

Parsing of JMRI's JSON into these objects lives in :mod:`pyjmri._parsing`
(``parse_roster_entry``). The :class:`Roster` collection is returned by
``Client.discover_roster`` — a standalone read-only subsystem, mirroring
``Client.discover_operations`` — and adds DCC-address lookup
(:meth:`Roster.by_address`).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from pyjmri.layout import EntityCollection

__all__ = [
    "Capability",
    "FunctionLabel",
    "Roster",
    "RosterEntry",
    "classify_capability",
    "firable_startup_functions",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True, slots=True)
class FunctionLabel:
    """One function-key label from a roster entry's ``functionKeys`` array.

    Read-only snapshot. ``num`` is the function number (``0`` for F0, ``1``
    for F1, ...); ``label`` is the user-entered DecoderPro label, or
    ``None`` when blank; ``lockable`` is ``True`` for a latching/toggle
    function (e.g. lights) and ``False`` for a momentary one (e.g.
    horn/bell).

    A labelled function ("Startup", "Horn", "Bell", ...) is the reliable
    signal of a locomotive's capabilities — decoder family/model strings
    are decoder-definition-file names, not capability tags.
    """

    num: int
    label: str | None
    lockable: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class RosterEntry:
    """A read-only locomotive roster entry (DecoderPro catalog metadata).

    Frozen snapshot captured at discovery. Carries identity, addressing,
    reference metadata, decoder identifiers, and per-function labels.

    ``name`` is the JMRI roster ID (e.g. ``"1029 NW2 Switcher"``) and the
    primary key; roster entries have no separate ``userName``, so
    :attr:`user_name` is always ``None`` (the roster ID is itself the
    human-facing label). ``decoder_family`` / ``decoder_model`` are
    decoder-definition-file identifiers, NOT capability tags — infer a
    locomotive's capabilities from :attr:`function_labels`.

    The roster catalogs every engine the user has programmed in
    DecoderPro; contrast :class:`~pyjmri.Engine`, which models only the
    operationally-active subset on the layout.
    """

    name: str
    user_name: str | None
    dcc_address: int
    long_address: bool
    road_name: str | None
    road_number: str | None
    model: str | None
    mfg: str | None
    owner: str | None
    comment: str | None
    image_path: str | None
    max_speed_pct: int | None
    decoder_family: str | None
    decoder_model: str | None
    function_labels: tuple[FunctionLabel, ...]


@dataclass(frozen=True, kw_only=True, slots=True)
class Capability:
    """What a locomotive can do, inferred from its roster function labels.

    Read-only result of :func:`classify_capability`. :attr:`sound` is
    ``True`` when at least one function carries a sound-related label;
    :attr:`sound_functions` are those labelled functions in entry order.
    :attr:`motor_only` is the inverse — the common case for an unlabelled
    or un-catalogued locomotive.

    Capability is inferred from function *labels*, never from decoder
    family/model strings (which are decoder-definition-file names, not
    capability tags).
    """

    sound: bool
    sound_functions: tuple[FunctionLabel, ...]

    @property
    def motor_only(self) -> bool:
        """``True`` when no sound-related function label was found."""
        return not self.sound


# Capability vocabulary: a function label (case-insensitive) containing any
# of these substrings marks a sound-capable function. This is the auditable
# decision input for classify_capability — intentionally label-based, NOT
# decoder-family-based (decoder_family/decoder_model are date-stamped
# definition-file names like "Jan 2012" or "ESU LokSound 5", not capability
# tags). Tune this set to refine classification.
_SOUND_KEYWORDS: frozenset[str] = frozenset(
    {"sound", "startup", "shutdown", "horn", "whistle", "bell", "engine", "mute"}
)


class Roster(EntityCollection[RosterEntry]):
    """Read-only roster collection: dual-name Mapping plus a DCC-address index.

    Returned by ``Client.discover_roster`` (a standalone read-only
    subsystem, mirroring ``Client.discover_operations``). Inherits the
    :class:`~pyjmri.EntityCollection` dual-name lookup, then adds a
    client-side address index (:meth:`by_address`) — JMRI's roster primary
    key is the entry name/ID, not the DCC address.

    Roster entries have no user name (:attr:`RosterEntry.user_name` is
    always ``None``), so ``roster[key]`` resolves via the roster-ID
    (system-name) index and :meth:`by_user_name` is not meaningful here —
    the roster ID *is* the name. :meth:`by_address` is the
    capability-relevant lookup.

    Read-only snapshot (FR56); re-run ``discover_roster()`` to refresh.

    Args:
        entries: Iterable of :class:`RosterEntry`. Consumed once. On a
            duplicate DCC address the first entry wins and a WARNING is
            logged (addresses are unique in practice).
    """

    def __init__(self, entries: Iterable[RosterEntry]) -> None:
        materialized = list(entries)
        super().__init__(materialized, entity_type="rosterEntry")
        by_address: dict[int, RosterEntry] = {}
        for entry in materialized:
            existing = by_address.get(entry.dcc_address)
            if existing is not None:
                logger.warning(
                    "duplicate DCC address %d in roster: keeping %r, ignoring %r",
                    entry.dcc_address,
                    existing.name,
                    entry.name,
                )
                continue
            by_address[entry.dcc_address] = entry
        self._by_address: dict[int, RosterEntry] = by_address

    def by_address(self, dcc_address: int) -> RosterEntry | None:
        """Return the roster entry for ``dcc_address``, or ``None`` if absent.

        A ``get()``-style find, **not** a raise: an address with no roster
        entry is a normal case (a brand-new, un-catalogued loco; FR55). On a
        miss this logs an informative WARNING naming the address and returns
        ``None`` — never raises.
        """
        entry = self._find_by_address(dcc_address)
        if entry is None:
            logger.warning("no roster entry for DCC address %d", dcc_address)
        return entry

    def _find_by_address(self, dcc_address: int) -> RosterEntry | None:
        """Silent address lookup — like :meth:`by_address` but logs nothing.

        Internal seam for callers that emit their own miss diagnostic (e.g.
        ``Client.throttle_for_entry``'s warn-and-drive path), so a single
        un-catalogued address produces one WARNING, not two.
        """
        return self._by_address.get(dcc_address)


def classify_capability(entry: RosterEntry) -> Capability:
    """Classify a locomotive's capabilities from its roster function labels.

    A pure function (no I/O, no Client). Reads ONLY
    :attr:`RosterEntry.function_labels` — never ``decoder_family`` /
    ``decoder_model``, which are decoder-definition-file names, not
    capability tags. A function is sound-related when its label is non-empty
    and (case-insensitively) contains any keyword in ``_SOUND_KEYWORDS``
    (e.g. "startup", "horn", "bell"). Falls back to a minimal motor-only
    classification when labels are blank, absent, or unrecognised — the
    common real case, since many roster entries have all-``None`` labels.

    Args:
        entry: The roster entry to classify.

    Returns:
        A :class:`Capability`. ``sound`` is ``True`` iff at least one
        function label matched; ``sound_functions`` holds the matching
        :class:`FunctionLabel` objects in entry order; ``motor_only`` is the
        inverse.
    """
    sound_functions = tuple(
        fl
        for fl in entry.function_labels
        if fl.label is not None and any(kw in fl.label.lower() for kw in _SOUND_KEYWORDS)
    )
    return Capability(sound=bool(sound_functions), sound_functions=sound_functions)


def firable_startup_functions(capability: Capability) -> tuple[int, ...]:
    """Return the throttle-commandable function numbers a startup should assert.

    Filters :attr:`Capability.sound_functions` to the range ``[0, 28]`` that
    :meth:`pyjmri.Throttle.set_function` accepts (F29+ is a Story 5.2 / FR26
    throttle-command constraint). A sound-labelled function above F28 is
    recognised by :func:`classify_capability` but is *not* commandable, so it
    is excluded here rather than passed to ``set_function`` (which would
    raise ``ValueError``). The result is ordered and de-duplicated.

    Args:
        capability: The classification result to derive firable functions from.

    Returns:
        The firable F0-F28 function numbers, in order, without duplicates.
    """
    seen: set[int] = set()
    nums: list[int] = []
    for fl in capability.sound_functions:
        if 0 <= fl.num <= 28 and fl.num not in seen:
            seen.add(fl.num)
            nums.append(fl.num)
    return tuple(nums)
