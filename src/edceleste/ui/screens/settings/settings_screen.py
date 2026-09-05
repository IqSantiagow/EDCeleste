from copy import deepcopy
import logging

from textual import on
from textual.containers import Grid
from textual.screen import Screen
from textual.widgets import ContentSwitcher, Footer, Label, LoadingIndicator
from textual.reactive import reactive
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel

from edceleste.ui.screens.settings.events.settings_events import (
    SectionSettingsChanged,
)

from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.widgets.widget_base_settings_container import (
    WidgetBaseSettingsContainer,
)
from edceleste.ui.screens.settings.widgets.widget_settings_header_content import (
    SaveState,
    WidgetSettingsHeaderContent,
)
from edceleste.ui.screens.settings.widgets.widget_settings_section_content_column import (  # noqa: E501
    WidgetSettingsSectionContentColumn,
)
from edceleste.ui.screens.settings.widgets.widget_settings_sections_column import (
    WidgetSettingsSectionsColumn,
)
from edceleste.ui.widgets.app_header import AppHeader

logger = logging.getLogger(__name__)


class SettingsScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("ctrl+s", "validate_and_save_settings", "Save Settings"),
    ]

    settings_state: reactive[SettingsModel | None] = reactive(None, recompose=True)

    _initial_settings_state: SettingsModel

    def __init__(self, settings_repository: SettingsRepository, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings_repository = settings_repository

    def on_mount(self) -> None:
        self._initial_settings_state = self.settings_repository.get_settings()
        self.settings_state = deepcopy(self._initial_settings_state)

    def compose(self):
        logger.debug("Composing SettingsScreen")
        with Grid(id="settings-grid", classes="screen-grid"):
            yield AppHeader(content=WidgetSettingsHeaderContent())
            yield Label(id="sections-title", classes="header-title", content="SECTIONS")
            yield Label(id="keybinds-title", classes="header-title", content="KEYBINDS")
            yield WidgetSettingsSectionsColumn(id="settings-sections-column")
            if not self.settings_state:
                yield LoadingIndicator()
            else:
                yield WidgetSettingsSectionContentColumn(
                    settings=deepcopy(self.settings_state),
                    keybinds=self.settings_repository.get_keybinds(),
                    id="settings-section-content-column",
                )
            yield Footer()

    @on(WidgetSettingsSectionsColumn.WidgetSettingsSectionSelected)
    def on_widget_settings_sections_item_selected(
        self, event: WidgetSettingsSectionsColumn.WidgetSettingsSectionSelected
    ) -> None:
        self.query_one("#settings-content-switcher", ContentSwitcher).current = format(
            event.section_id
        )

    def on_section_settings_changed(self, message: SectionSettingsChanged) -> None:
        if not self.settings_state:
            return

        setattr(self.settings_state, message.section.name.lower(), message.new_value)

        is_section_modified = (
            self.query(WidgetBaseSettingsContainer)
            .filter(f"#settings-{message.section.name.lower()}")
            .first()
            .is_modified()
        )

        self.query_one(WidgetSettingsSectionsColumn).change_section_modified_indicator(
            message.section, should_show=is_section_modified
        )

        is_any_section_modified = any(
            container.is_modified()
            for container in self.query(WidgetBaseSettingsContainer)
        )

        self.query_one(WidgetSettingsHeaderContent).save_state = (
            SaveState.MODIFIED if is_any_section_modified else SaveState.IDLE
        )

    def action_validate_and_save_settings(self) -> None:
        if not self.settings_state:
            return

        failures = self.settings_repository.update_settings(self.settings_state)
        if failures:
            self.query_one(WidgetSettingsHeaderContent).save_state = SaveState.FAILED
            self.notify_about_failures_to_sections(failures)
        else:
            self.query_one(WidgetSettingsHeaderContent).save_state = SaveState.SAVED
            self._initial_settings_state = deepcopy(self.settings_state)
            self.reset_all_validation_states()

    def notify_about_failures_to_sections(
        self, failures: list[SettingsIssueModel]
    ) -> None:
        if not failures:
            return
        for failure in failures:
            error_message = failure.message

            section_widget = (
                self.query(WidgetBaseSettingsContainer)
                .filter(
                    f"#settings-{failure.section.lower()}",
                )
                .first()
            )
            section_widget.show_validation_error(error_message)

    def reset_all_validation_states(self) -> None:
        self.query_one(WidgetSettingsSectionsColumn).reset_all_modified_indicators()
        for container in self.query(WidgetBaseSettingsContainer):
            container.reset_validation_state()
