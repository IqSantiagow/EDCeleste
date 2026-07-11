import asyncio
from collections.abc import AsyncGenerator
import logging
import threading

from projection.event_projections.fuel_projection import FuelProjection
from projection.event_projections.location_projection import LocationProjection
from projection.event_projections.player_projection import PlayerProjection
from projection.event_projections.projection import Projection
from services.event_bus import EventBus
from services.models.dashboard_stats_snapshot import DashboardStatsSnapshot
from services.models.game_events import GameEvent

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
        self.__queue_watchers_lock = threading.Lock()
        self.__event_loop: asyncio.AbstractEventLoop | None = None

        event_bus.subscribe(GameEvent, self.process_event)

    async def process_event(self, event: GameEvent):
        for projection in self.__projections:
            projection.process_event(event)

        with self.__queue_watchers_lock:
            watchers = list(self.__queue_watchers)

        for watcher in watchers:
            if self.__event_loop is None:
                watcher.put_nowait(event)
            else:
                self.__event_loop.call_soon_threadsafe(watcher.put_nowait, event)

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

    def get_dashboard_stats(self) -> DashboardStatsSnapshot:
        return DashboardStatsSnapshot(
            location=self.__location_projection.current_star_system or "",
            fuel=str(self.__fuel_projection.fuel_level),
            ship=self.__player_projection.player_ship or "",
        )

    async def stream_dashboard_stats(
        self,
    ) -> AsyncGenerator[DashboardStatsSnapshot, None]:
        queue: asyncio.Queue = asyncio.Queue()
        self.__event_loop = asyncio.get_running_loop()
        with self.__queue_watchers_lock:
            self.__queue_watchers.append(queue)

        try:
            while True:
                await queue.get()
                yield self.get_dashboard_stats()
        finally:
            with self.__queue_watchers_lock:
                self.__queue_watchers.remove(queue)

    async def stream_journal_events(self) -> AsyncGenerator[GameEvent, None]:
        queue: asyncio.Queue = asyncio.Queue()
        self.__event_loop = asyncio.get_running_loop()
        with self.__queue_watchers_lock:
            self.__queue_watchers.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            with self.__queue_watchers_lock:
                self.__queue_watchers.remove(queue)
