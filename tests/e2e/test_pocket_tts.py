import allure
import numpy as np
import pytest
import soundfile
from textual.pilot import Pilot

from edceleste.services.models.reply_texts import REPLY_TEXTS, build_reply_wav_file_name
from edceleste.ui.screens.settings.settings_screen import SettingsScreen
from tests.e2e.test_voice_profiles import (
    FAKE_SAMPLE_RATE_FOR_FILES,
    click_save_profile,
    entries_of_the_profiles_in,
    clone_recording_until_profile_is_ready,
    open_text_to_speech_settings,
    profile_names_in_list,
    switch_engine_to_chatterbox,
    type_profile_name,
    write_voice_profile_files,
    write_voice_recording,
)

pytestmark = [pytest.mark.anyio, allure.feature("Pocket TTS voices")]


def write_pocket_voice_files(edceleste, profile_name: str) -> None:
    profile_folder = edceleste.pocket_voices_folder / profile_name
    profile_folder.mkdir(parents=True, exist_ok=True)
    (profile_folder / "profile.npy").write_bytes(b"voice")
    (profile_folder / "sample.wav").write_bytes(b"sample")


def write_playable_pocket_sample(edceleste, profile_name: str) -> None:
    profile_folder = edceleste.pocket_voices_folder / profile_name
    profile_folder.mkdir(parents=True, exist_ok=True)
    one_second_of_silence = np.zeros(FAKE_SAMPLE_RATE_FOR_FILES)
    soundfile.write(
        profile_folder / "sample.wav",
        one_second_of_silence,
        FAKE_SAMPLE_RATE_FOR_FILES,
    )


def files_in(folder) -> list[str]:
    """The names in a folder, sorted, [] when it is not there."""
    if not folder.exists():
        return []
    return sorted(file.name for file in folder.iterdir())


async def pick_in_the_select(pilot: Pilot, select_id: str, *key_presses: str) -> None:
    await pilot.click(f"#{select_id} Select")
    await pilot.pause()
    await pilot.press(*key_presses, "enter")


async def switch_engine_from_edge_to_pocket(edceleste, pilot: Pilot) -> None:
    # Pocket TTS is the first engine of the location Local, above Remote
    await pick_in_the_select(pilot, "tts-location-input", "up")
    await edceleste.wait_until(
        pilot,
        lambda: pilot.app.screen.query("#clone-voice-button"),
        "the Pocket TTS settings with the profile list",
    )


@allure.title("A voice cloned for Pocket TTS is kept in its own voices folder")
async def test_should_clone_a_recording_into_the_pocket_voices_folder(
    edceleste, tmp_path
):
    with allure.step("Given the Commander has a 12 s voice recording"):
        recording = write_voice_recording(
            tmp_path / "recordings", "commander_voice.wav", seconds=12
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Pocket TTS"):
            await open_text_to_speech_settings(edceleste, pilot)
            await switch_engine_from_edge_to_pocket(edceleste, pilot)

        with allure.step("When the Commander clones the recording as 'narrator'"):
            await clone_recording_until_profile_is_ready(edceleste, pilot, recording)
            await type_profile_name(pilot, "narrator")
            await click_save_profile(edceleste, pilot)
            await edceleste.wait_until(
                pilot,
                lambda: isinstance(pilot.app.screen, SettingsScreen),
                "the settings back after saving the profile",
            )

        with allure.step("Then the list shows the voice 'narrator'"):
            await edceleste.wait_until(
                pilot,
                lambda: profile_names_in_list(pilot.app) == ["narrator"],
                "the voice 'narrator' in the list",
            )

        with allure.step("And its files are in the Pocket TTS voices folder"):
            assert entries_of_the_profiles_in(edceleste.pocket_voices_folder) == [
                "narrator/profile.npy",
                "narrator/replies",
                "narrator/sample.wav",
            ]

        with allure.step("And a spoken reply for every reply text is prepared"):
            narrator_replies = edceleste.pocket_voices_folder / "narrator" / "replies"
            assert files_in(narrator_replies) == (
                sorted(build_reply_wav_file_name(text) for text in REPLY_TEXTS)
            )

        with allure.step("And the Chatterbox voices folder has no new file"):
            assert entries_of_the_profiles_in(edceleste.chatterbox_voices_folder) == []


@allure.title("Pocket TTS lists only its own voices, not the ones of Chatterbox")
async def test_should_list_only_the_voices_of_the_engine_on_the_screen(edceleste):
    with allure.step(
        "Given the Commander has the Chatterbox voice 'narrator' "
        "and the Pocket TTS voice 'echo'"
    ):
        write_voice_profile_files(edceleste, "narrator")
        write_pocket_voice_files(edceleste, "echo")

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await open_text_to_speech_settings(edceleste, pilot)
            await switch_engine_to_chatterbox(edceleste, pilot)
            await edceleste.wait_until(
                pilot,
                lambda: profile_names_in_list(pilot.app) == ["narrator"],
                "only the voice 'narrator' in the Chatterbox list",
            )

        with allure.step("When the Commander switches the engine to Pocket TTS"):
            await pick_in_the_select(pilot, "tts-provider-type-input", "up")

        with allure.step("Then the list shows only the voice 'echo'"):
            await edceleste.wait_until(
                pilot,
                lambda: profile_names_in_list(pilot.app) == ["echo"],
                "only the voice 'echo' in the Pocket TTS list",
            )


@allure.title("Deleting a Pocket TTS voice keeps the Chatterbox voice of the same name")
async def test_should_delete_a_pocket_voice_and_keep_the_chatterbox_voice_with_its_name(
    edceleste,
):
    with allure.step(
        "Given the Commander has a Chatterbox voice and a Pocket TTS voice, "
        "both named 'narrator'"
    ):
        write_voice_profile_files(edceleste, "narrator")
        write_pocket_voice_files(edceleste, "narrator")

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Pocket TTS"):
            await open_text_to_speech_settings(edceleste, pilot)
            await switch_engine_from_edge_to_pocket(edceleste, pilot)
            await edceleste.wait_until(
                pilot,
                lambda: profile_names_in_list(pilot.app) == ["narrator"],
                "the voice 'narrator' in the Pocket TTS list",
            )

        with allure.step("When the Commander removes the voice 'narrator'"):
            await pilot.click("#profile-row-narrator .profile-delete-button")

        with allure.step("Then the Pocket TTS list shows no voice"):
            await edceleste.wait_until(
                pilot,
                lambda: profile_names_in_list(pilot.app) == [],
                "the Pocket TTS list without voices",
            )

        with allure.step("And the Pocket TTS voices folder is empty"):
            assert entries_of_the_profiles_in(edceleste.pocket_voices_folder) == []

        with allure.step("And the Chatterbox voice 'narrator' is still there"):
            assert entries_of_the_profiles_in(edceleste.chatterbox_voices_folder) == [
                "narrator/profile.pt",
                "narrator/sample.wav",
            ]


@allure.title("The play button of a Pocket TTS voice plays its saved sample")
async def test_should_play_the_sample_of_a_pocket_voice(edceleste):
    with allure.step(
        "Given the Commander has the Pocket TTS voice 'narrator' with a sample "
        "and a Chatterbox voice 'narrator' with no sample"
    ):
        write_pocket_voice_files(edceleste, "narrator")
        write_playable_pocket_sample(edceleste, "narrator")
        write_voice_profile_files(edceleste, "narrator")
        (edceleste.chatterbox_voices_folder / "narrator/sample.wav").unlink()

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Pocket TTS"):
            await open_text_to_speech_settings(edceleste, pilot)
            await switch_engine_from_edge_to_pocket(edceleste, pilot)
            await edceleste.wait_until(
                pilot,
                lambda: profile_names_in_list(pilot.app) == ["narrator"],
                "the voice 'narrator' in the Pocket TTS list",
            )

        with allure.step("When the Commander presses play on 'narrator'"):
            await pilot.click("#profile-row-narrator .profile-play-button")

        with allure.step("Then the speakers play the sample at the saved volume"):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the sample played"
            )
            assert [audio["volume"] for audio in edceleste.played_audio] == [1.0]
