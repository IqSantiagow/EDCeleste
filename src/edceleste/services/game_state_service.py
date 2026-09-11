import asyncio
from collections.abc import AsyncGenerator
import logging

from edceleste.projection.event_projections.fuel_projection import FuelProjection
from edceleste.projection.event_projections.location_projection import (
    LocationProjection,
)
from edceleste.projection.event_projections.player_projection import PlayerProjection
from edceleste.projection.event_projections.projection import Projection
from edceleste.services.event_bus import EventBus
from edceleste.services.models.game_events import GameEvent
from edceleste.services.models.game_state_changed_event import GameStateChangedEvent
from edceleste.services.models.game_stats import GameStatsSnapshot, PlayerStats

logger = logging.getLogger(__name__)


class GameStateService:
    GAME_PROJECTION = "Current game state is: {0}"

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.__game_state_projection = None
        self.__player_projection = PlayerProjection()
        self.__fuel_projection = FuelProjection()
        self.__location_projection = LocationProjection()
        self.__projections: frozenset[Projection] = frozenset(
            [
                self.__player_projection,
                self.__fuel_projection,
                self.__location_projection,
            ]
        )
        self.__queue_watchers: list[asyncio.Queue[GameEvent]] = []

        event_bus.subscribe(GameEvent, self.process_event)

    async def process_event(self, event: GameEvent):
        for projection in self.__projections:
            projection.process_event(event)

        for watcher in self.__queue_watchers:
            watcher.put_nowait(event)

        self.__refresh_state()

        await self.event_bus.publish(
            GameStateChangedEvent(game_state=self.get_game_state_projection())
        )

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

    def __build_game_stats_snapshot(self) -> GameStatsSnapshot:
        return GameStatsSnapshot(
            player=PlayerStats(
                name=self.__player_projection.player_name or "",
                ship=self.__player_projection.player_ship or "",
                credits=self.__player_projection.player_credits,
            ),
        )

    async def stream_game_stats(
        self,
    ) -> AsyncGenerator[GameStatsSnapshot, None]:
        queue: asyncio.Queue = asyncio.Queue()
        self.__queue_watchers.append(queue)

        try:
            while True:
                await queue.get()
                yield self.__build_game_stats_snapshot()
        finally:
            self.__queue_watchers.remove(queue)

    async def stream_journal_events(self) -> AsyncGenerator[GameEvent, None]:
        queue: asyncio.Queue = asyncio.Queue()
        self.__queue_watchers.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self.__queue_watchers.remove(queue)
