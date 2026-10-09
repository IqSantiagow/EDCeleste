from typing import AsyncGenerator

from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.ui.screens.dashboard.view_models.station_market_view_model import (
    StationMarketViewModel,
)


class StreamStationMarketUseCase:
    def __init__(self, game_state_protocol: GameStateProtocol):
        self.game_state_protocol = game_state_protocol

    async def __call__(self) -> AsyncGenerator[StationMarketViewModel, None]:
        """Never ends. Turns every market snapshot into the station market
        card. The current market comes at once, then a new one only after
        Market, Docked, Undocked or Location, not every second."""
        async for snapshot in self.game_state_protocol.stream_market():
            yield StationMarketViewModel.from_snapshot(snapshot)
