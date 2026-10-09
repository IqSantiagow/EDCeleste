from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.reactive import reactive
from textual.widgets import Label, ListItem, ListView
from textual.message import Message
from edceleste.ui.screens.settings.widgets.const_ids import SettingsSection

_SECTIONS_LABELS_WITH_ID: dict[str, str] = {
    "settings-keybinds": "KEYBINDS",
    "settings-paths": "PATHS",
    "settings-event_reactions": "EVENT REACTIONS",
    "settings-llm": "LLM",
    "settings-tts": "TTS",
    "settings-stt": "STT",
    "settings-game_actions": "GAME ACTIONS",
}


class WidgetSettingsSectionsColumn(ListView):
    DEFAULT_CLASSES = "settings-container"
    BORDER_TITLE = "SECTIONS"

    class WidgetSettingsSectionSelected(Message):
        def __init__(self, section_id: str) -> None:
            """Posted when the pilot picks a section in the list. section_id is
            the container id to show, e.g. "settings-tts". The settings screen
            switches the content to it."""
            self.section_id = section_id
            super().__init__()

    def compose(self) -> ComposeResult:
        """One list item per entry in _SECTIONS_LABELS_WITH_ID, in that
        order."""
        for item_id, label in _SECTIONS_LABELS_WITH_ID.items():
            yield WidgetSettingsSectionListItem(
                label, id=item_id, classes="section-nav-item"
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Runs on Enter or click on an item. Posts
        WidgetSettingsSectionSelected with the item id. An item without an id
        is ignored."""
        if event.item.id is None:
            return
        self.post_message(self.WidgetSettingsSectionSelected(section_id=event.item.id))

    def change_section_modified_indicator(
        self, section: SettingsSection, should_show: bool
    ) -> None:
        """Shows or hides the yellow "◉" next to one section. The item id is
        built from the enum name, so SettingsSection.EVENT_REACTIONS finds
        "settings-event_reactions"."""
        item_id = f"settings-{section.name.lower()}"
        list_item = self.query_one(f"#{item_id}", WidgetSettingsSectionListItem)
        list_item.should_show_changed_indicator = should_show

    def reset_all_modified_indicators(self) -> None:
        """Hides the "◉" next to every section. Called after a successful
        save."""
        for item_id in _SECTIONS_LABELS_WITH_ID:
            list_item = self.query_one(f"#{item_id}", WidgetSettingsSectionListItem)
            list_item.should_show_changed_indicator = False


class WidgetSettingsSectionListItem(ListItem):
    should_show_changed_indicator: reactive[bool] = reactive(False)

    def __init__(self, label: str, *args, **kwargs) -> None:
        """label is the section name shown in the list, e.g. "EVENT
        REACTIONS"."""
        super().__init__(*args, **kwargs)
        self.label = label

    def compose(self) -> ComposeResult:
        """The section name and a hidden "◉" modified marker after it."""
        with HorizontalGroup():
            yield Label(self.label, classes="section-label")
            yield Label("◉", classes="warning-label hidden")

    def watch_should_show_changed_indicator(self, should_show: bool) -> None:
        """Shows or hides the "◉" marker when should_show_changed_indicator is
        set by WidgetSettingsSectionsColumn."""
        self.query_one(".warning-label", Label).remove_class("hidden")
        if not should_show:
            self.query_one(".warning-label", Label).add_class("hidden")
