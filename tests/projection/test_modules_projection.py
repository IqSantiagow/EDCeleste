import unittest
from datetime import datetime
from pathlib import Path

from edceleste.projection.event_projections.modules_projection import (
    ModulesProjection,
)
from edceleste.services.models.game_events import ModuleInfoEvent

RESOURCES = Path(__file__).parent.parent / "resources"


def make_module_info_event(modules: list[dict]) -> ModuleInfoEvent:
    """A ModuleInfo event in the shape of ModulesInfo.json."""
    return ModuleInfoEvent(
        event="ModuleInfo", timestamp=datetime.now(), Modules=modules
    )


class TestModulesProjection(unittest.TestCase):
    def test_is_empty_before_the_modules_file_is_read(self):
        projection = ModulesProjection()

        self.assertEqual("", projection.create_projection())

    def test_lists_slot_module_power_and_priority(self):
        projection = ModulesProjection()

        projection.process_event(
            make_module_info_event(
                [
                    dict(
                        Slot="MainEngines",
                        Item="int_engine_size4_class1",
                        Power=3.28,
                        Priority=0,
                    ),
                    dict(
                        Slot="LifeSupport",
                        Item="int_lifesupport_size3_class1",
                        Power=0.42,
                        Priority=2,
                    ),
                ]
            )
        )

        self.assertEqual(
            "Ship modules (slot: module, power draw, power priority): "
            "MainEngines: int_engine_size4_class1, 3.28 MW, priority 0; "
            "LifeSupport: int_lifesupport_size3_class1, 0.42 MW, priority 2.",
            projection.create_projection(),
        )

    def test_module_without_priority_has_no_priority_in_the_text(self):
        projection = ModulesProjection()

        projection.process_event(
            make_module_info_event(
                [dict(Slot="PowerPlant", Item="int_powerplant_size4_class3", Power=0.0)]
            )
        )

        self.assertEqual(
            "Ship modules (slot: module, power draw, power priority): "
            "PowerPlant: int_powerplant_size4_class3, 0 MW.",
            projection.create_projection(),
        )

    def test_priority_zero_is_kept_and_not_taken_for_a_missing_priority(self):
        projection = ModulesProjection()

        projection.process_event(
            make_module_info_event(
                [dict(Slot="Radar", Item="int_sensors_size3_class1", Priority=0)]
            )
        )

        self.assertIn("priority 0", projection.create_projection())

    def test_new_file_replaces_the_old_list(self):
        projection = ModulesProjection()
        projection.process_event(
            make_module_info_event([dict(Slot="Radar", Item="old_sensors")])
        )

        projection.process_event(
            make_module_info_event([dict(Slot="LifeSupport", Item="new_life_support")])
        )

        self.assertNotIn("old_sensors", projection.create_projection())
        self.assertIn("new_life_support", projection.create_projection())

    def test_every_module_of_the_real_file_is_in_the_text(self):
        projection = ModulesProjection()
        real_event = ModuleInfoEvent.model_validate_json(
            (RESOURCES / "modules_info.json").read_text(encoding="utf-8")
        )

        projection.process_event(real_event)

        text = projection.create_projection()
        self.assertEqual(27, len(real_event.Modules))
        for module in real_event.Modules:
            self.assertIn(f"{module.Slot}: {module.Item}", text)

    def test_events_of_other_files_leave_the_modules_alone(self):
        projection = ModulesProjection()
        projection.process_event(
            make_module_info_event(
                [dict(Slot="Radar", Item="int_sensors_size3_class1")]
            )
        )

        projection.process_event(object())

        self.assertIn("int_sensors_size3_class1", projection.create_projection())
