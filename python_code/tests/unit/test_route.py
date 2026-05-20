"""Unit tests for :class:`pyjmri.Route`."""

from __future__ import annotations

from typing import Any, cast

import pytest

from pyjmri import Route
from pyjmri._protocols import ClientHandle
from pyjmri.exceptions import LayoutEntityNotControllable


def test_route_construction_with_user_name(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    route = Route(name="IO:1", user_name="North Yard Main", _handle=cast(ClientHandle, handle))

    assert route.name == "IO:1"
    assert route.user_name == "North Yard Main"


def test_route_has_no_get_state(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    route = Route(name="IO:1", user_name=None, _handle=cast(ClientHandle, handle))

    assert hasattr(route, "get_state") is False
    assert hasattr(route, "get_value") is False


async def test_activate_sends_active_state_code(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    route = Route(name="IO:1", user_name=None, _handle=cast(ClientHandle, handle))

    await route.activate()

    assert handle.command_calls == [("route", "IO:1", {"state": 2})]


@pytest.mark.anyio
async def test_activate_propagates_layout_entity_not_controllable(make_fake_handle: Any) -> None:
    handle = make_fake_handle(lambda _t, _n: {})
    handle.command_raises = LayoutEntityNotControllable(
        entity_type="route",
        name="IO:1",
        jmri_message="locked",
        status=409,
    )
    route = Route(name="IO:1", user_name=None, _handle=cast(ClientHandle, handle))

    with pytest.raises(LayoutEntityNotControllable):
        await route.activate()
