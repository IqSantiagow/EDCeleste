import pytest
from textual.app import App

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from edceleste.ui.screens.system_check.system_check_screen import (
    SystemCheckRow,
    SystemCheckScreen,
)

pytestmark = pytest.mark.anyio


async def test_should_open_the_dashboard_after_a_passing_preflight(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        assert isinstance(pilot.app.screen, DashboardScreen)


async def test_should_stop_watching_the_journal_when_the_app_closes(edceleste):
    game_watcher_service = edceleste.container.game_watcher_service()

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)
        assert game_watcher_service._game_watcher_tasks != []

    assert game_watcher_service._game_watcher_tasks == []


def preflight_row(app: App, service_name: str) -> SystemCheckRow:
    return app.screen.query_one(f"#system-check-row-{service_name}", SystemCheckRow)


async def test_should_stop_the_preflight_on_an_invalid_config(edceleste):
    edceleste.config_file.write_text("paths: {}")

    async with edceleste.run_app() as pilot:
        await edceleste.wait_until(
            pilot,
            lambda: preflight_row(pilot.app, "settings").state == "failed",
            "the settings row marked as failed",
        )
        await pilot.pause()

        assert isinstance(pilot.app.screen, SystemCheckScreen)
        assert (
            preflight_row(pilot.app, "settings").error_message
            == "Failed to load settings from config.yaml."
        )
        assert preflight_row(pilot.app, "game_watcher").state == "pending"


async def test_should_stop_the_preflight_when_the_journal_folder_is_missing(
    edceleste, tmp_path
):
    missing_journal_folder = tmp_path / "missing_journal"
    edceleste.settings.paths.journal_path = str(missing_journal_folder)
    edceleste.save_config()

    async with edceleste.run_app() as pilot:
        await edceleste.wait_until(
            pilot,
            lambda: preflight_row(pilot.app, "game_watcher").state == "failed",
            "the game watcher row marked as failed",
        )
        await pilot.pause()

        assert isinstance(pilot.app.screen, SystemCheckScreen)
        assert (
            preflight_row(pilot.app, "game_watcher").error_message
            == f"No journal files found in '{missing_journal_folder}'."
        )
        assert preflight_row(pilot.app, "keybinds").state == "pending"
