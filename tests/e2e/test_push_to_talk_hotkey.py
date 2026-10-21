import allure
import pytest
import yaml
from textual.pilot import Pilot
from textual.widgets import Label

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from edceleste.ui.screens.settings.settings_screen import SettingsScreen
from tests.e2e.conftest import (
    click_bind_and_wait_for_the_dialog,
    comms_entries,
    key_shown_in_the_dialog,
    open_stt_settings,
)
from tests.e2e.test_settings import save_state_text, section_shows_modified_indicator

pytestmark = [pytest.mark.anyio, allure.feature("Push-to-talk key")]

SPOKEN_COMMAND = "Request docking"
CELESTE_REPLY = "Docking request sent, Commander."


async def answer_docking_request(messages, agent_info):
    yield CELESTE_REPLY


def hotkey_shown_in_settings(app) -> str:
    return str(app.screen.query_one("#hotkey-value-label", Label).content)


async def bind_a_key_in_settings(edceleste, pilot: Pilot, key_name: str) -> None:
    await click_bind_and_wait_for_the_dialog(edceleste, pilot)
    await edceleste.global_keys_and_mouse.hold_key(key_name)
    await edceleste.wait_until(
        pilot,
        lambda: key_shown_in_the_dialog(pilot.app) == key_name,
        f"{key_name} caught in the dialog",
    )
    await edceleste.click_when_ready(pilot, "#bind-hotkey-confirm-button")
    await edceleste.wait_until(
        pilot,
        lambda: isinstance(pilot.app.screen, SettingsScreen),
        "the settings screen after the dialog closes",
    )


async def save_settings_with_ctrl_s(edceleste, pilot: Pilot) -> None:
    await pilot.press("ctrl+s")
    await edceleste.wait_until(
        pilot,
        lambda: save_state_text(pilot.app) == "◉ SAVED",
        "SAVED in the settings header",
    )


async def hold_and_release(edceleste, key_name: str) -> None:
    await edceleste.global_keys_and_mouse.hold_key(key_name)
    await edceleste.global_keys_and_mouse.release_key(key_name)


@allure.title("Holding the push-to-talk key sends the spoken command to COMMS")
async def test_should_send_the_spoken_command_when_the_push_to_talk_key_is_held(
    edceleste,
):
    with allure.step("Given speech to text is on and F9 is the push-to-talk key"):
        edceleste.turn_speech_to_text_on("Key.f9")

    with allure.step("And the microphone hears 'Request docking'"):
        edceleste.microphone.hears(SPOKEN_COMMAND)

    with allure.step("And the LLM answers 'Docking request sent, Commander.'"):
        edceleste.use_scripted_model(answer_docking_request)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander holds F9 and lets go of it"):
            await hold_and_release(edceleste, "Key.f9")

        with allure.step("Then COMMS shows the spoken command and Celeste's answer"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer in COMMS",
            )
            assert comms_entries(pilot.app, "user-command") == [SPOKEN_COMMAND]
            assert comms_entries(pilot.app, "llm-response") == [CELESTE_REPLY]

        with allure.step("And the microphone was on only while the key was held"):
            assert edceleste.microphone.times_opened == 1
            assert edceleste.microphone.times_closed == 1


@allure.title("A key held down for a long time makes one recording, not many")
async def test_should_record_once_when_the_key_is_held_and_the_keyboard_repeats_it(
    edceleste,
):
    with allure.step("Given speech to text is on and F9 is the push-to-talk key"):
        edceleste.turn_speech_to_text_on("Key.f9")

    with allure.step("And the microphone hears 'Request docking'"):
        edceleste.microphone.hears(SPOKEN_COMMAND)

    with allure.step("And the LLM answers 'Docking request sent, Commander.'"):
        edceleste.use_scripted_model(answer_docking_request)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander holds F9 while Windows repeats the key"):
            for _ in range(3):
                await edceleste.global_keys_and_mouse.hold_key("Key.f9")
            await edceleste.global_keys_and_mouse.release_key("Key.f9")

        with allure.step("Then COMMS shows the command once"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer in COMMS",
            )
            await pilot.pause()
            assert comms_entries(pilot.app, "user-command") == [SPOKEN_COMMAND]

        with allure.step("And the microphone was opened once"):
            assert edceleste.microphone.times_opened == 1


@allure.title("Without a push-to-talk key the keyboard does not record")
async def test_should_not_record_when_no_push_to_talk_key_is_set(edceleste):
    with allure.step("Given speech to text is on and no push-to-talk key is set"):
        edceleste.turn_speech_to_text_on(None)

    with allure.step("And the microphone hears 'Request docking'"):
        edceleste.microphone.hears(SPOKEN_COMMAND)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander holds F9 and lets go of it"):
            await hold_and_release(edceleste, "Key.f9")
            await pilot.pause()

        with allure.step("Then the microphone stays off and COMMS stays empty"):
            assert edceleste.microphone.times_opened == 0
            assert comms_entries(pilot.app, "user-command") == []


@allure.title("The mic button in COMMS still sends the spoken command")
async def test_should_send_the_spoken_command_when_the_mic_button_is_held(edceleste):
    with allure.step("Given speech to text is on and no push-to-talk key is set"):
        edceleste.turn_speech_to_text_on(None)

    with allure.step("And the microphone hears 'Request docking'"):
        edceleste.microphone.hears(SPOKEN_COMMAND)

    with allure.step("And the LLM answers 'Docking request sent, Commander.'"):
        edceleste.use_scripted_model(answer_docking_request)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander holds the mic button and lets go of it"):
            await pilot.mouse_down("#comms-stt-button")
            await pilot.mouse_up("#comms-stt-button")

        with allure.step("Then COMMS shows the spoken command and Celeste's answer"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer in COMMS",
            )
            assert comms_entries(pilot.app, "user-command") == [SPOKEN_COMMAND]
            assert comms_entries(pilot.app, "llm-response") == [CELESTE_REPLY]


@allure.title("A push-to-talk key chosen in Settings is saved to config.yaml")
async def test_should_save_the_key_chosen_in_settings_to_config_yaml(edceleste):
    with allure.step("Given speech to text is on and no push-to-talk key is set"):
        edceleste.turn_speech_to_text_on(None)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander opens Settings > Speech to text"):
            await open_stt_settings(edceleste, pilot)
            assert hotkey_shown_in_settings(pilot.app) == "None"

        with allure.step("When the Commander binds F9 in the dialog"):
            await bind_a_key_in_settings(edceleste, pilot, "Key.f9")

        with allure.step("Then the row shows Key.f9 and the section shows MODIFIED"):
            assert hotkey_shown_in_settings(pilot.app) == "Key.f9"
            assert save_state_text(pilot.app) == "◉ MODIFIED"
            assert section_shows_modified_indicator(pilot.app, "settings-stt")

        with allure.step("When the Commander saves with Ctrl+S"):
            await save_settings_with_ctrl_s(edceleste, pilot)

        with allure.step("Then config.yaml has the key and MODIFIED is gone"):
            saved_config = yaml.safe_load(edceleste.config_file.read_text())
            assert saved_config["stt"]["hotkey"] == "Key.f9"
            assert not section_shows_modified_indicator(pilot.app, "settings-stt")


@allure.title("After the Commander chooses another key only the new key records")
async def test_should_record_only_with_the_new_key_after_the_key_is_changed(edceleste):
    with allure.step("Given speech to text is on and F9 is the push-to-talk key"):
        edceleste.turn_speech_to_text_on("Key.f9")

    with allure.step("And the microphone hears 'Request docking'"):
        edceleste.microphone.hears(SPOKEN_COMMAND)

    with allure.step("And the LLM answers 'Docking request sent, Commander.'"):
        edceleste.use_scripted_model(answer_docking_request)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander changed the key to F10 in Settings"):
            await open_stt_settings(edceleste, pilot)
            await bind_a_key_in_settings(edceleste, pilot, "Key.f10")
            await save_settings_with_ctrl_s(edceleste, pilot)
            await pilot.press("escape")
            await edceleste.wait_until(
                pilot,
                lambda: isinstance(pilot.app.screen, DashboardScreen),
                "the dashboard after Escape",
            )

        with allure.step("When the Commander holds F9 and then F10"):
            await hold_and_release(edceleste, "Key.f9")
            await hold_and_release(edceleste, "Key.f10")

        with allure.step("Then only F10 recorded and sent one command"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer in COMMS",
            )
            await pilot.pause()
            assert edceleste.microphone.times_opened == 1
            assert comms_entries(pilot.app, "user-command") == [SPOKEN_COMMAND]
