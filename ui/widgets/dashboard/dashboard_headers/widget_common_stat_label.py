from collections.abc import Callable

from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Label


class WidgetCommonStatLabel(Widget):
    """A label for displaying common statistics in the dashboard."""

    def __init__(
        self,
        text: str,
        stat_value: str,
        value_color: str | None = None,
        color_reactivity: Callable[[str], str] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.text = text
        self.stat_value = stat_value
        self.value_color = value_color
        self.color_reactivity = color_reactivity

    def compose(self):
        if self.color_reactivity:
            self.value_color = self.color_reactivity(self.stat_value)
        with Horizontal():
            yield Label(self.text + ": ", classes="stat-key")
            yield Label(self.stat_value, classes="stat-value")

    def update_value(self, value: str) -> None:
        self.stat_value = value
        self.query_one(".stat-value", Label).update(value)
