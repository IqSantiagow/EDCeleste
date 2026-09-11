import asyncio
from datetime import datetime
import unittest
from unittest.mock import Mock

from edceleste.services.event_bus import EventBus
from edceleste.services.game_state_service import GameStateService
from edceleste.services.models.game_events import LoadedGameEvent


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


class TestGameStateServiceStreams(unittest.IsolatedAsyncioTestCase):
    async def test_stream_game_stats_yields_snapshot_reflecting_processed_event(
        self,
    ):
        # spec=EventBus makes `publish` an AsyncMock automatically (it's an
        # `async def` on the real class), so `await event_bus.publish(...)`
        # in process_event doesn't blow up on a plain Mock.
        service = GameStateService(Mock(spec=EventBus))
        stream = service.stream_game_stats()
        # Prime the subscriber so its queue is registered and the running loop is
        # captured before we publish; otherwise the event would not be dispatched.
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await service.process_event(_loaded_game_event())

        snapshot = await pending
        self.assertEqual(snapshot.player.name, "TestCommander")
        self.assertEqual(snapshot.player.ship, "Sidewinder")
        self.assertEqual(snapshot.player.credits, 1000000)
        await stream.aclose()

    async def test_stream_game_stats_yields_updated_snapshot_for_each_event(self):
        service = GameStateService(Mock(spec=EventBus))
        stream = service.stream_game_stats()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await service.process_event(_loaded_game_event(Ship="Sidewinder"))
        first_snapshot = await pending

        await service.process_event(_loaded_game_event(Ship="Anaconda"))
        second_snapshot = await stream.__anext__()

        self.assertEqual(first_snapshot.player.ship, "Sidewinder")
        self.assertEqual(second_snapshot.player.ship, "Anaconda")
        await stream.aclose()

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


if __name__ == "__main__":
    unittest.main()
