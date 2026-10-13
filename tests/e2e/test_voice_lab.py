import allure
import pytest
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import Button, Label, Select

from edceleste.services.models.settings_model import (
    EdgeParamsModel,
    TTSModel,
    VoiceLabModel,
)
from tests.e2e.conftest import FAKE_SAMPLE_RATE
from tests.e2e.test_settings import save_state_text
from tests.e2e.test_tts_settings import edge_voice_shown
from tests.e2e.test_voice_profiles import (
    notification_texts,
    open_text_to_speech_settings,
    switch_engine_to_chatterbox,
)

pytestmark = [pytest.mark.anyio, allure.feature("Voice Lab")]

TEST_BUTTON = "#voice-lab-test-button"
SONIA = "en-GB-SoniaNeural"
ARIA = "en-US-AriaNeural"


def edge_with_voice_lab(
    voice: str, volume: float, voice_lab: VoiceLabModel
) -> TTSModel:
    return TTSModel(
        provider="edge",
        params=EdgeParamsModel(type="edge", voice=voice),
        volume=volume,
        voice_lab=voice_lab,
    )


def voice_lab_button(app: App) -> Button:
    return app.screen.query_one(TEST_BUTTON, Button)


def slider_value_shown(app: App, row_id: str) -> str:
    return str(app.screen.query_one(f"{row_id} #slider-value-label", Label).content)


def voice_lab_sliders_are_hidden(app: App) -> bool:
    sliders = app.screen.query(".voice-lab-slider")
    return len(sliders) > 0 and all(not slider.display for slider in sliders)


async def press_test_voice(edceleste, pilot: Pilot) -> None:
    # The VOICE LAB block can sit below the visible part of the settings
    voice_lab_button(pilot.app).scroll_visible(animate=False)
    await pilot.pause()
    await edceleste.click_when_ready(pilot, TEST_BUTTON)


async def pick_the_second_edge_voice(edceleste, pilot: Pilot) -> None:
    voice_select = pilot.app.screen.query_one("#voice-input Select", Select)
    await pilot.click("#voice-input Select")
    await edceleste.wait_until(
        pilot, lambda: voice_select.expanded, "the list of voices to open"
    )
    await pilot.press("down", "enter")
    await edceleste.wait_until(
        pilot, lambda: edge_voice_shown(pilot) == ARIA, f"{ARIA} picked in the list"
    )


async def click_slider_and_wait_for_its_value(
    edceleste, pilot: Pilot, row_id: str, x_on_slider: int, value: str
) -> None:
    await pilot.click(f"{row_id} Slider", offset=(x_on_slider, 0))
    await edceleste.wait_until(
        pilot,
        lambda: slider_value_shown(pilot.app, row_id) == value,
        f"{row_id} to show {value}",
    )


@allure.title("Test voice speaks a sentence with the voice effects at the saved volume")
async def test_should_speak_a_test_sentence_with_the_effects_at_the_saved_volume(
    edceleste,
):
    with allure.step("Given Edge is saved with Aria, the effects on and volume 0.6"):
        edceleste.save_tts_settings(
            edge_with_voice_lab(ARIA, volume=0.6, voice_lab=VoiceLabModel())
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And Settings > Text to speech shows the Test voice button"):
            await open_text_to_speech_settings(edceleste, pilot)
            assert "Test voice" in str(voice_lab_button(pilot.app).label)

        with allure.step("When the Commander presses Test voice"):
            await press_test_voice(edceleste, pilot)

        with allure.step("Then Celeste speaks one test sentence in the saved voice"):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the test sentence played"
            )
            assert len(edceleste.spoken_texts) == 1
            spoken_params = edceleste.fake_tts_providers["edge"].spoken_params
            assert [params.voice for params in spoken_params] == [ARIA]

        with allure.step("And it is played once at the saved volume 0.6"):
            assert [audio["volume"] for audio in edceleste.played_audio] == [0.6]

        with allure.step(
            "And it has the Voice Lab effects: stereo, ringing on after the last word"
        ):
            heard_samples = edceleste.played_audio[0]["samples"]
            assert heard_samples.ndim == 2
            assert len(heard_samples) > FAKE_SAMPLE_RATE


@allure.title("Test voice plays what is on the screen and saves nothing")
async def test_should_play_the_unsaved_values_from_the_screen_and_save_nothing(
    edceleste,
):
    with allure.step("Given Edge is saved with Sonia, volume 1.0 and reverb 0.5"):
        edceleste.save_tts_settings(
            edge_with_voice_lab(SONIA, volume=1.0, voice_lab=VoiceLabModel(reverb=0.5))
        )
        config_before = edceleste.config_file.read_text()

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander opens Settings > Text to speech"):
            await open_text_to_speech_settings(edceleste, pilot)

        with allure.step(
            "And changes the voice to Aria, the volume to 0.3 and the reverb to 0, "
            "without saving"
        ):
            await pick_the_second_edge_voice(edceleste, pilot)
            await click_slider_and_wait_for_its_value(
                edceleste, pilot, "#volume-input", x_on_slider=40, value="0.3"
            )
            await click_slider_and_wait_for_its_value(
                edceleste,
                pilot,
                "#voice-lab-reverb-input",
                x_on_slider=0,
                value="0",
            )
            assert save_state_text(pilot.app) == "◉ MODIFIED"

        with allure.step("When the Commander presses Test voice"):
            await press_test_voice(edceleste, pilot)

        with allure.step("Then Celeste speaks in the voice from the screen, Aria"):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the test sentence played"
            )
            spoken_params = edceleste.fake_tts_providers["edge"].spoken_params
            assert [params.voice for params in spoken_params] == [ARIA]

        with allure.step("And plays it at the volume from the screen, 0.3"):
            assert [audio["volume"] for audio in edceleste.played_audio] == [0.3]

        with allure.step("And the voice does not ring on, as the reverb on the screen"):
            heard_samples = edceleste.played_audio[0]["samples"]
            assert len(heard_samples) == FAKE_SAMPLE_RATE

        with allure.step("And nothing is saved: config.yaml is the same as before"):
            assert edceleste.config_file.read_text() == config_before
            assert save_state_text(pilot.app) == "◉ MODIFIED"


@allure.title("With the voice effects off the Test voice button plays the plain voice")
async def test_should_play_the_plain_voice_when_the_voice_effects_are_off(edceleste):
    with allure.step("Given Edge is saved with the voice effects off and volume 0.8"):
        edceleste.save_tts_settings(
            edge_with_voice_lab(
                SONIA, volume=0.8, voice_lab=VoiceLabModel(enabled=False)
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And Settings > Text to speech hides the sliders"):
            await open_text_to_speech_settings(edceleste, pilot)
            assert voice_lab_sliders_are_hidden(pilot.app)

        with allure.step("And the Test voice button is still there"):
            assert voice_lab_button(pilot.app).display
            assert not voice_lab_button(pilot.app).disabled

        with allure.step("When the Commander presses Test voice"):
            await press_test_voice(edceleste, pilot)

        with allure.step("Then the plain voice is played at the saved volume 0.8"):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the test sentence played"
            )
            assert [audio["volume"] for audio in edceleste.played_audio] == [0.8]

        with allure.step("And it is the voice as the engine made it, no effects"):
            heard_samples = edceleste.played_audio[0]["samples"]
            assert heard_samples.ndim == 1
            assert len(heard_samples) == FAKE_SAMPLE_RATE


@allure.title("Test voice with an engine that is not set up shows an error")
async def test_should_show_an_error_when_the_engine_on_the_screen_is_not_set_up(
    edceleste,
):
    async with edceleste.run_app(show_notifications=True) as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander switches the engine to Chatterbox"):
            await open_text_to_speech_settings(edceleste, pilot)
            await switch_engine_to_chatterbox(edceleste, pilot)

        with allure.step("When the Commander presses Test voice"):
            await press_test_voice(edceleste, pilot)

        with allure.step("Then a notification says the voice test failed"):
            await edceleste.wait_until(
                pilot,
                lambda: notification_texts(pilot.app) != [],
                "the notification about the failed voice test",
            )
            assert notification_texts(pilot.app) == [
                "Voice test failed: Profile is not set."
            ]

        with allure.step("And nothing is spoken or played"):
            assert edceleste.spoken_texts == []
            assert edceleste.played_audio == []

        with allure.step("And the Test voice button works again"):
            assert not voice_lab_button(pilot.app).disabled
