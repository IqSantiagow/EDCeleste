import allure
import numpy as np
import pytest

from edceleste.services.models.settings_model import (
    ChatterboxParamsModel,
    PocketParamsModel,
    TTSModel,
    VoiceLabModel,
)
from tests.e2e.test_comms import send_comms_message
from tests.e2e.test_streaming_voice import what_the_speaker_should_play

pytestmark = [pytest.mark.anyio, allure.feature("Speech")]


@allure.title("Celeste speaks her answer with the saved engine, voice and volume")
async def test_should_speak_the_answer_with_the_saved_engine_voice_and_volume(
    edceleste,
):
    async def answer_copy_that(messages, agent_info):
        yield "Copy that, Commander."

    with allure.step("Given Edge speaks with the voice en-GB-SoniaNeural at volume 1"):
        edge_engine = edceleste.fake_tts_providers["edge"]
        assert edceleste.settings.tts.provider == "edge"
        assert edceleste.settings.tts.params.voice == "en-GB-SoniaNeural"

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
            assert edge_engine.spoken_texts == ["Copy that, Commander."]

        with allure.step("And it speaks with the saved voice"):
            assert edge_engine.spoken_params[0].voice == "en-GB-SoniaNeural"

        with allure.step("And the speakers play the speech at the saved volume"):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the speech played"
            )
            assert [audio["volume"] for audio in edceleste.played_audio] == [1.0]


@allure.title("Celeste speaks with the saved cloned voice and its saved settings")
async def test_should_speak_with_the_saved_cloned_voice(edceleste):
    async def answer_copy_that(messages, agent_info):
        yield "Copy that, Commander."

    with allure.step("Given Chatterbox is saved with the cloned voice 'narrator'"):
        (edceleste.chatterbox_voices_folder / "narrator").mkdir(parents=True)
        (edceleste.chatterbox_voices_folder / "narrator/profile.pt").write_bytes(
            b"voice"
        )
        edceleste.save_tts_settings(
            TTSModel(
                provider="chatterbox",
                params=ChatterboxParamsModel(
                    type="chatterbox",
                    profile="narrator",
                    exaggeration=0.7,
                    cfg_weight=0.4,
                ),
                volume=1.0,
            )
        )
        chatterbox_engine = edceleste.fake_tts_providers["chatterbox"]

    with allure.step("And the LLM answers 'Copy that, Commander.'"):
        edceleste.use_scripted_model(answer_copy_that)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then the Chatterbox engine is asked to say the answer"):
            await edceleste.wait_until(
                pilot,
                lambda: chatterbox_engine.spoken_texts != [],
                "the answer handed to the voice engine",
            )
            assert chatterbox_engine.spoken_texts == ["Copy that, Commander."]

        with allure.step(
            "And it uses the voice file 'narrator' from the voices folder"
        ):
            assert chatterbox_engine.spoken_profile_paths == [
                edceleste.chatterbox_voices_folder / "narrator/profile.pt"
            ]

        with allure.step("And it uses the saved exaggeration and pace"):
            spoken_params = chatterbox_engine.spoken_params[0]
            assert (spoken_params.exaggeration, spoken_params.cfg_weight) == (0.7, 0.4)

        with allure.step("And the speakers play the speech"):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the speech played"
            )


@allure.title("Celeste speaks with the saved Pocket TTS voice")
async def test_should_speak_with_the_saved_pocket_voice(edceleste):
    async def answer_copy_that(messages, agent_info):
        yield "Copy that, Commander."

    with allure.step(
        "Given Pocket TTS is saved with the cloned voice 'narrator', Voice Lab off"
    ):
        (edceleste.pocket_voices_folder / "narrator").mkdir(parents=True)
        (edceleste.pocket_voices_folder / "narrator/profile.npy").write_bytes(b"voice")
        edceleste.save_tts_settings(
            TTSModel(
                provider="pocket",
                params=PocketParamsModel(type="pocket", profile="narrator"),
                volume=0.5,
                voice_lab=VoiceLabModel(enabled=False),
            )
        )
        pocket_engine = edceleste.fake_tts_providers["pocket"]

    with allure.step("And the LLM answers 'Copy that, Commander.'"):
        edceleste.use_scripted_model(answer_copy_that)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then the Pocket TTS engine is asked to say the answer"):
            await edceleste.wait_until(
                pilot,
                lambda: "Copy that, Commander." in pocket_engine.spoken_texts,
                "the answer handed to the voice engine",
            )

        with allure.step(
            "And it uses the voice file 'narrator' from the Pocket TTS folder"
        ):
            assert pocket_engine.spoken_profile_paths[-1] == (
                edceleste.pocket_voices_folder / "narrator/profile.npy"
            )

        with allure.step("And the speakers play the voice at the saved volume"):
            await edceleste.wait_until(
                pilot,
                lambda: edceleste.fake_speaker.times_closed == 1,
                "the speakers done playing",
            )
            np.testing.assert_allclose(
                edceleste.fake_speaker.everything_played(),
                what_the_speaker_should_play(pocket_engine.voice_pieces, 0.5),
                atol=1e-6,
            )
