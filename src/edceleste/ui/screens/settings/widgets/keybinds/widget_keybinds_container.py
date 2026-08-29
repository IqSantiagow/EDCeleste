from textual.containers import VerticalScroll, Vertical

from edceleste.services.models.keybinds_model import Keybind
from edceleste.ui.widgets.common.widget_labeled_value_row import WidgetLabeledValueRow
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader


class WidgetKeybindsContainer(Vertical):
    def __init__(self, keybinds: list[Keybind], *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.keybinds = keybinds

    def compose(self):
        yield WidgetSectionHeader("LOADED KEYBINDS")
        with VerticalScroll(id="keybinds-entry-container"):
            for keybind in self.keybinds:
                yield WidgetLabeledValueRow(keybind.action, keybind.key)
