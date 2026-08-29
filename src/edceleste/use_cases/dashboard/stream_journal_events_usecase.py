from collections.abc import AsyncGenerator

from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.ui.widgets.dashboard.view_models.journal_log_view_model import (
    JournalLogViewModel,
)


class StreamJournalEventsUseCase:
    game_state_reader: GameStateProtocol

    def __init__(self, game_state_reader: GameStateProtocol):
        self.game_state_reader = game_state_reader

    async def __call__(self) -> AsyncGenerator[JournalLogViewModel, None]:
        async for event in self.game_state_reader.stream_journal_events():
            yield JournalLogViewModel.from_event(event)
