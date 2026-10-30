import asyncio
from datetime import datetime
import unittest
from unittest.mock import AsyncMock, Mock

from edceleste.services.event_bus import EventBus
from edceleste.services.game_state_service import GameStateService
from edceleste.services.models.game_events import (
    GameEvent,
    LoadedGameEvent,
    StatusEvent,
    StatusFlags,
    StatusFuelModel,
)
from edceleste.services.models.game_state_changed_event import GameStateChangedEvent
from edceleste.services.models.new_game_session_event import NewGameSessionEvent
from edceleste.services.models.startup_loading_finished_event import (
    StartupLoadingFinishedEvent,
)
from tests.projection.test_cargo_projection import make_cargo_event
from tests.projection.test_market_projection import (
    make_docked_event,
    make_market_event,
)
from tests.projection.test_modules_projection import make_module_info_event
from tests.projection.test_route_projection import make_nav_route_event


def _loaded_game_event(**overrides) -> LoadedGameEvent:
    defaults = dict(
        event="LoadGame",
        timestamp=datetime.now(),
        Commander="TestCommander",
        FID="F123456",
        Horizons=True,
        Odyssey=False,
        Ship="Sidewinder",
        ShipID=1,
        ShipIdent="TS-001",
        ShipName="Test Ship",
        StartLanded=False,
        StartDead=False,
        GameMode="Solo",
        Group="",
        Credits=1000000,
        Loan=0,
        FuelLevel=1.0,
        FuelCapacity=4.0,
    )
    defaults.update(overrides)
    return LoadedGameEvent(**defaults)


def _status_event(flags: int = 0) -> StatusEvent:
    return StatusEvent(event="Status", timestamp=datetime.now(), Flags=flags, Flags2=0)


class TestGameStateServiceGameStats(unittest.IsolatedAsyncioTestCase):
    """get_game_stats() is what PerformGameAction asks before it presses a key."""

    async def test_get_game_stats_returns_the_current_stats_without_a_stream(self):
        service = GameStateService(Mock(spec=EventBus))
        await service.process_event(_loaded_game_event())

        snapshot = service.get_game_stats()

        self.assertEqual(snapshot.player.name, "TestCommander")
        self.assertEqual(snapshot.player.ship, "Sidewinder")

    async def test_get_game_stats_reports_docked_landed_and_hyperspace_jump_from_status(
        self,
    ):
        readers = {
            StatusFlags.Docked: lambda stats: stats.navigation.is_docked,
            StatusFlags.Landed: lambda stats: stats.ship.is_landed,
            StatusFlags.FsdJump: lambda stats: stats.navigation.is_in_fsd_jump,
        }
        for flag, reads_own_field in readers.items():
            with self.subTest(flag=flag.name):
                service = GameStateService(Mock(spec=EventBus))

                await service.process_event(_status_event(flags=flag))
                stats = service.get_game_stats()

                self.assertTrue(reads_own_field(stats))
                for other_flag, reads_other_field in readers.items():
                    if other_flag != flag:
                        self.assertFalse(reads_other_field(stats))

    async def test_get_game_stats_reports_the_toggle_states_a_reply_is_named_after(
        self,
    ):
        readers = {
            StatusFlags.LandingGearDown: lambda stats: stats.ship.is_landing_gear_down,
            StatusFlags.HardpointsDeployed: lambda stats: (
                stats.ship.are_hardpoints_deployed
            ),
            StatusFlags.LightsOn: lambda stats: stats.ship.are_lights_on,
            StatusFlags.CargoScoopDeployed: lambda stats: (
                stats.ship.is_cargo_scoop_deployed
            ),
            StatusFlags.FlightAssistOff: lambda stats: stats.ship.is_flight_assist_off,
            StatusFlags.NightVision: lambda stats: stats.ship.is_night_vision_on,
        }
        for flag, reads_own_field in readers.items():
            with self.subTest(flag=flag.name):
                service = GameStateService(Mock(spec=EventBus))

                await service.process_event(_status_event(flags=flag))
                stats = service.get_game_stats()

                self.assertTrue(reads_own_field(stats))
                for other_flag, reads_other_field in readers.items():
                    if other_flag != flag:
                        self.assertFalse(reads_other_field(stats))

    async def test_get_game_stats_clears_the_flags_when_the_next_status_has_none(
        self,
    ):
        service = GameStateService(Mock(spec=EventBus))
        await service.process_event(_status_event(flags=StatusFlags.Docked))

        await service.process_event(_status_event(flags=0))
        stats = service.get_game_stats()

        self.assertFalse(stats.navigation.is_docked)

    async def test_get_game_stats_flags_are_false_before_the_first_status(self):
        service = GameStateService(Mock(spec=EventBus))

        stats = service.get_game_stats()

        self.assertFalse(stats.navigation.is_docked)
        self.assertFalse(stats.navigation.is_in_fsd_jump)
        self.assertFalse(stats.navigation.is_in_supercruise)
        self.assertFalse(stats.ship.is_landed)


class TestGameStateServiceStreams(unittest.IsolatedAsyncioTestCase):
    async def test_stream_game_stats_yields_snapshot_reflecting_processed_event(
        self,
    ):
        # spec=EventBus makes `publish` an AsyncMock automatically (it's an
        # `async def` on the real class), so `await event_bus.publish(...)`
        # in process_event doesn't blow up on a plain Mock.
        service = GameStateService(Mock(spec=EventBus))
        stream = service.stream_game_stats()
        # Subscribing always yields the current state first, so drop that
        # snapshot before testing what the events produce.
        await stream.__anext__()
        # Prime the subscriber so its queue is registered and the running loop is
        # captured before we publish; otherwise the event would not be dispatched.
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await service.process_event(_loaded_game_event())
        # Only Status.json events wake the stats stream. Journal events just
        # refresh the projections that the snapshot is built from.
        await service.process_event(_status_event())

        snapshot = await pending
        self.assertEqual(snapshot.player.name, "TestCommander")
        self.assertEqual(snapshot.player.ship, "Sidewinder")
        self.assertEqual(snapshot.player.credits, 1000000)
        await stream.aclose()

    async def test_stream_game_stats_yields_updated_snapshot_for_each_event(self):
        service = GameStateService(Mock(spec=EventBus))
        stream = service.stream_game_stats()
        # Discard the snapshot handed out on subscription.
        await stream.__anext__()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await service.process_event(_loaded_game_event(Ship="Sidewinder"))
        await service.process_event(_status_event())
        first_snapshot = await pending

        await service.process_event(_loaded_game_event(Ship="Anaconda"))
        await service.process_event(_status_event())
        second_snapshot = await stream.__anext__()

        self.assertEqual(first_snapshot.player.ship, "Sidewinder")
        self.assertEqual(second_snapshot.player.ship, "Anaconda")
        await stream.aclose()

    async def test_stream_game_stats_yields_initial_snapshot_without_waiting_for_event(
        self,
    ):
        # A fresh subscriber must get a snapshot straight away instead of
        # blocking until the next Status.json event arrives.
        service = GameStateService(Mock(spec=EventBus))
        stream = service.stream_game_stats()

        snapshot = await stream.__anext__()

        self.assertEqual(snapshot.player.name, "")
        self.assertEqual(snapshot.player.ship, "")
        self.assertEqual(snapshot.player.credits, 0)
        await stream.aclose()

    async def test_initial_snapshot_reflects_events_processed_before_subscribing(self):
        # A screen opened later (the settings header) subscribes long after the
        # game events were processed, and must still see the current state.
        service = GameStateService(Mock(spec=EventBus))
        await service.process_event(_loaded_game_event())

        stream = service.stream_game_stats()
        snapshot = await stream.__anext__()

        self.assertEqual(snapshot.player.name, "TestCommander")
        self.assertEqual(snapshot.player.ship, "Sidewinder")
        self.assertEqual(snapshot.player.credits, 1000000)
        await stream.aclose()

    async def test_stream_game_stats_unregisters_queue_when_closed(self):
        # The initial snapshot yields before the loop is entered, so make sure
        # the cleanup in `finally` still runs when the stream is closed.
        service = GameStateService(Mock(spec=EventBus))
        watchers = service._GameStateService__status_queue_watchers

        stream = service.stream_game_stats()
        await stream.__anext__()
        self.assertEqual(len(watchers), 1)

        await stream.aclose()
        self.assertEqual(watchers, [])

    async def test_stream_journal_events_yields_processed_event(self):
        service = GameStateService(Mock(spec=EventBus))
        stream = service.stream_journal_events()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        event = _loaded_game_event()
        await service.process_event(event)

        received = await pending
        self.assertIs(received, event)
        await stream.aclose()

    async def test_stream_journal_events_excludes_status_events(self):
        # Status.json is polled on its own cadence, not read from the
        # journal log file, so it must never reach the frontend's live
        # journal event stream.
        service = GameStateService(Mock(spec=EventBus))
        stream = service.stream_journal_events()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        status_event = StatusEvent(
            event="Status", timestamp=datetime.now(), Flags=0, Flags2=0
        )
        await service.process_event(status_event)

        journal_event = _loaded_game_event()
        await service.process_event(journal_event)

        # If the status event had been queued, this would resolve to it
        # instead of waiting for the journal event below.
        received = await pending
        self.assertIs(received, journal_event)
        await stream.aclose()

    async def test_status_events_still_update_projections_despite_being_excluded(
        self,
    ):
        service = GameStateService(Mock(spec=EventBus))

        status_event = StatusEvent(
            event="Status", timestamp=datetime.now(), Flags=0, Flags2=0
        )
        await service.process_event(status_event)

        self.assertIn(
            "Warning: ship shields are down.", service.get_game_state_projection()
        )


class TestGameStateServiceMarketStream(unittest.IsolatedAsyncioTestCase):
    async def test_stream_market_yields_the_current_snapshot_without_waiting(self):
        service = GameStateService(Mock(spec=EventBus))
        stream = service.stream_market()

        snapshot = await stream.__anext__()

        self.assertFalse(snapshot.is_docked)
        self.assertFalse(snapshot.is_market_data_current)
        await stream.aclose()

    async def test_stream_market_yields_commodities_when_the_market_ids_match(self):
        service = GameStateService(Mock(spec=EventBus))
        await service.process_event(make_docked_event())
        stream = service.stream_market()
        await stream.__anext__()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await service.process_event(make_market_event())

        snapshot = await pending
        self.assertTrue(snapshot.is_market_data_current)
        self.assertEqual(snapshot.station_name, "Fan Horizons")
        self.assertEqual(len(snapshot.commodities), 1)
        await stream.aclose()

    async def test_stream_market_reports_stale_data_after_docking_elsewhere(self):
        service = GameStateService(Mock(spec=EventBus))
        await service.process_event(make_market_event())
        stream = service.stream_market()
        await stream.__anext__()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await service.process_event(
            make_docked_event(StationName="Rutherford Prospect", MarketID=999)
        )

        snapshot = await pending
        self.assertTrue(snapshot.is_docked)
        self.assertFalse(snapshot.is_market_data_current)
        await stream.aclose()

    async def test_stream_market_is_not_woken_by_status_events(self):
        """Status.json ticks once a second - waking on it would rebuild the
        commodity table that often."""
        service = GameStateService(Mock(spec=EventBus))
        stream = service.stream_market()
        await stream.__anext__()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await service.process_event(_status_event())
        await asyncio.sleep(0)
        self.assertFalse(pending.done())

        # A docking event does wake it, which also proves the stream is live.
        await service.process_event(make_docked_event())
        snapshot = await pending
        self.assertEqual(snapshot.station_name, "Fan Horizons")
        await stream.aclose()

    async def test_stream_market_is_not_woken_by_unrelated_journal_events(self):
        service = GameStateService(Mock(spec=EventBus))
        stream = service.stream_market()
        await stream.__anext__()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await service.process_event(_loaded_game_event())
        await asyncio.sleep(0)
        self.assertFalse(pending.done())

        # Waking it with a real event leaves the generator idle again, so the
        # stream can be closed without cancelling a running __anext__.
        await service.process_event(make_docked_event())
        await pending
        await stream.aclose()

    async def test_market_events_never_reach_the_journal_event_stream(self):
        service = GameStateService(Mock(spec=EventBus))
        stream = service.stream_journal_events()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await service.process_event(make_market_event())

        journal_event = _loaded_game_event()
        await service.process_event(journal_event)

        received = await pending
        self.assertIs(received, journal_event)
        await stream.aclose()

    async def test_stream_market_unregisters_its_queue_when_closed(self):
        service = GameStateService(Mock(spec=EventBus))
        stream = service.stream_market()
        await stream.__anext__()

        await stream.aclose()

        self.assertEqual(service._GameStateService__market_queue_watchers, [])

    async def test_market_reaches_the_llm_projection(self):
        service = GameStateService(Mock(spec=EventBus))

        await service.process_event(make_docked_event())
        await service.process_event(make_market_event())

        projection = service.get_game_state_projection()
        self.assertIn("Fan Horizons", projection)
        self.assertIn("Platinum", projection)


class TestGameStateServiceProjectionText(unittest.IsolatedAsyncioTestCase):
    async def test_game_state_parts_go_commander_location_ship_fuel_hull_market(self):
        service = GameStateService(Mock(spec=EventBus))
        # Docked, but no ShieldsUp flag, so the ship part has a sentence too.
        status_event_docked = StatusEvent(
            event="Status",
            timestamp=datetime.now(),
            Flags=StatusFlags.Docked,
            Flags2=0,
        )

        await service.process_event(_loaded_game_event())
        await service.process_event(make_docked_event())
        await service.process_event(make_market_event())
        await service.process_event(status_event_docked)

        expected_game_state = (
            "Commander name is TestCommander. Commander has 1000000 of credits. "
            "Commander ship is Sidewinder. Commander plays in Solo game mode.\n"
            "Player is currently in the Beta Sculptoris system. "
            "Player is currently docked at station: Fan Horizons.\n"
            "Warning: ship shields are down.\n"
            "Current fuel level is: 1.0.\n"
            "Ship hull health is at 100%.\n"
            "Station Fan Horizons sells 1 commodities. The best prices against "
            "the galactic average: Platinum at 42220 (+22464 per tonne)."
        )
        self.assertEqual(expected_game_state, service.get_game_state_projection())

    async def test_route_modules_and_cargo_lines_come_after_their_neighbours(self):
        service = GameStateService(Mock(spec=EventBus))

        await service.process_event(_loaded_game_event())
        await service.process_event(make_docked_event())
        await service.process_event(make_market_event())
        await service.process_event(
            make_nav_route_event(["Beta Sculptoris", "Sol", "Sirius"])
        )
        await service.process_event(
            make_cargo_event([dict(Name="gold", Name_Localised="Gold", Count=5)])
        )
        await service.process_event(
            make_module_info_event(
                [
                    dict(
                        Slot="Radar",
                        Item="int_sensors_size3_class1",
                        Power=0.22,
                        Priority=2,
                    )
                ]
            )
        )

        expected_game_state = (
            "Commander name is TestCommander. Commander has 1000000 of credits. "
            "Commander ship is Sidewinder. Commander plays in Solo game mode.\n"
            "Player is currently in the Beta Sculptoris system. "
            "Player is currently un-docked from station: Fan Horizons flying nearby.\n"
            "Plotted route: destination Sirius, 2 jumps left. "
            "Next systems on the route: Sol, Sirius.\n"
            "Current fuel level is: 1.0.\n"
            "Ship hull health is at 100%.\n"
            "Ship modules (slot: module, power draw, power priority): "
            "Radar: int_sensors_size3_class1, 0.22 MW, priority 2.\n"
            "Cargo hold contains: 5 t Gold.\n"
            "Station Fan Horizons sells 1 commodities. The best prices against "
            "the galactic average: Platinum at 42220 (+22464 per tonne)."
        )
        self.assertEqual(expected_game_state, service.get_game_state_projection())

    async def test_game_state_leaves_out_parts_with_nothing_to_say(self):
        service = GameStateService(Mock(spec=EventBus))

        # Before any Status.json the ship part is empty, and without a location
        # or a market event those parts are empty too.
        await service.process_event(_loaded_game_event())

        expected_game_state = (
            "Commander name is TestCommander. Commander has 1000000 of credits. "
            "Commander ship is Sidewinder. Commander plays in Solo game mode.\n"
            "Current fuel level is: 1.0.\n"
            "Ship hull health is at 100%."
        )
        self.assertEqual(expected_game_state, service.get_game_state_projection())

    async def test_game_state_text_has_no_current_game_state_heading(self):
        service = GameStateService(Mock(spec=EventBus))

        await service.process_event(_loaded_game_event())

        self.assertNotIn("Current game state is", service.get_game_state_projection())


def _as_startup_loading(event: GameEvent) -> GameEvent:
    """A copy of the event, as the watcher publishes it while the app loads
    what the game wrote before the start."""
    return event.model_copy(update={"is_startup_loading": True})


class TestGameStateServiceStartupLoading(unittest.IsolatedAsyncioTestCase):
    async def _first_snapshot(self, service: GameStateService):
        stream = service.stream_game_stats()
        snapshot = await stream.__anext__()
        await stream.aclose()
        return snapshot

    async def test_startup_loading_event_updates_the_projections(self):
        service = GameStateService(Mock(spec=EventBus))

        await service.process_event(_as_startup_loading(_loaded_game_event()))

        snapshot = await self._first_snapshot(service)
        self.assertEqual(snapshot.player.name, "TestCommander")
        self.assertEqual(snapshot.player.ship, "Sidewinder")

    async def test_startup_loading_event_publishes_no_game_state_changed_event(self):
        event_bus = Mock(spec=EventBus)
        service = GameStateService(event_bus)

        await service.process_event(_as_startup_loading(_loaded_game_event()))
        event_bus.publish.assert_not_called()

        # A live event does publish, so the silence above comes from the flag.
        await service.process_event(_loaded_game_event())
        event_bus.publish.assert_awaited_once()

    async def test_startup_loading_event_does_not_reach_the_journal_stream(self):
        service = GameStateService(Mock(spec=EventBus))
        stream = service.stream_journal_events()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await service.process_event(_as_startup_loading(_loaded_game_event()))
        live_event = _loaded_game_event(Ship="Anaconda")
        await service.process_event(live_event)

        # If the loading event had been queued, this would be that event.
        received = await pending
        self.assertIs(received, live_event)
        await stream.aclose()

    async def test_startup_loading_events_do_not_wake_the_stats_and_market_streams(
        self,
    ):
        service = GameStateService(Mock(spec=EventBus))
        stats_stream = service.stream_game_stats()
        market_stream = service.stream_market()
        await stats_stream.__anext__()
        await market_stream.__anext__()
        stats_pending = asyncio.ensure_future(stats_stream.__anext__())
        market_pending = asyncio.ensure_future(market_stream.__anext__())
        await asyncio.sleep(0)

        await service.process_event(_as_startup_loading(_status_event()))
        await service.process_event(_as_startup_loading(make_docked_event()))
        await asyncio.sleep(0)

        self.assertFalse(stats_pending.done())
        self.assertFalse(market_pending.done())

        # The same events as live ones wake the streams, so the quiet above
        # comes from the flag.
        await service.process_event(_status_event())
        await service.process_event(make_docked_event())
        await stats_pending
        await market_pending
        await stats_stream.aclose()
        await market_stream.aclose()

    async def test_finishing_the_loading_wakes_the_stats_and_market_streams_once(
        self,
    ):
        service = GameStateService(Mock(spec=EventBus))
        stats_stream = service.stream_game_stats()
        market_stream = service.stream_market()
        await stats_stream.__anext__()
        await market_stream.__anext__()
        stats_pending = asyncio.ensure_future(stats_stream.__anext__())
        market_pending = asyncio.ensure_future(market_stream.__anext__())
        await asyncio.sleep(0)
        await service.process_event(_as_startup_loading(_loaded_game_event()))
        await service.process_event(_as_startup_loading(make_docked_event()))
        await service.process_event(_as_startup_loading(make_market_event()))

        await service.publish_game_state_after_startup_loading(
            StartupLoadingFinishedEvent()
        )

        stats_snapshot = await stats_pending
        market_snapshot = await market_pending
        self.assertEqual(stats_snapshot.player.name, "TestCommander")
        self.assertTrue(market_snapshot.is_docked)
        self.assertTrue(market_snapshot.is_market_data_current)
        # Once means once: no second snapshot is waiting in either stream.
        stats_again = asyncio.ensure_future(stats_stream.__anext__())
        market_again = asyncio.ensure_future(market_stream.__anext__())
        await asyncio.sleep(0)
        self.assertFalse(stats_again.done())
        self.assertFalse(market_again.done())
        stats_again.cancel()
        market_again.cancel()
        await asyncio.gather(stats_again, market_again, return_exceptions=True)
        await stats_stream.aclose()
        await market_stream.aclose()

    async def test_finishing_the_loading_does_not_wake_the_journal_stream(self):
        service = GameStateService(Mock(spec=EventBus))
        stream = service.stream_journal_events()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await service.process_event(_as_startup_loading(_loaded_game_event()))
        await service.publish_game_state_after_startup_loading(
            StartupLoadingFinishedEvent()
        )
        await asyncio.sleep(0)

        self.assertFalse(pending.done())
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await stream.aclose()

    async def test_finishing_the_loading_publishes_the_game_state_once(self):
        event_bus = Mock(spec=EventBus)
        service = GameStateService(event_bus)
        await service.process_event(_as_startup_loading(_loaded_game_event()))

        await service.publish_game_state_after_startup_loading(
            StartupLoadingFinishedEvent()
        )

        event_bus.publish.assert_awaited_once()
        published_event = event_bus.publish.await_args.args[0]
        self.assertIsInstance(published_event, GameStateChangedEvent)
        self.assertIn("Commander name is TestCommander.", published_event.game_state)
        self.assertEqual(
            published_event.game_state, service.get_game_state_projection()
        )

    async def test_finishing_a_loading_without_any_event_leaves_the_state_unknown(
        self,
    ):
        # An empty journal and no side files: nothing is known about the game.
        # The state text must stay empty (the fuel part would fill it with
        # "0.0"), because Instinct and the LLM take an empty text for "the game
        # has not started".
        event_bus = Mock(spec=EventBus)
        service = GameStateService(event_bus)
        stream = service.stream_game_stats()
        await stream.__anext__()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await service.publish_game_state_after_startup_loading(
            StartupLoadingFinishedEvent()
        )
        await asyncio.sleep(0)

        event_bus.publish.assert_not_called()
        self.assertEqual(service.get_game_state_projection(), "")
        self.assertFalse(pending.done())
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await stream.aclose()

    async def test_service_listens_for_the_finished_event_on_the_event_bus(self):
        event_bus = EventBus()
        service = GameStateService(event_bus)
        game_state_listener = AsyncMock()
        event_bus.subscribe(GameStateChangedEvent, game_state_listener)
        await event_bus.publish(_as_startup_loading(_loaded_game_event()))
        game_state_listener.assert_not_called()

        await event_bus.publish(StartupLoadingFinishedEvent())

        game_state_listener.assert_called_once()
        self.assertIn("TestCommander", game_state_listener.call_args.args[0].game_state)
        self.assertIn("TestCommander", service.get_game_state_projection())

    async def test_route_cargo_and_modules_of_the_loading_reach_the_state_when_it_ends(
        self,
    ):
        service = GameStateService(Mock(spec=EventBus))
        await service.process_event(_as_startup_loading(make_docked_event()))
        await service.process_event(
            _as_startup_loading(make_nav_route_event(["Beta Sculptoris", "Sol"]))
        )
        await service.process_event(
            _as_startup_loading(
                make_cargo_event([dict(Name="gold", Name_Localised="Gold", Count=5)])
            )
        )
        await service.process_event(
            _as_startup_loading(
                make_module_info_event([dict(Slot="Radar", Item="int_sensors")])
            )
        )

        self.assertEqual("", service.get_game_state_projection())

        await service.publish_game_state_after_startup_loading(
            StartupLoadingFinishedEvent()
        )

        state = service.get_game_state_projection()
        self.assertIn("destination Sol, 1 jump left", state)
        self.assertIn("Cargo hold contains: 5 t Gold.", state)
        self.assertIn("Radar: int_sensors", state)

    async def test_loading_the_same_events_twice_gives_the_same_state(self):
        service = GameStateService(Mock(spec=EventBus))
        loading_events = [
            _as_startup_loading(_loaded_game_event()),
            _as_startup_loading(make_docked_event()),
            _as_startup_loading(make_market_event()),
            _as_startup_loading(
                StatusEvent(
                    event="Status",
                    timestamp=datetime.now(),
                    Flags=0,
                    Flags2=0,
                    Pips=[4, 4, 4],
                    Cargo=12.0,
                    Fuel=StatusFuelModel(FuelMain=3.5, FuelReservoir=0.3),
                )
            ),
        ]

        for event in loading_events:
            await service.process_event(event)
        await service.publish_game_state_after_startup_loading(
            StartupLoadingFinishedEvent()
        )
        state_after_first_loading = service.get_game_state_projection()
        stats_after_first_loading = await self._first_snapshot(service)

        for event in loading_events:
            await service.process_event(event)
        await service.publish_game_state_after_startup_loading(
            StartupLoadingFinishedEvent()
        )

        self.assertEqual(state_after_first_loading, service.get_game_state_projection())
        self.assertEqual(stats_after_first_loading, await self._first_snapshot(service))
        self.assertEqual(stats_after_first_loading.ship.cargo_current, 12.0)


class TestGameStateServiceNewGameSession(unittest.IsolatedAsyncioTestCase):
    """The game was started again: the old session must not linger."""

    async def _loaded_service(self, event_bus: EventBus) -> GameStateService:
        service = GameStateService(event_bus)
        await service.process_event(_as_startup_loading(_loaded_game_event()))
        await service.process_event(_as_startup_loading(make_docked_event()))
        return service

    async def test_new_game_session_event_empties_the_game_stats(self):
        event_bus = EventBus()
        service = await self._loaded_service(event_bus)
        self.assertEqual(service.get_game_stats().player.name, "TestCommander")

        await event_bus.publish(NewGameSessionEvent())

        stats = service.get_game_stats()
        self.assertEqual(stats.player.name, "")
        self.assertEqual(stats.player.ship, "")
        self.assertFalse(stats.navigation.is_docked)

    async def test_new_game_session_event_keeps_the_open_ui_streams_working(self):
        event_bus = EventBus()
        service = await self._loaded_service(event_bus)
        stats_stream = service.stream_game_stats()
        await stats_stream.__anext__()
        pending_snapshot = asyncio.ensure_future(stats_stream.__anext__())
        await asyncio.sleep(0)

        await event_bus.publish(NewGameSessionEvent())
        await service.process_event(
            _as_startup_loading(_loaded_game_event(Ship="Anaconda"))
        )
        await event_bus.publish(StartupLoadingFinishedEvent())

        snapshot = await asyncio.wait_for(pending_snapshot, timeout=1)
        self.assertEqual(snapshot.player.ship, "Anaconda")
        await stats_stream.aclose()

    async def test_new_game_session_event_publishes_nothing(self):
        event_bus = EventBus()
        service = await self._loaded_service(event_bus)
        game_state_listener = AsyncMock()
        event_bus.subscribe(GameStateChangedEvent, game_state_listener)
        await event_bus.publish(StartupLoadingFinishedEvent())
        game_state_listener.reset_mock()

        await event_bus.publish(NewGameSessionEvent())

        # The old text stays until the loading of the new session ends.
        game_state_listener.assert_not_called()
        self.assertIn("TestCommander", service.get_game_state_projection())


if __name__ == "__main__":
    unittest.main()
