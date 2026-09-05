from textual.widget import Widget
from typing import Any


class WidgetBaseInput(Widget):
    def __init__(
        self,
        *args,
        value: Any = None,
        initial_value: Any = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        assert self.id is not None, "WidgetBaseInput must have an id"
        self.value = value
        self.initial_value = initial_value
        assert self.value is not None, "WidgetBaseInput must have a value"

    def is_modified(self) -> bool:
        return self.value != self.initial_value

    def reset_current_value(self) -> None:
        self.initial_value = self.value
