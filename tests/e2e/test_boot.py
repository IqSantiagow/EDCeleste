import allure
import pytest
from textual.app import App

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from edceleste.ui.screens.system_check.system_check_screen import (
    SystemCheckRow,
    SystemCheckScreen,
)

pytestmark = [pytest.mark.anyio, allure.feature("Start-up and preflight")]


@allure.title("EDCeleste opens the dashboard after a passing preflight")
async def test_should_open_the_dashboard_after_a_passing_preflight(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("Then the dashboard is open"):
            assert isinstance(pilot.app.screen, DashboardScreen)


@allure.title("EDCeleste stops watching the journal when the Commander quits")
async def test_should_stop_watching_the_journal_when_the_app_closes(edceleste):
    game_watcher_service = edceleste.container.game_watcher_service()

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And EDCeleste watches the journal"):
            assert game_watcher_service._game_watcher_tasks != []

        with allure.step("When the Commander quits with Ctrl+C"):
            await pilot.press("ctrl+c")

    with allure.step("Then EDCeleste no longer watches the journal"):
        assert game_watcher_service._game_watcher_tasks == []


def preflight_row(app: App, service_name: str) -> SystemCheckRow:
    return app.screen.query_one(f"#system-check-row-{service_name}", SystemCheckRow)


@allure.title("The preflight stops on an invalid config.yaml")
async def test_should_stop_the_preflight_on_an_invalid_config(edceleste):
    with allure.step("Given config.yaml has no valid settings"):
        edceleste.config_file.write_text("paths: {}")

    with allure.step("When EDCeleste starts"):
        async with edceleste.run_app() as pilot:
            with allure.step("Then the preflight marks the settings as failed"):
                await edceleste.wait_until(
                    pilot,
                    lambda: preflight_row(pilot.app, "settings").state == "failed",
                    "the settings row marked as failed",
                )
                await pilot.pause()
                assert (
                    preflight_row(pilot.app, "settings").error_message
                    == "Failed to load settings from config.yaml."
                )

            with allure.step("And the preflight stops before the journal check"):
                assert isinstance(pilot.app.screen, SystemCheckScreen)
                assert preflight_row(pilot.app, "game_watcher").state == "pending"


@allure.title("The preflight stops when the journal folder is missing")
async def test_should_stop_the_preflight_when_the_journal_folder_is_missing(
    edceleste, tmp_path
):
    missing_journal_folder = tmp_path / "missing_journal"

    with allure.step("Given the journal path in config.yaml points to no folder"):
        edceleste.settings.paths.journal_path = str(missing_journal_folder)
        edceleste.save_config()

    with allure.step("When EDCeleste starts"):
        async with edceleste.run_app() as pilot:
            with allure.step("Then the preflight marks the journal check as failed"):
                await edceleste.wait_until(
                    pilot,
                    lambda: preflight_row(pilot.app, "game_watcher").state == "failed",
                    "the game watcher row marked as failed",
                )
                await pilot.pause()
                assert (
                    preflight_row(pilot.app, "game_watcher").error_message
                    == f"No journal files found in '{missing_journal_folder}'."
                )

            with allure.step("And the preflight stops before the keybinds check"):
                assert isinstance(pilot.app.screen, SystemCheckScreen)
                assert preflight_row(pilot.app, "keybinds").state == "pending"
