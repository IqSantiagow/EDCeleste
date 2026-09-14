import unittest

from edceleste.use_cases.dashboard.stream_ship_stats_use_case import (
    StreamShipStatsUseCase,
)
from tests.use_cases.dashboard.game_stats_fixtures import (
    FakeGameStateProtocol,
    make_game_stats_snapshot,
    make_player_stats,
    make_ship_stats,
)


class TestStreamShipStatsUseCase(unittest.IsolatedAsyncioTestCase):
    def _make_use_case(self, snapshots) -> StreamShipStatsUseCase:
        return StreamShipStatsUseCase(FakeGameStateProtocol(snapshots))  # type: ignore

    async def test_maps_all_ship_fields_to_view_model(self):
        snapshot = make_game_stats_snapshot(ship=make_ship_stats())
        use_case = self._make_use_case([snapshot])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(len(view_models), 1)
        view_model = view_models[0]
        self.assertEqual(view_model.hull_pe, 0.87)
        self.assertFalse(view_model.gear)
        self.assertFalse(view_model.hardpoints)
        self.assertFalse(view_model.lights)
        self.assertEqual(view_model.mass, 285.6)
        self.assertEqual(view_model.cargo, 16.0)
        self.assertEqual(view_model.cargo_capacity, 64)
        self.assertEqual(view_model.legal_status, "Clean")
        self.assertEqual(view_model.rebuy, 1234567)
        self.assertTrue(view_model.modules_healthy)

    async def test_halves_pips_from_journal_scale(self):
        # The game reports pips in half steps (0-8), the dashboard shows 0-4.
        snapshot = make_game_stats_snapshot(
            ship=make_ship_stats(pips_system=8, pips_engine=4, pips_weapons=2)
        )
        use_case = self._make_use_case([snapshot])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(view_models[0].pips, (4.0, 2.0, 1.0))

    async def test_maps_raised_shields_to_full_shield_percent(self):
        snapshot = make_game_stats_snapshot(ship=make_ship_stats(are_shields_up=True))
        use_case = self._make_use_case([snapshot])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(view_models[0].shields_percent, 100.0)
        self.assertTrue(view_models[0].shields)

    async def test_maps_dropped_shields_to_zero_shield_percent(self):
        snapshot = make_game_stats_snapshot(ship=make_ship_stats(are_shields_up=False))
        use_case = self._make_use_case([snapshot])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(view_models[0].shields_percent, 0.0)
        self.assertFalse(view_models[0].shields)

    async def test_takes_ship_name_from_player_stats_not_ship_stats(self):
        snapshot = make_game_stats_snapshot(
            player=make_player_stats(ship="Krait Mk II"), ship=make_ship_stats()
        )
        use_case = self._make_use_case([snapshot])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(view_models[0].ship_name, "Krait Mk II")

    async def test_yields_one_view_model_per_streamed_snapshot(self):
        snapshots = [
            make_game_stats_snapshot(ship=make_ship_stats(hull_health=1.0)),
            make_game_stats_snapshot(ship=make_ship_stats(hull_health=0.6)),
            make_game_stats_snapshot(ship=make_ship_stats(hull_health=0.2)),
        ]
        use_case = self._make_use_case(snapshots)

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(
            [view_model.hull_pe for view_model in view_models], [1.0, 0.6, 0.2]
        )

    async def test_yields_nothing_when_stream_is_empty(self):
        use_case = self._make_use_case([])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(view_models, [])


if __name__ == "__main__":
    unittest.main()
