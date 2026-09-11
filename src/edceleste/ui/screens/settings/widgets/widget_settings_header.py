from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label

from edceleste.ui.screens.settings.widgets.widget_settings_header_content import (
    WidgetSettingsHeaderContent,
)


class WidgetSettingsHeader(HorizontalGroup):
    def __init__(self, **kwargs) -> None:
        super().__init__(id="app-header", **kwargs)

    def compose(self) -> ComposeResult:
        yield Label(content="EDCELESTE", id="dashboard-title")
        yield WidgetSettingsHeaderContent()
