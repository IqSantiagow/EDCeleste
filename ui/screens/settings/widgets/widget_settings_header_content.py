from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label


class WidgetSettingsHeaderContent(HorizontalGroup):
    def compose(self) -> ComposeResult:
        yield Label(" > SETTINGS", id="settings-header-label", classes="text-bold")
