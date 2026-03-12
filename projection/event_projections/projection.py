from abc import abstractmethod
from typing import Protocol


class Projection(Protocol):
    @abstractmethod
    def process_event(self, event):
        pass

    @abstractmethod
    def create_projection(self) -> str:
        pass
