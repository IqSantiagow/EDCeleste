from collections.abc import AsyncGenerator
import unittest

from edceleste.services.models.game_stats import (
    FlightDriveStats,
    GameStatsSnapshot,
    NavigationStats,
    PlayerStats,
    ShipStats,
)
from edceleste.use_cases.app.stream_app_header_stats_usecase import (
    StreamAppHeaderStatsUseCase,
)


async def _async_gen(items) -> AsyncGenerator:
    for item in items:
        yield item


class FakeGameStateProtocol:
    def __init__(self, game_stats_snapshots=None):
        self._game_stats_snapshots = game_stats_snapshots or []

    async def stream_game_stats(self):
        async for snapshot in _async_gen(self._game_stats_snapshots):
            yield snapshot


def _game_stats_snapshot(
    player_name="TestCommander", player_ship="Sidewinder", player_credits=1000000
) -> GameStatsSnapshot:
    return GameStatsSnapshot(
        player=PlayerStats(name=player_name, ship=player_ship, credits=player_credits),
        navigation=NavigationStats(
            current_star_system="",
            system_security_level="",
            system_allegiance="",
            system_government="",
            system_economy="",
            system_second_economy="",
            system_population=0,
            current_body="",
            is_in_supercruise=False,
            route_next_star_system="",
            route_remaining_jumps=0,
        ),
        flight_drive=FlightDriveStats(
            fuel_level=0.0,
            fuel_capacity=0.0,
            fuel_reservoir=0.0,
            is_scooping_fuel=False,
            max_jump_range=0.0,
            fsd_module_item="",
        ),
        ship=ShipStats(
            is_landing_gear_down=False,
            are_hardpoints_deployed=False,
            are_lights_on=False,
            are_shields_up=False,
            pips_system=0,
            pips_engine=0,
            pips_weapons=0,
            cargo_current=0.0,
            cargo_capacity=0,
            legal_status="",
            hull_health=0.0,
            unladen_mass=0.0,
            rebuy_cost=0,
            are_all_modules_healthy=False,
        ),
    )


class TestStreamAppHeaderStatsUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_maps_game_stats_snapshot_to_view_model(self):
        game_state_protocol = FakeGameStateProtocol(
            game_stats_snapshots=[_game_stats_snapshot()]
        )
        use_case = StreamAppHeaderStatsUseCase(game_state_protocol)  # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].player_name, "TestCommander")
        self.assertEqual(results[0].player_ship, "Sidewinder")
        self.assertEqual(results[0].credits, 1000000)

    async def test_maps_empty_player_stats_to_empty_view_model(self):
        game_state_protocol = FakeGameStateProtocol(
            game_stats_snapshots=[
                _game_stats_snapshot(player_name="", player_ship="", player_credits=0)
            ]
        )
        use_case = StreamAppHeaderStatsUseCase(game_state_protocol)  # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(results[0].player_name, "")
        self.assertEqual(results[0].player_ship, "")
        self.assertEqual(results[0].credits, 0)

    async def test_yields_multiple_view_models_in_stream_order(self):
        snapshots = [
            _game_stats_snapshot(player_ship="Sidewinder"),
            _game_stats_snapshot(player_ship="Cobra Mk III"),
            _game_stats_snapshot(player_ship="Anaconda"),
        ]
        game_state_protocol = FakeGameStateProtocol(game_stats_snapshots=snapshots)
        use_case = StreamAppHeaderStatsUseCase(game_state_protocol)  # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(
            [view_model.player_ship for view_model in results],
            ["Sidewinder", "Cobra Mk III", "Anaconda"],
        )


if __name__ == "__main__":
    unittest.main()
