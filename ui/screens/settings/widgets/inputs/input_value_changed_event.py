from textual.message import Message
from typing import TypeVar
from typing import Generic

T = TypeVar("T")


class ValueChanged(Message, Generic[T]):
    def __init__(self, sender_id: str, new_value: T) -> None:
        super().__init__()
        self.new_value = new_value
        self.sender_id = sender_id
