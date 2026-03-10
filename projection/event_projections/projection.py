from abc import ABC, abstractmethod


class Projection(ABC):
    @abstractmethod
    def process_event(self, event):
        pass

    @abstractmethod
    def create_projection(self) -> str:
        pass
