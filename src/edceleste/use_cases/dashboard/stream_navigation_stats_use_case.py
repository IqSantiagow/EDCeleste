from edceleste.protocols.game_state_protocol import GameStateProtocol
from typing import AsyncGenerator

from edceleste.ui.screens.dashboard.view_models.game_stats_view_model import (
    NavigationStatsViewModel,
)


SUPERCRUISE_STATUS = "Supercruise"
NORMAL_SPACE_STATUS = "Normal space"


class StreamNavigationStatsUseCase:
    def __init__(self, game_state_protocol: GameStateProtocol):
        self.game_state_protocol = game_state_protocol

    async def __call__(self) -> AsyncGenerator[NavigationStatsViewModel, None]:
        async for game_state in self.game_state_protocol.stream_game_stats():
            yield NavigationStatsViewModel(
                system=game_state.navigation.current_star_system,
                security=game_state.navigation.system_security_level,
                body=game_state.navigation.current_body,
                status=SUPERCRUISE_STATUS
                if game_state.navigation.is_in_supercruise
                else NORMAL_SPACE_STATUS,
                allegiance=game_state.navigation.system_allegiance,
                government=game_state.navigation.system_government,
                economy=game_state.navigation.system_economy,
                second_economy=game_state.navigation.system_second_economy,
                population=game_state.navigation.system_population,
                route_next_system=game_state.navigation.route_next_star_system,
                route_remaining_jumps=game_state.navigation.route_remaining_jumps,
            )
