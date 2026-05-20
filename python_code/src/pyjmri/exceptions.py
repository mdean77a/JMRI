"""JMRIError hierarchy. See architecture §Exception Hierarchy."""

from __future__ import annotations

from typing import Any

__all__ = [
    "JMRIConnectionError",
    "JMRIError",
    "JMRIProtocolError",
    "JMRIReconnectFailed",
    "JMRIRequestTimeout",
    "JMRIVersionUnsupported",
    "LayoutEntityNotControllable",
    "LayoutEntityNotFound",
    "ThrottleAcquireFailed",
    "ThrottleError",
    "ThrottleReleased",
    "WaitTimeout",
]


class JMRIError(Exception):
    """Base class for every error pyjmri raises.

    Library code never raises ``JMRIError`` directly — only concrete
    subclasses. The base exists so user code can catch every
    library-raised error with a single ``except JMRIError`` block.

    Args:
        message: Optional human-readable summary.
        **context: Diagnostic key/value pairs, surfaced via ``.context``
            and rendered into ``__str__``.
    """

    def __init__(self, message: str | None = None, /, **context: Any) -> None:
        super().__init__(message or "")
        self.context: dict[str, Any] = context

    def __str__(self) -> str:
        msg = super().__str__()
        if not self.context:
            return msg
        ctx = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
        return f"{msg} [{ctx}]" if msg else f"[{ctx}]"


class JMRIConnectionError(JMRIError):
    """Raised when the library cannot reach JMRI's web server.

    Carries ``host`` and ``port`` so user code can render an actionable
    error message without parsing a string. The default ``__str__``
    matches PRD FR35.
    """

    def __init__(
        self,
        message: str | None = None,
        /,
        *,
        host: str,
        port: int,
        **context: Any,
    ) -> None:
        super().__init__(message, host=host, port=port, **context)
        self.host = host
        self.port = port

    def __str__(self) -> str:
        return (
            f"could not connect to {self.host}:{self.port} — "
            f"is JMRI running with the web server enabled?"
        )


class JMRIReconnectFailed(JMRIConnectionError):
    """Raised when the WebSocket reconnect loop exhausts ``max_attempts``."""

    def __str__(self) -> str:
        attempts = self.context.get("attempts", "?")
        cause = self.context.get("cause", "unknown")
        return (
            f"WebSocket reconnect failed after {attempts} attempt(s) ({cause}) "
            f"on {self.host}:{self.port}"
        )


class JMRIRequestTimeout(JMRIError):
    """Raised when an HTTP request exceeds ``request_timeout``."""


class JMRIProtocolError(JMRIError):
    """Raised when JMRI's response does not match the assumed JSON contract."""


class JMRIVersionUnsupported(JMRIProtocolError):
    """Raised when the connected JMRI is older than the minimum version (5.14)."""


class LayoutEntityNotFound(JMRIError, KeyError):
    """Raised when a name is not in the user-name OR system-name index.

    Multi-inherits :class:`KeyError` so :meth:`collections.abc.Mapping.get`
    (which catches only ``KeyError``) returns the supplied default rather
    than surfacing the lookup miss.
    """


class LayoutEntityNotControllable(JMRIError):
    """Raised when a command is rejected because the entity is not controllable.

    Two raise sites: (1) ``HTTPClient.command`` when JMRI returns HTTP 400/403/409
    with a JMRI error envelope (e.g. a turnout locked by an active Dispatcher section);
    (2) ``EntityCollection.__getitem__`` when ``set_state`` is called on a read-only
    entity type (e.g. ``SignalMast``).
    """


class ThrottleError(JMRIError):
    """Base for throttle lifecycle errors."""


class ThrottleAcquireFailed(ThrottleError):
    """Raised when JMRI rejects a throttle acquire request."""


class ThrottleReleased(ThrottleError):
    """Raised when a throttle method is called after ``.release()``."""


class WaitTimeout(JMRIError, TimeoutError):
    """Raised when an ``await wait_*`` exceeds its optional timeout.

    Multi-inherits the builtin :class:`TimeoutError` so user code can
    catch either ``JMRIError`` or ``TimeoutError``.
    """
