import allure
import pytest

from tests.e2e.conftest import recorded_journal_line, ship_log_events

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


@allure.title("Cyrillic and Polish letters in the journal do not stop the ship log")
async def test_should_keep_showing_events_after_a_journal_line_with_non_english_letters(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step(
            "When the game writes a Docked line with the station name "
            "Привет, Łódź and then an FSDJump to the journal"
        ):
            docked_line = recorded_journal_line("Docked").replace(
                "Fan Horizons", "Привет, Łódź"
            )
            with edceleste.journal_file.open("a", encoding="utf-8") as journal:
                journal.write(docked_line + "\n")
            edceleste.append_journal_event("FSDJump")

        with allure.step("Then the ship log shows FSDJump"):
            await edceleste.wait_until(
                pilot,
                lambda: "FSDJump" in ship_log_events(pilot.app),
                "FSDJump in the ship log after the line with non-English letters",
            )
