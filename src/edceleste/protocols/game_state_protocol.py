from collections.abc import AsyncGenerator
from typing import Protocol

from edceleste.services.models.game_events import GameEvent
from edceleste.services.models.game_stats import GameStatsSnapshot


class GameStateProtocol(Protocol):
    def stream_game_stats(
        self,
    ) -> AsyncGenerator[GameStatsSnapshot, None]: ...

    def stream_journal_events(self) -> AsyncGenerator[GameEvent, None]: ...

    def get_game_state_projection(self) -> str: ...
