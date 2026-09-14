import logging

from pydantic import BaseModel

from edceleste.projection.event_projections.projection import Projection
from edceleste.services.models.game_events import StatusEvent, StatusFlags

logger = logging.getLogger(__name__)


class ShipProjection(Projection):
    LANDED_PROJECTION = "Ship is currently landed on the surface."
    LANDING_GEAR_DOWN_PROJECTION = "Landing gear is down."
    SHIELDS_DOWN_PROJECTION = "Warning: ship shields are down."
    HARDPOINTS_DEPLOYED_PROJECTION = "Hardpoints are deployed."
    CARGO_SCOOP_DEPLOYED_PROJECTION = "Cargo scoop is deployed."
    SILENT_RUNNING_PROJECTION = "Ship is running silent."
    FLIGHT_ASSIST_OFF_PROJECTION = "Flight assist is off."
    OVERHEATING_PROJECTION = "Warning: ship is overheating."
    IN_DANGER_PROJECTION = "Warning: ship is in danger."
    BEING_INTERDICTED_PROJECTION = "Warning: ship is being interdicted."
    FSD_MASS_LOCKED_PROJECTION = "FSD is mass locked and cannot jump."
    FSD_CHARGING_PROJECTION = "FSD is charging."
    FSD_COOLDOWN_PROJECTION = "FSD is cooling down."

    def __init__(self):
        self.is_landed = False
        self.is_landing_gear_down = False
        # ShieldsUp defaults to True so a "shields down" warning never fires
        # before the first Status.json read actually reports them down.
        self.are_shields_up = True
        self.are_hardpoints_deployed = False
        self.are_lights_on = False
        self.is_cargo_scoop_deployed = False
        self.is_silent_running = False
        self.is_flight_assist_off = False
        self.is_overheating = False
        self.is_in_danger = False
        self.is_being_interdicted = False
        self.is_fsd_mass_locked = False
        self.is_fsd_charging = False
        self.is_fsd_in_cooldown = False
        self.pips_system = 0
        self.pips_engine = 0
        self.pips_weapons = 0
        self.cargo_current = 0.0
        self.legal_status = None

    def process_event(self, event: BaseModel) -> None:
        if isinstance(event, StatusEvent):
            logger.debug("Received ship state event: %s", event)
            self.is_landed = bool(event.Flags & StatusFlags.Landed)
            self.is_landing_gear_down = bool(event.Flags & StatusFlags.LandingGearDown)
            self.are_shields_up = bool(event.Flags & StatusFlags.ShieldsUp)
            self.are_hardpoints_deployed = bool(
                event.Flags & StatusFlags.HardpointsDeployed
            )
            self.are_lights_on = bool(event.Flags & StatusFlags.LightsOn)
            self.is_cargo_scoop_deployed = bool(
                event.Flags & StatusFlags.CargoScoopDeployed
            )
            self.is_silent_running = bool(event.Flags & StatusFlags.SilentRunning)
            self.is_flight_assist_off = bool(event.Flags & StatusFlags.FlightAssistOff)
            self.is_overheating = bool(event.Flags & StatusFlags.Overheating)
            self.is_in_danger = bool(event.Flags & StatusFlags.IsInDanger)
            self.is_being_interdicted = bool(event.Flags & StatusFlags.BeingInterdicted)
            self.is_fsd_mass_locked = bool(event.Flags & StatusFlags.FsdMassLocked)
            self.is_fsd_charging = bool(event.Flags & StatusFlags.FsdCharging)
            self.is_fsd_in_cooldown = bool(event.Flags & StatusFlags.FsdCooldown)
            # Pips are reported by the game in half-pip units (0-8 per bank).
            if len(event.Pips) == 3:
                self.pips_system, self.pips_engine, self.pips_weapons = event.Pips
            if event.Cargo:
                self.cargo_current = event.Cargo
            if event.LegalState:
                self.legal_status = event.LegalState
            return

        logger.debug("Received event but not withing allowed events. Skipping...")

    def create_projection(self) -> str:
        projection_string = ""

        if self.is_landed:
            projection_string += self.LANDED_PROJECTION

        if self.is_landing_gear_down:
            projection_string += self.LANDING_GEAR_DOWN_PROJECTION

        if not self.are_shields_up:
            projection_string += self.SHIELDS_DOWN_PROJECTION

        if self.are_hardpoints_deployed:
            projection_string += self.HARDPOINTS_DEPLOYED_PROJECTION

        if self.is_cargo_scoop_deployed:
            projection_string += self.CARGO_SCOOP_DEPLOYED_PROJECTION

        if self.is_silent_running:
            projection_string += self.SILENT_RUNNING_PROJECTION

        if self.is_flight_assist_off:
            projection_string += self.FLIGHT_ASSIST_OFF_PROJECTION

        if self.is_fsd_mass_locked:
            projection_string += self.FSD_MASS_LOCKED_PROJECTION

        if self.is_fsd_charging:
            projection_string += self.FSD_CHARGING_PROJECTION

        if self.is_fsd_in_cooldown:
            projection_string += self.FSD_COOLDOWN_PROJECTION

        if self.is_overheating:
            projection_string += self.OVERHEATING_PROJECTION

        if self.is_being_interdicted:
            projection_string += self.BEING_INTERDICTED_PROJECTION

        if self.is_in_danger:
            projection_string += self.IN_DANGER_PROJECTION

        return projection_string
