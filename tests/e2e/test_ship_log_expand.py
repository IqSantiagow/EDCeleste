import pytest
from textual.app import App

pytestmark = pytest.mark.anyio


def ship_log_is_full_width(app: App) -> bool:
    wide_ship_log = app.screen.query_one("#ship-log-wide")
    ship_log_rail = app.screen.query_one("#ship-log-rail")
    assert wide_ship_log.display != ship_log_rail.display
    return wide_ship_log.display


async def test_should_switch_the_ship_log_between_the_rail_and_full_width_on_ctrl_e(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)
        assert not ship_log_is_full_width(pilot.app)

        await pilot.press("ctrl+e")
        assert ship_log_is_full_width(pilot.app)

        await pilot.press("ctrl+e")
        assert not ship_log_is_full_width(pilot.app)


async def test_should_open_the_station_card_full_width_and_keep_it_on_ctrl_e(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        await pilot.click("#ship-log-rail #--content-tab-ship-log-tab-stn")
        assert ship_log_is_full_width(pilot.app)

        await pilot.press("ctrl+e")
        assert ship_log_is_full_width(pilot.app)
