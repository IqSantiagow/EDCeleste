from collections.abc import AsyncGenerator
import unittest

from use_cases.dashboard.stream_dashboard_stats_usecase import (
    StreamDashboardStatsUseCase,
)


async def _async_gen(items) -> AsyncGenerator:
    for item in items:
        yield item


class FakeGameStateReader:
    def __init__(self, snapshots=None, error=None):
        self._snapshots = snapshots or []
        self._error = error

    async def stream_dashboard_stats(self):
        async for snapshot in _async_gen(self._snapshots):
            yield snapshot
        if self._error is not None:
            raise self._error


class TestStreamDashboardStatsUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_map_snapshot_to_view_model(self):
        reader = FakeGameStateReader(
            snapshots=[
                {"player": "X", "location": "Sol", "ship": "Sidewinder", "fuel": "5.0"}
            ]
        )
        use_case = StreamDashboardStatsUseCase(reader) # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].location, "Sol")
        self.assertEqual(results[0].ship, "Sidewinder")
        self.assertEqual(results[0].fuel, "5.0")

    async def test_should_default_missing_keys_to_empty_string(self):
        reader = FakeGameStateReader(snapshots=[{}])
        use_case = StreamDashboardStatsUseCase(reader) # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(results[0].location, "")
        self.assertEqual(results[0].ship, "")
        self.assertEqual(results[0].fuel, "")

    async def test_should_yield_multiple_view_models_in_order(self):
        snapshots = [
            {"location": "Sol"},
            {"location": "Alpha Centauri"},
            {"location": "Sirius"},
        ]
        reader = FakeGameStateReader(snapshots=snapshots)
        use_case = StreamDashboardStatsUseCase(reader) # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(
            [view_model.location for view_model in results],
            ["Sol", "Alpha Centauri", "Sirius"],
        )

    async def test_should_complete_when_stream_is_empty(self):
        reader = FakeGameStateReader(snapshots=[])
        use_case = StreamDashboardStatsUseCase(reader) # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(results, [])

    async def test_should_propagate_exception_from_underlying_stream(self):
        reader = FakeGameStateReader(snapshots=[], error=RuntimeError("boom"))
        use_case = StreamDashboardStatsUseCase(reader) # type: ignore

        with self.assertRaises(RuntimeError):
            async for _ in use_case():
                pass


if __name__ == "__main__":
    unittest.main()
