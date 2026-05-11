"""Slim Client surface that domain entities depend on.

Defining this Protocol keeps ``_transport.py`` out of ``turnout.py``,
``sensor.py``, etc. Entity modules import only :class:`ClientHandle`.
The concrete implementation lives on :class:`pyjmri.Client`; the
indirection lets unit tests construct entities with a fake handle.

Architecture sec. Internal Layering: domain entities hold a
Protocol-typed handle to the Client for issuing commands. They do not
import ``_transport`` directly.
"""

from __future__ import annotations

from typing import Any, Protocol


class ClientHandle(Protocol):
    """Internal Protocol for entity -> Client read-back calls.

    The :class:`pyjmri.Client` implements this Protocol implicitly via
    duck typing: it has a matching ``get_entity`` method.

    This Protocol is not part of the public API; users of pyjmri never
    interact with it. It exists to satisfy mypy strict mode in entity
    modules without importing ``_transport`` (transport/domain
    boundary preservation).
    """

    async def get_entity(self, entity_type: str, name: str) -> dict[str, Any]: ...
