from textual.content import Content
from textual.widgets import Button


class WidgetButton(Button):
    def __init__(self, value: str, **kwargs) -> None:
        super().__init__(
            Content(f"[{value}]"),
            flat=True,
            **kwargs,
        )
