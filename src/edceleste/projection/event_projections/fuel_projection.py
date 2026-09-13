import logging

from pydantic import BaseModel

from edceleste.projection.event_projections.projection import Projection
from edceleste.services.models.game_events import (
    FSDJumpEvent,
    LoadedGameEvent,
    FuelScoopEvent,
    ReservoirReplenishedEvent,
    RefuelAllEvent,
    StatusEvent,
    StatusFlags,
)

logger = logging.getLogger(__name__)


class FuelProjection(Projection):
    PROJECTION_STRING = "Current fuel level is: {0}"

    SCOOPING_FUEL_PROJECTION = "Player is currently scooping fuel from a star."

    LOW_FUEL_PROJECTION = "Warning: fuel is low."

    def __init__(self):
        self.fuel_level = 0.0
        self.fuel_capacity = 0.0
        self.is_scooping_fuel = False
        self.is_low_fuel = False

    def process_event(self, event: BaseModel):
        if isinstance(event, FSDJumpEvent):
            logger.debug("Received fuel event: %s", event)
            self.fuel_level = event.FuelLevel
            return

        if isinstance(event, LoadedGameEvent):
            logger.debug("Received fuel event: %s", event)
            self.fuel_level = event.FuelLevel
            self.fuel_capacity = event.FuelCapacity
            return

        if isinstance(event, FuelScoopEvent):
            logger.debug("Received fuel event: %s", event)
            # Verified against real journals: Total is the main tank level after
            # the scoop (clamped to FuelCapacity), while Scooped is only the
            # amount gained since the previous FuelScoop event.
            self.fuel_level = event.Total
            return

        if isinstance(event, ReservoirReplenishedEvent):
            logger.debug("Received fuel event: %s", event)
            self.fuel_level = event.FuelMain
            return

        if isinstance(event, RefuelAllEvent):
            logger.debug("Received fuel event: %s", event)
            # RefuelAll tops the main tank off. Add the purchased amount and, when
            # the capacity is known, clamp to it so a missed LoadGame or drifted
            # level can never push the tracked value past the real tank size.
            self.fuel_level += event.Amount
            if self.fuel_capacity:
                self.fuel_level = min(self.fuel_level, self.fuel_capacity)
            return

        if isinstance(event, StatusEvent):
            logger.debug("Received fuel event: %s", event)
            self.is_scooping_fuel = bool(event.Flags & StatusFlags.ScoopingFuel)
            self.is_low_fuel = bool(event.Flags & StatusFlags.LowFuel)
            return

        logger.debug("Received event but not withing allowed events. Skipping...")

    def create_projection(self) -> str:
        if self.fuel_level == 0.0:
            logger.warning("Fuel level is at 0. Does the game started?")

        projection_string = self.PROJECTION_STRING.format(self.fuel_level)

        if self.is_scooping_fuel:
            projection_string += self.SCOOPING_FUEL_PROJECTION

        if self.is_low_fuel:
            projection_string += self.LOW_FUEL_PROJECTION

        return projection_string
