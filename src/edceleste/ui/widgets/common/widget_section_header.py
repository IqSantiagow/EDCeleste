from textual.app import ComposeResult
from textual.containers import VerticalGroup
from textual.widgets import Label, Rule


class WidgetSectionHeader(VerticalGroup):
    def __init__(self, title: str, **kwargs) -> None:
        """Only keeps the title, the Label is built in compose()."""
        super().__init__(**kwargs)
        self.title = title

    def compose(self) -> ComposeResult:
        """The title with a horizontal line under it, styled by the
        section-header-label and section-divider classes in ui/css.tcss."""
        yield Label(self.title, classes="section-header-label")
        yield Rule(orientation="horizontal", classes="section-divider")
