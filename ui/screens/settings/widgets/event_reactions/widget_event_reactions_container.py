from textual.app import ComposeResult
from textual.containers import Vertical

from services.models.settings_model import SettingsModel
from ui.widgets.common.widget_section_header import WidgetSectionHeader


class WidgetEventReactionsContainer(Vertical):
    def __init__(self, settings_model: SettingsModel, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.settings_model = settings_model

    def compose(self) -> ComposeResult:
        yield WidgetSectionHeader("EVENT REACTIONS")
