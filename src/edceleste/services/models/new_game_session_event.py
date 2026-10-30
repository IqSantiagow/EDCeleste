from pydantic import BaseModel


class NewGameSessionEvent(BaseModel):
    """
    Published by the game watcher when the game started again and writes a new
    journal file (not just the next part of the same long session). Whoever
    keeps the game state must forget the old session, the new journal file is
    loaded right after this event.
    """
