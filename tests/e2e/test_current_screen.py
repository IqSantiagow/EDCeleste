import logging

import allure
import pytest

from tests.e2e.conftest import comms_entries
from tests.e2e.test_journal_to_dashboard_stats import header_value, label_text
from tests.e2e.test_startup_loading import (
    fuel_in_the_hud,
    remember_prompts_and_answer,
    write_the_files_of_a_session_in_progress,
)

pytestmark = [
    pytest.mark.anyio,
    allure.feature("Celeste knows which screen the pilot is on"),
]

# The numbers the game writes as GuiFocus to Status.json
COCKPIT = 0
LEFT_PANEL = 2
GALAXY_MAP = 6

STATUS_SUPERCRUISE = 16


def screen_changes_in_the_log(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("Screen changed")
    ]


def screen_in_the_game_stats(edceleste) -> str:
    game_stats = edceleste.container.game_state_service().get_game_stats()
    return str(game_stats.player.screen)


async def pilot_is_on_screen(edceleste, pilot, gui_focus: int, screen: str) -> None:
    """The game writes Status.json with the screen and Celeste learns it"""
    edceleste.write_status_file(gui_focus=gui_focus)
    await edceleste.wait_until(
        pilot,
        lambda: screen_in_the_game_stats(edceleste) == screen,
        f"{screen} in the game stats",
    )


@allure.title("Opening and closing the left panel is written to the log")
async def test_should_log_opening_and_closing_the_left_panel(edceleste, caplog):
    caplog.set_level(logging.INFO)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the game reports the pilot in the cockpit"):
            await pilot_is_on_screen(edceleste, pilot, COCKPIT, "cockpit")

        with allure.step("When the pilot opens the left panel"):
            await pilot_is_on_screen(edceleste, pilot, LEFT_PANEL, "left panel")

        with allure.step(
            "Then the log says the screen changed from cockpit to left panel"
        ):
            assert screen_changes_in_the_log(caplog)[-1] == (
                "Screen changed from cockpit to left panel"
            )

        with allure.step("And the pilot closes the left panel"):
            await pilot_is_on_screen(edceleste, pilot, COCKPIT, "cockpit")

        with allure.step(
            "Then the log says the screen changed from left panel to cockpit"
        ):
            assert screen_changes_in_the_log(caplog) == [
                "Screen changed from unknown to cockpit",
                "Screen changed from cockpit to left panel",
                "Screen changed from left panel to cockpit",
            ]


@allure.title("Opening and closing the galaxy map is written to the log")
async def test_should_log_opening_and_closing_the_galaxy_map(edceleste, caplog):
    caplog.set_level(logging.INFO)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the game reports the pilot in the cockpit"):
            await pilot_is_on_screen(edceleste, pilot, COCKPIT, "cockpit")

        with allure.step("When the pilot opens the galaxy map"):
            await pilot_is_on_screen(edceleste, pilot, GALAXY_MAP, "galaxy map")

        with allure.step(
            "Then the log says the screen changed from cockpit to galaxy map"
        ):
            assert screen_changes_in_the_log(caplog)[-1] == (
                "Screen changed from cockpit to galaxy map"
            )

        with allure.step("And the pilot closes the galaxy map"):
            await pilot_is_on_screen(edceleste, pilot, COCKPIT, "cockpit")

        with allure.step(
            "Then the log says the screen changed from galaxy map to cockpit"
        ):
            assert screen_changes_in_the_log(caplog) == [
                "Screen changed from unknown to cockpit",
                "Screen changed from cockpit to galaxy map",
                "Screen changed from galaxy map to cockpit",
            ]


@allure.title("The same screen written again is not logged as a change")
async def test_should_not_log_a_change_while_the_screen_stays_the_same(
    edceleste, caplog
):
    caplog.set_level(logging.INFO)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the game reports the pilot in the cockpit"):
            await pilot_is_on_screen(edceleste, pilot, COCKPIT, "cockpit")

        with allure.step("When the game writes Status.json again, in the cockpit"):
            edceleste.write_status_file(fuel_main=12.5, gui_focus=COCKPIT)
            await edceleste.wait_until(
                pilot,
                lambda: fuel_in_the_hud(pilot.app) == "12.5",
                "12.5 tonnes of fuel in the HUD",
            )

        with allure.step("Then the log has only the first change, to the cockpit"):
            assert screen_changes_in_the_log(caplog) == [
                "Screen changed from unknown to cockpit"
            ]


@allure.title(
    "Celeste started with the galaxy map open knows the screen and stays silent"
)
async def test_should_know_the_galaxy_map_is_open_and_stay_silent_at_the_start(
    edceleste, caplog
):
    prompts_sent_to_llm: list[str] = []
    caplog.set_level(logging.INFO)

    with allure.step("Given the game already wrote its journal and Status.json"):
        write_the_files_of_a_session_in_progress(edceleste)

    with allure.step("And the galaxy map is open in the game"):
        edceleste.write_status_file(fuel_main=12.5, cargo=3, gui_focus=GALAXY_MAP)

    with allure.step("And Celeste has a reaction to LoadGame in the settings"):
        edceleste.react_to_event("LoadGame")

    with allure.step("And the LLM remembers every prompt it receives"):
        edceleste.use_scripted_model(
            remember_prompts_and_answer(prompts_sent_to_llm, "Noted, Commander.")
        )

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="When")

        with allure.step("Then Celeste knows the game: the header shows SANTIAGOW"):
            await edceleste.wait_until(
                pilot,
                lambda: header_value(pilot.app, "#stat-cmdr") == "SANTIAGOW",
                "the commander name in the header",
            )
            await edceleste.wait_until(
                pilot,
                lambda: fuel_in_the_hud(pilot.app) == "12.5",
                "12.5 tonnes of fuel in the HUD",
            )

        with allure.step("And the screen is the galaxy map"):
            assert screen_in_the_game_stats(edceleste) == "galaxy map"

        with allure.step("And the log has no screen change"):
            assert screen_changes_in_the_log(caplog) == []

        with allure.step("And the LLM got no request"):
            assert prompts_sent_to_llm == []

        with allure.step("And COMMS shows no answer from Celeste"):
            assert comms_entries(pilot.app, "llm-response") == []

        with allure.step("And Celeste said nothing aloud"):
            assert edceleste.spoken_texts == []


@allure.title(
    "A Status.json without the screen makes it unknown and Celeste keeps running"
)
async def test_should_make_the_screen_unknown_when_status_json_has_no_screen(
    edceleste, caplog
):
    caplog.set_level(logging.INFO)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the game reports the pilot in the left panel"):
            await pilot_is_on_screen(edceleste, pilot, LEFT_PANEL, "left panel")

        with allure.step("When the game writes a Status.json without the screen"):
            edceleste.write_status_file(flags=STATUS_SUPERCRUISE)

        with allure.step("Then the screen is unknown"):
            await edceleste.wait_until(
                pilot,
                lambda: screen_in_the_game_stats(edceleste) == "unknown",
                "unknown in the game stats",
            )

        with allure.step("And Celeste keeps running: navigation shows SUPERCRUISE"):
            await edceleste.wait_until(
                pilot,
                lambda: label_text(pilot.app, "#navigation-status") == "SUPERCRUISE",
                "SUPERCRUISE in navigation",
            )
