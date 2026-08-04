from textual.app import ComposeResult
from textual.containers import VerticalGroup
from textual.widgets import Label, Rule


class WidgetSectionHeader(VerticalGroup):
    def __init__(self, title: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.title = title

    def compose(self) -> ComposeResult:
        yield Label(self.title, classes="section-header-label")
        yield Rule(orientation="horizontal", classes="section-divider")
