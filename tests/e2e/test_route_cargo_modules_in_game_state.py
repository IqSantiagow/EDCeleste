import json
import shutil
from pathlib import Path

import allure
import pytest

from tests.e2e.conftest import comms_entries
from tests.e2e.test_game_state_prompt import (
    game_state_lines,
    game_state_of_llm,
    instructions_remembering_llm,
    send_message_and_get_instructions,
)
from tests.e2e.test_startup_loading import WELCOME_MESSAGE

pytestmark = [
    pytest.mark.anyio,
    allure.feature("Route, cargo and modules in the game state"),
]

SAMPLE_FILES_FOLDER = Path(__file__).parent.parent / "resources"

# The first system is the one where the route was plotted. HIP 115966 is the
# system of the recorded Location event and Beta Sculptoris the one of the
# recorded FSDJump, so the first jump of the route is a jump the journal knows
ROUTE_SYSTEMS = [
    "HIP 115966",
    "Beta Sculptoris",
    "Alpha Centauri",
    "Barnard's Star",
    "Wolf 359",
    "Ross 154",
]

ROUTE_LINE_START = "Plotted route:"
NO_ROUTE_SENTENCE = "No route is plotted."
CARGO_LINE_START = "Cargo hold"
MODULES_LINE_START = "Ship modules"


def write_route_file(edceleste, system_names: list[str]) -> None:
    route = [
        {
            "StarSystem": name,
            "SystemAddress": 1000 + number,
            "StarPos": [0.0, 0.0, float(number)],
            "StarClass": "M",
        }
        for number, name in enumerate(system_names)
    ]
    event_name = "NavRoute" if system_names else "NavRouteClear"
    route_file = {
        "timestamp": "2026-10-23T19:40:12Z",
        "event": event_name,
        "Route": route,
    }
    (edceleste.journal_file.parent / "NavRoute.json").write_text(
        json.dumps(route_file), encoding="utf-8"
    )


def write_cargo_file(edceleste, inventory: dict[str, int]) -> None:
    cargo_file = {
        "timestamp": "2026-10-23T19:55:02Z",
        "event": "Cargo",
        "Vessel": "Ship",
        "Count": sum(inventory.values()),
        "Inventory": [
            {
                "Name": name.lower(),
                "Name_Localised": name,
                "Count": tonnes,
                "Stolen": 0,
            }
            for name, tonnes in inventory.items()
        ],
    }
    (edceleste.journal_file.parent / "Cargo.json").write_text(
        json.dumps(cargo_file), encoding="utf-8"
    )


def write_modules_file_of_a_cobra(edceleste) -> None:
    shutil.copy(
        SAMPLE_FILES_FOLDER / "modules_info.json",
        edceleste.journal_file.parent / "ModulesInfo.json",
    )


def line_of_game_state_starting_with(edceleste, start: str) -> str | None:
    for line in game_state_of_llm(edceleste).split("\n"):
        if line.startswith(start):
            return line
    return None


def line_of_instructions_starting_with(instructions: str, start: str) -> str | None:
    for line in game_state_lines(instructions):
        if line.startswith(start):
            return line
    return None


@allure.title("A route plotted in the game shows in the game state with its length")
async def test_should_tell_the_llm_the_route_the_commander_plotted(edceleste):
    instructions_sent_to_llm: list[str] = []

    with allure.step("Given the LLM remembers the instructions of every request"):
        edceleste.use_scripted_model(
            instructions_remembering_llm(instructions_sent_to_llm)
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander is in HIP 115966"):
            edceleste.append_journal_event("Location")
            await edceleste.wait_until(
                pilot,
                lambda: "HIP 115966" in game_state_of_llm(edceleste),
                "HIP 115966 in the game state",
            )

        with allure.step("When the Commander plots a route of five jumps to Ross 154"):
            write_route_file(edceleste, ROUTE_SYSTEMS)
            await edceleste.wait_until(
                pilot,
                lambda: (
                    line_of_game_state_starting_with(edceleste, ROUTE_LINE_START)
                    is not None
                ),
                "the plotted route in the game state",
            )

        instructions = await send_message_and_get_instructions(
            edceleste, pilot, instructions_sent_to_llm
        )

        with allure.step(
            "Then Celeste knows the destination and that 5 jumps are left"
        ):
            assert (
                line_of_instructions_starting_with(instructions, ROUTE_LINE_START)
                == "Plotted route: destination Ross 154, 5 jumps left. "
                "Next systems on the route: Beta Sculptoris, Alpha Centauri, "
                "Barnard's Star."
            )

        with allure.step("And she names only the next three systems, not the rest"):
            game_state = "\n".join(game_state_lines(instructions))
            assert "Wolf 359" not in game_state


@allure.title("After a jump along the route one jump less is left")
async def test_should_take_one_jump_off_the_route_after_a_jump(edceleste):
    instructions_sent_to_llm: list[str] = []

    with allure.step("Given the LLM remembers the instructions of every request"):
        edceleste.use_scripted_model(
            instructions_remembering_llm(instructions_sent_to_llm)
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "And the Commander is in HIP 115966 with a route of five jumps"
        ):
            edceleste.append_journal_event("Location")
            write_route_file(edceleste, ROUTE_SYSTEMS)
            await edceleste.wait_until(
                pilot,
                lambda: "5 jumps left" in game_state_of_llm(edceleste),
                "five jumps left in the game state",
            )

        with allure.step("When the game writes the jump to Beta Sculptoris"):
            edceleste.append_journal_event("FSDJump")
            await edceleste.wait_until(
                pilot,
                lambda: "4 jumps left" in game_state_of_llm(edceleste),
                "four jumps left in the game state",
            )

        instructions = await send_message_and_get_instructions(
            edceleste, pilot, instructions_sent_to_llm
        )

        with allure.step("Then Celeste knows that 4 jumps are left to Ross 154"):
            assert (
                line_of_instructions_starting_with(instructions, ROUTE_LINE_START)
                == "Plotted route: destination Ross 154, 4 jumps left. "
                "Next systems on the route: Alpha Centauri, Barnard's Star, "
                "Wolf 359."
            )

        with allure.step("And the system she jumped to is not a next system any more"):
            route_line = line_of_instructions_starting_with(
                instructions, ROUTE_LINE_START
            )
            assert "Beta Sculptoris" not in route_line


@allure.title("After the Commander clears the route Celeste knows there is none")
async def test_should_tell_the_llm_that_no_route_is_plotted_after_the_route_is_cleared(
    edceleste,
):
    instructions_sent_to_llm: list[str] = []

    with allure.step("Given the LLM remembers the instructions of every request"):
        edceleste.use_scripted_model(
            instructions_remembering_llm(instructions_sent_to_llm)
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander plotted a route to Ross 154"):
            write_route_file(edceleste, ROUTE_SYSTEMS)
            await edceleste.wait_until(
                pilot,
                lambda: "destination Ross 154" in game_state_of_llm(edceleste),
                "the route to Ross 154 in the game state",
            )

        with allure.step("When the Commander clears the route in the game"):
            write_route_file(edceleste, [])
            await edceleste.wait_until(
                pilot,
                lambda: NO_ROUTE_SENTENCE in game_state_of_llm(edceleste),
                "'No route is plotted.' in the game state",
            )

        instructions = await send_message_and_get_instructions(
            edceleste, pilot, instructions_sent_to_llm
        )

        with allure.step("Then Celeste knows that no route is plotted"):
            assert (
                line_of_instructions_starting_with(instructions, NO_ROUTE_SENTENCE)
                == NO_ROUTE_SENTENCE
            )

        with allure.step("And she no longer mentions the old destination"):
            game_state = "\n".join(game_state_lines(instructions))
            assert "Ross 154" not in game_state
            assert "jumps left" not in game_state


@allure.title(
    "When the cargo changes Celeste names what is in the hold, then an empty hold"
)
async def test_should_tell_the_llm_what_is_in_the_cargo_hold(edceleste):
    instructions_sent_to_llm: list[str] = []

    with allure.step("Given the LLM remembers the instructions of every request"):
        edceleste.use_scripted_model(
            instructions_remembering_llm(instructions_sent_to_llm)
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the hold has 5 t Gold and 2 t Water"):
            write_cargo_file(edceleste, {"Gold": 5, "Water": 2})
            await edceleste.wait_until(
                pilot,
                lambda: "5 t Gold" in game_state_of_llm(edceleste),
                "5 t Gold in the game state",
            )

        with allure.step("When the Commander sells the gold and buys 4 t Silver"):
            write_cargo_file(edceleste, {"Water": 2, "Silver": 4})
            await edceleste.wait_until(
                pilot,
                lambda: "4 t Silver" in game_state_of_llm(edceleste),
                "4 t Silver in the game state",
            )

        instructions = await send_message_and_get_instructions(
            edceleste, pilot, instructions_sent_to_llm
        )

        with allure.step("Then Celeste knows the hold has 2 t Water and 4 t Silver"):
            assert (
                line_of_instructions_starting_with(instructions, CARGO_LINE_START)
                == "Cargo hold contains: 2 t Water, 4 t Silver."
            )

        with allure.step("And she no longer mentions the gold"):
            assert "Gold" not in "\n".join(game_state_lines(instructions))

        with allure.step(
            "And when the Commander empties the hold, she knows it is empty"
        ):
            write_cargo_file(edceleste, {})
            await edceleste.wait_until(
                pilot,
                lambda: "Cargo hold is empty." in game_state_of_llm(edceleste),
                "'Cargo hold is empty.' in the game state",
            )
            instructions = await send_message_and_get_instructions(
                edceleste, pilot, instructions_sent_to_llm
            )
            assert (
                line_of_instructions_starting_with(instructions, CARGO_LINE_START)
                == "Cargo hold is empty."
            )


@allure.title("The modules of the ship show in the game state with power and priority")
async def test_should_tell_the_llm_the_modules_of_the_ship(edceleste):
    instructions_sent_to_llm: list[str] = []

    with allure.step("Given the LLM remembers the instructions of every request"):
        edceleste.use_scripted_model(
            instructions_remembering_llm(instructions_sent_to_llm)
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the game writes the modules of a Cobra Mk III"):
            write_modules_file_of_a_cobra(edceleste)
            await edceleste.wait_until(
                pilot,
                lambda: (
                    line_of_game_state_starting_with(edceleste, MODULES_LINE_START)
                    is not None
                ),
                "the ship modules in the game state",
            )

        instructions = await send_message_and_get_instructions(
            edceleste, pilot, instructions_sent_to_llm
        )
        modules_line = line_of_instructions_starting_with(
            instructions, MODULES_LINE_START
        )

        with allure.step("Then every module has its slot, power draw and priority"):
            assert (
                "MainEngines: int_engine_size4_class1, 3.28 MW, priority 0"
                in modules_line
            )
            assert "CargoHatch: modularcargobaydoor, 0.6 MW, priority 2" in modules_line
            assert (
                "FrameShiftDrive: int_hyperdrive_size4_class1, 0.24 MW, priority 2"
                in modules_line
            )

        with allure.step("And a module without a priority has none in the list"):
            assert "ShipCockpit: cobramkiii_cockpit, 0 MW;" in modules_line

        with allure.step("And the list holds all 27 modules, the last one at the end"):
            assert modules_line.count(" MW") == 27
            assert modules_line.endswith("ColonisationSuite: int_colonisation, 0 MW.")


@allure.title(
    "Celeste started in a session knows route, cargo and modules but says nothing"
)
async def test_should_know_the_side_files_written_before_the_start_and_stay_silent(
    edceleste,
):
    instructions_sent_to_llm: list[str] = []

    with allure.step(
        "Given the game already wrote its journal, a route, the cargo and the modules"
    ):
        for event_name in ["LoadGame", "Commander", "Loadout", "Location"]:
            edceleste.append_journal_event(event_name)
        write_route_file(edceleste, ROUTE_SYSTEMS)
        write_cargo_file(edceleste, {"Gold": 5, "Water": 2})
        write_modules_file_of_a_cobra(edceleste)

    with allure.step("And Celeste has a reaction for each of those files"):
        for event_name in ["NavRoute", "Cargo", "ModuleInfo"]:
            edceleste.react_to_event(event_name)

    with allure.step("And the LLM remembers the instructions of every request"):
        edceleste.use_scripted_model(
            instructions_remembering_llm(instructions_sent_to_llm)
        )

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="When")

        await edceleste.wait_until(
            pilot,
            lambda: all(
                line_of_game_state_starting_with(edceleste, start) is not None
                for start in [ROUTE_LINE_START, CARGO_LINE_START, MODULES_LINE_START]
            ),
            "the route, the cargo and the modules in the game state",
        )

        with allure.step("Then the LLM got no request"):
            assert instructions_sent_to_llm == []

        with allure.step("And COMMS shows only the welcome message"):
            assert comms_entries(pilot.app, "llm-response") == []
            assert comms_entries(pilot.app, "user-command") == []
            assert comms_entries(pilot.app, "system-message") == [WELCOME_MESSAGE]

        with allure.step("And Celeste said nothing aloud"):
            assert edceleste.spoken_texts == []

        with allure.step(
            "And when the Commander asks, the LLM is told the route, the cargo "
            "and the modules"
        ):
            instructions = await send_message_and_get_instructions(
                edceleste, pilot, instructions_sent_to_llm
            )
            game_state = "\n".join(game_state_lines(instructions))
            assert "destination Ross 154, 5 jumps left" in game_state
            assert "Cargo hold contains: 5 t Gold, 2 t Water." in game_state
            assert "MainEngines: int_engine_size4_class1, 3.28 MW" in game_state
