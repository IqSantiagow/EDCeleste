import logging

from pydantic import BaseModel

from services.models.game_events import FSDJumpEvent, LoadedGameEvent, FuelScoopEvent

logger = logging.getLogger(__name__)


class FuelProjection:
    PROJECTION_STRING = "Current fuel level is: {0}"

    def __init__(self):
        self.fuel_level = 0.0

    def process_event(self, event: BaseModel):

        if isinstance(event, FSDJumpEvent):
            logger.debug("Received fuel event: %s", event)
            self.fuel_level = event.FuelLevel
            return

        if isinstance(event, LoadedGameEvent):
            logger.debug("Received fuel event: %s", event)
            self.fuel_level = event.FuelLevel
            return

        if isinstance(event, FuelScoopEvent):
            logger.debug("Received fuel event: %s", event)
            # TODO: Check in game if its total fuel or total scooped
            self.fuel_level = event.Total
            return
        logger.debug("Received event but not withing allowed events. Skipping...")

    def create_projection(self) -> str:
        return self.PROJECTION_STRING.format(self.fuel_level)
