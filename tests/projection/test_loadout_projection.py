from datetime import datetime
import unittest

from edceleste.projection.event_projections.loadout_projection import (
    LoadoutProjection,
)
from edceleste.services.models.game_events import LoadoutEvent, UnknownCheckedEvent


def _loadout_event(**overrides) -> LoadoutEvent:
    fields = {
        "event": "Loadout",
        "timestamp": datetime.now(),
        "Ship": "cobramkiii",
        "ShipID": 3,
        "ShipName": "",
        "ShipIdent": "",
        "HullValue": 109532,
        "ModulesValue": 753500,
        "HullHealth": 1.0,
        "UnladenMass": 180.671997,
        "CargoCapacity": 24,
        "MaxJumpRange": 18.516312,
        "FuelCapacity": {"Main": 16.0, "Reserve": 0.41},
        "Rebuy": 43151,
        "Modules": [
            {
                "Slot": "MainEngines",
                "Item": "int_engine_size4_class3",
                "On": True,
                "Priority": 0,
                "Health": 1.0,
            },
            {
                "Slot": "FrameShiftDrive",
                "Item": "int_hyperdrive_size3_class5",
                "On": True,
                "Priority": 1,
                "Health": 1.0,
            },
        ],
    }
    fields.update(overrides)
    return LoadoutEvent(**fields)


class LoadoutProjectionTest(unittest.TestCase):
    def test_should_create_default_projection_before_any_loadout_event(self):
        loadout_projection = LoadoutProjection()

        self.assertEqual(
            "Ship hull health is at 100%.", loadout_projection.create_projection()
        )

    def test_should_track_loadout_fields(self):
        loadout_projection = LoadoutProjection()

        loadout_projection.process_event(_loadout_event())

        self.assertEqual(loadout_projection.hull_health, 1.0)
        self.assertEqual(loadout_projection.unladen_mass, 180.671997)
        self.assertEqual(loadout_projection.cargo_capacity, 24)
        self.assertEqual(loadout_projection.max_jump_range, 18.516312)
        self.assertEqual(loadout_projection.rebuy_cost, 43151)
        self.assertEqual(
            loadout_projection.fsd_module_item, "int_hyperdrive_size3_class5"
        )

    def test_should_report_damaged_module_as_not_all_healthy(self):
        loadout_projection = LoadoutProjection()

        loadout_projection.process_event(
            _loadout_event(
                Modules=[
                    {
                        "Slot": "MainEngines",
                        "Item": "int_engine_size4_class3",
                        "On": True,
                        "Priority": 0,
                        "Health": 0.75,
                    }
                ]
            )
        )

        self.assertFalse(loadout_projection.are_all_modules_healthy)

    def test_should_report_no_fsd_module_when_not_fitted(self):
        loadout_projection = LoadoutProjection()

        loadout_projection.process_event(_loadout_event(Modules=[]))

        self.assertIsNone(loadout_projection.fsd_module_item)

    def test_should_include_hull_health_in_projection(self):
        loadout_projection = LoadoutProjection()

        loadout_projection.process_event(_loadout_event(HullHealth=0.82))

        self.assertEqual(
            "Ship hull health is at 82%.", loadout_projection.create_projection()
        )

    def test_should_ignore_unrelated_events(self):
        loadout_projection = LoadoutProjection()

        loadout_projection.process_event(
            UnknownCheckedEvent(event="SomeEvent", timestamp=datetime.now())
        )

        self.assertEqual(1.0, loadout_projection.hull_health)


if __name__ == "__main__":
    unittest.main()
