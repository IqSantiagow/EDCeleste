import re

import allure
import pytest
from pydantic_ai.messages import UserPromptPart
from textual.app import App
from textual.widgets import Digits, Label

from tests.e2e.conftest import (
    comms_entries,
    recorded_journal_line,
    send_comms_message,
    ship_log_events,
)
from tests.e2e.test_journal_to_dashboard_stats import header_value, label_text

pytestmark = [pytest.mark.anyio, allure.feature("Start in the middle of a session")]

GAME_STATE_IS_NOT_SET = "Game state is not set. Cannot send message to LLM."
WELCOME_MESSAGE = (
    "Welcome to EDCeleste! Type your command below to communicate with Celeste."
)

EVENTS_ALREADY_IN_THE_JOURNAL = ["LoadGame", "Commander", "Loadout", "FSDJump"]

# A long journal, like the one of a real evening of flying. The loading has to
# go on after the services that react to events are ready, and only a journal
# of some hundreds of lines is that long
EVENTS_OF_ONE_JUMP = ["StartJump", "FSDJump", "FuelScoop"]
JUMPS_IN_THE_LONG_JOURNAL = 150
EVENTS_IN_THE_LONG_JOURNAL = ["LoadGame", "Commander", "Loadout", *EVENTS_OF_ONE_JUMP]


def write_the_files_of_a_session_in_progress(edceleste) -> None:
    for event_name in EVENTS_ALREADY_IN_THE_JOURNAL:
        edceleste.append_journal_event(event_name)
    edceleste.write_status_file(fuel_main=12.5, cargo=3)


def write_the_files_of_a_long_session_in_progress(edceleste) -> None:
    lines_of_one_jump = [recorded_journal_line(name) for name in EVENTS_OF_ONE_JUMP]
    with edceleste.journal_file.open("a", encoding="utf-8") as journal:
        for event_name in ["LoadGame", "Commander", "Loadout"]:
            journal.write(recorded_journal_line(event_name) + "\n")
        for _ in range(JUMPS_IN_THE_LONG_JOURNAL):
            journal.write("\n".join(lines_of_one_jump) + "\n")
    edceleste.write_status_file(fuel_main=12.5, cargo=3)


def react_to_every_event_in_the_long_journal(edceleste) -> None:
    for event_name in EVENTS_IN_THE_LONG_JOURNAL:
        edceleste.react_to_event(event_name)


def fuel_in_the_hud(app: App) -> str:
    return str(app.screen.query_one("#fuel-main-digits", Digits).value)


def cargo_in_the_hud(app: App) -> str:
    return str(app.screen.query_one("#cargo-bar .stat-bar-value", Label).content)


def remember_prompts_and_answer(prompts_sent_to_llm: list[str], answer: str):
    async def scripted_answer(messages, agent_info):
        for part in messages[-1].parts:
            if isinstance(part, UserPromptPart):
                prompts_sent_to_llm.append(str(part.content))
        yield answer

    return scripted_answer


def answer_with_the_system_from_the_game_state(instructions_sent_to_llm: list[str]):
    """The game state is the last part of the instructions the agent sends with
    every request, not a part of the conversation history."""

    async def scripted_answer(messages, agent_info):
        instructions = agent_info.instructions or ""
        instructions_sent_to_llm.append(instructions)
        system = re.search(r"Player is currently in the (.+?) system\.", instructions)
        if system:
            yield f"You are in {system.group(1)}."
        else:
            yield "I do not know where we are."

    return scripted_answer


@allure.title(
    "Celeste started in the middle of a session shows the header and the HUD at once"
)
async def test_should_show_the_header_and_the_hud_at_once_when_started_in_a_session(
    edceleste,
):
    with allure.step("Given the game already wrote its journal and Status.json"):
        write_the_files_of_a_session_in_progress(edceleste)

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="When")

        with allure.step("Then the header shows SANTIAGOW, Cobra Mk III, 575382 CR"):
            await edceleste.wait_until(
                pilot,
                lambda: header_value(pilot.app, "#stat-cmdr") == "SANTIAGOW",
                "the commander name in the header",
            )
            assert header_value(pilot.app, "#stat-ship") == "Cobra Mk III"
            assert header_value(pilot.app, "#stat-credits") == "575382"

        with allure.step("And navigation shows Beta Sculptoris and its facts"):
            await edceleste.wait_until(
                pilot,
                lambda: (
                    label_text(pilot.app, "#navigation-system") == "Beta Sculptoris"
                ),
                "Beta Sculptoris in navigation",
            )
            assert label_text(pilot.app, "#navigation-security") == "● HIGH SECURITY"
            assert label_text(pilot.app, "#navigation-allegiance") == "Independent"
            assert (
                label_text(pilot.app, "#navigation-economy") == "High Tech / Extraction"
            )
            assert label_text(pilot.app, "#navigation-population") == "14 182 335"

        with allure.step("And the HUD shows 12.5 tonnes of fuel"):
            await edceleste.wait_until(
                pilot,
                lambda: fuel_in_the_hud(pilot.app) == "12.5",
                "12.5 tonnes of fuel in the HUD",
            )

        with allure.step("And the cargo bar shows 3 / 24 t"):
            await edceleste.wait_until(
                pilot,
                lambda: cargo_in_the_hud(pilot.app) == "3 / 24 t",
                "3 / 24 t in the cargo bar",
            )


@allure.title("Celeste answers 'where am I?' right after she started in a session")
async def test_should_answer_where_am_i_right_after_starting_in_a_session(edceleste):
    instructions_sent_to_llm: list[str] = []

    with allure.step("Given the game already wrote its journal and Status.json"):
        write_the_files_of_a_session_in_progress(edceleste)

    with allure.step("And the LLM names the system it finds in the game state"):
        edceleste.use_scripted_model(
            answer_with_the_system_from_the_game_state(instructions_sent_to_llm)
        )

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("And the HUD already shows the fuel of the game"):
            await edceleste.wait_until(
                pilot,
                lambda: fuel_in_the_hud(pilot.app) == "12.5",
                "12.5 tonnes of fuel in the HUD",
            )

        with allure.step("When the Commander asks 'where am I?' in COMMS"):
            await send_comms_message(pilot, "where am I?")

        with allure.step("Then COMMS shows 'You are in Beta Sculptoris.'"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [
                "You are in Beta Sculptoris."
            ]

        with allure.step(
            "And the LLM was told who the Commander is and the fuel in its instructions"
        ):
            assert len(instructions_sent_to_llm) == 1
            assert "Commander name is SANTIAGOW." in instructions_sent_to_llm[0]
            assert "Current fuel level is: 12.5." in instructions_sent_to_llm[0]


@allure.title("Celeste stays silent about what the game wrote before she started")
async def test_should_stay_silent_about_what_the_game_wrote_before_the_start(
    edceleste,
):
    prompts_sent_to_llm: list[str] = []

    with allure.step("Given the game already wrote a long journal and Status.json"):
        write_the_files_of_a_long_session_in_progress(edceleste)

    with allure.step("And every event in that journal has a reaction in the settings"):
        react_to_every_event_in_the_long_journal(edceleste)

    with allure.step("And the LLM remembers every prompt it receives"):
        edceleste.use_scripted_model(
            remember_prompts_and_answer(prompts_sent_to_llm, "Noted, Commander.")
        )

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="When")

        with allure.step("Then Celeste knows the game: the HUD shows the fuel"):
            await edceleste.wait_until(
                pilot,
                lambda: fuel_in_the_hud(pilot.app) == "12.5",
                "12.5 tonnes of fuel in the HUD",
            )

        with allure.step("And the LLM got no request"):
            assert prompts_sent_to_llm == []

        with allure.step("And COMMS shows only the welcome message"):
            assert comms_entries(pilot.app, "llm-response") == []
            assert comms_entries(pilot.app, "user-command") == []
            assert comms_entries(pilot.app, "system-message") == [WELCOME_MESSAGE]

        with allure.step("And Celeste said nothing aloud"):
            assert edceleste.spoken_texts == []

        with allure.step("And the ship log has no entry"):
            assert ship_log_events(pilot.app) == []


@allure.title("After the start, a new jump still gets its reaction, once")
async def test_should_react_once_to_a_jump_the_game_writes_after_the_start(edceleste):
    prompts_sent_to_llm: list[str] = []

    with allure.step("Given the game already wrote a long journal and Status.json"):
        write_the_files_of_a_long_session_in_progress(edceleste)

    with allure.step("And every event in that journal has a reaction in the settings"):
        react_to_every_event_in_the_long_journal(edceleste)

    with allure.step("And the LLM answers 'Jump complete, Commander.'"):
        edceleste.use_scripted_model(
            remember_prompts_and_answer(
                prompts_sent_to_llm, "Jump complete, Commander."
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("And Celeste knows the game: the HUD shows the fuel"):
            await edceleste.wait_until(
                pilot,
                lambda: fuel_in_the_hud(pilot.app) == "12.5",
                "12.5 tonnes of fuel in the HUD",
            )

        with allure.step("When the game writes a new FSDJump to the journal"):
            edceleste.append_journal_event("FSDJump")

        with allure.step("Then COMMS shows Celeste's answer to that jump"):
            await edceleste.wait_until(
                pilot,
                lambda: (
                    comms_entries(pilot.app, "llm-response") != []
                    and "FSDJump" in ship_log_events(pilot.app)
                ),
                "Celeste's reaction to the jump in COMMS and FSDJump in the ship log",
            )
            assert comms_entries(pilot.app, "user-command") == []
            assert comms_entries(pilot.app, "llm-response") == [
                "Jump complete, Commander."
            ]
            assert comms_entries(pilot.app, "system-message") == [WELCOME_MESSAGE]

        with allure.step("And Celeste speaks the answer"):
            assert edceleste.spoken_texts == ["Jump complete, Commander."]

        with allure.step("And the LLM was asked about the FSDJump event once"):
            assert len(prompts_sent_to_llm) == 1
            assert '"event":"FSDJump"' in prompts_sent_to_llm[0]

        with allure.step("And the ship log shows only the new FSDJump"):
            assert ship_log_events(pilot.app) == ["FSDJump"]


@allure.title("With an empty journal Celeste says her game state is not set")
async def test_should_say_the_game_state_is_not_set_when_the_journal_is_empty(
    edceleste,
):
    prompts_sent_to_llm: list[str] = []

    with allure.step("Given the journal is empty and the game wrote no Status.json"):
        assert edceleste.journal_file.read_text() == ""
        assert not edceleste.status_file.exists()

    with allure.step("And the LLM remembers every prompt it receives"):
        edceleste.use_scripted_model(
            remember_prompts_and_answer(prompts_sent_to_llm, "Copy that, Commander.")
        )

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step(f"Then COMMS shows '{GAME_STATE_IS_NOT_SET}'"):
            await edceleste.wait_until(
                pilot,
                lambda: (
                    GAME_STATE_IS_NOT_SET in comms_entries(pilot.app, "system-message")
                ),
                "the game state is not set message in COMMS",
            )

        with allure.step("And the LLM got no request"):
            assert prompts_sent_to_llm == []
