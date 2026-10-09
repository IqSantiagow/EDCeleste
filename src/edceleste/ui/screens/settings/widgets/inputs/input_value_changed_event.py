from textual.message import Message


class ValueChanged[T](Message):
    def __init__(self, sender_id: str, new_value: T) -> None:
        """Posted by every settings input row when the pilot changes its value.

        It bubbles up to the section container (paths, LLM, TTS, ...), which
        uses sender_id (the row's widget id) to know which settings field to
        write new_value into.
        """
        super().__init__()
        self.new_value = new_value
        self.sender_id = sender_id
