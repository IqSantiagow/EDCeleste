from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label
from textual.reactive import reactive

from edceleste.ui.screens.settings.widgets.save_states import SaveState


class WidgetSettingsHeader(HorizontalGroup):
    def __init__(self, **kwargs) -> None:
        super().__init__(classes="settings-header", **kwargs)

    def compose(self) -> ComposeResult:
        yield Label(content="SETTINGS", id="settings-title")
        yield WidgetSettingsHeaderContent()


class WidgetSettingsHeaderContent(HorizontalGroup):
    save_state: reactive[SaveState] = reactive(SaveState.IDLE)

    def compose(self) -> ComposeResult:
        yield Label(" > SETTINGS", id="settings-header-label")
        yield Label(
            "", classes="warning-label hidden", id="settings-header-modified-indicator"
        )

    def watch_save_state(self) -> None:
        self._render_indicator()

    def _render_indicator(self) -> None:
        label = self.query_one(".warning-label", Label)
        label.remove_class("error")
        label.remove_class("success")

        if self.save_state is SaveState.MODIFIED:
            label.update("◉ MODIFIED")
            label.remove_class("hidden")
        elif self.save_state is SaveState.SAVING:
            label.update("◉ SAVING...")
            label.remove_class("hidden")
        elif self.save_state is SaveState.FAILED:
            label.update("◉ ERROR DURING SAVING")
            label.add_class("error")
            label.remove_class("hidden")
        elif self.save_state is SaveState.SAVED:
            label.update("◉ SAVED")
            label.remove_class("hidden")
            label.add_class("success")
        else:
            label.add_class("hidden")
