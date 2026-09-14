from typing import AsyncGenerator

from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.ui.screens.dashboard.view_models.game_stats_view_model import (
    FlightAndDriveViewModel,
)


class StreamFlightAndDriveStatsUseCase:
    def __init__(self, game_state_protocol: GameStateProtocol):
        self.game_state_protocol = game_state_protocol

    async def __call__(self) -> AsyncGenerator[FlightAndDriveViewModel, None]:
        async for game_state in self.game_state_protocol.stream_game_stats():
            yield FlightAndDriveViewModel(
                fuel=game_state.flight_drive.fuel_level,
                fuel_capacity=game_state.flight_drive.fuel_capacity,
                is_scooping=game_state.flight_drive.is_scooping_fuel,
                fuel_reservoir=game_state.flight_drive.fuel_reservoir,
                jump_range=game_state.flight_drive.max_jump_range,
                fsd_module=game_state.flight_drive.fsd_module_item,
            )
