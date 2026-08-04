from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.reactive import reactive
from textual.widgets import Label, ListItem, ListView
from textual.message import Message
from ui.screens.settings.widgets.const_ids import SettingsSection

_SECTIONS_LABELS_WITH_ID: dict[str, str] = {
    "settings-keybinds": "KEYBINDS",
    "settings-paths": "PATHS",
    "settings-event-reactions": "EVENT REACTIONS",
    "settings-llm": "LLM",
}


class WidgetSettingsSectionsColumn(ListView):
    class WidgetSettingsSectionSelected(Message):
        def __init__(self, section_id: str) -> None:
            self.section_id = section_id
            super().__init__()

    def compose(self) -> ComposeResult:
        for item_id, label in _SECTIONS_LABELS_WITH_ID.items():
            yield WidgetSettingsSectionListItem(
                label, id=item_id, classes="section-nav-item"
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id is None:
            return
        self.post_message(self.WidgetSettingsSectionSelected(section_id=event.item.id))

    def change_section_modified_indicator(
        self, section: SettingsSection, should_show: bool
    ) -> None:
        item_id = next(
            (
                item_id
                for item_id, sec in _SECTIONS_LABELS_WITH_ID.items()
                if sec == section.name
            ),
            None,
        )
        if item_id is not None:
            list_item = self.query_one(f"#{item_id}", WidgetSettingsSectionListItem)
            list_item.should_show_changed_indicator = should_show

    def reset_all_modified_indicators(self) -> None:
        for item_id in _SECTIONS_LABELS_WITH_ID:
            list_item = self.query_one(f"#{item_id}", WidgetSettingsSectionListItem)
            list_item.should_show_changed_indicator = False


class WidgetSettingsSectionListItem(ListItem):
    should_show_changed_indicator: reactive[bool] = reactive(False)

    def __init__(self, label: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.label = label

    def compose(self) -> ComposeResult:
        with HorizontalGroup():
            yield Label(self.label, classes="section-label")
            yield Label("◉", classes="warning-label hidden")

    def watch_should_show_changed_indicator(self, should_show: bool) -> None:
        self.query_one(".warning-label", Label).remove_class("hidden")
        if not should_show:
            self.query_one(".warning-label", Label).add_class("hidden")
