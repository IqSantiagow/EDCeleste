from collections.abc import AsyncGenerator
from typing import Protocol

from edceleste.services.models.game_events import GameEvent
from edceleste.services.models.game_stats import GameStatsSnapshot
from edceleste.services.models.market_stats import MarketSnapshot


class GameStateProtocol(Protocol):
    def stream_game_stats(
        self,
    ) -> AsyncGenerator[GameStatsSnapshot, None]: ...

    def stream_journal_events(self) -> AsyncGenerator[GameEvent, None]: ...

    def stream_market(self) -> AsyncGenerator[MarketSnapshot, None]: ...

    def get_game_state_projection(self) -> str: ...
