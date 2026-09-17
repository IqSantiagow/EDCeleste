import asyncio
from collections.abc import AsyncGenerator
import logging

from edceleste.projection.event_projections.fuel_projection import FuelProjection
from edceleste.projection.event_projections.loadout_projection import (
    LoadoutProjection,
)
from edceleste.projection.event_projections.location_projection import (
    LocationProjection,
)
from edceleste.projection.event_projections.player_projection import PlayerProjection
from edceleste.projection.event_projections.projection import Projection
from edceleste.projection.event_projections.ship_projection import ShipProjection
from edceleste.services.event_bus import EventBus
from edceleste.services.models.game_events import GameEvent, NonJournalFileEvent
from edceleste.services.models.game_state_changed_event import GameStateChangedEvent
from edceleste.services.models.game_stats import (
    FlightDriveStats,
    GameStatsSnapshot,
    NavigationStats,
    PlayerStats,
    ShipStats,
)

logger = logging.getLogger(__name__)


class GameStateService:
    GAME_PROJECTION = "Current game state is: {0}"

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.__game_state_projection = None
        self.__player_projection = PlayerProjection()
        self.__fuel_projection = FuelProjection()
        self.__location_projection = LocationProjection()
        self.__ship_projection = ShipProjection()
        self.__loadout_projection = LoadoutProjection()
        self.__projections: frozenset[Projection] = frozenset(
            [
                self.__player_projection,
                self.__fuel_projection,
                self.__location_projection,
                self.__ship_projection,
                self.__loadout_projection,
            ]
        )
        self.__journal_queue_watchers: list[asyncio.Queue[GameEvent]] = []
        self.__status_queue_watchers: list[asyncio.Queue[GameEvent]] = []

        event_bus.subscribe(GameEvent, self.process_event)

    async def process_event(self, event: GameEvent):
        for projection in self.__projections:
            projection.process_event(event)

        # All side files event should not be consumed here, it goes to front. Anyway
        # stats refresh is in stream_game_stats method so simple trick as mixing works
        if not isinstance(event, NonJournalFileEvent):
            for watcher in self.__journal_queue_watchers:
                watcher.put_nowait(event)
        else:
            for watcher in self.__status_queue_watchers:
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
            navigation=NavigationStats(
                current_star_system=self.__location_projection.current_star_system
                or "",
                system_security_level=self.__location_projection.system_security_level
                or "",
                system_allegiance=self.__location_projection.system_allegiance or "",
                system_government=self.__location_projection.system_government or "",
                system_economy=self.__location_projection.system_economy or "",
                system_second_economy=self.__location_projection.system_second_economy
                or "",
                system_population=self.__location_projection.system_population or 0,
                current_body=self.__location_projection.current_body or "",
                is_in_supercruise=self.__location_projection.is_in_supercruise,
                route_next_star_system=self.__location_projection.route_next_star_system
                or "",
                route_remaining_jumps=self.__location_projection.route_remaining_jumps
                or 0,
            ),
            flight_drive=FlightDriveStats(
                fuel_level=self.__fuel_projection.fuel_level,
                fuel_capacity=self.__fuel_projection.fuel_capacity,
                fuel_reservoir=self.__fuel_projection.fuel_reservoir,
                is_scooping_fuel=self.__fuel_projection.is_scooping_fuel,
                max_jump_range=self.__loadout_projection.max_jump_range,
                fsd_module_item=self.__loadout_projection.fsd_module_item or "",
            ),
            ship=ShipStats(
                is_landing_gear_down=self.__ship_projection.is_landing_gear_down,
                are_hardpoints_deployed=self.__ship_projection.are_hardpoints_deployed,
                are_lights_on=self.__ship_projection.are_lights_on,
                are_shields_up=self.__ship_projection.are_shields_up,
                pips_system=self.__ship_projection.pips_system,
                pips_engine=self.__ship_projection.pips_engine,
                pips_weapons=self.__ship_projection.pips_weapons,
                cargo_current=self.__ship_projection.cargo_current,
                cargo_capacity=self.__loadout_projection.cargo_capacity,
                legal_status=self.__ship_projection.legal_status or "",
                hull_health=self.__loadout_projection.hull_health,
                unladen_mass=self.__loadout_projection.unladen_mass,
                rebuy_cost=self.__loadout_projection.rebuy_cost,
                are_all_modules_healthy=self.__loadout_projection.are_all_modules_healthy,
            ),
        )

    async def stream_game_stats(
        self,
    ) -> AsyncGenerator[GameStatsSnapshot, None]:
        queue: asyncio.Queue = asyncio.Queue()
        self.__status_queue_watchers.append(queue)

        try:
            yield self.__build_game_stats_snapshot()
            while True:
                await queue.get()
                yield self.__build_game_stats_snapshot()
        finally:
            self.__status_queue_watchers.remove(queue)

    async def stream_journal_events(self) -> AsyncGenerator[GameEvent, None]:
        queue: asyncio.Queue = asyncio.Queue()
        self.__journal_queue_watchers.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self.__journal_queue_watchers.remove(queue)
