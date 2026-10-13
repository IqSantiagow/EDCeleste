import allure
import numpy as np
import pytest

from edceleste.services.models.settings_model import (
    ChatterboxParamsModel,
    TTSModel,
    VoiceLabModel,
)
from tests.e2e.conftest import FAKE_SAMPLE_RATE, comms_entries, send_comms_message
from tests.e2e.test_voice_profiles import write_voice_profile_files

pytestmark = [pytest.mark.anyio, allure.feature("Streaming voice")]

ANSWER = "Copy that, Commander."
SAVED_VOLUME = 0.5
# Voice Lab with reverb 0.5 lets the reverb ring out for 0.3 + 0.6 * 0.5 seconds
REVERB_RINGING_OUT_SAMPLES = int(0.6 * FAKE_SAMPLE_RATE)


def chatterbox_settings(
    device: str, volume: float = SAVED_VOLUME, voice_lab_enabled: bool = False
) -> TTSModel:
    return TTSModel(
        provider="chatterbox",
        params=ChatterboxParamsModel(
            type="chatterbox", profile="narrator", device=device
        ),
        volume=volume,
        voice_lab=VoiceLabModel(enabled=voice_lab_enabled),
    )


def what_the_speaker_should_play(pieces: list[np.ndarray], volume: float) -> np.ndarray:
    voice = np.concatenate(pieces) * volume
    return np.stack([voice, voice], axis=1)


def tone_in_three_pieces() -> list[np.ndarray]:
    seconds_of_voice = 0.6
    times = np.arange(int(seconds_of_voice * FAKE_SAMPLE_RATE)) / FAKE_SAMPLE_RATE
    getting_louder = np.linspace(0.2, 0.8, len(times))
    tone = (getting_louder * np.sin(2 * np.pi * 220 * times)).astype(np.float32)
    return np.split(tone, 3)


@allure.title("Celeste starts speaking before her whole answer is made")
async def test_should_play_the_first_piece_while_the_rest_of_the_voice_is_still_made(
    edceleste,
):
    async def answer_copy_that(messages, agent_info):
        yield ANSWER

    with allure.step(
        "Given Chatterbox on a GPU is saved with the voice 'narrator' at volume 0.5"
    ):
        write_voice_profile_files(edceleste, "narrator")
        edceleste.save_tts_settings(chatterbox_settings(device="cuda"))
        chatterbox = edceleste.fake_tts_providers["chatterbox"]
        speaker = edceleste.fake_speaker

    with allure.step("And the LLM answers 'Copy that, Commander.'"):
        edceleste.use_scripted_model(answer_copy_that)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the voice engine is slow after its first piece"):
            chatterbox.make_the_voice_slow()

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then the speakers play the first piece of the voice"):
            await edceleste.wait_until(
                pilot, lambda: speaker.blocks != [], "the first piece in the speakers"
            )
            np.testing.assert_allclose(
                speaker.everything_played(),
                what_the_speaker_should_play(chatterbox.voice_pieces[:1], SAVED_VOLUME),
                atol=1e-6,
            )

        with allure.step("And the speaker stays open, the voice is not finished"):
            assert speaker.times_closed == 0

        with allure.step("And COMMS shows the answer"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [ANSWER]

        with allure.step("And when the voice engine makes the rest of the voice"):
            chatterbox.let_the_voice_finish()

        with allure.step(
            "Then the speakers play every piece in order, in both ears, at volume 0.5"
        ):
            await edceleste.wait_until(
                pilot, lambda: speaker.times_closed == 1, "the speakers done playing"
            )
            assert speaker.sample_rate == FAKE_SAMPLE_RATE
            np.testing.assert_allclose(
                speaker.everything_played(),
                what_the_speaker_should_play(chatterbox.voice_pieces, SAVED_VOLUME),
                atol=1e-6,
            )

        with allure.step("And the voice was not played as one whole piece"):
            assert edceleste.played_audio == []


@allure.title(
    "The Voice Lab effects cover the whole streamed voice and the reverb "
    "rings out after the last word"
)
async def test_should_apply_voice_lab_to_the_whole_streamed_voice(
    edceleste,
):
    async def answer_copy_that(messages, agent_info):
        yield ANSWER

    with allure.step(
        "Given Chatterbox on a GPU is saved with Voice Lab on at volume 0.5"
    ):
        write_voice_profile_files(edceleste, "narrator")
        edceleste.save_tts_settings(
            chatterbox_settings(device="cuda", voice_lab_enabled=True)
        )
        speaker = edceleste.fake_speaker

    with allure.step("And the voice engine makes a tone of 0.6 s in three pieces"):
        chatterbox = edceleste.fake_tts_providers["chatterbox"]
        chatterbox.voice_pieces = tone_in_three_pieces()
        voice = np.concatenate(chatterbox.voice_pieces)

    with allure.step("And the LLM answers 'Copy that, Commander.'"):
        edceleste.use_scripted_model(answer_copy_that)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then the speakers play the voice in stereo until it ends"):
            await edceleste.wait_until(
                pilot, lambda: speaker.times_closed == 1, "the speakers done playing"
            )
            played = speaker.everything_played()
            assert played.shape == (len(voice) + REVERB_RINGING_OUT_SAMPLES, 2)

        with allure.step(
            "And it sounds as if Voice Lab was applied once to the whole voice"
        ):
            voice_lab = edceleste.container.voice_lab_service()
            whole_voice_with_effects = voice_lab.apply_effects(voice, FAKE_SAMPLE_RATE)
            np.testing.assert_allclose(
                played, whole_voice_with_effects * SAVED_VOLUME, atol=1e-5
            )

        with allure.step("And the reverb still rings after the last word"):
            reverb_after_the_voice = played[len(voice) :]
            assert np.abs(reverb_after_the_voice).max() > 0.001


@allure.title("On a CPU the voice is made whole before it is played, as before")
async def test_should_make_the_whole_voice_before_playing_it_on_a_cpu(edceleste):
    async def answer_copy_that(messages, agent_info):
        yield ANSWER

    with allure.step(
        "Given Chatterbox on the CPU is saved with the voice 'narrator' at volume 0.5"
    ):
        write_voice_profile_files(edceleste, "narrator")
        edceleste.save_tts_settings(chatterbox_settings(device="cpu"))
        chatterbox = edceleste.fake_tts_providers["chatterbox"]

    with allure.step("And the LLM answers 'Copy that, Commander.'"):
        edceleste.use_scripted_model(answer_copy_that)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then the whole voice is played at the saved volume"):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the whole voice played"
            )
            assert [audio["volume"] for audio in edceleste.played_audio] == [
                SAVED_VOLUME
            ]

        with allure.step("And the voice engine was asked for the answer only"):
            assert chatterbox.spoken_texts == [ANSWER]

        with allure.step("And nothing was played piece by piece"):
            assert edceleste.fake_speaker.times_opened == 0


@allure.title(
    "A voice engine that breaks in the middle of an answer does not silence "
    "the next one"
)
async def test_should_speak_the_next_answer_after_the_voice_engine_broke(edceleste):
    answers = iter(["First answer.", "Second answer."])

    async def answer_in_turn(messages, agent_info):
        yield next(answers)

    with allure.step(
        "Given Chatterbox on a GPU is saved with the voice 'narrator' at volume 0.5"
    ):
        write_voice_profile_files(edceleste, "narrator")
        edceleste.save_tts_settings(chatterbox_settings(device="cuda"))
        chatterbox = edceleste.fake_tts_providers["chatterbox"]
        speaker = edceleste.fake_speaker

    with allure.step("And the LLM answers 'First answer.' and then 'Second answer.'"):
        edceleste.use_scripted_model(answer_in_turn)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "And the voice engine broke after the first piece of the first answer"
        ):
            chatterbox.break_the_voice_once()
            await send_comms_message(pilot, "hello")
            await edceleste.wait_until(
                pilot,
                lambda: speaker.times_closed == 1,
                "the speakers released after the broken voice",
            )
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "the first answer in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == ["First answer."]

        with allure.step("When the Commander sends 'hello again' in COMMS"):
            await send_comms_message(pilot, "hello again")

        with allure.step("Then COMMS shows the second answer"):
            await edceleste.wait_until(
                pilot,
                lambda: len(comms_entries(pilot.app, "llm-response")) == 2,
                "the second answer in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [
                "First answer.",
                "Second answer.",
            ]

        with allure.step("And the speakers play the whole second answer"):
            await edceleste.wait_until(
                pilot, lambda: speaker.times_closed == 2, "the speakers done again"
            )
            cut_short_first_voice = chatterbox.voice_pieces[:1]
            expected = what_the_speaker_should_play(
                cut_short_first_voice + chatterbox.voice_pieces, SAVED_VOLUME
            )
            np.testing.assert_allclose(speaker.everything_played(), expected, atol=1e-6)

        with allure.step("And no speaker was left open"):
            assert speaker.times_opened == speaker.times_closed == 2
