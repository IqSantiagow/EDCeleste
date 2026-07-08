from textual.app import ComposeResult
from textual.widgets import Label, ListItem, ListView
from textual.message import Message


class WidgetSettingsSectionsColumn(ListView):
    DEFAULT_CLASSES = "p-x-1"

    class WidgetSettingsSectionSelected(Message):
        def __init__(self, section: str) -> None:
            self.section = section
            super().__init__()

    def compose(self) -> ComposeResult:
        yield ListItem(
            Label("KEYBINDS"), id="settings-keybinds-label", classes="shady p-b-1"
        )
        yield ListItem(Label("PATHS"), id="settings-paths-label", classes="shady p-b-1")
        yield ListItem(
            Label("EVENT REACTIONS"),
            id="settings-event-reactions-label",
            classes="shady p-b-1",
        )
        yield ListItem(
            Label("SYSTEM PROMPTS"),
            id="settings-system-prompts-label",
            classes="shady p-b-1",
        )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        selected_id = event.item.id
        if selected_id == "settings-keybinds-label":
            self.post_message(self.WidgetSettingsSectionSelected(section="KEYBINDS"))

        elif selected_id == "settings-paths-label":
            self.post_message(self.WidgetSettingsSectionSelected(section="PATHS"))
        elif selected_id == "settings-event-reactions-label":
            self.post_message(
                self.WidgetSettingsSectionSelected(section="EVENT_REACTIONS")
            )
        elif selected_id == "settings-system-prompts-label":
            self.post_message(
                self.WidgetSettingsSectionSelected(section="SYSTEM_PROMPTS")
            )
