from collections.abc import AsyncGenerator
from typing import Protocol

from edceleste.services.models.game_events import GameEvent
from edceleste.services.models.game_stats import GameStatsSnapshot
from edceleste.services.models.market_stats import MarketSnapshot


class GameStateProtocol(Protocol):
    """The three stream_* methods are broadcasts: every call gets its own
    queue, so two widgets can listen at the same time and both get every item.
    A stream never ends by itself. It stops listening when the caller stops
    iterating."""

    def stream_game_stats(
        self,
    ) -> AsyncGenerator[GameStatsSnapshot, None]:
        """Yields the current stats at once, then a fresh snapshot after every
        Status.json or Market.json update. Journal lines change the stats too,
        but they show up only with the next Status.json update, which the game
        writes about every second."""
        ...

    def stream_journal_events(self) -> AsyncGenerator[GameEvent, None]:
        """Yields only events read from the Journal*.log file, never the
        Status.json or Market.json ones. Starts with the next event, nothing
        from before the call is replayed."""
        ...

    def stream_market(self) -> AsyncGenerator[MarketSnapshot, None]:
        """Yields the current station market at once, then a new snapshot only
        after Market, Docked, Undocked or Location. Status.json is left out on
        purpose, so the commodity table is not rebuilt every second."""
        ...

    def get_game_state_projection(self) -> str:
        """The game state as text for the LLM prompt, built from all
        projections. An empty string means no event has arrived yet, e.g. the
        game is not running."""
        ...
