import unittest

from edceleste.use_cases.dashboard.stream_flight_and_drive_stats_use_case import (
    StreamFlightAndDriveStatsUseCase,
)
from tests.use_cases.dashboard.game_stats_fixtures import (
    FakeGameStateProtocol,
    make_flight_drive_stats,
    make_game_stats_snapshot,
)


class TestStreamFlightAndDriveStatsUseCase(unittest.IsolatedAsyncioTestCase):
    def _make_use_case(self, snapshots) -> StreamFlightAndDriveStatsUseCase:
        return StreamFlightAndDriveStatsUseCase(FakeGameStateProtocol(snapshots))  # type: ignore

    async def test_maps_all_flight_and_drive_fields_to_view_model(self):
        snapshot = make_game_stats_snapshot(flight_drive=make_flight_drive_stats())
        use_case = self._make_use_case([snapshot])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(len(view_models), 1)
        view_model = view_models[0]
        self.assertEqual(view_model.fuel, 12.5)
        self.assertEqual(view_model.fuel_capacity, 32.0)
        self.assertEqual(view_model.fuel_reservoir, 0.42)
        self.assertEqual(view_model.jump_range, 18.75)
        self.assertEqual(view_model.fsd_module, "int_hyperdrive_size5_class5")

    async def test_maps_active_fuel_scooping_flag(self):
        snapshot = make_game_stats_snapshot(
            flight_drive=make_flight_drive_stats(is_scooping_fuel=True)
        )
        use_case = self._make_use_case([snapshot])

        view_models = [view_model async for view_model in use_case()]

        self.assertTrue(view_models[0].is_scooping)

    async def test_maps_inactive_fuel_scooping_flag(self):
        snapshot = make_game_stats_snapshot(
            flight_drive=make_flight_drive_stats(is_scooping_fuel=False)
        )
        use_case = self._make_use_case([snapshot])

        view_models = [view_model async for view_model in use_case()]

        self.assertFalse(view_models[0].is_scooping)

    async def test_yields_updated_view_model_for_each_snapshot(self):
        snapshots = [
            make_game_stats_snapshot(
                flight_drive=make_flight_drive_stats(fuel_level=32.0)
            ),
            make_game_stats_snapshot(
                flight_drive=make_flight_drive_stats(fuel_level=18.0)
            ),
            make_game_stats_snapshot(
                flight_drive=make_flight_drive_stats(fuel_level=4.5)
            ),
        ]
        use_case = self._make_use_case(snapshots)

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(
            [view_model.fuel for view_model in view_models], [32.0, 18.0, 4.5]
        )

    async def test_yields_nothing_when_stream_is_empty(self):
        use_case = self._make_use_case([])

        view_models = [view_model async for view_model in use_case()]

        self.assertEqual(view_models, [])


if __name__ == "__main__":
    unittest.main()
