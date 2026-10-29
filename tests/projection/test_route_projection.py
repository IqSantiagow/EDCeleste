import unittest
from datetime import datetime
from pathlib import Path

from edceleste.projection.event_projections.route_projection import RouteProjection
from edceleste.services.models.game_events import (
    FSDJumpEvent,
    LocationEvent,
    NavRouteEvent,
)

RESOURCES = Path(__file__).parent.parent / "resources"

ROUTE_SYSTEMS = [
    "Sol",
    "Alpha Centauri",
    "Barnard's Star",
    "Wolf 359",
    "Lalande 21185",
    "Ross 154",
]


def make_nav_route_event(system_names=ROUTE_SYSTEMS) -> NavRouteEvent:
    """A NavRoute event for the given systems, the same shape as
    nav_route_plotted.json. No names means a cleared route."""
    return NavRouteEvent(
        event="NavRoute" if system_names else "NavRouteClear",
        timestamp=datetime.now(),
        Route=[
            dict(
                StarSystem=name,
                SystemAddress=index,
                StarPos=[0.0, 0.0, 0.0],
                StarClass="M",
            )
            for index, name in enumerate(system_names)
        ],
    )


def make_location_event(star_system: str) -> LocationEvent:
    return LocationEvent(
        event="Location",
        timestamp=datetime.now(),
        StarSystem=star_system,
        SystemAddress=1,
        StarPos=[0.0, 0.0, 0.0],
        DistFromStarLS=0.0,
        Docked=False,
    )


def make_fsd_jump_event(star_system: str) -> FSDJumpEvent:
    """An FSDJump event, built from the same fields as the real journal line."""
    return FSDJumpEvent.model_validate(
        {
            "timestamp": "2026-10-23T19:41:00Z",
            "event": "FSDJump",
            "Taxi": False,
            "Multicrew": False,
            "StarSystem": star_system,
            "SystemAddress": 1,
            "StarPos": [0.0, 0.0, 0.0],
            "SystemAllegiance": "",
            "SystemEconomy": "$economy_None;",
            "SystemEconomy_Localised": "None",
            "SystemSecondEconomy": "$economy_None;",
            "SystemSecondEconomy_Localised": "None",
            "SystemGovernment": "$government_None;",
            "SystemGovernment_Localised": "None",
            "SystemSecurity": "$GAlAXY_MAP_INFO_state_anarchy;",
            "SystemSecurity_Localised": "Anarchy",
            "Population": 0,
            "Body": star_system,
            "BodyID": 0,
            "BodyType": "Star",
            "JumpDist": 4.0,
            "FuelUsed": 0.3,
            "FuelLevel": 7.0,
        }
    )


class TestRouteProjection(unittest.TestCase):
    def test_is_empty_before_the_route_file_is_read(self):
        projection = RouteProjection()

        self.assertEqual("", projection.create_projection())

    def test_names_destination_jumps_left_and_next_three_systems(self):
        projection = RouteProjection()

        projection.process_event(make_location_event("Sol"))
        projection.process_event(make_nav_route_event())

        self.assertEqual(
            "Plotted route: destination Ross 154, 5 jumps left. "
            "Next systems on the route: Alpha Centauri, Barnard's Star, Wolf 359.",
            projection.create_projection(),
        )

    def test_every_jump_takes_one_jump_off(self):
        projection = RouteProjection()
        projection.process_event(make_location_event("Sol"))
        projection.process_event(make_nav_route_event())

        projection.process_event(make_fsd_jump_event("Alpha Centauri"))

        self.assertEqual(
            "Plotted route: destination Ross 154, 4 jumps left. "
            "Next systems on the route: Barnard's Star, Wolf 359, Lalande 21185.",
            projection.create_projection(),
        )

    def test_route_loaded_at_startup_counts_from_the_current_system(self):
        projection = RouteProjection()
        # The journal is loaded first, NavRoute.json after it. NavRoute.json
        # still holds the route from the place where it was plotted.
        projection.process_event(make_location_event("Sol"))
        projection.process_event(make_fsd_jump_event("Alpha Centauri"))
        projection.process_event(make_fsd_jump_event("Barnard's Star"))

        projection.process_event(make_nav_route_event())

        self.assertEqual(
            "Plotted route: destination Ross 154, 3 jumps left. "
            "Next systems on the route: Wolf 359, Lalande 21185, Ross 154.",
            projection.create_projection(),
        )

    def test_says_one_jump_not_one_jumps(self):
        projection = RouteProjection()
        projection.process_event(make_location_event("Lalande 21185"))

        projection.process_event(make_nav_route_event())

        self.assertEqual(
            "Plotted route: destination Ross 154, 1 jump left. "
            "Next systems on the route: Ross 154.",
            projection.create_projection(),
        )

    def test_nav_route_clear_means_no_route(self):
        projection = RouteProjection()
        projection.process_event(make_location_event("Sol"))
        projection.process_event(make_nav_route_event())

        projection.process_event(make_nav_route_event([]))

        self.assertEqual("No route is plotted.", projection.create_projection())

    def test_cleared_route_file_read_at_startup_means_no_route(self):
        projection = RouteProjection()
        real_clear_event = NavRouteEvent.model_validate_json(
            (RESOURCES / "nav_route_clear.json").read_text(encoding="utf-8")
        )

        projection.process_event(real_clear_event)

        self.assertEqual("No route is plotted.", projection.create_projection())

    def test_arrival_in_the_last_system_means_no_route(self):
        projection = RouteProjection()
        projection.process_event(make_location_event("Sol"))
        projection.process_event(make_nav_route_event())

        projection.process_event(make_fsd_jump_event("Ross 154"))

        self.assertEqual("No route is plotted.", projection.create_projection())

    def test_current_system_off_the_route_keeps_the_whole_route_ahead(self):
        projection = RouteProjection()
        projection.process_event(make_location_event("Sol"))
        projection.process_event(make_nav_route_event())

        projection.process_event(make_fsd_jump_event("Some Other System"))

        self.assertIn("5 jumps left", projection.create_projection())

    def test_new_route_replaces_the_old_one(self):
        projection = RouteProjection()
        projection.process_event(make_location_event("Sol"))
        projection.process_event(make_nav_route_event())

        projection.process_event(make_nav_route_event(["Sol", "Sirius"]))

        self.assertEqual(
            "Plotted route: destination Sirius, 1 jump left. "
            "Next systems on the route: Sirius.",
            projection.create_projection(),
        )

    def test_loading_the_same_events_twice_gives_the_same_text(self):
        projection = RouteProjection()
        loading_events = [
            make_location_event("Sol"),
            make_fsd_jump_event("Alpha Centauri"),
            make_nav_route_event(),
        ]
        for event in loading_events:
            projection.process_event(event)
        text_after_first_loading = projection.create_projection()

        for event in loading_events:
            projection.process_event(event)

        self.assertEqual(text_after_first_loading, projection.create_projection())
