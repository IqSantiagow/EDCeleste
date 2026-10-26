import json
import re

import allure
import pytest
from pydantic_ai.messages import UserPromptPart

from tests.e2e.conftest import history_lines, send_comms_message

pytestmark = [pytest.mark.anyio, allure.feature("Game state in the prompt")]

GAME_STATE_HEADING = "Current game state is:"

STATUS_SHIELDS_UP = 8
STATUS_SHIELDS_UP_AND_SUPERCRUISE = 8 + 16
STATUS_DOCKED_SHIELDS_DOWN = 1

DOCKED_MARKET_ID = 3222042112


def prompt_remembering_llm(prompts_sent_to_llm: list[str]):
    async def answer_and_remember_prompt(messages, agent_info):
        for part in messages[-1].parts:
            if isinstance(part, UserPromptPart):
                prompts_sent_to_llm.append(part.content)
        yield "Copy that, Commander."

    return answer_and_remember_prompt


def instructions_remembering_llm(instructions_sent_to_llm: list[str]):
    """The game state is the last part of the instructions the agent sends with
    every request, not a part of the conversation history."""

    async def answer_and_remember_instructions(messages, agent_info):
        instructions_sent_to_llm.append(agent_info.instructions)
        yield "Copy that, Commander."

    return answer_and_remember_instructions


def game_state_lines(instructions: str) -> list[str]:
    return instructions.split(GAME_STATE_HEADING + "\n", 1)[1].split("\n")


def write_status_file(edceleste, flags: int) -> None:
    status = {"timestamp": "2026-10-05T12:00:00Z", "event": "Status", "Flags": flags}
    edceleste.status_file.write_text(json.dumps(status), encoding="utf-8")


def write_market_file(edceleste) -> None:
    market = {
        "timestamp": "2026-10-05T12:00:00Z",
        "event": "Market",
        "MarketID": DOCKED_MARKET_ID,
        "StationName": "Fan Horizons",
        "StarSystem": "Beta Sculptoris",
        "Items": [],
    }
    market_file = edceleste.journal_file.parent / "Market.json"
    market_file.write_text(json.dumps(market), encoding="utf-8")


def game_state_of_llm(edceleste) -> str:
    return edceleste.container.llm_service().game_state


async def send_message_and_get_instructions(
    edceleste, pilot, instructions_sent_to_llm
) -> str:
    requests_before = len(instructions_sent_to_llm)
    await send_comms_message(pilot, "hello")
    await edceleste.wait_until(
        pilot,
        lambda: len(instructions_sent_to_llm) > requests_before,
        "the request reaching the LLM",
    )
    return instructions_sent_to_llm[-1]


@allure.title(
    "The instructions have one game state heading and every sentence kept apart"
)
async def test_should_send_the_game_state_once_with_every_sentence_kept_apart(
    edceleste,
):
    instructions_sent_to_llm: list[str] = []

    with allure.step("Given the LLM remembers the instructions of every request"):
        edceleste.use_scripted_model(
            instructions_remembering_llm(instructions_sent_to_llm)
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "And the Commander is in a system, in supercruise, scooping fuel"
        ):
            edceleste.append_journal_event("Commander")
            edceleste.append_journal_event("Location")
            edceleste.append_journal_event("SupercruiseEntry")
            edceleste.append_journal_event("FuelScoop")
            write_status_file(edceleste, STATUS_SHIELDS_UP_AND_SUPERCRUISE)
            await edceleste.wait_until(
                pilot,
                lambda: "in supercruise" in game_state_of_llm(edceleste),
                "supercruise in the game state",
            )

        with allure.step("When the Commander sends a message to Celeste"):
            instructions = await send_message_and_get_instructions(
                edceleste, pilot, instructions_sent_to_llm
            )

        with allure.step(
            "Then the instructions say 'Current game state is:' only once"
        ):
            assert instructions.count(GAME_STATE_HEADING) == 1

        with allure.step("And the heading is alone on its line above the game state"):
            lines = instructions.split("\n")
            heading_line = lines.index(GAME_STATE_HEADING)
            assert lines[heading_line + 1].startswith("Commander name is")

        game_state = "\n".join(game_state_lines(instructions))

        with allure.step("And the fuel sentence ends with a period"):
            assert re.search(
                r"^Current fuel level is: \d+\.\d+\.", game_state, re.MULTILINE
            )

        with allure.step("And no sentence runs into the next one"):
            assert not re.search(r"[.\d][A-Z]", game_state)
            assert "  " not in game_state


@allure.title("The parts of the game state come in a fixed order, market last")
async def test_should_send_the_game_state_parts_commander_first_and_market_last(
    edceleste,
):
    instructions_sent_to_llm: list[str] = []
    parts_in_the_expected_order = [
        "Commander name is",
        "Player is currently in the",
        "ship shields are down",
        "Current fuel level is",
        "Ship hull health is at",
        "sells",
    ]

    with allure.step("Given the LLM remembers the instructions of every request"):
        edceleste.use_scripted_model(
            instructions_remembering_llm(instructions_sent_to_llm)
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander is docked at a station with a market"):
            edceleste.append_journal_event("Commander")
            edceleste.append_journal_event("Loadout")
            edceleste.append_journal_event("Docked")
            write_status_file(edceleste, STATUS_DOCKED_SHIELDS_DOWN)
            write_market_file(edceleste)
            await edceleste.wait_until(
                pilot,
                lambda: "sells" in game_state_of_llm(edceleste),
                "the station market in the game state",
            )

        with allure.step("When the Commander sends a message to Celeste"):
            instructions = await send_message_and_get_instructions(
                edceleste, pilot, instructions_sent_to_llm
            )
        lines = game_state_lines(instructions)

        with allure.step(
            "Then the commander comes first, then location, ship, fuel, hull "
            "and the market last"
        ):
            line_of_each_part = []
            for part in parts_in_the_expected_order:
                matching_lines = [
                    number for number, line in enumerate(lines) if part in line
                ]
                assert matching_lines, f"No line with '{part}': {lines}"
                line_of_each_part.append(matching_lines[0])
            assert line_of_each_part == sorted(set(line_of_each_part))


@allure.title("Flying in space leaves no empty line where the ship and market go")
async def test_should_leave_out_the_ship_and_market_parts_when_there_is_nothing_to_say(
    edceleste,
):
    instructions_sent_to_llm: list[str] = []

    with allure.step("Given the LLM remembers the instructions of every request"):
        edceleste.use_scripted_model(
            instructions_remembering_llm(instructions_sent_to_llm)
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the ship flies with its shields up, not docked"):
            edceleste.append_journal_event("Commander")
            edceleste.append_journal_event("SupercruiseEntry")
            write_status_file(edceleste, STATUS_SHIELDS_UP)
            await edceleste.wait_until(
                pilot,
                lambda: "Player is currently in the" in game_state_of_llm(edceleste),
                "the system in the game state",
            )

        with allure.step("When the Commander sends a message to Celeste"):
            instructions = await send_message_and_get_instructions(
                edceleste, pilot, instructions_sent_to_llm
            )

        lines = game_state_lines(instructions)
        game_state = "\n".join(lines)

        with allure.step("Then the game state has no empty line"):
            assert "" not in lines

        with allure.step("And no double space"):
            assert "  " not in game_state

        with allure.step("And it says nothing about the ship or a market"):
            assert "shields are down" not in game_state
            assert "sells" not in game_state


@allure.title("Every message gets the newest game state and old states stay out")
async def test_should_send_only_the_newest_game_state_with_every_message(edceleste):
    requests_sent_to_llm: list[tuple[str, list[str]]] = []

    async def instructions_and_history_remembering_llm(messages, agent_info):
        requests_sent_to_llm.append((agent_info.instructions, history_lines(messages)))
        yield "Copy that, Commander."

    with allure.step(
        "Given the LLM remembers the instructions and history of every request"
    ):
        edceleste.use_scripted_model(instructions_and_history_remembering_llm)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the ship has 11.5 tonnes of fuel"):
            edceleste.write_status_file(fuel_main=11.5)
            await edceleste.wait_until(
                pilot,
                lambda: "fuel level is: 11.5." in game_state_of_llm(edceleste),
                "11.5 tonnes of fuel in the game state",
            )

        with allure.step("And the Commander sent a message to Celeste"):
            await send_comms_message(pilot, "first message")
            await edceleste.wait_until(
                pilot,
                lambda: len(requests_sent_to_llm) == 1,
                "the first message reaching the LLM",
            )

        with allure.step("And the fuel dropped to 7.5 tonnes"):
            edceleste.write_status_file(fuel_main=7.5)
            await edceleste.wait_until(
                pilot,
                lambda: "fuel level is: 7.5." in game_state_of_llm(edceleste),
                "7.5 tonnes of fuel in the game state",
            )

        with allure.step("When the Commander sends a second message to Celeste"):
            await send_comms_message(pilot, "second message")
            await edceleste.wait_until(
                pilot,
                lambda: len(requests_sent_to_llm) == 2,
                "the second message reaching the LLM",
            )

        first_instructions, _ = requests_sent_to_llm[0]
        second_instructions, second_history = requests_sent_to_llm[1]

        with allure.step("Then the first message came with 11.5 tonnes of fuel"):
            assert "Current fuel level is: 11.5." in first_instructions

        with allure.step("And the second message came with 7.5 tonnes and not 11.5"):
            assert "Current fuel level is: 7.5." in second_instructions
            assert "11.5" not in second_instructions

        with allure.step("And Celeste's memory holds the talk but no game state"):
            assert second_history == [
                "pilot: first message",
                "celeste: Copy that, Commander.",
                "pilot: second message",
            ]
