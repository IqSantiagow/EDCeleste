import asyncio
from datetime import datetime
import unittest
from unittest.mock import Mock

from edceleste.services.event_bus import EventBus
from edceleste.services.game_state_service import GameStateService
from edceleste.services.models.game_events import LoadedGameEvent, StatusEvent


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


if __name__ == "__main__":
    unittest.main()
