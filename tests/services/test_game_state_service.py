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
from edceleste.services.models.startup_loading_finished_event import (
    StartupLoadingFinishedEvent,
)
from tests.projection.test_market_projection import (
    make_docked_event,
    make_market_event,
)


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


def _status_event() -> StatusEvent:
    return StatusEvent(event="Status", timestamp=datetime.now(), Flags=0, Flags2=0)


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


if __name__ == "__main__":
    unittest.main()
