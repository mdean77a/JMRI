"""Unit tests for :class:`pyjmri.Route`."""

from __future__ import annotations

from pyjmri import Route


def test_route_construction_with_user_name() -> None:
    route = Route(name="IO:1", user_name="North Yard Main")

    assert route.name == "IO:1"
    assert route.user_name == "North Yard Main"


def test_route_has_no_get_state() -> None:
    route = Route(name="IO:1", user_name=None)

    assert hasattr(route, "get_state") is False
    assert hasattr(route, "get_value") is False
