import logging

from pydantic import BaseModel

from projection.event_projections.projection import Projection
from services.models.game_events import LoadedGameEvent

logger = logging.getLogger(__name__)


class PlayerProjection(Projection):
    PROJECTION_STRING = (
        "Commander name is {0}.Commander has {1} of credits.Commander ship is {2}."
    )

    def __init__(self):
        self.player_name = None
        self.player_credits = 0
        self.player_ship = None

    def process_event(self, event: BaseModel):
        if isinstance(event, LoadedGameEvent):
            logger.debug("Received player state event: %s", event)
            self.player_name = event.Commander
            self.player_credits = event.Credits
            self.player_ship = event.Ship
            return

        logger.debug("Received event but not withing allowed events. Skipping...")

    def create_projection(self) -> str:
        if not self.player_name or not self.player_ship:
            logger.warning("Player state not set. Does the game started?")
        return self.PROJECTION_STRING.format(
            self.player_name, self.player_credits, self.player_ship
        )
