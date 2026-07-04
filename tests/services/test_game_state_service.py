import asyncio
from datetime import datetime
import unittest
from unittest.mock import Mock

from services.game_state_service import GameStateService
from services.models.dashboard_stats_snapshot import DashboardStatsSnapshot
from services.models.game_events import LoadedGameEvent


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


class TestGameStateServiceDashboardStats(unittest.TestCase):
    def test_get_dashboard_stats_returns_snapshot_from_projections(self):
        service = GameStateService(Mock())

        service.process_event(_loaded_game_event())

        snapshot = service.get_dashboard_stats()
        self.assertEqual(snapshot.ship, "Sidewinder")
        self.assertEqual(snapshot.fuel, "1.0")
        # LoadGame does not carry a star system, so location stays empty.
        self.assertEqual(snapshot.location, "")

    def test_get_dashboard_stats_returns_defaults_when_no_events(self):
        service = GameStateService(Mock())

        snapshot = service.get_dashboard_stats()

        self.assertEqual(
            snapshot, DashboardStatsSnapshot(location="", ship="", fuel="0.0")
        )


class TestGameStateServiceStreams(unittest.IsolatedAsyncioTestCase):
    async def test_stream_dashboard_stats_yields_snapshot_after_event(self):
        service = GameStateService(Mock())
        stream = service.stream_dashboard_stats()
        # Prime the subscriber so its queue is registered and the running loop is
        # captured before we publish; otherwise the event would not be dispatched.
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        service.process_event(_loaded_game_event())

        snapshot = await pending
        self.assertEqual(snapshot.ship, "Sidewinder")
        self.assertEqual(snapshot.fuel, "1.0")
        await stream.aclose()

    async def test_stream_journal_events_yields_processed_event(self):
        service = GameStateService(Mock())
        stream = service.stream_journal_events()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        event = _loaded_game_event()
        service.process_event(event)

        received = await pending
        self.assertIs(received, event)
        await stream.aclose()


if __name__ == "__main__":
    unittest.main()
