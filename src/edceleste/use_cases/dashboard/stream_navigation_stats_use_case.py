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
        """Never ends. Listens to the game stats stream and keeps only the
        star system, body, route and the supercruise flag, shown as
        "Supercruise" or "Normal space". The current values come at once, then
        again after every Status.json update."""
        async for game_stats in self.game_state_protocol.stream_game_stats():
            yield NavigationStatsViewModel(
                system=game_stats.navigation.current_star_system,
                security=game_stats.navigation.system_security_level,
                body=game_stats.navigation.current_body,
                status=SUPERCRUISE_STATUS
                if game_stats.navigation.is_in_supercruise
                else NORMAL_SPACE_STATUS,
                allegiance=game_stats.navigation.system_allegiance,
                government=game_stats.navigation.system_government,
                economy=game_stats.navigation.system_economy,
                second_economy=game_stats.navigation.system_second_economy,
                population=game_stats.navigation.system_population,
                route_next_system=game_stats.navigation.route_next_star_system,
                route_remaining_jumps=game_stats.navigation.route_remaining_jumps,
            )
