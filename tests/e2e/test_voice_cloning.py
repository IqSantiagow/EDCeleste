import allure
import pytest

from edceleste.ui.screens.settings.settings_screen import SettingsScreen
from tests.e2e.test_voice_profiles import (
    click_save_profile,
    clone_recording_until_profile_is_ready,
    clone_window_is_open,
    continue_to_analysis,
    continue_to_cloning_and_wait_until_it_ends,
    label_texts,
    name_error_in_clone_window,
    next_button_is_enabled,
    notification_texts,
    open_clone_window,
    open_text_to_speech_settings,
    pick_recording_in_clone_window,
    profile_names_in_list,
    switch_engine_to_chatterbox,
    type_profile_name,
    voice_files_in_folder,
    write_playable_sample,
    write_voice_profile_files,
    write_voice_recording,
)

pytestmark = [pytest.mark.anyio, allure.feature("Voice cloning")]


async def switch_to_chatterbox_in_settings(edceleste, pilot) -> None:
    await open_text_to_speech_settings(edceleste, pilot)
    await switch_engine_to_chatterbox(edceleste, pilot)


@allure.title("Cancel after cloning deletes the unsaved voice and keeps the others")
async def test_should_delete_the_unsaved_clone_when_the_commander_cancels(
    edceleste, tmp_path
):
    with allure.step("Given the Commander has the cloned voice 'narrator'"):
        write_voice_profile_files(edceleste, "narrator")
        recording = write_voice_recording(
            tmp_path / "recordings", "commander_voice.wav", seconds=12
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await switch_to_chatterbox_in_settings(edceleste, pilot)

        with allure.step("And a new voice is cloned and waits to be named"):
            await clone_recording_until_profile_is_ready(edceleste, pilot, recording)
            assert "commander_voice.pt" in voice_files_in_folder(edceleste)

        with allure.step("When the Commander presses Cancel"):
            await pilot.click("#voice-clone-cancel-button")
            await edceleste.wait_until(
                pilot,
                lambda: isinstance(pilot.app.screen, SettingsScreen),
                "the settings back after Cancel",
            )

        with allure.step("Then the voices folder holds only the files of 'narrator'"):
            assert voice_files_in_folder(edceleste) == [
                "narrator.pt",
                "narrator_sample.wav",
            ]

        with allure.step("And the list still shows only 'narrator'"):
            assert profile_names_in_list(pilot.app) == ["narrator"]


@allure.title("Another file deletes the unsaved voice and goes back to choosing a file")
async def test_should_delete_the_unsaved_clone_when_the_commander_picks_another_file(
    edceleste, tmp_path
):
    with allure.step("Given the Commander has a 12 s voice recording"):
        recording = write_voice_recording(
            tmp_path / "recordings", "first_take.wav", seconds=12
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await switch_to_chatterbox_in_settings(edceleste, pilot)

        with allure.step("And the voice is cloned and waits to be named"):
            await clone_recording_until_profile_is_ready(edceleste, pilot, recording)
            assert "first_take.pt" in voice_files_in_folder(edceleste)

        with allure.step("When the Commander presses Another file"):
            await pilot.click("#voice-clone-pick-another-button")
            await edceleste.wait_until(
                pilot,
                lambda: (
                    clone_window_is_open(pilot.app)
                    and pilot.app.screen.query("#selected-file-label")
                    .first()
                    .has_class("hidden")
                ),
                "the clone window asking for a file again",
            )

        with allure.step("Then the voices folder is empty"):
            assert voice_files_in_folder(edceleste) == []

        with allure.step("And Next is disabled until a file is chosen"):
            assert not next_button_is_enabled(pilot.app)


@allure.title("After Another file a different recording can be cloned to the end")
async def test_should_clone_a_second_recording_after_another_file(edceleste, tmp_path):
    with allure.step("Given the Commander has two 12 s voice recordings"):
        first_recording = write_voice_recording(
            tmp_path / "recordings", "first_take.wav", seconds=12
        )
        second_recording = write_voice_recording(
            tmp_path / "recordings", "second_take.wav", seconds=12
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await switch_to_chatterbox_in_settings(edceleste, pilot)

        with allure.step("And the first recording was cloned, then Another file"):
            await clone_recording_until_profile_is_ready(
                edceleste, pilot, first_recording
            )
            await pilot.click("#voice-clone-pick-another-button")
            await edceleste.wait_until(
                pilot,
                lambda: (
                    clone_window_is_open(pilot.app)
                    and pilot.app.screen.query("#selected-file-label")
                    .first()
                    .has_class("hidden")
                ),
                "the clone window asking for a file again",
            )

        with allure.step("When the Commander clones the second recording and saves"):
            await pick_recording_in_clone_window(edceleste, pilot, second_recording)
            await continue_to_analysis(edceleste, pilot)
            await continue_to_cloning_and_wait_until_it_ends(edceleste, pilot)
            await click_save_profile(edceleste, pilot)
            await edceleste.wait_until(
                pilot,
                lambda: isinstance(pilot.app.screen, SettingsScreen),
                "the settings back after saving",
            )

        with allure.step("Then the list shows only 'second_take'"):
            await edceleste.wait_until(
                pilot,
                lambda: profile_names_in_list(pilot.app) == ["second_take"],
                "only the voice 'second_take' in the list",
            )

        with allure.step("And the voices folder holds only its files"):
            assert voice_files_in_folder(edceleste) == [
                "second_take.pt",
                "second_take_sample.wav",
            ]


@allure.title("A name that is already taken is refused and no voice is lost")
async def test_should_refuse_a_taken_name_and_lose_no_voice(edceleste, tmp_path):
    with allure.step("Given the Commander has the cloned voice 'narrator'"):
        write_voice_profile_files(edceleste, "narrator")
        recording = write_voice_recording(
            tmp_path / "recordings", "commander_voice.wav", seconds=12
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await switch_to_chatterbox_in_settings(edceleste, pilot)

        with allure.step("And a new voice is cloned and waits to be named"):
            await clone_recording_until_profile_is_ready(edceleste, pilot, recording)

        with allure.step("When the Commander names it 'narrator' and saves"):
            await type_profile_name(pilot, "narrator")
            await click_save_profile(edceleste, pilot)
            await edceleste.wait_until(
                pilot,
                lambda: name_error_in_clone_window(pilot.app) != "",
                "an error under the name",
            )

        with allure.step("Then the error says the name already exists"):
            error_text = name_error_in_clone_window(pilot.app)
            assert "narrator" in error_text
            assert "already exists" in error_text

        with allure.step("And the clone window stays open"):
            assert clone_window_is_open(pilot.app)

        with allure.step("And the files of 'narrator' are untouched"):
            old_voice = (edceleste.voices_folder / "narrator.pt").read_bytes()
            old_sample = (edceleste.voices_folder / "narrator_sample.wav").read_bytes()
            assert (old_voice, old_sample) == (b"voice", b"sample")

        with allure.step("And the new clone still exists under its first name"):
            assert voice_files_in_folder(edceleste) == [
                "commander_voice.pt",
                "commander_voice_sample.wav",
                "narrator.pt",
                "narrator_sample.wav",
            ]


@allure.title(
    "A recording shorter than 10 s is refused as too short and writes nothing"
)
async def test_should_refuse_a_recording_shorter_than_ten_seconds(edceleste, tmp_path):
    with allure.step("Given the Commander has a 6 s voice recording"):
        recording = write_voice_recording(
            tmp_path / "recordings", "short_voice.wav", seconds=6
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await switch_to_chatterbox_in_settings(edceleste, pilot)

        with allure.step("When the Commander chooses the recording and goes on"):
            await open_clone_window(edceleste, pilot)
            await pick_recording_in_clone_window(edceleste, pilot, recording)
            await continue_to_analysis(edceleste, pilot)
            await pilot.pause()

        with allure.step("Then the analysis says the recording is too short"):
            assert any("Too short" in text for text in label_texts(pilot.app))

        with allure.step("And Next stays disabled"):
            assert not next_button_is_enabled(pilot.app)

        with allure.step("And nothing is written to the voices folder"):
            assert voice_files_in_folder(edceleste) == []


@allure.title("Cloning a recording named like an existing voice does not replace it")
async def test_should_not_replace_an_existing_voice_when_a_recording_has_its_name(
    edceleste, tmp_path
):
    with allure.step("Given the Commander has the cloned voice 'celeste'"):
        write_voice_profile_files(edceleste, "celeste")
        recording = write_voice_recording(
            tmp_path / "recordings", "celeste.wav", seconds=12
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await switch_to_chatterbox_in_settings(edceleste, pilot)

        with allure.step("When the Commander clones a recording called celeste.wav"):
            await clone_recording_until_profile_is_ready(edceleste, pilot, recording)

        with allure.step("Then the old voice 'celeste' still has its own files"):
            old_voice = (edceleste.voices_folder / "celeste.pt").read_bytes()
            old_sample = (edceleste.voices_folder / "celeste_sample.wav").read_bytes()
            assert (old_voice, old_sample) == (b"voice", b"sample")


@allure.title("Cancel after cloning a recording named like a voice keeps that voice")
async def test_should_keep_the_existing_voice_when_the_commander_cancels_the_clone(
    edceleste, tmp_path
):
    with allure.step("Given the Commander has the cloned voice 'celeste'"):
        write_voice_profile_files(edceleste, "celeste")
        recording = write_voice_recording(
            tmp_path / "recordings", "celeste.wav", seconds=12
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await switch_to_chatterbox_in_settings(edceleste, pilot)

        with allure.step("And a recording called celeste.wav is cloned"):
            await clone_recording_until_profile_is_ready(edceleste, pilot, recording)

        with allure.step("When the Commander presses Cancel"):
            await pilot.click("#voice-clone-cancel-button")
            await edceleste.wait_until(
                pilot,
                lambda: isinstance(pilot.app.screen, SettingsScreen),
                "the settings back after Cancel",
            )

        with allure.step("Then the old voice 'celeste' still has its own files"):
            assert voice_files_in_folder(edceleste) == [
                "celeste.pt",
                "celeste_sample.wav",
            ]
            old_voice = (edceleste.voices_folder / "celeste.pt").read_bytes()
            old_sample = (edceleste.voices_folder / "celeste_sample.wav").read_bytes()
            assert (old_voice, old_sample) == (b"voice", b"sample")


@allure.title("An empty voice name is refused with 'Name cannot be empty.'")
async def test_should_refuse_an_empty_voice_name(edceleste, tmp_path):
    with allure.step("Given the Commander has a 12 s voice recording"):
        recording = write_voice_recording(
            tmp_path / "recordings", "commander_voice.wav", seconds=12
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await switch_to_chatterbox_in_settings(edceleste, pilot)

        with allure.step("And the voice is cloned and waits to be named"):
            await clone_recording_until_profile_is_ready(edceleste, pilot, recording)

        with allure.step("When the Commander clears the name and saves"):
            await type_profile_name(pilot, "")
            await click_save_profile(edceleste, pilot)
            await edceleste.wait_until(
                pilot,
                lambda: name_error_in_clone_window(pilot.app) != "",
                "an error under the name",
            )

        with allure.step("Then the error says 'Name cannot be empty.'"):
            assert name_error_in_clone_window(pilot.app) == "Name cannot be empty."

        with allure.step("And the clone window stays open with the clone untouched"):
            assert clone_window_is_open(pilot.app)
            assert "commander_voice.pt" in voice_files_in_folder(edceleste)


@allure.title("A voice name with ../ cannot write outside the voices folder")
async def test_should_not_write_outside_the_voices_folder_for_a_name_with_dots(
    edceleste, tmp_path
):
    with allure.step("Given the Commander has a 12 s voice recording"):
        recording = write_voice_recording(
            tmp_path / "recordings", "commander_voice.wav", seconds=12
        )

    def files_outside_the_voices_folder() -> list[str]:
        return sorted(
            str(file.relative_to(tmp_path))
            for file in tmp_path.rglob("*")
            if file.is_file() and edceleste.voices_folder not in file.parents
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await switch_to_chatterbox_in_settings(edceleste, pilot)

        with allure.step("And the voice is cloned and waits to be named"):
            await clone_recording_until_profile_is_ready(edceleste, pilot, recording)
            files_before = files_outside_the_voices_folder()

        with allure.step("When the Commander names the voice '../x' and saves"):
            await type_profile_name(pilot, "../x")
            await click_save_profile(edceleste, pilot)
            await edceleste.wait_until(
                pilot,
                lambda: (
                    isinstance(pilot.app.screen, SettingsScreen)
                    or name_error_in_clone_window(pilot.app) != ""
                ),
                "the settings back or an error under the name",
            )

        with allure.step("Then no file appeared outside the voices folder"):
            assert files_outside_the_voices_folder() == files_before

        with allure.step("And the app is still running"):
            assert pilot.app.is_running


@allure.title("The play button of a cloned voice plays its saved sample")
async def test_should_play_the_sample_of_a_cloned_voice(edceleste):
    with allure.step(
        "Given the Commander has the cloned voice 'narrator' with a sample"
    ):
        write_voice_profile_files(edceleste, "narrator")
        write_playable_sample(edceleste, "narrator")

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await switch_to_chatterbox_in_settings(edceleste, pilot)

        with allure.step("When the Commander presses play on 'narrator'"):
            await pilot.click("#profile-row-narrator .profile-play-button")

        with allure.step("Then the speakers play the sample at the saved volume"):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the sample played"
            )
            assert [audio["volume"] for audio in edceleste.played_audio] == [1.0]


@allure.title(
    "A cloned voice without a sample shows a notification and the app stays up"
)
async def test_should_notify_when_the_sample_of_a_cloned_voice_is_missing(edceleste):
    with allure.step(
        "Given the Commander has the cloned voice 'narrator' with no sample"
    ):
        write_voice_profile_files(edceleste, "narrator")
        (edceleste.voices_folder / "narrator_sample.wav").unlink()

    async with edceleste.run_app(show_notifications=True) as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await switch_to_chatterbox_in_settings(edceleste, pilot)

        with allure.step("When the Commander presses play on 'narrator'"):
            await pilot.click("#profile-row-narrator .profile-play-button")

        with allure.step("Then a notification says there is no sample audio"):
            await edceleste.wait_until(
                pilot,
                lambda: notification_texts(pilot.app) != [],
                "a notification about the missing sample",
            )
            assert notification_texts(pilot.app) == [
                "No sample audio found for 'narrator'."
            ]

        with allure.step("And nothing was played and the settings stay open"):
            assert edceleste.played_audio == []
            assert isinstance(pilot.app.screen, SettingsScreen)
