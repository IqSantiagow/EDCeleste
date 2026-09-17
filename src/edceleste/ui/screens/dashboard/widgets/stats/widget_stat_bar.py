from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label, ProgressBar
from textual.renderables.bar import Bar as BarRenderable

FULL_PERCENT = 100.0


class ThickBarRenderable(BarRenderable):
    HALF_BAR_LEFT = "▐"
    BAR = "█"
    HALF_BAR_RIGHT = "▌"


class ThickProgressBar(ProgressBar):
    BAR_RENDERABLE = ThickBarRenderable


class WidgetStatBar(HorizontalGroup):
    DEFAULT_CLASSES = "stat-bar"

    def __init__(self, label: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.label = label

    def compose(self) -> ComposeResult:
        yield Label(self.label, classes="stat-label")
        yield ThickProgressBar(
            total=FULL_PERCENT,
            show_eta=False,
            show_percentage=False,
            classes="stat-bar-track",
        )
        yield Label("-", classes="stat-bar-value")

    def update_bar(self, filled_percent: float, value_text: str) -> None:
        self.query_one(ThickProgressBar).update(progress=filled_percent)
        self.query_one(".stat-bar-value", Label).update(value_text)
