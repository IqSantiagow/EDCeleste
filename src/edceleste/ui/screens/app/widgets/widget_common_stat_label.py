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
        """text is the key shown before the value, e.g. "CMDR". value_color and
        color_reactivity are only stored: nothing draws the value in that
        color yet."""
        super().__init__(**kwargs)
        self.text = text
        self.stat_value = stat_value
        self.value_color = value_color
        self.color_reactivity = color_reactivity

    def compose(self):
        """Key and value side by side ("CMDR " + value). When
        color_reactivity is set, it first picks value_color from the value,
        but that color is not used by any Label."""
        if self.color_reactivity:
            self.value_color = self.color_reactivity(self.stat_value)
        with Horizontal():
            yield Label(self.text + " ", classes="stat-key")
            yield Label(self.stat_value, classes="stat-value")

    def update_value(self, value: str) -> None:
        """Redraws only the value Label, the key stays. color_reactivity is not
        run again here."""
        self.stat_value = value
        self.query_one(".stat-value", Label).update(value)
