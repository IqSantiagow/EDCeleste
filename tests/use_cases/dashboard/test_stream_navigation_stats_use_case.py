import unittest

from edceleste.use_cases.dashboard.stream_navigation_stats_use_case import (
    StreamNavigationStatsUseCase,
)
from tests.use_cases.dashboard.game_stats_fixtures import (
    FakeGameStateProtocol,
    make_game_stats_snapshot,
    make_navigation_stats,
)


class TestStreamNavigationStatsUseCase(unittest.IsolatedAsyncioTestCase):
    def _make_use_case(self, snapshots) -> StreamNavigationStatsUseCase:
        return StreamNavigationStatsUseCase(FakeGameStateProtocol(snapshots))  # type: ignore

    async def test_maps_all_navigation_fields_to_view_model(self):
        snapshot = make_game_stats_snapshot(navigation=make_navigation_stats())
        use_case = self._make_use_case([snapshot])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(len(view_models), 1)
        view_model = view_models[0]
        self.assertEqual(view_model.system, "Sol")
        self.assertEqual(view_model.security, "High")
        self.assertEqual(view_model.body, "Earth")
        self.assertEqual(view_model.allegiance, "Federation")
        self.assertEqual(view_model.government, "Democracy")
        self.assertEqual(view_model.economy, "Refinery")
        self.assertEqual(view_model.second_economy, "Industrial")
        self.assertEqual(view_model.population, 22780919531)
        self.assertEqual(view_model.route_next_system, "Alpha Centauri")
        self.assertEqual(view_model.route_remaining_jumps, 3)

    async def test_maps_supercruise_flag_to_supercruise_status(self):
        snapshot = make_game_stats_snapshot(
            navigation=make_navigation_stats(is_in_supercruise=True)
        )
        use_case = self._make_use_case([snapshot])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(view_models[0].status, "Supercruise")

    async def test_maps_cleared_supercruise_flag_to_normal_space_status(self):
        snapshot = make_game_stats_snapshot(
            navigation=make_navigation_stats(is_in_supercruise=False)
        )
        use_case = self._make_use_case([snapshot])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(view_models[0].status, "Normal space")

    async def test_yields_one_view_model_per_streamed_snapshot(self):
        snapshots = [
            make_game_stats_snapshot(
                navigation=make_navigation_stats(current_star_system="Sol")
            ),
            make_game_stats_snapshot(
                navigation=make_navigation_stats(current_star_system="Shinrarta Dezhra")
            ),
            make_game_stats_snapshot(
                navigation=make_navigation_stats(current_star_system="Colonia")
            ),
        ]
        use_case = self._make_use_case(snapshots)

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(
            [view_model.system for view_model in view_models],
            ["Sol", "Shinrarta Dezhra", "Colonia"],
        )

    async def test_yields_nothing_when_stream_is_empty(self):
        use_case = self._make_use_case([])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(view_models, [])


if __name__ == "__main__":
    unittest.main()
