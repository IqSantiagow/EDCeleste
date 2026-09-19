import unittest

from edceleste.ui.screens.dashboard.view_models.station_market_view_model import (
    NO_STATION_MESSAGE,
)
from edceleste.use_cases.dashboard.stream_station_market_use_case import (
    StreamStationMarketUseCase,
)
from tests.projection.test_market_projection import make_market_item
from tests.use_cases.dashboard.game_stats_fixtures import (
    FakeGameStateProtocol,
    make_market_snapshot,
)


class TestStreamStationMarketUseCase(unittest.IsolatedAsyncioTestCase):
    def _make_use_case(self, snapshots) -> StreamStationMarketUseCase:
        return StreamStationMarketUseCase(
            FakeGameStateProtocol(market_snapshots=snapshots)  # type: ignore
        )

    async def test_maps_a_snapshot_with_commodities_to_table_rows(self):
        snapshot = make_market_snapshot(commodities=(make_market_item(),))
        use_case = self._make_use_case([snapshot])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(len(view_models), 1)
        self.assertEqual(view_models[0].message, "")
        self.assertEqual(view_models[0].rows[0].commodity, "Platinum")

    async def test_maps_a_snapshot_without_a_station_to_a_message(self):
        use_case = self._make_use_case([make_market_snapshot(is_docked=False)])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(view_models[0].message, NO_STATION_MESSAGE)

    async def test_yields_one_view_model_per_streamed_snapshot(self):
        use_case = self._make_use_case(
            [make_market_snapshot(), make_market_snapshot(is_docked=False)]
        )

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(len(view_models), 2)

    async def test_completes_when_the_stream_is_empty(self):
        use_case = self._make_use_case([])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(view_models, [])


if __name__ == "__main__":
    unittest.main()
