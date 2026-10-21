from textual import on
from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Button, Label

from edceleste.services.models.keybinds_model import Keybind
from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_base_input import (
    WidgetBaseInput,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_button import WidgetButton
from edceleste.ui.screens.settings.widgets.stt.bind_hotkey_modal_screen import (
    BindHotkeyModalScreen,
)


class WidgetHotkeyRow(WidgetBaseInput):
    DEFAULT_CLASSES = "entry-row-full"

    def __init__(
        self, label: str, value: str, game_keybinds: list[Keybind], **kwargs
    ) -> None:
        """One row: label, the key as pynput names it ("Key.f9") and the [BIND]
        button. An empty value means no hotkey, the row shows "None".
        game_keybinds are passed on to the BIND modal, which refuses a key the
        game already uses."""
        super().__init__(value=value, initial_value=value, **kwargs)
        self.label = label
        self.game_keybinds = game_keybinds

    def compose(self) -> ComposeResult:
        with HorizontalGroup(id="settings-entry-row-container"):
            yield Label(self.label, classes="entry-label")
            yield Label(self.value or "None", id="hotkey-value-label")
            yield WidgetButton("BIND", id="hotkey-bind-button")

    @on(Button.Pressed, "#hotkey-bind-button")
    def open_bind_modal(self, event: Button.Pressed) -> None:
        """Stops the press here and opens BindHotkeyModalScreen. Its result
        goes to show_bound_key()."""
        event.stop()
        self.app.push_screen(
            BindHotkeyModalScreen(self.game_keybinds), callback=self.show_bound_key
        )

    def show_bound_key(self, key: str | None) -> None:
        """None means the pilot cancelled, nothing changes. Otherwise shows the
        key and tells the STT section, which marks the settings as modified."""
        if key is None:
            return
        self.value = key
        self.query_one("#hotkey-value-label", Label).update(key)
        self.post_message(ValueChanged(self.id, key))  # type: ignore
