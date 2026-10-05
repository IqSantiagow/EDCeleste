import pytest

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen

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
