"""Route entity (typed metadata only in v1; activation lands in Epic 4)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = ["Route"]


class Route:
    """A JMRI route — a saved sequence of turnout positions.

    In pyjmri v1 a :class:`Route` is metadata only: name and user name.
    Route activation (firing the saved sequence) lands in Epic 4 as
    ``await route.activate()``. Routes have no readable state in v1.

    Example:
        Enumerate available routes::

            for route in layout.routes.values():
                print(route.name)

    Args:
        name: JMRI system name.
        user_name: Optional JMRI user name.
    """

    def __init__(
        self,
        *,
        name: str,
        user_name: str | None,
    ) -> None:
        self.name = name
        self.user_name = user_name
