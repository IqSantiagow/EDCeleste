import allure
import pytest
import yaml
from textual.app import App
from textual.widgets import Button, Label, Switch

from edceleste.services.models.settings_model import TTSModel
from tests.e2e.conftest import send_comms_message
from tests.e2e.test_settings import (
    save_state_text,
    saved_config,
    section_shows_modified_indicator,
)
from tests.e2e.test_voice_profiles import label_texts, open_text_to_speech_settings

pytestmark = [pytest.mark.anyio, allure.feature("Ship effect")]

ANSWER = "Copy that, Commander."
SAVED_VOLUME = 1.0
SHIP_EFFECT_ROW = "#ship-effect-input"


def write_config_from_before_the_ship_effect(edceleste) -> None:
    config = yaml.safe_load(edceleste.config_file.read_text())
    del config["tts"]["ship_effect"]
    config["tts"]["voice_lab"] = {
        "enabled": False,
        "clarity": 0.9,
        "reverb": 0.1,
        "stereo_width": 0.2,
    }
    edceleste.config_file.write_text(yaml.safe_dump(config))


def ship_effect_switch(app: App) -> Switch:
    return app.screen.query_one(f"{SHIP_EFFECT_ROW} Switch", Switch)


def texts_on_the_screen(app: App) -> list[str]:
    button_texts = [str(button.label) for button in app.screen.query(Button)]
    return label_texts(app) + button_texts


@allure.title(
    "A config.yaml from before the ship effect, with the old Voice Lab block, "
    "still starts and has the ship effect on"
)
async def test_should_start_with_a_config_that_has_the_old_voice_lab_block(
    edceleste,
):
    with allure.step(
        "Given config.yaml has the old Voice Lab block and no ship effect setting"
    ):
        write_config_from_before_the_ship_effect(edceleste)

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander opens Settings > Text to speech"):
            await open_text_to_speech_settings(edceleste, pilot)

        with allure.step("Then the Ship effect switch is shown and it is on"):
            label = pilot.app.screen.query_one(f"{SHIP_EFFECT_ROW} .entry-label", Label)
            assert str(label.content) == "Ship effect:"
            assert ship_effect_switch(pilot.app).value is True

        with allure.step("And it says it sounds like inside the ship"):
            assert "sounds like inside the ship" in label_texts(pilot.app)

        with allure.step("And the old Voice Lab block is gone"):
            texts = [text.lower() for text in texts_on_the_screen(pilot.app)]
            assert not [text for text in texts if "voice lab" in text]

        with allure.step("And the Test voice button is still there"):
            assert "[▶ Test voice]" in texts_on_the_screen(pilot.app)


@allure.title(
    "Turning the ship effect off and saving stores it in config.yaml "
    "and drops the old Voice Lab block"
)
async def test_should_save_the_ship_effect_switched_off_to_config_yaml(edceleste):
    with allure.step("Given config.yaml still has the old Voice Lab block"):
        write_config_from_before_the_ship_effect(edceleste)
        assert "voice_lab" in saved_config(edceleste)["tts"]

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "And the Commander opens Settings > Text to speech, the ship effect is on"
        ):
            await open_text_to_speech_settings(edceleste, pilot)
            assert ship_effect_switch(pilot.app).value is True

        with allure.step(
            "And the Commander turns the ship effect off, the settings show MODIFIED"
        ):
            await pilot.click(f"{SHIP_EFFECT_ROW} Switch")
            await edceleste.wait_until(
                pilot,
                lambda: save_state_text(pilot.app) == "◉ MODIFIED",
                "MODIFIED in the settings header",
            )
            assert ship_effect_switch(pilot.app).value is False
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

        with allure.step("And config.yaml says the ship effect is off"):
            assert saved_config(edceleste)["tts"]["ship_effect"] is False

        with allure.step("And the old Voice Lab block is gone from config.yaml"):
            assert "voice_lab" not in saved_config(edceleste)["tts"]


@allure.title("Celeste's spoken answer is played with the ship effect when it is on")
async def test_should_play_the_spoken_answer_with_the_ship_effect_when_it_is_on(
    edceleste,
):
    async def answer_copy_that(messages, agent_info):
        yield ANSWER

    with allure.step("Given Edge speaks at volume 1 with the ship effect on"):
        edceleste.save_tts_settings(TTSModel(volume=SAVED_VOLUME, ship_effect=True))
        edge_engine = edceleste.fake_tts_providers["edge"]

    with allure.step("And the LLM answers 'Copy that, Commander.'"):
        edceleste.use_scripted_model(answer_copy_that)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then the Edge engine is asked to say the answer"):
            await edceleste.wait_until(
                pilot,
                lambda: edge_engine.spoken_texts != [],
                "the answer handed to the voice engine",
            )
            assert edge_engine.spoken_texts == [ANSWER]

        with allure.step("And the speakers play the answer once at the saved volume"):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the answer played"
            )
            assert [audio["volume"] for audio in edceleste.played_audio] == [
                SAVED_VOLUME
            ]

        with allure.step("And it is played with the ship effect"):
            assert [audio["with_ship_effect"] for audio in edceleste.played_audio] == [
                True
            ]


@allure.title("With the ship effect off Celeste's spoken answer is played plain")
async def test_should_play_the_spoken_answer_plain_when_the_ship_effect_is_off(
    edceleste,
):
    async def answer_copy_that(messages, agent_info):
        yield ANSWER

    with allure.step("Given Edge speaks at volume 1 with the ship effect off"):
        edceleste.save_tts_settings(TTSModel(volume=SAVED_VOLUME, ship_effect=False))
        edge_engine = edceleste.fake_tts_providers["edge"]

    with allure.step("And the LLM answers 'Copy that, Commander.'"):
        edceleste.use_scripted_model(answer_copy_that)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then the Edge engine is asked to say the answer"):
            await edceleste.wait_until(
                pilot,
                lambda: edge_engine.spoken_texts != [],
                "the answer handed to the voice engine",
            )
            assert edge_engine.spoken_texts == [ANSWER]

        with allure.step("And the speakers play the answer once at the saved volume"):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the answer played"
            )
            assert [audio["volume"] for audio in edceleste.played_audio] == [
                SAVED_VOLUME
            ]

        with allure.step("And it is played without the ship effect"):
            assert [audio["with_ship_effect"] for audio in edceleste.played_audio] == [
                False
            ]
