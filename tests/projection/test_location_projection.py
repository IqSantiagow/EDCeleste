import unittest
from datetime import datetime

from projection.event_projections.location_projection import LocationProjection
from services.models.game_events import (
    DockedEvent,
    UndockedEvent,
    LocationEvent,
    FSDJumpEvent,
)
from services.models.game_models import BaseFactionModel, StationEconomyModel


class TestLocationProjection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docked_event = DockedEvent(
            event="Docked",
            timestamp=datetime.now(),
            StarSystem="Sol",
            StationName="Galileo",
            MarketID=12345,
            StationType="Coriolis",
            SystemAddress=123456789,
            StationFaction=BaseFactionModel(
                Name="Galileo Corporation",
                FactionState="Boom",
            ),
            StationEconomy_Localised="Industrial",
            StationEconomies=[
                StationEconomyModel(Name_Localised="Industrial", Proportion=0.7)
            ],
            DistFromStarLS=100.0,
            StationGovernment_Localised="Democracy",
            StationAllegiance="Federation",
            StationServices=["Refuel", "Repair"],
        )

        cls.undocked_event = UndockedEvent(
            event="Undocked",
            timestamp=datetime.now(),
            StationName="Galileo",
        )

        cls.location_event = LocationEvent(
            event="Location",
            timestamp=datetime.now(),
            StarSystem="Sol",
            SystemAddress=123456789,
            StarPos=[0.0, 0.0, 0.0],
            DistFromStarLS=100.0,
            Docked=True,
            StationName="Galileo",
            StationType="Coriolis",
        )

        cls.fsd_jump_event = FSDJumpEvent(
            event="FSDJump",
            timestamp=datetime.now(),
            StarSystem="Proxima Centauri",
            SystemAddress=987654321,
            StarPos=[1.0, 2.0, 3.0],
            SystemAllegiance="Independent",
            SystemEconomy_Localised="Agriculture",
            SystemSecondEconomy_Localised="Refinery",
            SystemGovernment_Localised="Democracy",
            SystemSecurity_Localised="Low",
            Population=1000000,
            JumpDist=10.5,
            FuelUsed=2.5,
            FuelLevel=45.0,
        )

    def test_should_process_docked_event_and_create_projection(self):
        location_projection = LocationProjection()

        location_projection.process_event(self.docked_event)

        expected_projection = "Player is currently in the Sol system.Player is currently docked at station: Galileo."

        self.assertEqual(expected_projection, location_projection.create_projection())

    def test_should_process_undocked_event_and_create_projection(self):
        location_projection = LocationProjection()

        location_projection.process_event(self.docked_event)
        location_projection.process_event(self.undocked_event)

        expected_projection = "Player is currently in the Sol system.Player is currently un-docked from station: Galileo flying nearby."

        self.assertEqual(expected_projection, location_projection.create_projection())

    def test_should_process_location_event_and_create_projection(self):
        location_projection = LocationProjection()

        location_projection.process_event(self.location_event)

        expected_projection = "Player is currently in the Sol system.Player is currently docked at station: Galileo."

        self.assertEqual(expected_projection, location_projection.create_projection())

    def test_should_process_fsd_jump_event_and_create_projection(self):
        location_projection = LocationProjection()

        location_projection.process_event(self.fsd_jump_event)

        expected_projection = (
            "Player is currently during the FSD jump to system Proxima Centauri."
        )

        self.assertEqual(expected_projection, location_projection.create_projection())

    def test_should_set_fsd_jump_state_to_false_after_docked_and_undocked_event(self):
        location_projection = LocationProjection()

        location_projection.process_event(self.fsd_jump_event)
        location_projection.process_event(self.docked_event)

        expected_projection = "Player is currently in the Sol system.Player is currently docked at station: Galileo."

        self.assertEqual(expected_projection, location_projection.create_projection())
