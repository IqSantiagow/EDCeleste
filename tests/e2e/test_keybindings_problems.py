import os
import re
import time
from pathlib import Path

import allure
import pytest

from edceleste.ui.screens.system_check.system_check_screen import SystemCheckScreen
from tests import TEST_BINDS_FILE_LOCATION
from tests.e2e.conftest import (
    PILOT_AND_CELESTE_ENTRIES,
    comms_entries,
    comms_entry_types,
    send_comms_message,
)
from tests.e2e.test_boot import preflight_row
from tests.e2e.test_game_action_availability import (
    tell_the_pilot_what_the_scoop_tool_answered,
)

pytestmark = [pytest.mark.anyio, allure.feature("Broken or incomplete keybindings")]

KEYBINDS_NOT_LOADED = "Game actions are not available: the keybindings are not loaded."


def keybindings_folder(edceleste) -> Path:
    return Path(edceleste.settings.paths.keybindings_path)


def put_an_empty_file_as_the_newest_binds_file(edceleste) -> None:
    empty_file = keybindings_folder(edceleste) / "Newest.binds"
    empty_file.write_text("")
    one_minute_from_now = time.time() + 60
    os.utime(empty_file, (one_minute_from_now, one_minute_from_now))


def remove_supercruise_from_the_binds_file(edceleste) -> None:
    good_file_text = TEST_BINDS_FILE_LOCATION.read_text(encoding="utf-8")
    file_without_supercruise = re.sub(
        r"\s*<Supercruise>.*?</Supercruise>", "", good_file_text, flags=re.DOTALL
    )
    assert "<Supercruise>" not in file_without_supercruise
    (keybindings_folder(edceleste) / "Custom.4.2.binds").write_text(
        file_without_supercruise, encoding="utf-8"
    )


@allure.title("The dashboard opens even when the newest keybindings file is empty")
async def test_should_open_the_dashboard_when_the_newest_keybindings_file_is_empty(
    edceleste, monkeypatch
):
    with allure.step("Given the newest file in the keybindings folder is empty"):
        put_an_empty_file_as_the_newest_binds_file(edceleste)

    with allure.step("And the preflight stays open 2 s so the results can be read"):
        monkeypatch.setattr(SystemCheckScreen, "SECONDS_BEFORE_DASHBOARD", 2)

    with allure.step("When EDCeleste starts"):
        async with edceleste.run_app() as pilot:
            with allure.step("Then the preflight marks the keybinds check as failed"):
                await edceleste.wait_until(
                    pilot,
                    lambda: preflight_row(pilot.app, "keybinds").state == "failed",
                    "the keybinds row marked as failed",
                )
                await pilot.pause()
                assert preflight_row(pilot.app, "keybinds").error_message

            await edceleste.open_dashboard(pilot, step_keyword="And")


@allure.title("The dashboard opens even when the keybindings file misses an action")
async def test_should_open_the_dashboard_when_the_keybindings_file_misses_an_action(
    edceleste, monkeypatch
):
    with allure.step("Given the keybindings file has no Supercruise action"):
        remove_supercruise_from_the_binds_file(edceleste)

    with allure.step("And the preflight stays open 2 s so the results can be read"):
        monkeypatch.setattr(SystemCheckScreen, "SECONDS_BEFORE_DASHBOARD", 2)

    with allure.step("When EDCeleste starts"):
        async with edceleste.run_app() as pilot:
            with allure.step("Then the preflight marks the keybinds check as failed"):
                await edceleste.wait_until(
                    pilot,
                    lambda: preflight_row(pilot.app, "keybinds").state == "failed",
                    "the keybinds row marked as failed",
                )
                await pilot.pause()

            with allure.step("And the message names the missing Supercruise"):
                assert (
                    preflight_row(pilot.app, "keybinds").error_message
                    == "Missing required keybinds: Supercruise"
                )

            await edceleste.open_dashboard(pilot, step_keyword="And")


@allure.title("The dashboard opens even when there is no keybindings file at all")
async def test_should_open_the_dashboard_when_there_is_no_keybindings_file(
    edceleste, monkeypatch
):
    with allure.step("Given the keybindings folder has no file"):
        (keybindings_folder(edceleste) / "Custom.4.2.binds").unlink()

    with allure.step("And the preflight stays open 2 s so the results can be read"):
        monkeypatch.setattr(SystemCheckScreen, "SECONDS_BEFORE_DASHBOARD", 2)

    with allure.step("When EDCeleste starts"):
        async with edceleste.run_app() as pilot:
            with allure.step("Then the preflight marks the keybinds check as failed"):
                await edceleste.wait_until(
                    pilot,
                    lambda: preflight_row(pilot.app, "keybinds").state == "failed",
                    "the keybinds row marked as failed",
                )
                await pilot.pause()

            with allure.step("And the message says no keybindings file was found"):
                assert (
                    preflight_row(pilot.app, "keybinds").error_message
                    == f"No .binds files found in {keybindings_folder(edceleste)}"
                )

            await edceleste.open_dashboard(pilot, step_keyword="And")


@allure.title("Celeste says game actions are not available when the keybindings failed")
async def test_should_say_game_actions_are_unavailable_without_keybindings(
    edceleste,
):
    tool_answers_seen_by_llm: list[str] = []

    with allure.step("Given the newest file in the keybindings folder is empty"):
        put_an_empty_file_as_the_newest_binds_file(edceleste)

    with allure.step("And game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step(
        "And the LLM toggles the cargo scoop and repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            tell_the_pilot_what_the_scoop_tool_answered(tool_answers_seen_by_llm)
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'scoop' in COMMS"):
            await send_comms_message(pilot, "scoop")

        with allure.step(
            "Then COMMS shows Celeste relaying that the keybindings failed"
        ):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer after the game action",
            )
            assert comms_entries(pilot.app, "llm-response") == [
                f"Negative, Commander. {KEYBINDS_NOT_LOADED}"
            ]

        with allure.step("And COMMS shows no error line"):
            assert set(comms_entry_types(pilot.app)) <= PILOT_AND_CELESTE_ENTRIES

        with allure.step("And no key is pressed in the game"):
            assert edceleste.fake_keyboard.keyboard_log == []
