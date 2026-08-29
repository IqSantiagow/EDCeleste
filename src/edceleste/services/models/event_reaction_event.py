from pydantic import BaseModel

from edceleste.services.models.game_events import GameEvent


class EventReactionEvent(BaseModel):
    """
    Model used to represent an event that is sent to the LLM for processing.
    """

    event: GameEvent
