import asyncio

import pytest
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall
from textual.app import App
from textual.pilot import Pilot

from tests.e2e.conftest import comms_entries

pytestmark = pytest.mark.anyio


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


async def test_should_show_and_speak_celestes_answer(edceleste):
    async def answer_copy_that(messages, agent_info):
        yield "Copy that, "
        yield "Commander."

    edceleste.use_scripted_model(answer_copy_that)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        await send_comms_message(pilot, "hello")

        await edceleste.wait_until(
            pilot,
            lambda: comms_entries(pilot.app, "llm-response") != [],
            "Celeste's answer in COMMS",
        )
        assert comms_entries(pilot.app, "user-command") == ["hello"]
        assert comms_entries(pilot.app, "llm-response") == ["Copy that, Commander."]
        assert edceleste.spoken_texts == ["Copy that, Commander."]


async def test_should_show_the_thinking_indicator_only_while_celeste_answers(
    edceleste,
):
    model_may_answer = asyncio.Event()

    async def answer_when_allowed(messages, agent_info):
        await model_may_answer.wait()
        yield "Copy that, Commander."

    edceleste.use_scripted_model(answer_when_allowed)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)
        assert not thinking_indicator_is_visible(pilot.app)

        await send_comms_message(pilot, "hello")

        await edceleste.wait_until(
            pilot,
            lambda: thinking_indicator_is_visible(pilot.app),
            "the thinking indicator while the model answers",
        )

        model_may_answer.set()

        await edceleste.wait_until(
            pilot,
            lambda: not thinking_indicator_is_visible(pilot.app),
            "the thinking indicator hidden after the answer",
        )
        assert comms_entries(pilot.app, "llm-response") == ["Copy that, Commander."]


async def test_should_press_the_bound_key_when_celeste_performs_a_game_action(
    edceleste,
):
    edceleste.allow_game_actions()
    edceleste.use_scripted_model(answer_with_landing_gear_toggle)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        await send_comms_message(pilot, "gear")

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
        assert edceleste.fake_keyboard.keyboard_log == [
            "keyDown shiftleft",
            "press l",
            "keyUp shiftleft",
        ]


async def test_should_show_an_error_and_press_nothing_when_game_actions_are_off(
    edceleste,
):
    edceleste.use_scripted_model(answer_with_landing_gear_toggle)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        await send_comms_message(pilot, "gear")

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
        assert edceleste.fake_keyboard.keyboard_log == []


async def test_should_show_a_failed_turn_and_stop_thinking_when_the_connection_drops(
    edceleste,
):
    async def answer_and_lose_the_connection(messages, agent_info):
        yield "Copy that, "
        raise ConnectionError("Provider is down")

    edceleste.use_scripted_model(answer_and_lose_the_connection)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        await send_comms_message(pilot, "hello")

        await edceleste.wait_until(
            pilot,
            lambda: (
                "LLM turn failed: Provider is down"
                in comms_entries(pilot.app, "system-message")
            ),
            "the failed turn in COMMS",
        )
        await edceleste.wait_until(
            pilot,
            lambda: not thinking_indicator_is_visible(pilot.app),
            "the thinking indicator hidden after the failed turn",
        )


async def test_should_answer_the_next_message_after_a_failed_turn(edceleste):
    connection_is_down = True

    async def answer_unless_the_connection_is_down(messages, agent_info):
        if connection_is_down:
            raise ConnectionError("Provider is down")
        yield "Copy that, Commander."

    edceleste.use_scripted_model(answer_unless_the_connection_is_down)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        await send_comms_message(pilot, "hello")
        await edceleste.wait_until(
            pilot,
            lambda: (
                "LLM turn failed: Provider is down"
                in comms_entries(pilot.app, "system-message")
            ),
            "the failed turn in COMMS",
        )

        connection_is_down = False
        await send_comms_message(pilot, "again")

        await edceleste.wait_until(
            pilot,
            lambda: comms_entries(pilot.app, "llm-response") != [],
            "Celeste's answer after the failed turn",
        )
        assert comms_entries(pilot.app, "llm-response") == ["Copy that, Commander."]
