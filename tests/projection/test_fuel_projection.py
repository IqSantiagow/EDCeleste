from datetime import datetime
import unittest

from projection.event_projections.fuel_projection import FuelProjection
from services.models.game_events import (
    FuelScoopEvent,
    LoadedGameEvent,
    FSDJumpEvent,
    ReservoirReplenishedEvent,
    RefuelAllEvent,
)


class FuelProjectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fuel_scoop_event = FuelScoopEvent(
            event="FuelScoop", timestamp=datetime.now(), Scooped=1.0, Total=1.0
        )
        cls.loaded_game_event = LoadedGameEvent(
            event="LoadGame",
            timestamp=datetime.now(),
            Commander="TestCommander",
            FID="F123456",
            Horizons=True,
            Odyssey=False,
            Ship="Sidewinder",
            ShipID=1,
            ShipIdent="TS-001",
            ShipName="Test Ship",
            StartLanded=False,
            StartDead=False,
            GameMode="Solo",
            Group="",
            Credits=1000000,
            Loan=0,
            FuelLevel=1.0,
            FuelCapacity=4.0,
        )
        cls.fsd_jump_event = FSDJumpEvent(
            event="FSDJump",
            timestamp=datetime.now(),
            StarSystem="Test System",
            SystemAddress=123456789,
            StarPos=[0.0, 0.0, 0.0],
            SystemAllegiance="Independent",
            SystemEconomy_Localised="High Tech",
            SystemSecondEconomy_Localised="Industrial",
            SystemGovernment_Localised="Democracy",
            SystemSecurity_Localised="Low",
            Population=1000000,
            JumpDist=10.0,
            FuelUsed=1.0,
            FuelLevel=1.0,
            Factions=[],
            SystemFaction=None,
        )
        cls.reservoir_replenished_event = ReservoirReplenishedEvent(
            event="ReservoirReplenished",
            timestamp=datetime.now(),
            FuelMain=15.5,
            FuelReservoir=0.5,
        )
        cls.refuel_all_event = RefuelAllEvent(
            event="RefuelAll",
            timestamp=datetime.now(),
            Cost=50,
            Amount=1.5,
        )

    def test_should_process_to_event_and_set_fuel_level(self):
        fuel_projection = FuelProjection()

        fuel_projection.process_event(self.fuel_scoop_event)
        self.assertEqual(fuel_projection.fuel_level, self.fuel_scoop_event.Total)

        fuel_projection.process_event(self.loaded_game_event)
        self.assertEqual(fuel_projection.fuel_level, self.loaded_game_event.FuelLevel)

        fuel_projection.process_event(self.fsd_jump_event)
        self.assertEqual(fuel_projection.fuel_level, self.fsd_jump_event.FuelLevel)

    def test_should_set_fuel_level_from_reservoir_replenished_event(self):
        fuel_projection = FuelProjection()

        fuel_projection.process_event(self.reservoir_replenished_event)

        self.assertEqual(
            fuel_projection.fuel_level, self.reservoir_replenished_event.FuelMain
        )

    def test_should_fill_to_capacity_on_refuel_all_when_capacity_known(self):
        fuel_projection = FuelProjection()

        fuel_projection.process_event(self.loaded_game_event)
        fuel_projection.process_event(self.refuel_all_event)

        self.assertEqual(
            fuel_projection.fuel_level, self.loaded_game_event.FuelCapacity
        )

    def test_should_add_amount_on_refuel_all_when_capacity_unknown(self):
        fuel_projection = FuelProjection()

        fuel_projection.process_event(self.refuel_all_event)

        self.assertEqual(fuel_projection.fuel_level, self.refuel_all_event.Amount)

    def test_should_create_projection(self):
        fuel_projection = FuelProjection()

        event = self.fuel_scoop_event

        fuel_projection.process_event(event)

        expected_projection = "Current fuel level is: {0}".format(event.Total)

        self.assertEqual(expected_projection, fuel_projection.create_projection())
