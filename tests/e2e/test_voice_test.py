import allure
import pytest
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import Button, Label, Select

from edceleste.services.models.settings_model import (
    EdgeParamsModel,
    PocketParamsModel,
    TTSModel,
)
from edceleste.services.tts_service import VOICE_TEST_TEXT
from tests.e2e.conftest import FAKE_SAMPLE_RATE, SCREEN_SIZE
from tests.e2e.test_pocket_tts import write_pocket_voice_files
from tests.e2e.test_settings import save_state_text
from tests.e2e.test_ship_effect import SHIP_EFFECT_ROW, ship_effect_switch
from tests.e2e.test_tts_settings import edge_voice_shown, open_pocket_tts_settings
from tests.e2e.test_voice_profiles import (
    notification_texts,
    open_text_to_speech_settings,
    profile_names_in_list,
    switch_engine_to_chatterbox,
)

pytestmark = [pytest.mark.anyio, allure.feature("Voice test")]

TEST_BUTTON = "#voice-test-button"
CLONE_BUTTON = "#clone-voice-button"
VOLUME_ROW = "#volume-input"
SONIA = "en-GB-SoniaNeural"
ARIA = "en-US-AriaNeural"
SMALL_TERMINAL_HEIGHT = 16


def edge_voice_with(voice: str, volume: float, ship_effect: bool) -> TTSModel:
    return TTSModel(
        provider="edge",
        params=EdgeParamsModel(type="edge", voice=voice),
        volume=volume,
        ship_effect=ship_effect,
    )


def voice_test_button(app: App) -> Button:
    return app.screen.query_one(TEST_BUTTON, Button)


def slider_value_shown(app: App, row_id: str) -> str:
    return str(app.screen.query_one(f"{row_id} #slider-value-label", Label).content)


def spoken_edge_voices(edceleste) -> list[str]:
    spoken_params = edceleste.fake_tts_providers["edge"].spoken_params
    return [params.voice for params in spoken_params]


def volumes_played(edceleste) -> list[float]:
    return [audio["volume"] for audio in edceleste.played_audio]


def ship_effect_flags_played(edceleste) -> list[bool]:
    return [audio["with_ship_effect"] for audio in edceleste.played_audio]


async def press_test_voice(edceleste, pilot: Pilot) -> None:
    # The button is the last row of the section and can sit below the visible part
    voice_test_button(pilot.app).scroll_visible(animate=False)
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


async def open_pocket_settings_with_one_voice(edceleste, pilot: Pilot) -> None:
    await open_pocket_tts_settings(edceleste, pilot)
    await edceleste.wait_until(
        pilot,
        lambda: profile_names_in_list(pilot.app) == ["echo"],
        "the cloned voice 'echo' in the list",
    )
    test_button = voice_test_button(pilot.app)
    await edceleste.wait_until(
        pilot,
        lambda: (
            test_button.region.y > pilot.app.screen.query_one(CLONE_BUTTON).region.y
        ),
        "the Test voice button laid out below the clone button",
    )


def save_pocket_with_one_voice(edceleste) -> None:
    write_pocket_voice_files(edceleste, "echo")
    edceleste.save_tts_settings(
        TTSModel(
            provider="pocket",
            params=PocketParamsModel(type="pocket", profile="echo"),
            volume=1.0,
        )
    )


@allure.title(
    "Test voice speaks a sentence at the saved volume with the ship effect on"
)
async def test_should_speak_a_test_sentence_at_the_saved_volume_with_the_ship_effect(
    edceleste,
):
    with allure.step(
        "Given Edge is saved with Aria, the ship effect on and volume 0.6"
    ):
        edceleste.save_tts_settings(edge_voice_with(ARIA, 0.6, ship_effect=True))

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("And Settings > Text to speech shows the Test voice button"):
            await open_text_to_speech_settings(edceleste, pilot)
            assert "Test voice" in str(voice_test_button(pilot.app).label)

        with allure.step("When the Commander presses Test voice"):
            await press_test_voice(edceleste, pilot)

        with allure.step(
            "Then Celeste speaks the test sentence once in the voice Aria"
        ):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the test sentence played"
            )
            assert edceleste.spoken_texts == [VOICE_TEST_TEXT]
            assert spoken_edge_voices(edceleste) == [ARIA]

        with allure.step("And it is played once at the saved volume 0.6"):
            assert volumes_played(edceleste) == [0.6]

        with allure.step("And it is played with the ship effect"):
            assert ship_effect_flags_played(edceleste) == [True]


@allure.title("Test voice plays what is on the screen and saves nothing")
async def test_should_play_the_unsaved_values_from_the_screen_and_save_nothing(
    edceleste,
):
    with allure.step(
        "Given Edge is saved with Sonia, the ship effect on and volume 1.0"
    ):
        edceleste.save_tts_settings(edge_voice_with(SONIA, 1.0, ship_effect=True))
        config_before = edceleste.config_file.read_text()

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander opens Settings > Text to speech"):
            await open_text_to_speech_settings(edceleste, pilot)

        with allure.step(
            "And changes the voice to Aria, the volume to 0.3 and turns the ship "
            "effect off, without saving"
        ):
            await pick_the_second_edge_voice(edceleste, pilot)
            await click_slider_and_wait_for_its_value(
                edceleste, pilot, VOLUME_ROW, x_on_slider=40, value="0.3"
            )
            await pilot.click(f"{SHIP_EFFECT_ROW} Switch")
            await edceleste.wait_until(
                pilot,
                lambda: ship_effect_switch(pilot.app).value is False,
                "the ship effect switch turned off",
            )
            assert save_state_text(pilot.app) == "◉ MODIFIED"

        with allure.step("When the Commander presses Test voice"):
            await press_test_voice(edceleste, pilot)

        with allure.step("Then Celeste speaks in the voice from the screen, Aria"):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the test sentence played"
            )
            assert edceleste.spoken_texts == [VOICE_TEST_TEXT]
            assert spoken_edge_voices(edceleste) == [ARIA]

        with allure.step("And plays it at the volume from the screen, 0.3"):
            assert volumes_played(edceleste) == [0.3]

        with allure.step("And plays it without the ship effect, as the switch shows"):
            assert ship_effect_flags_played(edceleste) == [False]

        with allure.step("And nothing is saved: config.yaml is the same as before"):
            assert edceleste.config_file.read_text() == config_before
            assert save_state_text(pilot.app) == "◉ MODIFIED"


@allure.title("With the ship effect off Test voice plays the plain voice")
async def test_should_play_the_plain_voice_when_the_ship_effect_is_off(edceleste):
    with allure.step(
        "Given Edge is saved with Sonia, the ship effect off and volume 0.8"
    ):
        edceleste.save_tts_settings(edge_voice_with(SONIA, 0.8, ship_effect=False))

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("And Settings > Text to speech shows the ship effect off"):
            await open_text_to_speech_settings(edceleste, pilot)
            assert ship_effect_switch(pilot.app).value is False

        with allure.step("When the Commander presses Test voice"):
            await press_test_voice(edceleste, pilot)

        with allure.step("Then the plain voice is played once at the saved volume 0.8"):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the test sentence played"
            )
            assert spoken_edge_voices(edceleste) == [SONIA]
            assert volumes_played(edceleste) == [0.8]

        with allure.step("And it is played without the ship effect"):
            assert ship_effect_flags_played(edceleste) == [False]

        with allure.step("And it is the voice as the engine made it"):
            heard_samples = edceleste.played_audio[0]["samples"]
            assert heard_samples.ndim == 1
            assert len(heard_samples) == FAKE_SAMPLE_RATE


@allure.title("Test voice with an engine that is not set up shows an error")
async def test_should_show_an_error_when_the_engine_on_the_screen_is_not_set_up(
    edceleste,
):
    async with edceleste.run_app(show_notifications=True) as pilot:
        await edceleste.open_dashboard(pilot)

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
            assert not voice_test_button(pilot.app).disabled


@allure.title(
    "In the Pocket TTS settings the volume, the ship effect and Test voice follow "
    "the voice profiles closely"
)
async def test_should_put_volume_ship_effect_and_test_voice_right_below_the_profiles(
    edceleste,
):
    with allure.step("Given Pocket TTS is saved with one cloned voice, 'echo'"):
        save_pocket_with_one_voice(edceleste)

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander opens Settings > Text to speech"):
            await open_pocket_settings_with_one_voice(edceleste, pilot)

        screen = pilot.app.screen
        clone_button_row = screen.query_one(CLONE_BUTTON).region.y
        volume_row = screen.query_one(VOLUME_ROW).region.y
        ship_effect_row = screen.query_one(SHIP_EFFECT_ROW).region.y
        test_button = voice_test_button(pilot.app)

        with allure.step("Then the Volume row is right below the clone button"):
            assert 0 < volume_row - clone_button_row <= 3

        with allure.step("And the Ship effect row follows the Volume row"):
            assert 0 < ship_effect_row - volume_row <= 3

        with allure.step("And the Test voice button follows the Ship effect row"):
            assert 0 < test_button.region.y - ship_effect_row <= 3

        with allure.step("And the Test voice button is the last row of the section"):
            section_rows = screen.query_one("#settings-tts VerticalScroll").children
            lowest_row_bottom = max(row.region.bottom for row in section_rows)
            assert test_button.region.bottom == lowest_row_bottom


@allure.title("In a small terminal the text to speech section scrolls to Test voice")
async def test_should_scroll_the_text_to_speech_section_to_the_test_voice_button(
    edceleste,
):
    with allure.step("Given Pocket TTS is saved with one cloned voice, 'echo'"):
        save_pocket_with_one_voice(edceleste)

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step(f"And the terminal is only {SMALL_TERMINAL_HEIGHT} rows high"):
            await pilot.resize_terminal(SCREEN_SIZE[0], SMALL_TERMINAL_HEIGHT)

        with allure.step("When the Commander opens Settings > Text to speech"):
            await open_pocket_settings_with_one_voice(edceleste, pilot)

        section = pilot.app.screen.query_one("#settings-tts VerticalScroll")
        test_button = voice_test_button(pilot.app)

        with allure.step("Then the section does not fit and can be scrolled"):
            await edceleste.wait_until(
                pilot,
                lambda: section.max_scroll_y > 0,
                "the text to speech section to be scrollable",
            )

        with allure.step("And the Test voice button is below the visible part"):
            assert not section.region.contains_region(test_button.region)

        with allure.step("And scrolling down to it makes the button visible"):
            test_button.scroll_visible(animate=False)
            await edceleste.wait_until(
                pilot,
                lambda: section.region.contains_region(test_button.region),
                "the Test voice button inside the visible part of the section",
            )
