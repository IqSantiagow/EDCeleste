from datetime import datetime
import unittest

from edceleste.projection.event_projections.ship_projection import ShipProjection
from edceleste.services.models.game_events import (
    StatusEvent,
    StatusFlags,
    UnknownCheckedEvent,
)


def _status_event(flags: int = 0, flags2: int = 0, **extra) -> StatusEvent:
    return StatusEvent(
        event="Status", timestamp=datetime.now(), Flags=flags, Flags2=flags2, **extra
    )


class ShipProjectionTest(unittest.TestCase):
    def test_should_create_empty_projection_before_any_status_event(self):
        ship_projection = ShipProjection()

        self.assertEqual("", ship_projection.create_projection())

    def test_should_not_warn_about_shields_before_any_status_event(self):
        # Shields default to "up" so a false "shields down" warning never
        # fires before the first real Status.json read comes in.
        ship_projection = ShipProjection()

        self.assertTrue(ship_projection.are_shields_up)

    def test_should_report_shields_down(self):
        ship_projection = ShipProjection()

        ship_projection.process_event(_status_event(flags=0))

        self.assertFalse(ship_projection.are_shields_up)
        self.assertEqual(
            "Warning: ship shields are down.", ship_projection.create_projection()
        )

    def test_should_clear_shields_down_warning_once_shields_are_up(self):
        ship_projection = ShipProjection()

        ship_projection.process_event(_status_event(flags=0))
        ship_projection.process_event(_status_event(flags=StatusFlags.ShieldsUp))

        self.assertEqual("", ship_projection.create_projection())

    def test_should_report_landed_and_landing_gear_down(self):
        ship_projection = ShipProjection()

        ship_projection.process_event(
            _status_event(
                flags=StatusFlags.ShieldsUp
                | StatusFlags.Landed
                | StatusFlags.LandingGearDown
            )
        )

        expected_projection = (
            "Ship is currently landed on the surface.Landing gear is down."
        )

        self.assertEqual(expected_projection, ship_projection.create_projection())

    def test_should_report_hardpoints_and_cargo_scoop_deployed(self):
        ship_projection = ShipProjection()

        ship_projection.process_event(
            _status_event(
                flags=StatusFlags.ShieldsUp
                | StatusFlags.HardpointsDeployed
                | StatusFlags.CargoScoopDeployed
            )
        )

        expected_projection = "Hardpoints are deployed.Cargo scoop is deployed."

        self.assertEqual(expected_projection, ship_projection.create_projection())

    def test_should_report_silent_running_and_flight_assist_off(self):
        ship_projection = ShipProjection()

        ship_projection.process_event(
            _status_event(
                flags=StatusFlags.ShieldsUp
                | StatusFlags.SilentRunning
                | StatusFlags.FlightAssistOff
            )
        )

        expected_projection = "Ship is running silent.Flight assist is off."

        self.assertEqual(expected_projection, ship_projection.create_projection())

    def test_should_report_fsd_mass_locked_charging_and_cooldown(self):
        ship_projection = ShipProjection()

        ship_projection.process_event(
            _status_event(
                flags=StatusFlags.ShieldsUp
                | StatusFlags.FsdMassLocked
                | StatusFlags.FsdCharging
                | StatusFlags.FsdCooldown
            )
        )

        expected_projection = (
            "FSD is mass locked and cannot jump.FSD is charging.FSD is cooling down."
        )

        self.assertEqual(expected_projection, ship_projection.create_projection())

    def test_should_report_overheating_interdiction_and_danger(self):
        ship_projection = ShipProjection()

        ship_projection.process_event(
            _status_event(
                flags=StatusFlags.ShieldsUp
                | StatusFlags.Overheating
                | StatusFlags.BeingInterdicted
                | StatusFlags.IsInDanger
            )
        )

        expected_projection = (
            "Warning: ship is overheating."
            "Warning: ship is being interdicted."
            "Warning: ship is in danger."
        )

        self.assertEqual(expected_projection, ship_projection.create_projection())

    def test_should_track_pips_cargo_and_legal_status_from_status_event(self):
        ship_projection = ShipProjection()

        ship_projection.process_event(
            _status_event(Pips=[4, 8, 0], Cargo=12.0, LegalState="Wanted")
        )

        self.assertEqual(ship_projection.pips_system, 4)
        self.assertEqual(ship_projection.pips_engine, 8)
        self.assertEqual(ship_projection.pips_weapons, 0)
        self.assertEqual(ship_projection.cargo_current, 12.0)
        self.assertEqual(ship_projection.legal_status, "Wanted")

    def test_should_update_cargo_when_hold_becomes_empty(self):
        # Cargo 0.0 means an empty hold, not a missing value, so it must
        # replace the last known cargo instead of being skipped.
        ship_projection = ShipProjection()

        ship_projection.process_event(_status_event(Cargo=12.0))
        ship_projection.process_event(_status_event(Cargo=0.0))

        self.assertEqual(ship_projection.cargo_current, 0.0)

    def test_should_keep_last_known_legal_status_when_status_event_omits_it(self):
        ship_projection = ShipProjection()

        ship_projection.process_event(_status_event(LegalState="Clean"))
        ship_projection.process_event(_status_event())

        self.assertEqual(ship_projection.legal_status, "Clean")

    def test_should_ignore_unrelated_events(self):
        ship_projection = ShipProjection()

        ship_projection.process_event(
            UnknownCheckedEvent(event="SomeEvent", timestamp=datetime.now())
        )

        self.assertEqual("", ship_projection.create_projection())


if __name__ == "__main__":
    unittest.main()
