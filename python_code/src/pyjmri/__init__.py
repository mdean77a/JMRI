"""pyjmri — async Python client for the JMRI web server."""

from __future__ import annotations

import logging

from pyjmri.block import BlockState
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
from pyjmri.light import LightState
from pyjmri.power import PowerState
from pyjmri.sensor import SensorState
from pyjmri.signal import SignalHeadAppearance, SignalMastAspect
from pyjmri.turnout import TurnoutState

logging.getLogger("pyjmri").addHandler(logging.NullHandler())

__all__ = [
    "BlockState",
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
    "LightState",
    "PowerState",
    "ReconnectConfig",
    "SensorState",
    "SignalHeadAppearance",
    "SignalMastAspect",
    "ThrottleAcquireFailed",
    "ThrottleError",
    "ThrottleReleased",
    "TurnoutState",
    "WaitTimeout",
]
