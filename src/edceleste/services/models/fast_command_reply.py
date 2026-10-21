from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FastCommandReply:
    """The answer of Instinct to a pilot command. text goes to COMMS and to the
    conversation history. is_spoken tells whether Celeste says it out loud: it is
    False when the game state says the same thing by itself a moment later
    (see ACTIONS_SAID_BY_GAME_STATE), or the pilot would hear it twice."""

    text: str
    is_spoken: bool = True
