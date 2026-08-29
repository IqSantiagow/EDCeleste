import logging

from pydantic import BaseModel

from edceleste.projection.event_projections.projection import Projection
from edceleste.services.models.game_events import (
    FSDJumpEvent,
    LoadedGameEvent,
    FuelScoopEvent,
    ReservoirReplenishedEvent,
    RefuelAllEvent,
)

logger = logging.getLogger(__name__)


class FuelProjection(Projection):
    PROJECTION_STRING = "Current fuel level is: {0}"

    def __init__(self):
        self.fuel_level = 0.0
        self.fuel_capacity = 0.0

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

        logger.debug("Received event but not withing allowed events. Skipping...")

    def create_projection(self) -> str:
        if self.fuel_level == 0.0:
            logger.warning("Fuel level is at 0. Does the game started?")
        return self.PROJECTION_STRING.format(self.fuel_level)
