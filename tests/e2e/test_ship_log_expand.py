import allure
import pytest
from textual.app import App

pytestmark = [pytest.mark.anyio, allure.feature("Ship log")]


def ship_log_is_full_width(app: App) -> bool:
    wide_ship_log = app.screen.query_one("#ship-log-wide")
    ship_log_rail = app.screen.query_one("#ship-log-rail")
    assert wide_ship_log.display != ship_log_rail.display
    return wide_ship_log.display


@allure.title("Ctrl+E switches the ship log between the rail and full width")
async def test_should_switch_the_ship_log_between_the_rail_and_full_width_on_ctrl_e(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the ship log sits in the rail"):
            assert not ship_log_is_full_width(pilot.app)

        with allure.step("When the Commander presses Ctrl+E"):
            await pilot.press("ctrl+e")

        with allure.step("Then the ship log opens full width"):
            assert ship_log_is_full_width(pilot.app)

        with allure.step("When the Commander presses Ctrl+E again"):
            await pilot.press("ctrl+e")

        with allure.step("Then the ship log goes back to the rail"):
            assert not ship_log_is_full_width(pilot.app)


@allure.title("The station card opens the ship log full width and Ctrl+E keeps it")
async def test_should_open_the_station_card_full_width_and_keep_it_on_ctrl_e(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("When the Commander clicks the station tab in the rail"):
            await pilot.click("#ship-log-rail #--content-tab-ship-log-tab-stn")

        with allure.step("Then the ship log opens full width"):
            assert ship_log_is_full_width(pilot.app)

        with allure.step("When the Commander presses Ctrl+E"):
            await pilot.press("ctrl+e")

        with allure.step("Then the ship log stays full width"):
            assert ship_log_is_full_width(pilot.app)
