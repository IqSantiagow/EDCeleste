import pytest
import yaml
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import Input, Label

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from edceleste.ui.screens.settings.settings_screen import SettingsScreen

pytestmark = pytest.mark.anyio


def save_state_text(app: App) -> str:
    indicator = app.screen.query_one("#settings-header-modified-indicator", Label)
    if indicator.has_class("hidden"):
        return ""
    return str(indicator.content)


def section_shows_modified_indicator(app: App, section_id: str) -> bool:
    indicator = app.screen.query_one(f"#{section_id} .warning-label", Label)
    return not indicator.has_class("hidden")


def section_error_text(app: App, section_id: str) -> str:
    error_label = app.screen.query_one(f"#{section_id} .error-message-label", Label)
    return str(error_label.content)


def saved_config(edceleste) -> dict:
    return yaml.safe_load(edceleste.config_file.read_text())


async def open_settings_section(edceleste, pilot: Pilot, section_id: str) -> None:
    await pilot.press("ctrl+r")
    await edceleste.wait_until(
        pilot,
        lambda: isinstance(pilot.app.screen, SettingsScreen),
        "the settings screen",
    )
    await pilot.click(f"#settings-sections-column #{section_id}")
    await pilot.pause()


async def test_should_save_a_changed_setting_to_config_yaml_and_go_back_on_escape(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)
        await open_settings_section(edceleste, pilot, "settings-game_actions")

        await pilot.click("#game-actions-enabled-input Switch")
        await pilot.pause()

        assert save_state_text(pilot.app) == "◉ MODIFIED"
        assert section_shows_modified_indicator(pilot.app, "settings-game_actions")

        await pilot.press("ctrl+s")
        await edceleste.wait_until(
            pilot,
            lambda: save_state_text(pilot.app) == "◉ SAVED",
            "SAVED in the settings header",
        )

        assert saved_config(edceleste)["game_actions"]["enabled"] is True
        assert not section_shows_modified_indicator(pilot.app, "settings-game_actions")

        await pilot.press("escape")
        await pilot.pause()

        assert isinstance(pilot.app.screen, DashboardScreen)


async def test_should_show_the_validation_error_in_the_section_and_keep_config_yaml(
    edceleste,
):
    config_before_saving = edceleste.config_file.read_text()

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)
        await open_settings_section(edceleste, pilot, "settings-paths")

        await pilot.click("#journal-path-input")
        await edceleste.wait_until(
            pilot,
            lambda: isinstance(pilot.app.focused, Input),
            "the journal path field focused for typing",
        )
        await pilot.press("end", *"_missing", "enter")
        await pilot.pause()

        await pilot.press("ctrl+s")
        await edceleste.wait_until(
            pilot,
            lambda: save_state_text(pilot.app) == "◉ ERROR DURING SAVING",
            "ERROR DURING SAVING in the settings header",
        )

        missing_journal_path = edceleste.settings.paths.journal_path + "_missing"
        assert (
            section_error_text(pilot.app, "settings-paths")
            == f"✗ Journal path '{missing_journal_path}' does not exist."
        )
        assert edceleste.config_file.read_text() == config_before_saving
