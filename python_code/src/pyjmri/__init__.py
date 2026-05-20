"""pyjmri — async Python client for the JMRI web server."""

from __future__ import annotations

import logging

from pyjmri.block import Block, BlockState
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
from pyjmri.layout import EntityCollection, Layout
from pyjmri.light import Light, LightState
from pyjmri.memory import Memory
from pyjmri.power import PowerState
from pyjmri.route import Route, RouteState
from pyjmri.sensor import Sensor, SensorState
from pyjmri.signal import SignalHead, SignalHeadAppearance, SignalMast, SignalMastAspect
from pyjmri.turnout import Turnout, TurnoutState

logging.getLogger("pyjmri").addHandler(logging.NullHandler())

__all__ = [
    "Block",
    "BlockState",
    "Client",
    "ClientConfig",
    "EntityCollection",
    "JMRIConnectionError",
    "JMRIError",
    "JMRIProtocolError",
    "JMRIReconnectFailed",
    "JMRIRequestTimeout",
    "JMRIVersionUnsupported",
    "Layout",
    "LayoutEntityNotControllable",
    "LayoutEntityNotFound",
    "Light",
    "LightState",
    "Memory",
    "PowerState",
    "ReconnectConfig",
    "Route",
    "RouteState",
    "Sensor",
    "SensorState",
    "SignalHead",
    "SignalHeadAppearance",
    "SignalMast",
    "SignalMastAspect",
    "ThrottleAcquireFailed",
    "ThrottleError",
    "ThrottleReleased",
    "Turnout",
    "TurnoutState",
    "WaitTimeout",
]
