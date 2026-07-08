from textual import on
from textual.containers import Grid
from textual.screen import Screen
from textual.widgets import Footer, Label

from ui.screens.settings.widgets.widget_settings_header_content import (
    WidgetSettingsHeaderContent,
)
from ui.screens.settings.widgets.widget_settings_section_content_column import (
    SectionToShow,
    WidgetSettingsSectionContentColumn,
)
from ui.screens.settings.widgets.widget_settings_sections_column import (
    WidgetSettingsSectionsColumn,
)
from ui.widgets.app_header import AppHeader


class SettingsScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, settings_repository, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings_repository = settings_repository

    def compose(self):
        with Grid(id="settings-grid", classes="screen-grid"):
            yield AppHeader(content=WidgetSettingsHeaderContent())
            yield Label(
                id="sections-title", classes="shady header-title", content="SECTIONS"
            )
            yield Label(
                id="keybinds-title", classes="shady header-title", content="KEYBINDS"
            )
            yield WidgetSettingsSectionsColumn(id="settings-sections-column")
            yield WidgetSettingsSectionContentColumn(
                settings_repository=self.settings_repository,
                id="settings-section-content-column",
            )
            yield Footer()

    @on(WidgetSettingsSectionsColumn.WidgetSettingsSectionSelected)
    def on_widget_settings_sections_item_selected(
        self, event: WidgetSettingsSectionsColumn.WidgetSettingsSectionSelected
    ) -> None:
        self.query_one(
            WidgetSettingsSectionContentColumn
        ).section_to_show_state = SectionToShow[event.section]
