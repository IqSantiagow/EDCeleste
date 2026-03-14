import logging

from pydantic import BaseModel

from projection.event_projections.fuel_projection import FuelProjection
from projection.event_projections.location_projection import LocationProjection
from projection.event_projections.player_projection import PlayerProjection
from projection.event_projections.projection import Projection
from services.event_bus import EventBus
from services.models.game_events import GameEvent

logger = logging.getLogger(__name__)


class GameState:
    GAME_PROJECTION = "Current game state is: {0}"

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.__game_state_projection = None
        self.__projections: frozenset[Projection] = frozenset(
            [PlayerProjection(), FuelProjection(), LocationProjection()]
        )

        event_bus.subscribe(GameEvent, self.process_event)

    def process_event(self, event: BaseModel):
        for projection in self.__projections:
            projection.process_event(event)

        self.__refresh_state()

    def get_game_state_projection(self) -> str:
        if not self.__game_state_projection:
            logger.warning("Game state projection is empty. Does the game started?")
            return ""
        return self.GAME_PROJECTION.format(self.__game_state_projection)

    def __refresh_state(self):
        self.__game_state_projection = "".join(
            [projection.create_projection() for projection in self.__projections]
        )
        logger.debug(
            "Game state projection refreshed: %s", self.__game_state_projection
        )
