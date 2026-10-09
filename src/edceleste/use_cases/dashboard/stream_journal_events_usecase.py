from collections.abc import AsyncGenerator

from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.ui.screens.dashboard.view_models.journal_log_view_model import (
    JournalLogViewModel,
)


class StreamJournalEventsUseCase:
    game_state_protocol: GameStateProtocol

    def __init__(self, game_state_protocol: GameStateProtocol):
        self.game_state_protocol = game_state_protocol

    async def __call__(self) -> AsyncGenerator[JournalLogViewModel, None]:
        """Never ends. Turns every new journal log event into one row for the
        dashboard journal log. Status.json and Market.json updates never come
        here, and events from before the call are not replayed."""
        async for event in self.game_state_protocol.stream_journal_events():
            yield JournalLogViewModel.from_event(event)
