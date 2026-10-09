from collections.abc import AsyncGenerator
import logging
from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.ui.screens.app.view_models.app_header_view_model import (
    AppHeaderViewModel,
)


logger = logging.getLogger(__name__)


class StreamAppHeaderStatsUseCase:
    def __init__(self, game_state_protocol: GameStateProtocol) -> None:
        self.game_state_protocol = game_state_protocol

    async def __call__(self) -> AsyncGenerator[AppHeaderViewModel, None]:
        """Never ends. Listens to the game stats stream and keeps only the
        pilot name, ship and credits for the app header. The current values
        come at once, then again after every Status.json update."""
        async for game_stats in self.game_state_protocol.stream_game_stats():
            yield AppHeaderViewModel(
                player_name=game_stats.player.name,
                player_ship=game_stats.player.ship,
                credits=game_stats.player.credits,
            )
