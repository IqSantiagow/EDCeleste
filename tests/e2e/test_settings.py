import allure
import pytest
import yaml
from textual.app import App
from textual.widgets import Input, Label

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from tests.e2e.conftest import open_settings_section

pytestmark = [pytest.mark.anyio, allure.feature("Settings")]


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


@allure.title("A changed setting is saved to config.yaml and Escape goes back")
async def test_should_save_a_changed_setting_to_config_yaml_and_go_back_on_escape(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens Settings > Game actions"):
            await open_settings_section(edceleste, pilot, "settings-game_actions")

        with allure.step("When the Commander turns game actions on"):
            await pilot.click("#game-actions-enabled-input Switch")
            await pilot.pause()

        with allure.step("Then the header and the section show MODIFIED"):
            assert save_state_text(pilot.app) == "◉ MODIFIED"
            assert section_shows_modified_indicator(pilot.app, "settings-game_actions")

        with allure.step("When the Commander saves with Ctrl+S"):
            await pilot.press("ctrl+s")

        with allure.step("Then the header shows SAVED and config.yaml has the change"):
            await edceleste.wait_until(
                pilot,
                lambda: save_state_text(pilot.app) == "◉ SAVED",
                "SAVED in the settings header",
            )
            assert saved_config(edceleste)["game_actions"]["enabled"] is True
            assert not section_shows_modified_indicator(
                pilot.app, "settings-game_actions"
            )

        with allure.step("When the Commander presses Escape"):
            await pilot.press("escape")
            await pilot.pause()

        with allure.step("Then the dashboard is back"):
            assert isinstance(pilot.app.screen, DashboardScreen)


@allure.title("An invalid journal path shows an error and config.yaml stays as it was")
async def test_should_show_the_validation_error_in_the_section_and_keep_config_yaml(
    edceleste,
):
    config_before_saving = edceleste.config_file.read_text()

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens Settings > Paths"):
            await open_settings_section(edceleste, pilot, "settings-paths")

        with allure.step(
            "When the Commander changes the journal path to a missing folder"
        ):
            await pilot.click("#journal-path-input")
            await edceleste.wait_until(
                pilot,
                lambda: isinstance(pilot.app.focused, Input),
                "the journal path field focused for typing",
            )
            await pilot.press("end", *"_missing", "enter")
            await pilot.pause()

        with allure.step("And saves with Ctrl+S"):
            await pilot.press("ctrl+s")

        with allure.step("Then the header shows ERROR DURING SAVING"):
            await edceleste.wait_until(
                pilot,
                lambda: save_state_text(pilot.app) == "◉ ERROR DURING SAVING",
                "ERROR DURING SAVING in the settings header",
            )

        with allure.step("And the Paths section says the folder does not exist"):
            missing_journal_path = edceleste.settings.paths.journal_path + "_missing"
            assert (
                section_error_text(pilot.app, "settings-paths")
                == f"✗ Journal path '{missing_journal_path}' does not exist."
            )

        with allure.step("And config.yaml is unchanged"):
            assert edceleste.config_file.read_text() == config_before_saving


@allure.title(
    "A changed Edge voice is saved to config.yaml as the engine and its params"
)
async def test_should_save_the_engine_and_its_voice_to_config_yaml(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens Settings > Text to speech"):
            await open_settings_section(edceleste, pilot, "settings-tts")
            await edceleste.wait_until(
                pilot,
                lambda: pilot.app.screen.query("#voice-input Select"),
                "the list of Edge voices",
            )

        with allure.step("When the Commander picks the voice en-US-AriaNeural"):
            await pilot.click("#voice-input Select")
            await pilot.pause()
            await pilot.press("down", "enter")
            await pilot.pause()

        with allure.step("And saves with Ctrl+S"):
            await pilot.press("ctrl+s")
            await edceleste.wait_until(
                pilot,
                lambda: save_state_text(pilot.app) == "◉ SAVED",
                "SAVED in the settings header",
            )

        with allure.step("Then config.yaml has Edge as the engine with that voice"):
            saved_tts = saved_config(edceleste)["tts"]
            assert saved_tts["provider"] == "edge"
            assert saved_tts["params"] == {"voice": "en-US-AriaNeural"}
