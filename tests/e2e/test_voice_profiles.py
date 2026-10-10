import allure
import numpy as np
import pytest
import soundfile
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import Label, Select
from textual.widgets._toast import Toast

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from edceleste.ui.screens.settings.settings_screen import SettingsScreen
from edceleste.ui.screens.settings.widgets.tts.voice_clone_modal_screen import (
    VoiceCloneModalScreen,
)
from tests.e2e.conftest import open_settings_section
from tests.e2e.test_settings import saved_config

pytestmark = [pytest.mark.anyio, allure.feature("Voice cloning")]


FAKE_SAMPLE_RATE_FOR_FILES = 24000


def write_voice_profile_files(edceleste, profile_name: str) -> None:
    edceleste.voices_folder.mkdir(exist_ok=True)
    (edceleste.voices_folder / f"{profile_name}.pt").write_bytes(b"voice")
    (edceleste.voices_folder / f"{profile_name}_sample.wav").write_bytes(b"sample")


def write_voice_recording(folder, file_name: str, seconds: int):
    folder.mkdir(exist_ok=True)
    sample_rate = 16000
    voice_like_noise = np.random.default_rng(1).uniform(
        -0.3, 0.3, seconds * sample_rate
    )
    recording = folder / file_name
    soundfile.write(recording, voice_like_noise, sample_rate)
    return recording


def profile_names_in_list(app: App) -> list[str]:
    labels = app.screen.query(".profile-name").results(Label)
    return [str(label.content).removeprefix("⧉ ") for label in labels]


def voice_files_in_folder(edceleste) -> list[str]:
    if not edceleste.voices_folder.exists():
        return []
    return sorted(file.name for file in edceleste.voices_folder.iterdir())


def engine_shown(app: App) -> str:
    return str(app.screen.query_one("#tts-provider-type-input Select", Select).value)


def next_button_is_enabled(app: App) -> bool:
    # A button ignores a click while it still plays its press animation (class
    # "-active", 0.2 s), and Next is the same button in all three steps
    next_buttons = app.screen.query("#voice-clone-next-button")
    return (
        len(next_buttons) == 1
        and not next_buttons.first().disabled
        and not next_buttons.first().has_class("-active")
    )


async def switch_engine_to_chatterbox(edceleste, pilot: Pilot) -> None:
    await pilot.click("#tts-provider-type-input Select")
    await pilot.pause()
    await pilot.press("down", "enter")
    await edceleste.wait_until(
        pilot,
        lambda: pilot.app.screen.query("#clone-voice-button"),
        "the Chatterbox settings with the profile list",
    )


async def open_text_to_speech_settings(edceleste, pilot: Pilot) -> None:
    await open_settings_section(edceleste, pilot, "settings-tts")
    await edceleste.wait_until(
        pilot,
        lambda: pilot.app.screen.query("#voice-input Select"),
        "the Edge settings with the list of voices",
    )


def write_playable_sample(edceleste, profile_name: str) -> None:
    edceleste.voices_folder.mkdir(exist_ok=True)
    one_second_of_silence = np.zeros(FAKE_SAMPLE_RATE_FOR_FILES)
    soundfile.write(
        edceleste.voices_folder / f"{profile_name}_sample.wav",
        one_second_of_silence,
        FAKE_SAMPLE_RATE_FOR_FILES,
    )


def label_texts(app: App) -> list[str]:
    return [str(label.content) for label in app.screen.query(Label)]


def notification_texts(app: App) -> list[str]:
    return [str(toast.render()) for toast in app.screen.query(Toast)]


def clone_window_is_open(app: App) -> bool:
    return isinstance(app.screen, VoiceCloneModalScreen)


def name_error_in_clone_window(app: App) -> str:
    errors = app.screen.query("#save-name-error")
    if len(errors) == 0 or errors.first().has_class("hidden"):
        return ""
    return str(errors.first().content)


def clone_finished(app: App) -> bool:
    name_input_is_shown = len(app.screen.query("#save-profile-name-input")) == 1
    cloning_failed = any(text.startswith("Cloning failed") for text in label_texts(app))
    return name_input_is_shown or cloning_failed


def save_button_is_ready(app: App) -> bool:
    next_buttons = app.screen.query("#voice-clone-next-button")
    return next_button_is_enabled(app) and "Save profile" in str(
        next_buttons.first().label
    )


async def open_clone_window(edceleste, pilot: Pilot) -> None:
    await pilot.click("#clone-voice-button")
    await edceleste.wait_until(
        pilot, lambda: clone_window_is_open(pilot.app), "the clone voice window"
    )


async def pick_recording_in_clone_window(edceleste, pilot: Pilot, recording) -> None:
    await pilot.click("#clone-voice-button")
    await edceleste.wait_until(
        pilot, lambda: pilot.app.screen.query("#select"), "the file picker"
    )
    await pilot.click("FileOpen Input")
    await pilot.press(*recording.as_posix(), "enter")

    def recording_is_shown_as_chosen() -> bool:
        if not clone_window_is_open(pilot.app):
            return False
        chosen_file = pilot.app.screen.query("#selected-file-label")
        return (
            len(chosen_file) == 1
            and not chosen_file.first().has_class("hidden")
            and recording.name in str(chosen_file.first().content)
            and next_button_is_enabled(pilot.app)
        )

    await edceleste.wait_until(
        pilot, recording_is_shown_as_chosen, f"{recording.name} shown as chosen"
    )


async def continue_to_analysis(edceleste, pilot: Pilot) -> None:
    await edceleste.wait_until(
        pilot, lambda: next_button_is_enabled(pilot.app), "Next ready to be clicked"
    )
    await pilot.click("#voice-clone-next-button")
    await edceleste.wait_until(
        pilot,
        lambda: pilot.app.screen.query("#analysis-play-button"),
        "the analysis of the recording",
    )


async def continue_to_cloning_and_wait_until_it_ends(edceleste, pilot: Pilot) -> None:
    await edceleste.wait_until(
        pilot,
        lambda: next_button_is_enabled(pilot.app),
        "Next enabled for a long enough recording",
    )
    await pilot.click("#voice-clone-next-button")
    await edceleste.wait_until(
        pilot,
        lambda: clone_finished(pilot.app),
        "the cloning to end",
        timeout_seconds=20,
    )
    await edceleste.wait_until(
        pilot,
        lambda: save_button_is_ready(pilot.app),
        "the Save profile button",
        timeout_seconds=20,
    )


async def clone_recording_until_profile_is_ready(
    edceleste, pilot: Pilot, recording
) -> None:
    await open_clone_window(edceleste, pilot)
    await pick_recording_in_clone_window(edceleste, pilot, recording)
    await continue_to_analysis(edceleste, pilot)
    await continue_to_cloning_and_wait_until_it_ends(edceleste, pilot)


async def click_save_profile(edceleste, pilot: Pilot) -> None:
    await edceleste.wait_until(
        pilot,
        lambda: save_button_is_ready(pilot.app),
        "Save profile ready to be clicked",
    )
    await pilot.click("#voice-clone-next-button")


async def type_profile_name(pilot: Pilot, profile_name: str) -> None:
    await pilot.click("#save-profile-name-input")
    await pilot.press("end", "ctrl+u", *profile_name)


@allure.title("Switching to Chatterbox without saving shows the cloned voices")
async def test_should_list_cloned_voices_after_switching_engine_without_saving(
    edceleste,
):
    with allure.step("Given the Commander has two cloned voices and saved Edge"):
        write_voice_profile_files(edceleste, "narrator")
        write_voice_profile_files(edceleste, "wingman")

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander opens Settings > Text to speech"):
            await open_text_to_speech_settings(edceleste, pilot)

        with allure.step("When the Commander switches the engine to Chatterbox"):
            await switch_engine_to_chatterbox(edceleste, pilot)

        with allure.step("Then the settings still work and list both cloned voices"):
            assert isinstance(pilot.app.screen, SettingsScreen)
            assert sorted(profile_names_in_list(pilot.app)) == ["narrator", "wingman"]

        with allure.step("And config.yaml still has Edge, nothing was saved"):
            assert saved_config(edceleste)["tts"]["provider"] == "edge"


@allure.title("A cloned voice can be removed after switching engine without saving")
async def test_should_remove_a_cloned_voice_after_switching_engine_without_saving(
    edceleste,
):
    with allure.step("Given the Commander has two cloned voices and saved Edge"):
        write_voice_profile_files(edceleste, "narrator")
        write_voice_profile_files(edceleste, "wingman")

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await open_text_to_speech_settings(edceleste, pilot)
            await switch_engine_to_chatterbox(edceleste, pilot)

        with allure.step("When the Commander removes the voice 'narrator'"):
            await pilot.click("#profile-row-narrator .profile-delete-button")

        with allure.step("Then the list shows only 'wingman'"):
            await edceleste.wait_until(
                pilot,
                lambda: profile_names_in_list(pilot.app) == ["wingman"],
                "only the voice 'wingman' in the list",
            )

        with allure.step("And the files of 'narrator' are gone from the voices folder"):
            assert voice_files_in_folder(edceleste) == [
                "wingman.pt",
                "wingman_sample.wav",
            ]

        with allure.step("And the Commander is still in the settings"):
            assert isinstance(pilot.app.screen, SettingsScreen)


@allure.title(
    "A voice cloned before the engine is saved is still there after reopening"
)
async def test_should_keep_a_cloned_voice_when_the_engine_was_never_saved(
    edceleste, tmp_path
):
    recording = write_voice_recording(
        tmp_path / "recordings", "commander_voice.wav", seconds=12
    )

    with allure.step("Given the Commander saved Edge and has a 12 s voice recording"):
        assert edceleste.settings.tts.provider == "edge"

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander switched the engine to Chatterbox"):
            await open_text_to_speech_settings(edceleste, pilot)
            await switch_engine_to_chatterbox(edceleste, pilot)

        with allure.step("When the Commander clones the voice from the recording"):
            await clone_recording_until_profile_is_ready(edceleste, pilot, recording)
            await type_profile_name(pilot, "commander")
            await click_save_profile(edceleste, pilot)
            await edceleste.wait_until(
                pilot,
                lambda: isinstance(pilot.app.screen, SettingsScreen),
                "the settings back after saving the profile",
            )

        with allure.step("Then the list shows the voice 'commander'"):
            await edceleste.wait_until(
                pilot,
                lambda: profile_names_in_list(pilot.app) == ["commander"],
                "the voice 'commander' in the list",
            )

        with allure.step("And its files are in the voices folder"):
            assert voice_files_in_folder(edceleste) == [
                "commander.pt",
                "commander_sample.wav",
            ]

        with allure.step("When the Commander leaves the settings without saving"):
            await pilot.press("escape")
            await edceleste.wait_until(
                pilot,
                lambda: isinstance(pilot.app.screen, DashboardScreen),
                "the dashboard",
            )

        with allure.step("And opens the settings again"):
            await open_text_to_speech_settings(edceleste, pilot)

        with allure.step("Then the engine is Edge again, as nothing was saved"):
            assert engine_shown(pilot.app) == "edge"

        with allure.step("When the Commander switches to Chatterbox again"):
            await switch_engine_to_chatterbox(edceleste, pilot)

        with allure.step("Then the cloned voice 'commander' is in the list"):
            assert profile_names_in_list(pilot.app) == ["commander"]
