import unittest
from pathlib import Path

from edceleste.services.models.game_events import (
    CargoEvent,
    ModuleInfoEvent,
    NavRouteEvent,
)

RESOURCES = Path(__file__).parent.parent.parent / "resources"


def read_sample(file_name: str) -> str:
    return (RESOURCES / file_name).read_text(encoding="utf-8")


class TestSideFileEvents(unittest.TestCase):
    """The samples are the files as the game writes them. nav_route_clear.json,
    cargo_empty.json and modules_info.json are copies of real files, the other
    two are written by hand in the same format, because the real ones held no
    route and no cargo."""

    def test_real_nav_route_clear_file_parses_with_an_empty_route(self):
        event = NavRouteEvent.model_validate_json(read_sample("nav_route_clear.json"))

        self.assertEqual("NavRouteClear", event.event)
        self.assertEqual([], event.Route)

    def test_plotted_route_parses_every_system_in_order(self):
        event = NavRouteEvent.model_validate_json(read_sample("nav_route_plotted.json"))

        self.assertEqual("NavRoute", event.event)
        self.assertEqual(
            [
                "Sol",
                "Alpha Centauri",
                "Barnard's Star",
                "Wolf 359",
                "Lalande 21185",
                "Ross 154",
            ],
            [system.StarSystem for system in event.Route],
        )

    def test_real_empty_cargo_file_parses(self):
        event = CargoEvent.model_validate_json(read_sample("cargo_empty.json"))

        self.assertEqual("Ship", event.Vessel)
        self.assertEqual(0, event.Count)
        self.assertEqual([], event.Inventory)

    def test_cargo_file_with_inventory_parses_names_and_counts(self):
        event = CargoEvent.model_validate_json(read_sample("cargo_with_inventory.json"))

        self.assertEqual(
            [("gold", "Gold", 5), ("water", None, 2)],
            [(item.Name, item.Name_Localised, item.Count) for item in event.Inventory],
        )

    def test_real_modules_info_file_parses_and_keeps_a_missing_priority_as_none(self):
        event = ModuleInfoEvent.model_validate_json(read_sample("modules_info.json"))

        modules_by_slot = {module.Slot: module for module in event.Modules}
        self.assertEqual(27, len(event.Modules))
        self.assertEqual(3.28, modules_by_slot["MainEngines"].Power)
        self.assertEqual(0, modules_by_slot["MainEngines"].Priority)
        self.assertIsNone(modules_by_slot["PowerPlant"].Priority)
