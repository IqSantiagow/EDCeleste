import asyncio

import allure
import numpy as np
import pytest
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall

from tests.e2e.conftest import FAKE_SAMPLE_RATE, comms_entries, send_comms_message
from tests.e2e.test_comms import thinking_indicator_is_visible
from tests.e2e.test_instinct_spoken_reply import (
    DEPLOY_LANDING_GEAR,
    LANDING_GEAR_KEYS,
    STATUS_LANDING_GEAR_DOWN,
)
from tests.e2e.test_ship_replies import (
    STATUS_LIGHTS_ON,
    game_changes_the_flags,
    game_writes_first_status_file,
    wait_for_the_gear_in_the_ship_panel,
)
from tests.e2e.test_streaming_voice import (
    SAVED_VOLUME,
    chatterbox_settings,
    what_the_speaker_should_play,
)
from tests.e2e.test_voice_profiles import write_voice_profile_files

pytestmark = [pytest.mark.anyio, allure.feature("Voice queue")]

LONG_ANSWER = "Here is everything I know about this system, Commander."
SECOND_ANSWER = "The next system is a quiet one, Commander."
PAD_ANSWER = "Your pad is twelve, Commander."
GEAR_REPLY = "Landing gear deployed"
LIGHTS_REPLY = "Lights on"
TELL_ME_ABOUT_THE_SYSTEM = "tell me about the system"
DEPLOY_GEAR_AND_TELL_ME_THE_PAD = "deploy the landing gear and tell me which pad"

# The fake voice has three pieces of two slices each. The speaker is held after
# the first slice, so it has played a sixth of the voice when the Commander cuts it
SLICES_IN_ONE_VOICE = 6
SLICES_PLAYED_BEFORE_THE_HOLD = 1
SLICES_PLAYED_WHEN_CUT = SLICES_PLAYED_BEFORE_THE_HOLD + 1
SAMPLES_IN_ONE_SLICE = FAKE_SAMPLE_RATE // 20

HOLD_THE_KEY = "the push-to-talk key"
HOLD_THE_MIC_BUTTON = "the mic button in COMMS"

TALKING_WAYS = [
    pytest.param(HOLD_THE_KEY, id="push-to-talk-key"),
    pytest.param(HOLD_THE_MIC_BUTTON, id="mic-button"),
]


def answer_with(*answers: str):
    """An LLM that gives the answers one after the other, one for every message"""
    answers_left = iter(answers)

    async def answer_in_turn(messages, agent_info):
        yield next(answers_left)

    return answer_in_turn


def celeste_speaks_with_a_voice_on_a_gpu(edceleste) -> None:
    """Chatterbox on a GPU speaks in pieces through the speaker, and the speaker
    stops after its first slice until the test lets it go on"""
    write_voice_profile_files(edceleste, "narrator")
    edceleste.save_tts_settings(chatterbox_settings(device="cuda"))
    edceleste.fake_speaker.hold_playback_after(SLICES_PLAYED_BEFORE_THE_HOLD)


def turn_on_talking(edceleste, way: str) -> None:
    key = "Key.f9" if way == HOLD_THE_KEY else None
    edceleste.turn_speech_to_text_on(key)


async def start_talking(edceleste, pilot, way: str) -> None:
    if way == HOLD_THE_KEY:
        await edceleste.global_keys_and_mouse.hold_key("Key.f9")
    else:
        await pilot.mouse_down("#comms-stt-button")
    await edceleste.wait_until(
        pilot, lambda: edceleste.microphone.times_opened == 1, "the microphone on"
    )


async def stop_talking(edceleste, pilot, way: str) -> None:
    if way == HOLD_THE_KEY:
        await edceleste.global_keys_and_mouse.release_key("Key.f9")
    else:
        await pilot.mouse_up("#comms-stt-button")


async def celeste_is_saying_the_answer(edceleste, pilot, message: str) -> None:
    await send_comms_message(pilot, message)
    await edceleste.wait_until(
        pilot, lambda: edceleste.fake_speaker.is_holding, "Celeste in the middle of it"
    )


async def game_reports_the_gear_down_while_celeste_speaks(edceleste, pilot) -> None:
    game_changes_the_flags(edceleste, STATUS_LANDING_GEAR_DOWN)
    await wait_for_the_gear_in_the_ship_panel(edceleste, pilot)
    # The voice line is queued by the same Status.json, before the panel is drawn
    await pilot.pause()


def the_voice_played_in_full(chatterbox, times: int = 1) -> np.ndarray:
    one_voice = what_the_speaker_should_play(chatterbox.voice_pieces, SAVED_VOLUME)
    return np.concatenate([one_voice] * times)


def played_after_the_cut(speaker) -> np.ndarray:
    return speaker.everything_played()[SLICES_PLAYED_WHEN_CUT * SAMPLES_IN_ONE_SLICE :]


def slices_played(edceleste) -> int:
    return len(edceleste.fake_speaker.blocks)


@allure.title("Holding {way} cuts Celeste off in the middle of a sentence")
@pytest.mark.parametrize("way", TALKING_WAYS)
async def test_should_cut_celeste_off_when_the_commander_starts_to_talk(edceleste, way):
    with allure.step("Given speech to text is on"):
        turn_on_talking(edceleste, way)

    with allure.step("And Celeste has a voice on a GPU and a slow speaker"):
        celeste_speaks_with_a_voice_on_a_gpu(edceleste)
        speaker = edceleste.fake_speaker

    with allure.step("And the LLM answers a long text"):
        edceleste.use_scripted_model(answer_with(LONG_ANSWER))

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")
        spoken_at_boot = len(edceleste.spoken_texts)
        await game_writes_first_status_file(edceleste, pilot, flags=0)

        with allure.step("And Celeste is in the middle of saying the answer"):
            await celeste_is_saying_the_answer(
                edceleste, pilot, TELL_ME_ABOUT_THE_SYSTEM
            )

        with allure.step("And the game reports the gear down, Celeste has to wait"):
            await game_reports_the_gear_down_while_celeste_speaks(edceleste, pilot)

        with allure.step(f"When the Commander holds {way}"):
            await start_talking(edceleste, pilot, way)

        with allure.step("Then Celeste goes silent in the middle of the sentence"):
            speaker.let_playing_go_on()
            await edceleste.wait_until(
                pilot, lambda: speaker.times_closed == 1, "the speaker closed"
            )
            assert speaker.times_aborted == 1
            assert slices_played(edceleste) == SLICES_PLAYED_WHEN_CUT
            assert slices_played(edceleste) < SLICES_IN_ONE_VOICE

        with allure.step("And what waited to be said is not said any more"):
            await pilot.pause(0.5)
            assert edceleste.spoken_texts[spoken_at_boot:] == [LONG_ANSWER]
            assert speaker.times_opened == 1

        with allure.step("And COMMS shows the whole answer"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "the answer in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [LONG_ANSWER]

        await stop_talking(edceleste, pilot, way)


@allure.title("After the Commander cut her off, Celeste says the next thing in full")
async def test_should_say_the_next_reply_in_full_after_the_commander_cut_her_off(
    edceleste,
):
    with allure.step("Given speech to text is on with F9 as the push-to-talk key"):
        edceleste.turn_speech_to_text_on("Key.f9")

    with allure.step("And the microphone hears 'deploy the landing gear'"):
        edceleste.microphone.hears(DEPLOY_LANDING_GEAR)

    with allure.step("And game actions are allowed and Instinct picks the gear"):
        edceleste.allow_game_actions()
        instinct_model = edceleste.turn_instinct_on()
        instinct_model.choices_by_message[DEPLOY_LANDING_GEAR] = "LandingGearToggle"

    with allure.step("And Celeste has a voice on a GPU and a slow speaker"):
        celeste_speaks_with_a_voice_on_a_gpu(edceleste)
        chatterbox = edceleste.fake_tts_providers["chatterbox"]
        speaker = edceleste.fake_speaker

    with allure.step("And the LLM answers a long text"):
        edceleste.use_scripted_model(answer_with(LONG_ANSWER))

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")
        spoken_at_boot = len(edceleste.spoken_texts)
        await game_writes_first_status_file(edceleste, pilot, flags=0)

        with allure.step("And Celeste is in the middle of saying the answer"):
            await celeste_is_saying_the_answer(
                edceleste, pilot, TELL_ME_ABOUT_THE_SYSTEM
            )

        with allure.step(
            "When the Commander holds F9, says 'deploy the landing gear' and lets go"
        ):
            await start_talking(edceleste, pilot, HOLD_THE_KEY)
            speaker.let_playing_go_on()
            await stop_talking(edceleste, pilot, HOLD_THE_KEY)

        with allure.step("Then the landing gear key is pressed in the game"):
            await edceleste.wait_until(
                pilot,
                lambda: edceleste.fake_keyboard.keyboard_log == LANDING_GEAR_KEYS,
                "the landing gear key pressed",
            )

        with allure.step("And when the game reports the gear down Celeste says so"):
            game_changes_the_flags(edceleste, STATUS_LANDING_GEAR_DOWN)
            await edceleste.wait_until(
                pilot,
                lambda: speaker.times_closed == 2,
                "the second voice played to the end",
            )
            assert edceleste.spoken_texts[spoken_at_boot:] == [LONG_ANSWER, GEAR_REPLY]

        with allure.step("And she says all of it, not a cut piece"):
            assert speaker.times_aborted == 1
            np.testing.assert_allclose(
                speaker.everything_played()[
                    SLICES_PLAYED_WHEN_CUT * SAMPLES_IN_ONE_SLICE :
                ],
                the_voice_played_in_full(chatterbox),
                atol=1e-6,
            )


@allure.title("A message typed while Celeste speaks cuts her off")
async def test_should_cut_celeste_off_when_the_commander_sends_a_message(edceleste):
    with allure.step("Given Celeste has a voice on a GPU and a slow speaker"):
        celeste_speaks_with_a_voice_on_a_gpu(edceleste)
        chatterbox = edceleste.fake_tts_providers["chatterbox"]
        speaker = edceleste.fake_speaker

    with allure.step("And the LLM answers the first and then the second message"):
        edceleste.use_scripted_model(answer_with(LONG_ANSWER, SECOND_ANSWER))

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")
        spoken_at_boot = len(edceleste.spoken_texts)
        await game_writes_first_status_file(edceleste, pilot, flags=0)

        with allure.step("And Celeste is in the middle of saying the first answer"):
            await celeste_is_saying_the_answer(
                edceleste, pilot, TELL_ME_ABOUT_THE_SYSTEM
            )

        with allure.step("And the game reports the gear down, Celeste has to wait"):
            await game_reports_the_gear_down_while_celeste_speaks(edceleste, pilot)

        with allure.step("When the Commander types another message in COMMS"):
            await send_comms_message(pilot, "and the next system?")
            await edceleste.wait_until(
                pilot,
                lambda: len(comms_entries(pilot.app, "llm-response")) == 2,
                "the second answer in COMMS",
            )
            speaker.let_playing_go_on()

        with allure.step("Then the first answer is cut and the second one is said"):
            await edceleste.wait_until(
                pilot, lambda: speaker.times_closed == 2, "the second voice played"
            )
            assert speaker.times_aborted == 1
            assert edceleste.spoken_texts[spoken_at_boot:] == [
                LONG_ANSWER,
                SECOND_ANSWER,
            ]

        with allure.step("And the second answer is said in full"):
            np.testing.assert_allclose(
                speaker.everything_played()[
                    SLICES_PLAYED_WHEN_CUT * SAMPLES_IN_ONE_SLICE :
                ],
                the_voice_played_in_full(chatterbox),
                atol=1e-6,
            )

        with allure.step("And what waited to be said before is never said"):
            await pilot.pause(0.5)
            assert GEAR_REPLY not in edceleste.spoken_texts


@allure.title("Two reactions to the game are both heard, in order, one at a time")
async def test_should_say_two_reactions_in_order_one_after_the_other(edceleste):
    with allure.step("Given Celeste has a voice on a GPU and a slow speaker"):
        celeste_speaks_with_a_voice_on_a_gpu(edceleste)
        chatterbox = edceleste.fake_tts_providers["chatterbox"]
        speaker = edceleste.fake_speaker

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")
        spoken_at_boot = len(edceleste.spoken_texts)

        with allure.step("And the game reports the gear up and the lights off"):
            await game_writes_first_status_file(edceleste, pilot, flags=0)

        with allure.step("When the game reports the gear down and the lights on"):
            game_changes_the_flags(
                edceleste, STATUS_LANDING_GEAR_DOWN | STATUS_LIGHTS_ON
            )
            await edceleste.wait_until(
                pilot, lambda: speaker.is_holding, "Celeste in the middle of the first"
            )

        with allure.step("Then Celeste says the gear first and the lights wait"):
            await pilot.pause(0.3)
            assert edceleste.spoken_texts[spoken_at_boot:] == [GEAR_REPLY]
            assert speaker.times_opened == 1

        with allure.step("And when the first is done she says the lights"):
            speaker.let_playing_go_on()
            await edceleste.wait_until(
                pilot, lambda: speaker.times_closed == 2, "both voices played"
            )
            assert edceleste.spoken_texts[spoken_at_boot:] == [GEAR_REPLY, LIGHTS_REPLY]

        with allure.step("And the speaker played both in full, one after the other"):
            np.testing.assert_allclose(
                speaker.everything_played(),
                the_voice_played_in_full(chatterbox, times=2),
                atol=1e-6,
            )


def answer_the_pad_after_the_game_reports_the_gear(answer_may_come: asyncio.Event):
    """An LLM that presses the landing gear key at once and gives the answer only
    when the test lets it, like a model that needs time to think"""

    async def press_the_gear_then_answer(messages, agent_info):
        tool_already_answered = any(
            isinstance(part, ToolReturnPart) for part in messages[-1].parts
        )
        if not tool_already_answered:
            yield {
                0: DeltaToolCall(
                    name="perform_game_action",
                    json_args='{"action": "LandingGearToggle"}',
                )
            }
        else:
            await answer_may_come.wait()
            yield PAD_ANSWER

    return press_the_gear_then_answer


@allure.title(
    "An answer waits for the reaction that Celeste is saying, then goes before "
    "the ones still waiting"
)
async def test_should_say_the_answer_between_the_playing_and_the_waiting_reaction(
    edceleste,
):
    answer_may_come = asyncio.Event()

    with allure.step("Given game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step("And Celeste has a voice on a GPU and a slow speaker"):
        celeste_speaks_with_a_voice_on_a_gpu(edceleste)
        chatterbox = edceleste.fake_tts_providers["chatterbox"]
        speaker = edceleste.fake_speaker

    with allure.step("And the LLM presses the gear and thinks about the pad"):
        edceleste.use_scripted_model(
            answer_the_pad_after_the_game_reports_the_gear(answer_may_come)
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")
        spoken_at_boot = len(edceleste.spoken_texts)
        await game_writes_first_status_file(edceleste, pilot, flags=0)

        with allure.step(
            "And the Commander asked to deploy the gear and tell which pad"
        ):
            await send_comms_message(pilot, DEPLOY_GEAR_AND_TELL_ME_THE_PAD)
            await edceleste.wait_until(
                pilot,
                lambda: edceleste.fake_keyboard.keyboard_log == LANDING_GEAR_KEYS,
                "the landing gear key pressed",
            )

        with allure.step("When the game reports the gear down and the lights on"):
            game_changes_the_flags(
                edceleste, STATUS_LANDING_GEAR_DOWN | STATUS_LIGHTS_ON
            )
            await edceleste.wait_until(
                pilot, lambda: speaker.is_holding, "Celeste saying the gear"
            )

        with allure.step("And Celeste finishes thinking about the pad"):
            answer_may_come.set()

        with allure.step("Then the answer is written but does not cut the gear reply"):
            await edceleste.wait_until(
                pilot,
                lambda: (
                    comms_entries(pilot.app, "llm-response") != []
                    and not thinking_indicator_is_visible(pilot.app)
                ),
                "the answer in COMMS and Celeste done thinking",
            )
            assert comms_entries(pilot.app, "llm-response") == [PAD_ANSWER]
            assert edceleste.spoken_texts[spoken_at_boot:] == [GEAR_REPLY]

        with allure.step("And she says the answer before the lights"):
            speaker.let_playing_go_on()
            await edceleste.wait_until(
                pilot, lambda: speaker.times_closed == 3, "all three voices played"
            )
            assert edceleste.spoken_texts[spoken_at_boot:] == [
                GEAR_REPLY,
                PAD_ANSWER,
                LIGHTS_REPLY,
            ]

        with allure.step("And nothing was cut: all three were said in full"):
            assert speaker.times_aborted == 0
            np.testing.assert_allclose(
                speaker.everything_played(),
                the_voice_played_in_full(chatterbox, times=3),
                atol=1e-6,
            )


WAITED_UNDER_THE_LIMIT = 4
WAITED_OVER_THE_LIMIT = 6


@allure.title(
    "A reaction that waited {seconds_waited} s behind an answer is {what_happens}"
)
@pytest.mark.parametrize(
    "seconds_waited, what_happens, gear_is_said",
    [
        pytest.param(WAITED_UNDER_THE_LIMIT, "still said", True, id="waited-4-seconds"),
        pytest.param(WAITED_OVER_THE_LIMIT, "not said", False, id="waited-6-seconds"),
    ],
)
async def test_should_not_say_a_reaction_that_waited_longer_than_five_seconds(
    edceleste, seconds_waited, what_happens, gear_is_said
):
    with allure.step("Given Celeste has a voice on a GPU and a slow speaker"):
        celeste_speaks_with_a_voice_on_a_gpu(edceleste)
        speaker = edceleste.fake_speaker

    with allure.step("And the LLM answers a long text"):
        edceleste.use_scripted_model(answer_with(LONG_ANSWER))

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")
        spoken_at_boot = len(edceleste.spoken_texts)
        await game_writes_first_status_file(edceleste, pilot, flags=0)

        with allure.step("And Celeste is in the middle of saying the answer"):
            await celeste_is_saying_the_answer(
                edceleste, pilot, TELL_ME_ABOUT_THE_SYSTEM
            )

        with allure.step("And the game reports the gear down, Celeste has to wait"):
            await game_reports_the_gear_down_while_celeste_speaks(edceleste, pilot)

        with allure.step(f"When the answer takes {seconds_waited} seconds to say"):
            edceleste.clock.move_on(seconds_waited)
            speaker.let_playing_go_on()

        with allure.step(f"Then the gear reply is {what_happens}"):
            await edceleste.wait_until(
                pilot, lambda: speaker.times_closed >= 1, "the answer played"
            )
            # Nothing visible tells that a reply was dropped, so we look for a moment
            await pilot.pause(0.5)
            expected = [LONG_ANSWER, GEAR_REPLY]
            if not gear_is_said:
                expected.remove(GEAR_REPLY)
            assert edceleste.spoken_texts[spoken_at_boot:] == expected

        with allure.step("And a reaction that does not wait is said as always"):
            edceleste.clock.go_back_to_real_time()
            game_changes_the_flags(
                edceleste, STATUS_LANDING_GEAR_DOWN | STATUS_LIGHTS_ON
            )
            await edceleste.wait_until(
                pilot,
                lambda: LIGHTS_REPLY in edceleste.spoken_texts,
                "the lights reply said",
            )
            assert edceleste.spoken_texts[spoken_at_boot:] == expected + [LIGHTS_REPLY]


@allure.title("Celeste stops thinking when her answer is written, not when it is said")
async def test_should_stop_thinking_while_celeste_is_still_saying_the_answer(edceleste):
    with allure.step("Given Celeste has a voice on a GPU and a slow speaker"):
        celeste_speaks_with_a_voice_on_a_gpu(edceleste)
        speaker = edceleste.fake_speaker

    with allure.step("And the LLM answers a long text"):
        edceleste.use_scripted_model(answer_with(LONG_ANSWER))

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks about the system in COMMS"):
            await send_comms_message(pilot, TELL_ME_ABOUT_THE_SYSTEM)

        with allure.step("Then COMMS shows the answer and Celeste is not thinking"):
            await edceleste.wait_until(
                pilot,
                lambda: (
                    comms_entries(pilot.app, "llm-response") != []
                    and not thinking_indicator_is_visible(pilot.app)
                ),
                "the answer in COMMS and the thinking indicator gone",
            )
            assert comms_entries(pilot.app, "llm-response") == [LONG_ANSWER]

        with allure.step("And she is still saying it"):
            await edceleste.wait_until(
                pilot, lambda: speaker.is_holding, "Celeste in the middle of it"
            )
            assert speaker.times_closed == 0
            speaker.let_playing_go_on()
