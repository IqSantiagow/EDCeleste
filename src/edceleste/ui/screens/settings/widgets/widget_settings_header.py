from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label
from textual.reactive import reactive

from edceleste.ui.screens.settings.widgets.save_states import SaveState


class WidgetSettingsHeader(HorizontalGroup):
    def __init__(self, **kwargs) -> None:
        """Always gets the "settings-header" CSS class, extra classes passed
        in kwargs would clash with it."""
        super().__init__(classes="settings-header", **kwargs)

    def compose(self) -> ComposeResult:
        """The "SETTINGS" title and the breadcrumb with the save state marker
        (WidgetSettingsHeaderContent)."""
        yield Label(content="SETTINGS", id="settings-title")
        yield WidgetSettingsHeaderContent()


class WidgetSettingsHeaderContent(HorizontalGroup):
    save_state: reactive[SaveState] = reactive(SaveState.IDLE)

    def compose(self) -> ComposeResult:
        """The breadcrumb and the save state marker, hidden at the start."""
        yield Label(" > SETTINGS", id="settings-header-label")
        yield Label(
            "", classes="warning-label hidden", id="settings-header-modified-indicator"
        )

    def watch_save_state(self) -> None:
        """The settings screen sets save_state when the pilot changes a value
        and when saving fails or succeeds. Nothing sets SAVING yet."""
        self._render_indicator()

    def _render_indicator(self) -> None:
        """MODIFIED and SAVING in yellow, ERROR DURING SAVING in red, SAVED in
        green. IDLE hides the marker."""
        label = self.query_one(".warning-label", Label)
        label.remove_class("error")
        label.remove_class("success")

        match self.save_state:
            case SaveState.MODIFIED:
                label.update("◉ MODIFIED")
                label.remove_class("hidden")
            case SaveState.SAVING:
                label.update("◉ SAVING...")
                label.remove_class("hidden")
            case SaveState.FAILED:
                label.update("◉ ERROR DURING SAVING")
                label.add_class("error")
                label.remove_class("hidden")
            case SaveState.SAVED:
                label.update("◉ SAVED")
                label.remove_class("hidden")
                label.add_class("success")
            case _:
                label.add_class("hidden")
