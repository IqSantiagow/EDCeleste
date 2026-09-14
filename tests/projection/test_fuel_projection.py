from datetime import datetime
import unittest

from edceleste.projection.event_projections.fuel_projection import FuelProjection
from edceleste.services.models.game_events import (
    FuelScoopEvent,
    LoadedGameEvent,
    FSDJumpEvent,
    ReservoirReplenishedEvent,
    RefuelAllEvent,
    StatusEvent,
    StatusFlags,
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
        cls.status_event_scooping_fuel = StatusEvent(
            event="Status",
            timestamp=datetime.now(),
            Flags=StatusFlags.ScoopingFuel,
            Flags2=0,
        )
        cls.status_event_not_scooping_fuel = StatusEvent(
            event="Status",
            timestamp=datetime.now(),
            Flags=StatusFlags.Supercruise,
            Flags2=0,
        )
        cls.status_event_low_fuel = StatusEvent(
            event="Status",
            timestamp=datetime.now(),
            Flags=StatusFlags.LowFuel,
            Flags2=0,
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

    def test_should_clamp_to_capacity_on_refuel_all_when_capacity_known(self):
        fuel_projection = FuelProjection()

        overshooting_refuel = RefuelAllEvent(
            event="RefuelAll",
            timestamp=datetime.now(),
            Cost=200,
            Amount=10.0,
        )

        fuel_projection.process_event(self.loaded_game_event)
        fuel_projection.process_event(overshooting_refuel)

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

    def test_should_set_scooping_fuel_from_status_event(self):
        fuel_projection = FuelProjection()

        fuel_projection.process_event(self.status_event_scooping_fuel)

        self.assertTrue(fuel_projection.is_scooping_fuel)

    def test_should_include_scooping_fuel_in_projection(self):
        fuel_projection = FuelProjection()

        fuel_projection.process_event(self.fuel_scoop_event)
        fuel_projection.process_event(self.status_event_scooping_fuel)

        expected_projection = (
            "Current fuel level is: {0}".format(self.fuel_scoop_event.Total)
            + "Player is currently scooping fuel from a star."
        )

        self.assertEqual(expected_projection, fuel_projection.create_projection())

    def test_should_clear_scooping_fuel_when_status_event_flag_unset(self):
        fuel_projection = FuelProjection()

        fuel_projection.process_event(self.status_event_scooping_fuel)
        fuel_projection.process_event(self.status_event_not_scooping_fuel)

        self.assertFalse(fuel_projection.is_scooping_fuel)

    def test_should_set_low_fuel_from_status_event(self):
        fuel_projection = FuelProjection()

        fuel_projection.process_event(self.status_event_low_fuel)

        self.assertTrue(fuel_projection.is_low_fuel)

    def test_should_include_low_fuel_warning_in_projection(self):
        fuel_projection = FuelProjection()

        fuel_projection.process_event(self.fuel_scoop_event)
        fuel_projection.process_event(self.status_event_low_fuel)

        expected_projection = (
            "Current fuel level is: {0}".format(self.fuel_scoop_event.Total)
            + "Warning: fuel is low."
        )

        self.assertEqual(expected_projection, fuel_projection.create_projection())

    def test_should_clear_low_fuel_when_status_event_flag_unset(self):
        fuel_projection = FuelProjection()

        fuel_projection.process_event(self.status_event_low_fuel)
        fuel_projection.process_event(self.status_event_not_scooping_fuel)

        self.assertFalse(fuel_projection.is_low_fuel)

    def test_should_set_fuel_level_and_reservoir_from_status_event_fuel(self):
        fuel_projection = FuelProjection()

        status_event_with_fuel = StatusEvent(
            event="Status",
            timestamp=datetime.now(),
            Flags=0,
            Flags2=0,
            Fuel={"FuelMain": 12.5, "FuelReservoir": 0.4},
        )

        fuel_projection.process_event(status_event_with_fuel)

        self.assertEqual(fuel_projection.fuel_level, 12.5)
        self.assertEqual(fuel_projection.fuel_reservoir, 0.4)

    def test_should_keep_last_known_fuel_when_status_event_omits_it(self):
        fuel_projection = FuelProjection()

        fuel_projection.process_event(self.reservoir_replenished_event)
        fuel_projection.process_event(self.status_event_not_scooping_fuel)

        self.assertEqual(
            fuel_projection.fuel_reservoir,
            self.reservoir_replenished_event.FuelReservoir,
        )
