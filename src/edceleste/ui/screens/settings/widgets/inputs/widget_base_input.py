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
        """value is what the row shows now, initial_value is the last saved
        value. The section container compares the two to show the
        "modified" marker. Both an id and a value are required, the asserts
        fail otherwise."""
        super().__init__(*args, **kwargs)
        assert self.id is not None, "WidgetBaseInput must have an id"
        self.value = value
        self.initial_value = initial_value
        assert self.value is not None, "WidgetBaseInput must have a value"

    def is_modified(self) -> bool:
        """True when the pilot changed the value since the last save."""
        return self.value != self.initial_value

    def mark_current_value_as_saved(self) -> None:
        """Called after a successful save. The value on screen stays as it is,
        it only becomes the new saved value, so is_modified() turns False."""
        self.initial_value = self.value
