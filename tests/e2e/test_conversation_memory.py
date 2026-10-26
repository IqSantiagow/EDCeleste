import allure
import pytest
from pydantic_ai.messages import ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import DeltaToolCall

from tests.e2e.conftest import (
    comms_entries,
    history_lines,
    history_remembering_llm,
    send_comms_message,
)

pytestmark = [pytest.mark.anyio, allure.feature("Celeste's memory of the conversation")]

LOWER_THE_GEAR = "lower the gear"
LANDING_GEAR_TOOL_CALL = (
    "tool call: perform_game_action {'action': 'LandingGearToggle'}"
)
LANDING_GEAR_KEYS = ["keyDown shiftleft", "press l", "keyUp shiftleft"]


def llm_that_lowers_the_gear_then_answers(
    histories_sent_to_llm: list[list[str]],
    answer_after_the_tool: str,
    final_answer: str,
):
    """Calls the landing gear tool for 'lower the gear', says answer_after_the_tool
    when the tool has answered, and remembers the history for any other message."""

    async def lower_the_gear_then_answer(messages, agent_info):
        last_parts = messages[-1].parts
        if any(isinstance(part, ToolReturnPart) for part in last_parts):
            yield answer_after_the_tool
        elif any(
            isinstance(part, UserPromptPart) and part.content == LOWER_THE_GEAR
            for part in last_parts
        ):
            yield {
                0: DeltaToolCall(
                    name="perform_game_action",
                    json_args='{"action": "LandingGearToggle"}',
                )
            }
        else:
            histories_sent_to_llm.append(history_lines(messages))
            yield final_answer

    return lower_the_gear_then_answer


def number_of_answers_in_comms(app) -> int:
    return len(comms_entries(app, "llm-response"))


@allure.title(
    "Celeste forgets what is older than her last ten exchanges, reactions included"
)
async def test_should_forget_the_exchanges_older_than_the_last_ten(edceleste):
    histories_sent_to_llm: list[list[str]] = []

    with allure.step("Given the FSDJump reaction is on in the settings"):
        edceleste.react_to_event("FSDJump")

    with allure.step("And the LLM answers 'Answer 1.', 'Answer 2.' and so on"):
        edceleste.use_scripted_model(
            history_remembering_llm(histories_sent_to_llm, "Answer {number}.")
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "And the Commander asked question 1, Celeste reacted to a jump, "
            "and the Commander asked questions 2 to 10"
        ):
            await send_comms_message(pilot, "question 1")
            await edceleste.wait_until(
                pilot,
                lambda: number_of_answers_in_comms(pilot.app) == 1,
                "the answer to question 1 in COMMS",
            )

            edceleste.append_journal_event("FSDJump")
            await edceleste.wait_until(
                pilot,
                lambda: number_of_answers_in_comms(pilot.app) == 2,
                "Celeste's reaction to the jump in COMMS",
            )

            for question_number in range(2, 11):
                await send_comms_message(pilot, f"question {question_number}")
                await edceleste.wait_until(
                    pilot,
                    lambda: (
                        number_of_answers_in_comms(pilot.app) == question_number + 1
                    ),
                    f"the answer to question {question_number} in COMMS",
                )

        with allure.step("When the Commander asks question 11"):
            await send_comms_message(pilot, "question 11")
            await edceleste.wait_until(
                pilot,
                lambda: len(histories_sent_to_llm) == 12,
                "question 11 reaching the LLM",
            )

        history = histories_sent_to_llm[-1]
        jump_reaction_line = next(
            line for line in history if '"event":"FSDJump"' in line
        )

        with allure.step(
            "Then Celeste remembers the jump and questions 2 to 10 with their answers"
        ):
            expected_history = [jump_reaction_line, "celeste: Answer 2."]
            for question_number in range(2, 11):
                expected_history.append(f"pilot: question {question_number}")
                expected_history.append(f"celeste: Answer {question_number + 1}.")
            expected_history.append("pilot: question 11")
            assert history == expected_history

        with allure.step("And she no longer knows question 1 or her answer to it"):
            assert "pilot: question 1" not in history
            assert "celeste: Answer 1." not in history


@allure.title("After lowering the landing gear Celeste knows she did it")
async def test_should_remember_the_tool_she_used_and_its_result(edceleste):
    histories_sent_to_llm: list[list[str]] = []

    with allure.step("Given game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step("And the LLM toggles the landing gear when asked to lower it"):
        edceleste.use_scripted_model(
            llm_that_lowers_the_gear_then_answers(
                histories_sent_to_llm,
                answer_after_the_tool="Landing gear is down, Commander.",
                final_answer="I lowered the landing gear, Commander.",
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander asked Celeste to lower the gear"):
            await send_comms_message(pilot, LOWER_THE_GEAR)
            await edceleste.wait_until(
                pilot,
                lambda: (
                    "Landing gear is down, Commander."
                    in comms_entries(pilot.app, "llm-response")
                ),
                "Celeste's answer after the landing gear",
            )

        with allure.step("When the Commander asks 'what did you do?'"):
            await send_comms_message(pilot, "what did you do?")
            await edceleste.wait_until(
                pilot,
                lambda: len(histories_sent_to_llm) == 1,
                "the question reaching the LLM",
            )

        with allure.step(
            "Then Celeste's history has the request, the landing gear call, "
            "its result and her answer, before the question"
        ):
            assert histories_sent_to_llm[0] == [
                f"pilot: {LOWER_THE_GEAR}",
                LANDING_GEAR_TOOL_CALL,
                "tool result: perform_game_action",
                "celeste: Landing gear is down, Commander.",
                "pilot: what did you do?",
            ]

        with allure.step("And the landing gear key was pressed only once"):
            await edceleste.wait_until(
                pilot,
                lambda: (
                    "I lowered the landing gear, Commander."
                    in comms_entries(pilot.app, "llm-response")
                ),
                "Celeste's answer to the question",
            )
            assert edceleste.fake_keyboard.keyboard_log == LANDING_GEAR_KEYS


@allure.title("A turn that fails halfway leaves nothing of itself in Celeste's memory")
async def test_should_forget_a_turn_that_failed_after_a_tool_call(edceleste):
    histories_sent_to_llm: list[list[str]] = []

    async def lose_the_connection_after_the_tool(messages, agent_info):
        last_parts = messages[-1].parts
        if any(isinstance(part, ToolReturnPart) for part in last_parts):
            raise ConnectionError("Provider is down")
        if any(
            isinstance(part, UserPromptPart) and part.content == LOWER_THE_GEAR
            for part in last_parts
        ):
            yield {
                0: DeltaToolCall(
                    name="perform_game_action",
                    json_args='{"action": "LandingGearToggle"}',
                )
            }
        else:
            histories_sent_to_llm.append(history_lines(messages))
            yield "Yes, Commander."

    with allure.step("Given game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step(
        "And the LLM toggles the landing gear and then loses the connection"
    ):
        edceleste.use_scripted_model(lose_the_connection_after_the_tool)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "And the Commander asked to lower the gear and the turn failed"
        ):
            await send_comms_message(pilot, LOWER_THE_GEAR)
            await edceleste.wait_until(
                pilot,
                lambda: (
                    "LLM turn failed: Provider is down"
                    in comms_entries(pilot.app, "system-message")
                ),
                "the failed turn in COMMS",
            )

        with allure.step("When the Commander asks 'are you there?'"):
            await send_comms_message(pilot, "are you there?")
            await edceleste.wait_until(
                pilot,
                lambda: len(histories_sent_to_llm) == 1,
                "the question reaching the LLM",
            )

        with allure.step(
            "Then Celeste's history has only the new question, nothing of the "
            "failed turn"
        ):
            assert histories_sent_to_llm[0] == ["pilot: are you there?"]

        with allure.step("And Celeste answers in COMMS and out loud"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") == ["Yes, Commander."],
                "Celeste's answer in COMMS",
            )
            assert edceleste.spoken_texts == ["Yes, Commander."]
