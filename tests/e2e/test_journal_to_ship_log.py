import allure
import pytest

from tests.e2e.conftest import ship_log_events

pytestmark = [pytest.mark.anyio, allure.feature("Ship log")]


@allure.title("An event the game writes to the journal shows in the ship log")
async def test_should_show_an_event_written_to_the_journal_in_the_ship_log(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("When the game writes FSDJump to the journal"):
            edceleste.append_journal_event("FSDJump")

        with allure.step("Then the ship log shows FSDJump"):
            await edceleste.wait_until(
                pilot,
                lambda: "FSDJump" in ship_log_events(pilot.app),
                "FSDJump in the ship log",
            )
