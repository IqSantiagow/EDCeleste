import shutil
from pathlib import Path

import allure
import pytest
import yaml
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import Input, Label

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from tests import TEST_BINDS_FILE_LOCATION
from tests.e2e.conftest import open_settings_section

pytestmark = [pytest.mark.anyio, allure.feature("Settings")]

JOURNAL_PATH_ROW = "journal-path-input"
KEYBINDS_PATH_ROW = "keybinds-path-input"


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


def path_is_shown_in_yellow(app: App, row_id: str) -> bool:
    # query, not query_one: while the row is drawn again it has no Label for a moment
    value_labels = app.screen.query(f"#{row_id} .entry-value")
    return len(value_labels) == 1 and value_labels.first().has_class("warning-label")


def path_is_shown_without_yellow(app: App, row_id: str) -> bool:
    value_labels = app.screen.query(f"#{row_id} .entry-value")
    return len(value_labels) == 1 and not value_labels.first().has_class(
        "warning-label"
    )


def path_text(app: App, row_id: str) -> str:
    return str(app.screen.query_one(f"#{row_id} .entry-value", Label).content)


def make_journal_folder_with_a_log_file(edceleste, folder_suffix: str) -> str:
    new_folder = Path(edceleste.settings.paths.journal_path + folder_suffix)
    new_folder.mkdir()
    (new_folder / "Journal.2026-10-05T120001.01.log").touch()
    return str(new_folder)


def make_keybinds_folder_with_a_binds_file(edceleste, folder_suffix: str) -> str:
    new_folder = Path(edceleste.settings.paths.keybindings_path + folder_suffix)
    new_folder.mkdir()
    shutil.copy(TEST_BINDS_FILE_LOCATION, new_folder / "Custom.4.2.binds")
    return str(new_folder)


async def edit_the_end_of_a_path(edceleste, pilot: Pilot, row_id: str, *keys: str):
    await pilot.click(f"#{row_id}")
    await edceleste.wait_until(
        pilot,
        lambda: isinstance(pilot.app.focused, Input),
        "the path field focused for typing",
    )
    await pilot.press("end", *keys, "enter")


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


@allure.title("A changed journal path is not yellow any more after a successful save")
async def test_should_remove_the_yellow_mark_from_the_journal_path_after_a_save(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens Settings > Paths"):
            await open_settings_section(edceleste, pilot, "settings-paths")

        with allure.step("And a folder with a journal file exists next to the journal"):
            new_journal_path = make_journal_folder_with_a_log_file(edceleste, "_new")

        with allure.step("And the Commander changes the journal path to that folder"):
            await edit_the_end_of_a_path(edceleste, pilot, JOURNAL_PATH_ROW, *"_new")
            await edceleste.wait_until(
                pilot,
                lambda: path_is_shown_in_yellow(pilot.app, JOURNAL_PATH_ROW),
                "the changed journal path in yellow",
            )

        with allure.step("When the Commander saves with Ctrl+S"):
            await pilot.press("ctrl+s")

        with allure.step("Then the header shows SAVED and config.yaml has the path"):
            await edceleste.wait_until(
                pilot,
                lambda: save_state_text(pilot.app) == "◉ SAVED",
                "SAVED in the settings header",
            )
            assert saved_config(edceleste)["paths"]["journal_path"] == new_journal_path

        with allure.step("And the journal path shows the new folder, not in yellow"):
            await edceleste.wait_until(
                pilot,
                lambda: path_is_shown_without_yellow(pilot.app, JOURNAL_PATH_ROW),
                "the journal path no longer in yellow",
            )
            assert path_text(pilot.app, JOURNAL_PATH_ROW) == new_journal_path


@allure.title(
    "A changed journal path and a changed keybinds path are not yellow any more "
    "after a successful save"
)
async def test_should_remove_the_yellow_mark_from_both_paths_after_a_save(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens Settings > Paths"):
            await open_settings_section(edceleste, pilot, "settings-paths")

        with allure.step("And a folder with a journal file exists next to the journal"):
            new_journal_path = make_journal_folder_with_a_log_file(edceleste, "_new")

        with allure.step("And a folder with keybinds exists next to the keybinds"):
            new_keybinds_path = make_keybinds_folder_with_a_binds_file(
                edceleste, "_new"
            )

        with allure.step("And the Commander changes both paths to those folders"):
            await edit_the_end_of_a_path(edceleste, pilot, JOURNAL_PATH_ROW, *"_new")
            await edceleste.wait_until(
                pilot,
                lambda: path_is_shown_in_yellow(pilot.app, JOURNAL_PATH_ROW),
                "the changed journal path in yellow",
            )
            await edit_the_end_of_a_path(edceleste, pilot, KEYBINDS_PATH_ROW, *"_new")
            await edceleste.wait_until(
                pilot,
                lambda: path_is_shown_in_yellow(pilot.app, KEYBINDS_PATH_ROW),
                "the changed keybinds path in yellow",
            )

        with allure.step("When the Commander saves with Ctrl+S"):
            await pilot.press("ctrl+s")

        with allure.step("Then the header shows SAVED and config.yaml has both paths"):
            await edceleste.wait_until(
                pilot,
                lambda: save_state_text(pilot.app) == "◉ SAVED",
                "SAVED in the settings header",
            )
            saved_paths = saved_config(edceleste)["paths"]
            assert saved_paths["journal_path"] == new_journal_path
            assert saved_paths["keybindings_path"] == new_keybinds_path

        with allure.step("And neither path is shown in yellow"):
            await edceleste.wait_until(
                pilot,
                lambda: (
                    path_is_shown_without_yellow(pilot.app, JOURNAL_PATH_ROW)
                    and path_is_shown_without_yellow(pilot.app, KEYBINDS_PATH_ROW)
                ),
                "both paths no longer in yellow",
            )
            assert path_text(pilot.app, JOURNAL_PATH_ROW) == new_journal_path
            assert path_text(pilot.app, KEYBINDS_PATH_ROW) == new_keybinds_path


@allure.title("A journal path that fails the check stays yellow and shows the error")
async def test_should_keep_the_journal_path_yellow_when_the_save_fails(edceleste):
    config_before_saving = edceleste.config_file.read_text()

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens Settings > Paths"):
            await open_settings_section(edceleste, pilot, "settings-paths")

        with allure.step("And a folder without any journal file exists"):
            folder_without_journal = Path(
                edceleste.settings.paths.journal_path + "_empty"
            )
            folder_without_journal.mkdir()

        with allure.step("And the Commander changes the journal path to that folder"):
            await edit_the_end_of_a_path(edceleste, pilot, JOURNAL_PATH_ROW, *"_empty")
            await edceleste.wait_until(
                pilot,
                lambda: path_is_shown_in_yellow(pilot.app, JOURNAL_PATH_ROW),
                "the changed journal path in yellow",
            )

        with allure.step("When the Commander saves with Ctrl+S"):
            await pilot.press("ctrl+s")

        with allure.step("Then the header shows ERROR DURING SAVING"):
            await edceleste.wait_until(
                pilot,
                lambda: save_state_text(pilot.app) == "◉ ERROR DURING SAVING",
                "ERROR DURING SAVING in the settings header",
            )

        with allure.step("And the Paths section says there are no journal files"):
            assert section_error_text(pilot.app, "settings-paths") == (
                f"✗ No journal log files found in '{folder_without_journal}'."
            )

        with allure.step("And the journal path is still shown in yellow"):
            await pilot.pause()
            assert path_is_shown_in_yellow(pilot.app, JOURNAL_PATH_ROW)
            assert path_text(pilot.app, JOURNAL_PATH_ROW) == str(folder_without_journal)

        with allure.step("And config.yaml is unchanged"):
            assert edceleste.config_file.read_text() == config_before_saving


@allure.title("A path typed back to the saved value is not shown in yellow")
async def test_should_not_show_the_path_in_yellow_when_the_saved_value_is_typed_back(
    edceleste,
):
    saved_journal_path = edceleste.settings.paths.journal_path

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens Settings > Paths"):
            await open_settings_section(edceleste, pilot, "settings-paths")

        with allure.step("And the Commander changes the journal path"):
            await edit_the_end_of_a_path(edceleste, pilot, JOURNAL_PATH_ROW, *"_x")
            await edceleste.wait_until(
                pilot,
                lambda: path_is_shown_in_yellow(pilot.app, JOURNAL_PATH_ROW),
                "the changed journal path in yellow",
            )
            await edceleste.wait_until(
                pilot,
                lambda: save_state_text(pilot.app) == "◉ MODIFIED",
                "MODIFIED in the settings header",
            )

        with allure.step("When the Commander types the saved path back"):
            await edit_the_end_of_a_path(
                edceleste, pilot, JOURNAL_PATH_ROW, "backspace", "backspace"
            )

        with allure.step("Then the journal path shows the saved path, not in yellow"):
            await edceleste.wait_until(
                pilot,
                lambda: path_is_shown_without_yellow(pilot.app, JOURNAL_PATH_ROW),
                "the journal path no longer in yellow",
            )
            assert path_text(pilot.app, JOURNAL_PATH_ROW) == saved_journal_path

        with allure.step("And the header does not show MODIFIED any more"):
            await edceleste.wait_until(
                pilot,
                lambda: save_state_text(pilot.app) == "",
                "no MODIFIED in the settings header",
            )
