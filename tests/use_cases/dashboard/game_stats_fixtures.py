"""Shared builders for GameStatsSnapshot based use case tests.

Every stats use case reads one snapshot and maps it to a view model, so the
tests would otherwise repeat the same large snapshot setup over and over.
"""

from collections.abc import AsyncGenerator

from edceleste.services.models.game_stats import (
    FlightDriveStats,
    GameStatsSnapshot,
    NavigationStats,
    PlayerStats,
    ShipStats,
)


class FakeGameStateProtocol:
    def __init__(self, game_stats_snapshots=None):
        self.game_stats_snapshots = game_stats_snapshots or []

    async def stream_game_stats(self) -> AsyncGenerator[GameStatsSnapshot, None]:
        for snapshot in self.game_stats_snapshots:
            yield snapshot


def make_player_stats(**overrides) -> PlayerStats:
    defaults = dict(name="TestCommander", ship="Sidewinder", credits=1000000)
    defaults.update(overrides)
    return PlayerStats(**defaults)  # type: ignore


def make_navigation_stats(**overrides) -> NavigationStats:
    defaults = dict(
        current_star_system="Sol",
        system_security_level="High",
        system_allegiance="Federation",
        system_government="Democracy",
        system_economy="Refinery",
        system_second_economy="Industrial",
        system_population=22780919531,
        current_body="Earth",
        is_in_supercruise=False,
        route_next_star_system="Alpha Centauri",
        route_remaining_jumps=3,
    )
    defaults.update(overrides)
    return NavigationStats(**defaults)  # type: ignore


def make_flight_drive_stats(**overrides) -> FlightDriveStats:
    defaults = dict(
        fuel_level=12.5,
        fuel_capacity=32.0,
        fuel_reservoir=0.42,
        is_scooping_fuel=False,
        max_jump_range=18.75,
        fsd_module_item="int_hyperdrive_size5_class5",
    )
    defaults.update(overrides)
    return FlightDriveStats(**defaults)  # type: ignore


def make_ship_stats(**overrides) -> ShipStats:
    defaults = dict(
        is_landing_gear_down=False,
        are_hardpoints_deployed=False,
        are_lights_on=False,
        are_shields_up=True,
        pips_system=8,
        pips_engine=4,
        pips_weapons=2,
        cargo_current=16.0,
        cargo_capacity=64,
        legal_status="Clean",
        hull_health=0.87,
        unladen_mass=285.6,
        rebuy_cost=1234567,
        are_all_modules_healthy=True,
    )
    defaults.update(overrides)
    return ShipStats(**defaults)  # type: ignore


def make_game_stats_snapshot(
    player=None, navigation=None, flight_drive=None, ship=None
) -> GameStatsSnapshot:
    return GameStatsSnapshot(
        player=player or make_player_stats(),
        navigation=navigation or make_navigation_stats(),
        flight_drive=flight_drive or make_flight_drive_stats(),
        ship=ship or make_ship_stats(),
    )
