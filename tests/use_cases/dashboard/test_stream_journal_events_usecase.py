from collections.abc import AsyncGenerator
from datetime import datetime
import unittest

from edceleste.services.models.game_events import (
    DockedEvent,
    LoadedGameEvent,
    StartJumpEvent,
    UnknownCheckedEvent,
)
from edceleste.services.models.game_models import BaseFactionModel
from edceleste.use_cases.dashboard.stream_journal_events_usecase import (
    StreamJournalEventsUseCase,
)


async def _async_gen(items) -> AsyncGenerator:
    for item in items:
        yield item


class FakeGameStateReader:
    def __init__(self, events=None, error=None):
        self._events = events or []
        self._error = error

    async def stream_journal_events(self):
        async for event in _async_gen(self._events):
            yield event
        if self._error is not None:
            raise self._error


class TestStreamJournalEventsUseCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.loaded_game_event = LoadedGameEvent(
            event="LoadGame",
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            Commander="TestCommander",
            FID="F123456",
            Horizons=True,
            Odyssey=False,
            Ship="Sidewinder",
            ShipID=1,
            ShipIdent="TS-001",
            ShipName="Test Ship",
            GameMode="Solo",
            Credits=1000000,
            Loan=0,
            FuelLevel=1.0,
            FuelCapacity=4.0,
        )
        self.start_jump_event = StartJumpEvent(
            event="StartJump",
            timestamp=datetime(2026, 1, 1, 12, 1, 0),
            JumpType="Hyperspace",
            Taxi=False,
            StarSystem="Sol",
            SystemAddress=10477373803,
        )
        self.docked_event = DockedEvent(
            event="Docked",
            timestamp=datetime(2026, 1, 1, 12, 2, 0),
            StarSystem="Sol",
            StationName="Abraham Lincoln",
            StationType="Coriolis",
            SystemAddress=10477373803,
            MarketID=128132520,
            StationFaction=BaseFactionModel(Name="Federation"),
            StationGovernment_Localised="Corporate",
            StationServices=["dock", "refuel"],
            StationEconomy_Localised="Industrial",
            StationEconomies=[],
            DistFromStarLS=490.0,
        )

    async def test_should_map_loaded_game_event_to_view_model(self):
        reader = FakeGameStateReader(events=[self.loaded_game_event])
        use_case = StreamJournalEventsUseCase(reader)  # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(results[0].event, "LoadGame")
        self.assertEqual(results[0].details, "TestCommander · Test Ship · 1 000 000 CR")

    async def test_should_map_start_jump_event_to_view_model(self):
        reader = FakeGameStateReader(events=[self.start_jump_event])
        use_case = StreamJournalEventsUseCase(reader)  # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(results[0].event, "StartJump")
        self.assertEqual(results[0].details, "Hyperspace charging → Sol")
        self.assertEqual(results[0].system, "Sol")

    async def test_should_map_docked_event_to_view_model(self):
        reader = FakeGameStateReader(events=[self.docked_event])
        use_case = StreamJournalEventsUseCase(reader)  # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(results[0].event, "Docked")
        self.assertEqual(results[0].details, "Abraham Lincoln · Coriolis")
        self.assertEqual(results[0].system, "Sol")

    async def test_should_leave_details_empty_for_unhandled_event_type(self):
        unknown_event = UnknownCheckedEvent(
            event="SomeBrandNewEvent", timestamp=datetime(2026, 1, 1, 12, 4, 0)
        )
        reader = FakeGameStateReader(events=[unknown_event])
        use_case = StreamJournalEventsUseCase(reader)  # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(results[0].event, "SomeBrandNewEvent")
        self.assertEqual(results[0].details, "")

    async def test_should_preserve_event_timestamp(self):
        reader = FakeGameStateReader(events=[self.start_jump_event])
        use_case = StreamJournalEventsUseCase(reader)  # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(results[0].timestamp, self.start_jump_event.timestamp)

    async def test_should_yield_multiple_events_in_order(self):
        reader = FakeGameStateReader(events=[self.loaded_game_event, self.docked_event])
        use_case = StreamJournalEventsUseCase(reader)  # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(
            [view_model.event for view_model in results], ["LoadGame", "Docked"]
        )

    async def test_should_complete_when_stream_is_empty(self):
        reader = FakeGameStateReader(events=[])
        use_case = StreamJournalEventsUseCase(reader)  # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(results, [])

    async def test_should_propagate_exception_from_underlying_stream(self):
        reader = FakeGameStateReader(events=[], error=RuntimeError("boom"))
        use_case = StreamJournalEventsUseCase(reader)  # type: ignore

        with self.assertRaises(RuntimeError):
            async for _ in use_case():
                pass


if __name__ == "__main__":
    unittest.main()
