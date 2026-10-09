from textual.containers import VerticalScroll

from edceleste.services.models.keybinds_model import Keybind
from edceleste.ui.widgets.common.widget_labeled_value_row import WidgetLabeledValueRow
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader


from edceleste.ui.screens.settings.widgets.widget_base_settings_container import (
    WidgetBaseSettingsContainer,
)


class WidgetKeybindsContainer(WidgetBaseSettingsContainer):
    DEFAULT_CLASSES = "settings-container"
    BORDER_TITLE = "KEYBINDS"

    def __init__(self, keybinds: list[Keybind], *args, **kwargs) -> None:
        """Read only section. keybinds are only shown, nothing here can change
        them, so this section never posts SectionSettingsChanged."""
        super().__init__(*args, **kwargs)
        self.keybinds = keybinds

    def compose(self):
        """A scrollable list with one "action  key combo" row per keybind."""
        yield from super().compose()
        yield WidgetSectionHeader("LOADED KEYBINDS")
        with VerticalScroll(id="keybinds-entry-container"):
            for keybind in self.keybinds:
                yield WidgetLabeledValueRow(keybind.action, keybind_as_text(keybind))


def keybind_as_text(keybind: Keybind) -> str:
    """LeftShift+L, or "no keyboard key" for an action bound only elsewhere."""
    if keybind.key is None:
        return "no keyboard key"
    return "+".join([*keybind.modifiers, keybind.key])
