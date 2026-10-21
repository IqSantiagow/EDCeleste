import allure
import pytest
from textual.app import App
from textual.widgets import Label, Switch

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from tests.e2e.test_settings import (
    save_state_text,
    saved_config,
    section_shows_modified_indicator,
)
from tests.e2e.test_ship_effect import SHIP_EFFECT_ROW
from tests.e2e.test_ship_replies import (
    STATUS_LANDING_GEAR_DOWN,
    game_changes_the_flags,
    game_writes_first_status_file,
    wait_for_the_gear_in_the_ship_panel,
)
from tests.e2e.test_voice_profiles import label_texts, open_text_to_speech_settings
from tests.e2e.test_voice_test import TEST_BUTTON

pytestmark = [pytest.mark.anyio, allure.feature("Ship replies setting")]

SHIP_REPLIES_ROW = "#play-ship-replies-input"


def ship_replies_switch(app: App) -> Switch:
    return app.screen.query_one(f"{SHIP_REPLIES_ROW} Switch", Switch)


async def turn_ship_replies_off_and_save(edceleste, pilot) -> None:
    await open_text_to_speech_settings(edceleste, pilot)
    await pilot.click(f"{SHIP_REPLIES_ROW} Switch")
    await edceleste.wait_until(
        pilot,
        lambda: save_state_text(pilot.app) == "◉ MODIFIED",
        "MODIFIED in the settings header",
    )
    await pilot.press("ctrl+s")
    await edceleste.wait_until(
        pilot,
        lambda: save_state_text(pilot.app) == "◉ SAVED",
        "SAVED in the settings header",
        timeout_seconds=15,
    )


@allure.title("Settings > Text to speech has a Ship replies switch, on by default")
async def test_should_show_the_ship_replies_switch_on_in_the_text_to_speech_settings(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="Given")

        with allure.step("When the Commander opens Settings > Text to speech"):
            await open_text_to_speech_settings(edceleste, pilot)

        with allure.step("Then the Ship replies switch is shown and it is on"):
            label = pilot.app.screen.query_one(
                f"{SHIP_REPLIES_ROW} .entry-label", Label
            )
            assert str(label.content) == "Ship replies:"
            assert ship_replies_switch(pilot.app).value is True

        with allure.step("And it says what the switch does"):
            assert (
                "say 'Landing gear deployed' and the like when a switch changes"
                in label_texts(pilot.app)
            )

        with allure.step("And it sits between the Ship effect row and Test voice"):
            screen = pilot.app.screen
            ship_effect_row = screen.query_one(SHIP_EFFECT_ROW).region.y
            ship_replies_row = screen.query_one(SHIP_REPLIES_ROW).region.y
            test_button_row = screen.query_one(TEST_BUTTON).region.y
            assert ship_effect_row < ship_replies_row < test_button_row


@allure.title("Turning Ship replies off and saving stores it in config.yaml")
async def test_should_save_ship_replies_switched_off_to_config_yaml(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step(
            "And the Commander opens Settings > Text to speech, Ship replies is on"
        ):
            await open_text_to_speech_settings(edceleste, pilot)
            assert ship_replies_switch(pilot.app).value is True

        with allure.step(
            "And the Commander turns Ship replies off, the settings show MODIFIED"
        ):
            await pilot.click(f"{SHIP_REPLIES_ROW} Switch")
            await edceleste.wait_until(
                pilot,
                lambda: save_state_text(pilot.app) == "◉ MODIFIED",
                "MODIFIED in the settings header",
            )
            assert ship_replies_switch(pilot.app).value is False
            assert section_shows_modified_indicator(pilot.app, "settings-tts")

        with allure.step("When the Commander saves with Ctrl+S"):
            await pilot.press("ctrl+s")

        with allure.step("Then the header shows SAVED"):
            await edceleste.wait_until(
                pilot,
                lambda: save_state_text(pilot.app) == "◉ SAVED",
                "SAVED in the settings header",
                timeout_seconds=15,
            )

        with allure.step("And config.yaml says Ship replies is off"):
            assert saved_config(edceleste)["tts"]["play_ship_replies"] is False

        with allure.step("And the ship effect and the volume are not touched"):
            assert saved_config(edceleste)["tts"]["ship_effect"] is True
            assert saved_config(edceleste)["tts"]["volume"] == 1.0


@allure.title("Right after saving Ship replies off Celeste stops saying the switches")
async def test_should_stop_saying_ship_switches_right_after_saving_ship_replies_off(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the game reports the landing gear up"):
            await game_writes_first_status_file(edceleste, pilot, flags=0)

        with allure.step("And the Commander turned Ship replies off and saved"):
            await turn_ship_replies_off_and_save(edceleste, pilot)

        with allure.step("And the Commander is back on the dashboard"):
            await pilot.press("escape")
            await edceleste.wait_until(
                pilot,
                lambda: isinstance(pilot.app.screen, DashboardScreen),
                "the dashboard",
            )

        with allure.step("When the game reports the landing gear down"):
            game_changes_the_flags(edceleste, STATUS_LANDING_GEAR_DOWN)

        with allure.step("Then the ship panel shows the gear down"):
            await wait_for_the_gear_in_the_ship_panel(edceleste, pilot)

        with allure.step("And Celeste said and played nothing"):
            await pilot.pause(0.5)
            assert edceleste.spoken_texts == []
            assert edceleste.played_audio == []
