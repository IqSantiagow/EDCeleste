import unittest
from datetime import datetime

from edceleste.projection.event_projections.cargo_projection import CargoProjection
from edceleste.services.models.game_events import CargoEvent


def make_cargo_event(inventory: list[dict]) -> CargoEvent:
    """A Cargo event in the shape of Cargo.json. Every item is a dict with Name,
    Count and optionally Name_Localised."""
    return CargoEvent(
        event="Cargo",
        timestamp=datetime.now(),
        Vessel="Ship",
        Count=sum(item["Count"] for item in inventory),
        Inventory=inventory,
    )


class TestCargoProjection(unittest.TestCase):
    def test_is_empty_before_the_cargo_file_is_read(self):
        projection = CargoProjection()

        self.assertEqual("", projection.create_projection())

    def test_lists_every_commodity_with_tonnes(self):
        projection = CargoProjection()

        projection.process_event(
            make_cargo_event(
                [
                    dict(Name="gold", Name_Localised="Gold", Count=5),
                    dict(Name="water", Name_Localised="Water", Count=2),
                    dict(Name="silver", Name_Localised="Silver", Count=11),
                ]
            )
        )

        self.assertEqual(
            "Cargo hold contains: 5 t Gold, 2 t Water, 11 t Silver.",
            projection.create_projection(),
        )

    def test_uses_the_localised_name_and_falls_back_to_the_raw_name(self):
        projection = CargoProjection()

        projection.process_event(
            make_cargo_event(
                [
                    dict(Name="gold", Name_Localised="Gold", Count=5),
                    dict(Name="water", Count=2),
                ]
            )
        )

        self.assertEqual(
            "Cargo hold contains: 5 t Gold, 2 t water.",
            projection.create_projection(),
        )

    def test_empty_hold_is_said_and_not_left_out(self):
        projection = CargoProjection()

        projection.process_event(make_cargo_event([]))

        self.assertEqual("Cargo hold is empty.", projection.create_projection())

    def test_new_file_replaces_the_old_inventory(self):
        projection = CargoProjection()
        projection.process_event(
            make_cargo_event([dict(Name="gold", Name_Localised="Gold", Count=5)])
        )

        projection.process_event(
            make_cargo_event([dict(Name="water", Name_Localised="Water", Count=2)])
        )

        self.assertEqual(
            "Cargo hold contains: 2 t Water.", projection.create_projection()
        )

    def test_loading_the_same_file_twice_does_not_double_the_cargo(self):
        projection = CargoProjection()
        cargo_event = make_cargo_event(
            [dict(Name="gold", Name_Localised="Gold", Count=5)]
        )

        projection.process_event(cargo_event)
        projection.process_event(cargo_event)

        self.assertEqual(
            "Cargo hold contains: 5 t Gold.", projection.create_projection()
        )

    def test_events_of_other_files_leave_the_cargo_alone(self):
        projection = CargoProjection()
        projection.process_event(
            make_cargo_event([dict(Name="gold", Name_Localised="Gold", Count=5)])
        )

        projection.process_event(object())

        self.assertEqual(
            "Cargo hold contains: 5 t Gold.", projection.create_projection()
        )
