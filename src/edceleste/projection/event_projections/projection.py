from abc import abstractmethod
from typing import Protocol


class Projection(Protocol):
    @abstractmethod
    def process_event(self, event):
        """GameStateService calls it for EVERY game event, not only the ones
        this projection cares about. It copies the values of the events it
        knows into its own fields and skips the rest. Publishes nothing."""
        pass

    @abstractmethod
    def create_projection(self) -> str:
        """Turns the stored fields into plain sentences for the LLM prompt,
        each ending with a period and joined with one space. GameStateService
        calls it after every event and puts the text of every projection on
        its own line. An empty string means nothing worth saying, and the line
        is left out."""
        pass
