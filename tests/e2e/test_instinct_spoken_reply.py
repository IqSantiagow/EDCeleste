import allure
import numpy as np
import pytest
import soundfile

from edceleste.services.models.reply_texts import build_reply_wav_file_name
from edceleste.services.models.settings_model import DEFAULT_EDGE_VOICE, TTSModel
from tests.e2e.conftest import (
    FAKE_VOICE_PIECE_SAMPLES,
    comms_entries,
    send_comms_message,
)
from tests.e2e.test_game_state_prompt import prompt_remembering_llm
from tests.e2e.test_journal_to_dashboard_stats import label_text
from tests.e2e.test_streaming_voice import (
    chatterbox_settings,
    what_the_speaker_should_play,
)
from tests.e2e.test_voice_profiles import write_voice_profile_files

pytestmark = [pytest.mark.anyio, allure.feature("Instinct speaks its reply")]

# The bit of the Flags field the game writes to Status.json when the gear is down
STATUS_LANDING_GEAR_DOWN = 4

DEPLOY_LANDING_GEAR = "deploy the landing gear"
LANDING_GEAR_KEYS = ["keyDown shiftleft", "press l", "keyUp shiftleft"]
SAVED_VOLUME = 0.5
CLIP_SAMPLE_RATE = 24000


def write_prepared_reply_clip(edceleste, voice: str, text: str) -> np.ndarray:
    """Saves a real wav as the prepared clip of the reply and returns its samples"""
    replies_folder = edceleste.voices_folder / "edge" / voice / "replies"
    replies_folder.mkdir(parents=True)
    clip_samples = np.linspace(-0.5, 0.5, 2400, dtype=np.float32)
    soundfile.write(
        replies_folder / build_reply_wav_file_name(text), clip_samples, CLIP_SAMPLE_RATE
    )
    return clip_samples


@allure.title("A prepared clip of the reply is played instead of a live voice")
async def test_should_play_the_prepared_clip_of_the_reply_instead_of_speaking_it_live(
    edceleste,
):
    prompts_sent_to_llm: list[str] = []

    with allure.step("Given game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step(
        "And Instinct on the GPU picks the gear for 'deploy the landing gear'"
    ):
        instinct_model = edceleste.turn_instinct_on()
        instinct_model.choices_by_message[DEPLOY_LANDING_GEAR] = "LandingGearToggle"

    with allure.step("And the LLM remembers every prompt it receives"):
        edceleste.use_scripted_model(prompt_remembering_llm(prompts_sent_to_llm))

    with allure.step(
        "And Edge speaks at volume 0.5 with the ship effect on and has a "
        "prepared clip of 'Landing gear deployed'"
    ):
        edceleste.save_tts_settings(TTSModel(volume=SAVED_VOLUME, ship_effect=True))
        clip_samples = write_prepared_reply_clip(
            edceleste, DEFAULT_EDGE_VOICE, "Landing gear deployed"
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'deploy the landing gear' in COMMS"):
            await send_comms_message(pilot, DEPLOY_LANDING_GEAR)

        with allure.step("Then COMMS shows the reply 'Landing gear deployed'"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Instinct's reply in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == ["Landing gear deployed"]

        with allure.step("And the speakers play the prepared clip once"):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the clip played"
            )
            assert len(edceleste.played_audio) == 1
            played = edceleste.played_audio[0]
            assert played["sample_rate"] == CLIP_SAMPLE_RATE
            np.testing.assert_allclose(played["samples"], clip_samples, atol=1e-3)

        with allure.step("And it is played at the saved volume with the ship effect"):
            assert played["volume"] == SAVED_VOLUME
            assert played["with_ship_effect"] is True

        with allure.step("And the voice engine is not asked to say anything"):
            assert edceleste.spoken_texts == []


@allure.title("With the landing gear down Instinct retracts it and says so")
async def test_should_retract_the_landing_gear_and_say_it_when_the_gear_is_down(
    edceleste,
):
    prompts_sent_to_llm: list[str] = []

    with allure.step("Given game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step(
        "And Instinct on the GPU picks the gear for 'deploy the landing gear'"
    ):
        instinct_model = edceleste.turn_instinct_on()
        instinct_model.choices_by_message[DEPLOY_LANDING_GEAR] = "LandingGearToggle"

    with allure.step("And the LLM remembers every prompt it receives"):
        edceleste.use_scripted_model(prompt_remembering_llm(prompts_sent_to_llm))

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the game reports the landing gear down"):
            edceleste.write_status_file(flags=STATUS_LANDING_GEAR_DOWN)
            await edceleste.wait_until(
                pilot,
                lambda: label_text(pilot.app, "#ship-flag-gear") == "● gear",
                "the gear lit in the SHIP panel",
            )

        with allure.step("When the Commander sends 'deploy the landing gear' in COMMS"):
            await send_comms_message(pilot, DEPLOY_LANDING_GEAR)

        with allure.step("Then COMMS shows the reply 'Landing gear retracted'"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Instinct's reply in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [
                "Landing gear retracted"
            ]

        with allure.step("And Celeste says 'Landing gear retracted'"):
            await edceleste.wait_until(
                pilot,
                lambda: edceleste.spoken_texts != [],
                "the reply handed to the voice engine",
            )
            assert edceleste.spoken_texts == ["Landing gear retracted"]

        with allure.step("And the landing gear key Shift+L is pressed once"):
            assert edceleste.fake_keyboard.keyboard_log == LANDING_GEAR_KEYS

        with allure.step("And Celeste (the LLM) is not asked anything"):
            assert prompts_sent_to_llm == []


@allure.title("The reply is on the screen while Celeste is still saying it")
async def test_should_show_the_reply_in_comms_while_the_voice_is_still_speaking(
    edceleste,
):
    prompts_sent_to_llm: list[str] = []

    with allure.step("Given game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step(
        "And Instinct on the GPU picks the gear for 'deploy the landing gear'"
    ):
        instinct_model = edceleste.turn_instinct_on()
        instinct_model.choices_by_message[DEPLOY_LANDING_GEAR] = "LandingGearToggle"

    with allure.step("And the LLM remembers every prompt it receives"):
        edceleste.use_scripted_model(prompt_remembering_llm(prompts_sent_to_llm))

    with allure.step("And Chatterbox on a GPU is saved with the voice 'narrator'"):
        write_voice_profile_files(edceleste, "narrator")
        edceleste.save_tts_settings(
            chatterbox_settings(device="cuda", volume=SAVED_VOLUME)
        )
        chatterbox = edceleste.fake_tts_providers["chatterbox"]
        speaker = edceleste.fake_speaker

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")
        spoken_at_boot = len(edceleste.spoken_texts)

        with allure.step("And the voice engine is slow after its first piece"):
            chatterbox.make_the_voice_slow()

        with allure.step("When the Commander sends 'deploy the landing gear' in COMMS"):
            await send_comms_message(pilot, DEPLOY_LANDING_GEAR)

        with allure.step("Then COMMS shows the reply 'Landing gear deployed'"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Instinct's reply in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == ["Landing gear deployed"]

        with allure.step("And Celeste has said only the start of it so far"):
            await edceleste.wait_until(
                pilot, lambda: speaker.blocks != [], "the first piece in the speakers"
            )
            assert len(speaker.everything_played()) < 3 * FAKE_VOICE_PIECE_SAMPLES

        with allure.step("And once the voice is done the whole reply was said"):
            chatterbox.let_the_voice_finish()
            await edceleste.wait_until(
                pilot,
                lambda: (
                    len(speaker.everything_played()) == 3 * FAKE_VOICE_PIECE_SAMPLES
                ),
                "all three pieces of the voice in the speakers",
            )
            np.testing.assert_allclose(
                speaker.everything_played(),
                what_the_speaker_should_play(chatterbox.voice_pieces, SAVED_VOLUME),
            )
            assert edceleste.spoken_texts[spoken_at_boot:] == ["Landing gear deployed"]


@allure.title("A voice that breaks does not lose the reply or press the key twice")
async def test_should_keep_the_reply_and_press_the_key_once_when_the_voice_breaks(
    edceleste,
):
    prompts_sent_to_llm: list[str] = []

    with allure.step("Given game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step(
        "And Instinct on the GPU picks the gear for 'deploy the landing gear'"
    ):
        instinct_model = edceleste.turn_instinct_on()
        instinct_model.choices_by_message[DEPLOY_LANDING_GEAR] = "LandingGearToggle"

    with allure.step("And the LLM remembers every prompt it receives"):
        edceleste.use_scripted_model(prompt_remembering_llm(prompts_sent_to_llm))

    with allure.step("And Chatterbox on a GPU is saved with the voice 'narrator'"):
        write_voice_profile_files(edceleste, "narrator")
        edceleste.save_tts_settings(
            chatterbox_settings(device="cuda", volume=SAVED_VOLUME)
        )
        chatterbox = edceleste.fake_tts_providers["chatterbox"]
        speaker = edceleste.fake_speaker

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")
        spoken_at_boot = len(edceleste.spoken_texts)

        with allure.step("And the voice engine breaks once while speaking"):
            chatterbox.break_the_voice_once()

        with allure.step("When the Commander sends 'deploy the landing gear' in COMMS"):
            await send_comms_message(pilot, DEPLOY_LANDING_GEAR)

        with allure.step("Then COMMS still shows the reply 'Landing gear deployed'"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Instinct's reply in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == ["Landing gear deployed"]

        with allure.step("And the voice really broke after its first piece"):
            await edceleste.wait_until(
                pilot,
                lambda: speaker.blocks != [] and chatterbox.voice_breaks_once is False,
                "the voice engine broken",
            )

        with allure.step("And the landing gear key Shift+L was pressed only once"):
            assert edceleste.fake_keyboard.keyboard_log == LANDING_GEAR_KEYS

        with allure.step("And Celeste (the LLM) is not asked anything"):
            assert prompts_sent_to_llm == []

        with allure.step("And the next command is answered and spoken in full"):
            blocks_before_next_command = len(speaker.blocks)
            await send_comms_message(pilot, DEPLOY_LANDING_GEAR)
            await edceleste.wait_until(
                pilot,
                lambda: len(speaker.blocks) >= blocks_before_next_command + 3,
                "the whole voice of the next reply in the speakers",
            )
            assert comms_entries(pilot.app, "llm-response") == [
                "Landing gear deployed",
                "Landing gear deployed",
            ]
            assert edceleste.spoken_texts[spoken_at_boot:] == [
                "Landing gear deployed",
                "Landing gear deployed",
            ]
