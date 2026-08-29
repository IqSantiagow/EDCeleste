from copy import deepcopy
import logging

from textual import on
from textual.containers import Grid
from textual.screen import Screen
from textual.widgets import ContentSwitcher, Footer, Label, LoadingIndicator
from edceleste.ui.screens.settings.widgets.inputs.widget_settings_row import (
    WidgetSettingsRow,
)
from textual.reactive import reactive
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel

from edceleste.ui.screens.settings.events.settings_events import (
    SectionSettingsChanged,
)
from edceleste.ui.screens.settings.widgets.const_ids import (
    SECTION_ERROR_FIELD_TO_SECTION_TO_INPUT_WIDGET_ID,
)
from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.widgets.widget_settings_header_content import (
    SaveState,
    WidgetSettingsHeaderContent,
    WidgetSettingsHeaderModifiedIndicator,
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
    # TODO: The whole settings screen logic and state management is a pure shit
    # and needs to be refactored. Well, at least it works XD
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

        current_section_state = getattr(
            self.settings_state, message.section.name.lower()
        )

        modified_fields_count_in_section = self.compare_dicts_and_return_modified_count(
            current_section_state.model_dump(),
            getattr(
                self._initial_settings_state, message.section.name.lower()
            ).model_dump(),
        )

        if modified_fields_count_in_section > 0:
            self.query_one(
                WidgetSettingsSectionsColumn
            ).change_section_modified_indicator(message.section, should_show=True)
        else:
            self.query_one(
                WidgetSettingsSectionsColumn
            ).change_section_modified_indicator(message.section, should_show=False)

        self.query_one(
            WidgetSettingsHeaderModifiedIndicator
        ).set_number_of_modified_fields(
            self.compare_dicts_and_return_modified_count(
                self.settings_state.model_dump(),
                self._initial_settings_state.model_dump(),
            )
        )

    def compare_dicts_and_return_modified_count(
        self, setting_a: dict, setting_b: dict
    ) -> int:
        number_of_changes = 0
        for field in set(setting_a.keys()):
            if isinstance(setting_a[field], dict):
                number_of_changes += self.compare_dicts_and_return_modified_count(
                    setting_a[field], setting_b[field]
                )
            else:
                if setting_a[field] == setting_b[field]:
                    continue
                number_of_changes += 1
        return number_of_changes

    def action_validate_and_save_settings(self) -> None:
        if not self.settings_state:
            return
        if (
            self.compare_dicts_and_return_modified_count(
                self.settings_state.model_dump(),
                self._initial_settings_state.model_dump(),
            )
            == 0
        ):
            return
        failures = self.settings_repository.update_settings(self.settings_state)
        if failures:
            self.query_one(
                WidgetSettingsHeaderModifiedIndicator
            ).save_state = SaveState.FAILED
            self.notify_about_failures_to_inputs(failures)
        else:
            self.query_one(
                WidgetSettingsHeaderModifiedIndicator
            ).save_state = SaveState.SAVED
            self._initial_settings_state = deepcopy(self.settings_state)
            self.reset_all_validation_states()

    def notify_about_failures_to_inputs(
        self, failures: list[SettingsIssueModel]
    ) -> None:
        if not failures:
            return
        for failure in failures:
            failure_field_id = failure.field
            error_message = failure.message
            input_id = SECTION_ERROR_FIELD_TO_SECTION_TO_INPUT_WIDGET_ID.get(
                failure_field_id, (None, None)
            )[1]
            if not input_id:
                logging.warning(
                    f"Failed to find input widget id for error field "
                    f"'{failure_field_id}'. The fuck happened here?"
                )
                continue
            input_widget = self.query_one(f"#{input_id}", expect_type=WidgetSettingsRow)
            input_widget.notify_about_validation_failure(error_message)

    def reset_all_validation_states(self) -> None:
        for input_widget in self.query(WidgetSettingsRow):
            input_widget.reset_validation_state()
        self.query_one(WidgetSettingsSectionsColumn).reset_all_modified_indicators()
