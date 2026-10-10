import allure
import pytest
from textual.pilot import Pilot
from textual.widgets import Select

from edceleste.services.models.settings_model import (
    ChatterboxParamsModel,
    EdgeParamsModel,
    TTSModel,
)
from tests.e2e.conftest import open_settings_section
from tests.e2e.test_settings import (
    save_state_text,
    saved_config,
    section_error_text,
    section_shows_modified_indicator,
)
from tests.e2e.test_voice_profiles import (
    open_text_to_speech_settings,
    profile_names_in_list,
    switch_engine_to_chatterbox,
    write_voice_profile_files,
)

pytestmark = [pytest.mark.anyio, allure.feature("Text to speech settings")]


def chatterbox_with_voice(profile_name: str) -> TTSModel:
    return TTSModel(
        provider="chatterbox",
        params=ChatterboxParamsModel(type="chatterbox", profile=profile_name),
        volume=1.0,
    )


def edge_with_voice(voice: str) -> TTSModel:
    return TTSModel(
        provider="edge",
        params=EdgeParamsModel(type="edge", voice=voice),
        volume=1.0,
    )


def edge_voice_shown(pilot: Pilot) -> str:
    return str(pilot.app.screen.query_one("#voice-input Select", Select).value)


async def switch_engine_to_edge(edceleste, pilot: Pilot) -> None:
    await pilot.click("#tts-provider-type-input Select")
    await pilot.pause()
    await pilot.press("up", "enter")
    await edceleste.wait_until(
        pilot,
        lambda: pilot.app.screen.query("#voice-input Select"),
        "the Edge settings with the list of voices",
    )


@allure.title("Saving never stores a voice that the Commander has just deleted")
async def test_should_not_save_the_selected_voice_after_it_was_deleted(edceleste):
    with allure.step("Given Chatterbox is saved with the cloned voice 'narrator'"):
        write_voice_profile_files(edceleste, "narrator")
        write_voice_profile_files(edceleste, "wingman")
        edceleste.save_tts_settings(chatterbox_with_voice("narrator"))

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander opens Settings > Text to speech"):
            await open_settings_section(edceleste, pilot, "settings-tts")
            await edceleste.wait_until(
                pilot,
                lambda: (
                    sorted(profile_names_in_list(pilot.app)) == ["narrator", "wingman"]
                ),
                "both cloned voices in the list",
            )

        with allure.step("When the Commander deletes the voice 'narrator'"):
            await pilot.click("#profile-row-narrator .profile-delete-button")
            await edceleste.wait_until(
                pilot,
                lambda: profile_names_in_list(pilot.app) == ["wingman"],
                "only the voice 'wingman' in the list",
            )

        with allure.step("And saves with Ctrl+S"):
            await pilot.press("ctrl+s")
            await edceleste.wait_until(
                pilot,
                lambda: (
                    save_state_text(pilot.app) in ("◉ SAVED", "◉ ERROR DURING SAVING")
                ),
                "the result of saving in the settings header",
                timeout_seconds=15,
            )

        with allure.step("Then saving either refuses or stores a voice that exists"):
            stored_voice = saved_config(edceleste)["tts"]["params"]["profile"]
            voice_file_exists = (
                edceleste.voices_folder / f"{stored_voice}.pt"
            ).exists()
            saving_was_refused = save_state_text(pilot.app) == "◉ ERROR DURING SAVING"
            assert saving_was_refused or voice_file_exists, (
                f"config.yaml now stores the voice '{stored_voice}' "
                f"but the voices folder has no such voice"
            )


@allure.title("Switching Edge, Chatterbox, Edge shows the saved Edge voice again")
async def test_should_show_the_saved_edge_voice_after_switching_engines_back(
    edceleste,
):
    with allure.step("Given Edge is saved with the voice en-US-AriaNeural"):
        edceleste.save_tts_settings(edge_with_voice("en-US-AriaNeural"))

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And Settings > Text to speech shows that voice"):
            await open_text_to_speech_settings(edceleste, pilot)
            assert edge_voice_shown(pilot) == "en-US-AriaNeural"

        with allure.step("When the Commander switches to Chatterbox and back to Edge"):
            await switch_engine_to_chatterbox(edceleste, pilot)
            await switch_engine_to_edge(edceleste, pilot)

        with allure.step("Then the Edge voice is still en-US-AriaNeural"):
            assert edge_voice_shown(pilot) == "en-US-AriaNeural"


@allure.title("Switching to Chatterbox a second time still lists the cloned voices")
async def test_should_list_the_cloned_voices_on_a_second_switch_to_chatterbox(
    edceleste,
):
    with allure.step("Given the Commander has two cloned voices and saved Edge"):
        write_voice_profile_files(edceleste, "narrator")
        write_voice_profile_files(edceleste, "wingman")

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander opens Settings > Text to speech"):
            await open_text_to_speech_settings(edceleste, pilot)

        with allure.step(
            "When the Commander switches to Chatterbox, back to Edge and to "
            "Chatterbox again"
        ):
            await switch_engine_to_chatterbox(edceleste, pilot)
            await switch_engine_to_edge(edceleste, pilot)
            await switch_engine_to_chatterbox(edceleste, pilot)

        with allure.step("Then both cloned voices are in the list"):
            assert sorted(profile_names_in_list(pilot.app)) == ["narrator", "wingman"]


@allure.title("Saving Chatterbox with no voice shows an error and keeps config.yaml")
async def test_should_refuse_to_save_chatterbox_without_a_voice(edceleste):
    config_before_saving = edceleste.config_file.read_text()

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await open_text_to_speech_settings(edceleste, pilot)
            await switch_engine_to_chatterbox(edceleste, pilot)

        with allure.step("When the Commander saves with Ctrl+S"):
            await pilot.press("ctrl+s")
            await edceleste.wait_until(
                pilot,
                lambda: save_state_text(pilot.app) == "◉ ERROR DURING SAVING",
                "ERROR DURING SAVING in the settings header",
                timeout_seconds=15,
            )

        with allure.step("Then the Text to speech section says the voice is not set"):
            assert "Profile is not set" in section_error_text(pilot.app, "settings-tts")

        with allure.step("And config.yaml is unchanged"):
            assert edceleste.config_file.read_text() == config_before_saving


@allure.title("Switching the engine marks the section and the header as modified")
async def test_should_mark_the_settings_as_modified_after_switching_the_engine(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens Settings > Text to speech"):
            await open_text_to_speech_settings(edceleste, pilot)

        with allure.step("When the Commander switches the engine to Chatterbox"):
            await switch_engine_to_chatterbox(edceleste, pilot)
            await pilot.pause()

        with allure.step("Then the header shows MODIFIED"):
            assert save_state_text(pilot.app) == "◉ MODIFIED"

        with allure.step("And the Text to speech section shows the modified mark"):
            assert section_shows_modified_indicator(pilot.app, "settings-tts")
