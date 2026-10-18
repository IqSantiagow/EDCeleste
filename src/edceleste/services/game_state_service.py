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
from edceleste.projection.event_projections.market_projection import MarketProjection
from edceleste.projection.event_projections.player_projection import PlayerProjection
from edceleste.projection.event_projections.projection import Projection
from edceleste.projection.event_projections.ship_projection import ShipProjection
from edceleste.services.event_bus import EventBus
from edceleste.services.models.game_events import (
    DockedEvent,
    GameEvent,
    LocationEvent,
    MarketEvent,
    NonJournalFileEvent,
    UndockedEvent,
)
from edceleste.services.models.game_state_changed_event import GameStateChangedEvent
from edceleste.services.models.startup_loading_finished_event import (
    StartupLoadingFinishedEvent,
)
from edceleste.services.models.market_stats import MarketSnapshot
from edceleste.services.models.game_stats import (
    FlightDriveStats,
    GameStatsSnapshot,
    NavigationStats,
    PlayerStats,
    ShipStats,
)

logger = logging.getLogger(__name__)


class GameStateService:
    # Only these can change the station market card. Status.json is deliberately
    # left out - it arrives every second and would rebuild the whole commodity
    # table that often, losing the scroll position while the player reads it.
    MARKET_CARD_EVENTS = (MarketEvent, DockedEvent, UndockedEvent, LocationEvent)

    def __init__(self, event_bus: EventBus) -> None:
        """Builds one of every projection, all empty, and subscribes to the
        event bus. Nothing is known about the game until the first event. The
        game state text starts empty, and __has_loaded_any_event starts False:
        it tells later if the startup loading brought at least one event.

        Subscriptions:
        - GameEvent -> process_event
        - StartupLoadingFinishedEvent -> publish_game_state_after_startup_loading
        """
        self.event_bus = event_bus
        self.__game_state_projection = ""
        self.__has_loaded_any_event = False
        self.__player_projection = PlayerProjection()
        self.__fuel_projection = FuelProjection()
        self.__location_projection = LocationProjection()
        self.__ship_projection = ShipProjection()
        self.__loadout_projection = LoadoutProjection()
        self.__market_projection = MarketProjection()
        # The order of the parts in the game state text. "Who and where" first,
        # it is the context for everything else.
        self.__projections: list[Projection] = [
            self.__player_projection,
            self.__location_projection,
            self.__ship_projection,
            self.__fuel_projection,
            self.__loadout_projection,
            self.__market_projection,
        ]
        self.__journal_queue_watchers: list[asyncio.Queue[GameEvent]] = []
        self.__status_queue_watchers: list[
            asyncio.Queue[GameEvent | StartupLoadingFinishedEvent]
        ] = []
        self.__market_queue_watchers: list[
            asyncio.Queue[GameEvent | StartupLoadingFinishedEvent]
        ] = []

        event_bus.subscribe(GameEvent, self.process_event)
        event_bus.subscribe(
            StartupLoadingFinishedEvent, self.publish_game_state_after_startup_loading
        )

    async def process_event(self, event: GameEvent) -> None:
        """Runs for every game event on the event bus, live or from the
        startup loading. Returns nothing.

        1. Gives the event to every projection, each keeps its part of the
           game state.
        2. An event of the startup loading (is_startup_loading) stops here,
           after it has remembered that the loading brought an event.
           Thousands of old journal lines must not wake the UI or rebuild the
           text each time, publish_game_state_after_startup_loading does that
           once, when the loading is finished.
        3. Wakes up the UI streams that wait on it:
           - journal events -> stream_journal_events,
           - side file events (Status.json, Market.json) -> stream_game_stats,
           - market card events -> stream_market.
        4. Rebuilds the game state text from all projections.
        5. Publishes GameStateChangedEvent with that text, so LLMService has it
           for the next prompt.
        """
        for projection in self.__projections:
            projection.process_event(event)

        if event.is_startup_loading:
            self.__has_loaded_any_event = True
            return

        # All side files event should not be consumed here, it goes to front. Anyway
        # stats refresh is in stream_game_stats method so simple trick as mixing works
        if not isinstance(event, NonJournalFileEvent):
            for journal_watcher in self.__journal_queue_watchers:
                journal_watcher.put_nowait(event)
        else:
            for status_watcher in self.__status_queue_watchers:
                status_watcher.put_nowait(event)

        # Separate branch on purpose: the station card is fed by both a side
        # file (Market.json) and journal lines (Docked/Undocked/Location).
        if isinstance(event, self.MARKET_CARD_EVENTS):
            for market_watcher in self.__market_queue_watchers:
                market_watcher.put_nowait(event)

        await self.__rebuild_game_state_text_and_publish_it()

    async def publish_game_state_after_startup_loading(
        self, finished_event: StartupLoadingFinishedEvent
    ) -> None:
        """Runs every time a startup loading ends, that is when the watcher has
        read everything the game wrote before it started: once when the app
        starts, and again when the watcher is restarted (the settings change).
        The projections already hold that state, but nobody was told, because
        process_event stays silent during the loading. Returns nothing.

        1. Wakes up the stats stream and the market stream once, so a dashboard
           that opened before the loading ended draws the loaded state.
           finished_event is only the item put in their queues, its content
           is not used.
        2. Rebuilds the game state text and publishes GameStateChangedEvent,
           so LLMService can answer "where am I?" at once.
        The live journal stream gets nothing: old journal lines are not shown.

        When no loading event has come yet (an empty journal and no side
        files), it does nothing. The game state stays unknown, as it was
        before, until the first live event. __has_loaded_any_event, set by
        process_event, tells that, and once it is set it stays set.
        """
        if not self.__has_loaded_any_event:
            return

        for watcher in self.__status_queue_watchers + self.__market_queue_watchers:
            watcher.put_nowait(finished_event)

        await self.__rebuild_game_state_text_and_publish_it()

    async def __rebuild_game_state_text_and_publish_it(self) -> None:
        """Rebuilds the game state text from all projections, stores it and
        publishes it as GameStateChangedEvent (the event carries only that
        text), so LLMService has it for the next prompt. Used after every live
        event and after a startup loading. It publishes also when the text did
        not change, and waits until the subscribers have handled the event."""
        self.__rebuild_game_state_text()

        await self.event_bus.publish(
            GameStateChangedEvent(game_state=self.get_game_state_projection())
        )

    def get_game_state_projection(self) -> str:
        """The game state text for the LLM, as built by the last event: one
        line per projection, without any heading (LLMService adds it). Does
        not rebuild anything. An empty string means no live event came yet (or
        every projection is empty), and then every call logs a warning. During
        a startup loading the text stays as it was, empty at the app start,
        until publish_game_state_after_startup_loading rebuilds it."""
        if not self.__game_state_projection:
            logger.warning("Game state projection is empty. Does the game started?")
            return ""
        return self.__game_state_projection

    def __rebuild_game_state_text(self) -> None:
        """Asks every projection for its text and puts each one on its own
        line, in the order of the projections list: commander, location, ship,
        fuel, hull, market. A projection with nothing to say is left out, so
        there are no empty lines. Returns nothing: the result is stored and
        get_game_state_projection hands it out until the next rebuild."""
        projection_texts = [
            projection.create_projection() for projection in self.__projections
        ]
        self.__game_state_projection = "\n".join(
            text for text in projection_texts if text
        )
        logger.debug(
            "Game state projection refreshed: %s", self.__game_state_projection
        )

    def __build_game_stats_snapshot(self) -> GameStatsSnapshot:
        """Copies the current values out of the projections for the dashboard
        cards. A value the game has not sent yet becomes "" or 0 for the fields
        that cannot be None."""
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
        """Never ends on its own. Yields the current stats right away, then a
        fresh snapshot after every live Status.json or Market.json event, and
        once when a startup loading ends. Journal events do not wake it, but
        Status.json comes often, so the stats catch up soon. The events of the
        startup loading itself do not wake it either.

        Every caller gets its own queue, removed again when the caller stops
        iterating.
        """
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
        """Never ends on its own. Yields every journal event that comes after
        the caller started iterating, older events are not replayed. Side file
        events (Status.json, Market.json) are left out, and so are the events
        of the startup loading: old journal lines never reach this stream.

        Every caller gets its own queue, removed again when the caller stops
        iterating.
        """
        queue: asyncio.Queue = asyncio.Queue()
        self.__journal_queue_watchers.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self.__journal_queue_watchers.remove(queue)

    def __build_market_snapshot(self) -> MarketSnapshot:
        """Copies the station market card values out of the market projection.
        The ship counts as docked while the projection knows a docked market
        id."""
        market = self.__market_projection
        return MarketSnapshot(
            station_name=market.station_name or "",
            is_docked=market.docked_market_id is not None,
            has_commodities_market=market.has_commodities_market,
            is_market_data_current=market.is_market_data_current(),
            commodities=tuple(market.commodities),
        )

    async def stream_market(self) -> AsyncGenerator[MarketSnapshot, None]:
        """Never ends on its own. Yields the current station market right away,
        then a fresh snapshot only after a live MARKET_CARD_EVENTS event, and
        once when a startup loading ends, so the commodity table is not
        rebuilt every second by Status.json.

        Every caller gets its own queue, removed again when the caller stops
        iterating.
        """
        queue: asyncio.Queue = asyncio.Queue()
        self.__market_queue_watchers.append(queue)
        try:
            yield self.__build_market_snapshot()
            while True:
                await queue.get()
                yield self.__build_market_snapshot()
        finally:
            self.__market_queue_watchers.remove(queue)
