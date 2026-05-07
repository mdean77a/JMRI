"""pyjmri — async Python client for the JMRI web server."""

from __future__ import annotations

import logging

from pyjmri.client import Client, ClientConfig, ReconnectConfig
from pyjmri.exceptions import (
    JMRIConnectionError,
    JMRIError,
    JMRIProtocolError,
    JMRIReconnectFailed,
    JMRIRequestTimeout,
    JMRIVersionUnsupported,
    LayoutEntityNotControllable,
    LayoutEntityNotFound,
    ThrottleAcquireFailed,
    ThrottleError,
    ThrottleReleased,
    WaitTimeout,
)

logging.getLogger("pyjmri").addHandler(logging.NullHandler())

__all__ = [
    "Client",
    "ClientConfig",
    "JMRIConnectionError",
    "JMRIError",
    "JMRIProtocolError",
    "JMRIReconnectFailed",
    "JMRIRequestTimeout",
    "JMRIVersionUnsupported",
    "LayoutEntityNotControllable",
    "LayoutEntityNotFound",
    "ReconnectConfig",
    "ThrottleAcquireFailed",
    "ThrottleError",
    "ThrottleReleased",
    "WaitTimeout",
]
