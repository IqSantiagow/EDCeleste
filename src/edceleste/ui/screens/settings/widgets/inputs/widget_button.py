from textual.content import Content
from textual.widgets import Button


class WidgetButton(Button):
    def __init__(self, value: str, **kwargs) -> None:
        """A flat button whose label is drawn as "[value]". Content keeps the
        brackets as plain text, so Textual does not read them as markup."""
        super().__init__(
            Content(f"[{value}]"),
            flat=True,
            **kwargs,
        )
