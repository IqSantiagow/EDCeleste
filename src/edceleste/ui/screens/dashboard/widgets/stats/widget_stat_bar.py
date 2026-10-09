from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label, ProgressBar
from textual.renderables.bar import Bar as BarRenderable

FULL_PERCENT = 100.0


# Full block characters instead of Textual's thin default line, so the bar
# looks like a solid gauge.
class ThickBarRenderable(BarRenderable):
    HALF_BAR_LEFT = "▐"
    BAR = "█"
    HALF_BAR_RIGHT = "▌"


class ThickProgressBar(ProgressBar):
    BAR_RENDERABLE = ThickBarRenderable


class WidgetStatBar(HorizontalGroup):
    DEFAULT_CLASSES = "stat-bar"

    def __init__(self, label: str, **kwargs) -> None:
        """label is the short name shown left of the bar, e.g. "HULL"."""
        super().__init__(**kwargs)
        self.label = label

    def compose(self) -> ComposeResult:
        """Label, a thick progress bar out of 100 without ETA and percentage,
        and a value text that starts as "-" until update_bar() runs."""
        yield Label(self.label, classes="stat-label")
        yield ThickProgressBar(
            total=FULL_PERCENT,
            show_eta=False,
            show_percentage=False,
            classes="stat-bar-track",
        )
        yield Label("-", classes="stat-bar-value")

    def update_bar(self, filled_percent: float, value_text: str) -> None:
        """filled_percent is 0-100. value_text is shown as it is right of the
        bar, so the caller picks the unit, e.g. "87%" or "12 / 32 t"."""
        self.query_one(ThickProgressBar).update(progress=filled_percent)
        self.query_one(".stat-bar-value", Label).update(value_text)
