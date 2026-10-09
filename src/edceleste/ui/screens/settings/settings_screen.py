from copy import deepcopy
import logging

from textual import on
from textual.containers import Grid
from textual.screen import Screen
from textual.widgets import ContentSwitcher, Footer, LoadingIndicator
from textual.reactive import reactive
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel

from edceleste.ui.screens.app.widgets.app_header import AppHeader
from edceleste.ui.screens.settings.events.settings_events import (
    SectionSettingsChanged,
)

from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.widgets.widget_base_settings_container import (
    WidgetBaseSettingsContainer,
)
from edceleste.ui.screens.settings.widgets.widget_settings_section_content_column import (  # noqa: E501
    WidgetSettingsSectionContentColumn,
)
from edceleste.ui.screens.settings.widgets.widget_settings_sections_column import (
    WidgetSettingsSectionsColumn,
)
from edceleste.ui.screens.settings.widgets.widget_settings_header import (
    WidgetSettingsHeader,
    WidgetSettingsHeaderContent,
)
from edceleste.ui.screens.settings.widgets.save_states import SaveState

logger = logging.getLogger(__name__)


class SettingsScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("ctrl+s", "validate_and_save_settings", "Save Settings"),
    ]

    # The unsaved copy the pilot is editing. Setting it recomposes the screen.
    settings_state: reactive[SettingsModel | None] = reactive(None, recompose=True)

    _initial_settings_state: SettingsModel

    def __init__(self, settings_repository: SettingsRepository, *args, **kwargs):
        """Only stores the repository. The settings are read in on_mount()."""
        super().__init__(*args, **kwargs)
        self.settings_repository = settings_repository

    def on_mount(self) -> None:
        """Reads the saved settings and gives the screen its own copy to edit,
        so nothing changes for the app until the pilot saves. Setting
        settings_state recomposes the screen, which swaps the loading
        indicator for the section content."""
        self._initial_settings_state = self.settings_repository.get_settings()
        self.settings_state = deepcopy(self._initial_settings_state)

    def compose(self):
        """Runs again every time settings_state is set. Before the settings are
        read (None) a LoadingIndicator stands in for the section content.
        After that the content column gets its own copy of the settings and
        the keybinds already loaded from the game's .binds file."""
        yield AppHeader()
        yield WidgetSettingsHeader()
        with Grid(id="settings-grid", classes="screen-grid"):
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
        """Runs when the pilot picks a section in the left column. Switches the
        right column to the container with the same id, e.g.
        "settings-llm"."""
        self.query_one("#settings-content-switcher", ContentSwitcher).current = format(
            event.section_id
        )

    def on_section_settings_changed(self, message: SectionSettingsChanged) -> None:
        """Runs every time an input in a section changes.

        1. Puts the new section value into the unsaved settings copy.
        2. Shows or hides the "changed" mark of that section in the left
           column, depending on whether its inputs differ from the saved
           values.
        3. Sets the header to MODIFIED when any section differs, else IDLE.
        Nothing is validated or saved here. Before on_mount() has read the
        settings the message is ignored.
        """
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

    async def action_validate_and_save_settings(self) -> None:
        """Runs on ctrl+s. Every service checks the edited settings, the LLM
        check goes to the network.

        - Any issue: nothing is saved, the header shows FAILED and every
          section with an issue shows its error message.
        - No issue: the settings are saved to config.yaml and every service
          reloads with them (done by the repository). The header shows SAVED
          and all "changed" marks and errors are cleared.
        Before on_mount() has read the settings it does nothing.
        """
        if not self.settings_state:
            return

        failures = await self.settings_repository.validate_and_save_settings(
            self.settings_state
        )
        if failures:
            self.query_one(WidgetSettingsHeaderContent).save_state = SaveState.FAILED
            self.show_validation_errors_in_sections(failures)
        else:
            self.query_one(WidgetSettingsHeaderContent).save_state = SaveState.SAVED
            self._initial_settings_state = deepcopy(self.settings_state)
            self.mark_all_sections_as_saved()

    def show_validation_errors_in_sections(
        self, failures: list[SettingsIssueModel]
    ) -> None:
        """Shows each issue's message in the section container named by
        issue.section, e.g. "llm" -> #settings-llm. Two issues for the same
        section: the last one wins. An empty list does nothing."""
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

    def mark_all_sections_as_saved(self) -> None:
        """Called after a successful save.

        1. Hides the "changed" mark of every section in the left column.
        2. In every section hides the error box and makes the current input
           values the new saved values, so they no longer count as modified.
        """
        self.query_one(WidgetSettingsSectionsColumn).reset_all_modified_indicators()
        for container in self.query(WidgetBaseSettingsContainer):
            container.hide_error_and_mark_values_as_saved()
