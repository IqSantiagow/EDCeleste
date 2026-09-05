from textual.containers import VerticalScroll

from edceleste.services.models.keybinds_model import Keybind
from edceleste.ui.widgets.common.widget_labeled_value_row import WidgetLabeledValueRow
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader


from edceleste.ui.screens.settings.widgets.widget_base_settings_container import (
    WidgetBaseSettingsContainer,
)


class WidgetKeybindsContainer(WidgetBaseSettingsContainer):
    def __init__(self, keybinds: list[Keybind], *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.keybinds = keybinds

    def compose(self):
        yield from super().compose()
        yield WidgetSectionHeader("LOADED KEYBINDS")
        with VerticalScroll(id="keybinds-entry-container"):
            for keybind in self.keybinds:
                yield WidgetLabeledValueRow(keybind.action, keybind.key)
