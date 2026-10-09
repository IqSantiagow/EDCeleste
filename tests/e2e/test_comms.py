import asyncio

import allure
import pytest
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall
from textual.app import App
from textual.pilot import Pilot

from tests.e2e.conftest import comms_entries

pytestmark = [pytest.mark.anyio, allure.feature("COMMS conversation with Celeste")]


def thinking_indicator_is_visible(app: App) -> bool:
    return not app.screen.query_one("#comms-thinking-indicator").has_class("hidden")


async def send_comms_message(pilot: Pilot, message: str) -> None:
    await pilot.click("#comms-input")
    await pilot.press(*message)
    await pilot.press("enter")


async def answer_with_landing_gear_toggle(messages, agent_info):
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
        yield "Landing gear toggled, Commander."


@allure.title("Celeste shows her answer in COMMS and speaks it")
async def test_should_show_and_speak_celestes_answer(edceleste):
    async def answer_copy_that(messages, agent_info):
        yield "Copy that, "
        yield "Commander."

    with allure.step("Given the LLM answers 'Copy that, Commander.'"):
        edceleste.use_scripted_model(answer_copy_that)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then COMMS shows the message and the answer"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer in COMMS",
            )
            assert comms_entries(pilot.app, "user-command") == ["hello"]
            assert comms_entries(pilot.app, "llm-response") == ["Copy that, Commander."]

        with allure.step("And Celeste speaks the answer"):
            assert edceleste.spoken_texts == ["Copy that, Commander."]


@allure.title("The thinking indicator shows only while Celeste answers")
async def test_should_show_the_thinking_indicator_only_while_celeste_answers(
    edceleste,
):
    model_may_answer = asyncio.Event()

    async def answer_when_allowed(messages, agent_info):
        await model_may_answer.wait()
        yield "Copy that, Commander."

    with allure.step("Given the LLM waits before it answers"):
        edceleste.use_scripted_model(answer_when_allowed)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the thinking indicator is hidden"):
            assert not thinking_indicator_is_visible(pilot.app)

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then the thinking indicator shows while the LLM works"):
            await edceleste.wait_until(
                pilot,
                lambda: thinking_indicator_is_visible(pilot.app),
                "the thinking indicator while the model answers",
            )

        with allure.step("When the LLM answers"):
            model_may_answer.set()

        with allure.step("Then the thinking indicator hides and the answer shows"):
            await edceleste.wait_until(
                pilot,
                lambda: not thinking_indicator_is_visible(pilot.app),
                "the thinking indicator hidden after the answer",
            )
            assert comms_entries(pilot.app, "llm-response") == ["Copy that, Commander."]


@allure.title("Celeste toggles the landing gear by pressing its key in the game")
async def test_should_press_the_bound_key_when_celeste_performs_a_game_action(
    edceleste,
):
    with allure.step("Given game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step("And the LLM decides to toggle the landing gear"):
        edceleste.use_scripted_model(answer_with_landing_gear_toggle)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'gear' in COMMS"):
            await send_comms_message(pilot, "gear")

        with allure.step("Then COMMS shows the game action and Celeste's answer"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer after the game action",
            )
            assert comms_entries(pilot.app, "llm-action") == [
                "Perform Game Action -> LandingGearToggle"
            ]
            assert comms_entries(pilot.app, "llm-error") == []
            assert comms_entries(pilot.app, "llm-response") == [
                "Landing gear toggled, Commander."
            ]

        with allure.step("And the landing gear key Shift+L is pressed in the game"):
            assert edceleste.fake_keyboard.keyboard_log == [
                "keyDown shiftleft",
                "press l",
                "keyUp shiftleft",
            ]


@allure.title("Celeste presses no key when game actions are turned off")
async def test_should_show_an_error_and_press_nothing_when_game_actions_are_off(
    edceleste,
):
    with allure.step("Given game actions are off in the settings"):
        assert edceleste.settings.game_actions.enabled is False

    with allure.step("And the LLM decides to toggle the landing gear"):
        edceleste.use_scripted_model(answer_with_landing_gear_toggle)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'gear' in COMMS"):
            await send_comms_message(pilot, "gear")

        with allure.step("Then COMMS shows that the game action was refused"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer after the refused game action",
            )
            assert comms_entries(pilot.app, "llm-action") == [
                "Perform Game Action -> LandingGearToggle"
            ]
            assert comms_entries(pilot.app, "llm-error") == [
                "Game actions are disabled by the user."
            ]

        with allure.step("And no key is pressed in the game"):
            assert edceleste.fake_keyboard.keyboard_log == []


@allure.title("A dropped LLM connection shows a failed turn and stops thinking")
async def test_should_show_a_failed_turn_and_stop_thinking_when_the_connection_drops(
    edceleste,
):
    async def answer_and_lose_the_connection(messages, agent_info):
        yield "Copy that, "
        raise ConnectionError("Provider is down")

    with allure.step("Given the LLM connection drops in the middle of the answer"):
        edceleste.use_scripted_model(answer_and_lose_the_connection)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then COMMS shows that the turn failed"):
            await edceleste.wait_until(
                pilot,
                lambda: (
                    "LLM turn failed: Provider is down"
                    in comms_entries(pilot.app, "system-message")
                ),
                "the failed turn in COMMS",
            )

        with allure.step("And the thinking indicator hides"):
            await edceleste.wait_until(
                pilot,
                lambda: not thinking_indicator_is_visible(pilot.app),
                "the thinking indicator hidden after the failed turn",
            )


@allure.title("Celeste answers the next message after a failed turn")
async def test_should_answer_the_next_message_after_a_failed_turn(edceleste):
    connection_is_down = True

    async def answer_unless_the_connection_is_down(messages, agent_info):
        if connection_is_down:
            raise ConnectionError("Provider is down")
        yield "Copy that, Commander."

    with allure.step("Given the LLM connection is down"):
        edceleste.use_scripted_model(answer_unless_the_connection_is_down)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And a message sent in COMMS has failed"):
            await send_comms_message(pilot, "hello")
            await edceleste.wait_until(
                pilot,
                lambda: (
                    "LLM turn failed: Provider is down"
                    in comms_entries(pilot.app, "system-message")
                ),
                "the failed turn in COMMS",
            )

        with allure.step("When the connection is back"):
            connection_is_down = False

        with allure.step("And the Commander sends 'again' in COMMS"):
            await send_comms_message(pilot, "again")

        with allure.step("Then Celeste answers in COMMS"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer after the failed turn",
            )
            assert comms_entries(pilot.app, "llm-response") == ["Copy that, Commander."]
