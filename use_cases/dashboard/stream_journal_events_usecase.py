from collections.abc import AsyncGenerator

from protocols.game_state_reader import GameStateReader
from ui.widgets.dashboard.view_models.journal_log_view_model import JournalLogViewModel


class StreamJournalEventsUseCase:
    game_state_reader: GameStateReader

    def __init__(self, game_state_reader: GameStateReader):
        self.game_state_reader = game_state_reader

    async def __call__(self) -> AsyncGenerator[JournalLogViewModel, None]:
         async for event in self.game_state_reader.stream_journal_events():
             yield JournalLogViewModel.from_event(event)

             
    

            