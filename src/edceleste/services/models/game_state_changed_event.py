from pydantic import BaseModel


class GameStateChangedEvent(BaseModel):
    """
    Model used to represent a game state change event.
    """

    game_state: str
