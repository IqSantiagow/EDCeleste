import allure
import pytest
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall

from tests.e2e.conftest import (
    PILOT_AND_CELESTE_ENTRIES,
    comms_entries,
    comms_entry_types,
    send_comms_message,
)
from tests.e2e.test_game_state_prompt import prompt_remembering_llm
from tests.e2e.test_journal_to_dashboard_stats import label_text
from tests.e2e.test_startup_loading import fuel_in_the_hud

pytestmark = [
    pytest.mark.anyio,
    allure.feature("Game actions check the ship state"),
]

# The bits of the Flags field the game writes to Status.json
STATUS_DOCKED = 1
STATUS_SUPERCRUISE = 16

DEPLOY_LANDING_GEAR = "deploy the landing gear"
LANDING_GEAR_KEYS = ["keyDown shiftleft", "press l", "keyUp shiftleft"]

GEAR_UNAVAILABLE_IN_SUPERCRUISE = "Landing gear unavailable"
SCOOP_UNAVAILABLE_WHEN_DOCKED = "Cargo scoop unavailable: the ship is docked."


def tell_the_pilot_what_the_scoop_tool_answered(tool_answers_seen_by_llm: list[str]):
    async def toggle_the_scoop_then_relay_the_answer(messages, agent_info):
        tool_answers = [
            part for part in messages[-1].parts if isinstance(part, ToolReturnPart)
        ]
        if not tool_answers:
            yield {
                0: DeltaToolCall(
                    name="perform_game_action",
                    json_args='{"action": "ToggleCargoScoop"}',
                )
            }
        else:
            tool_answers_seen_by_llm.append(tool_answers[0].content)
            yield f"Negative, Commander. {tool_answers[0].content}"

    return toggle_the_scoop_then_relay_the_answer


@allure.title("Instinct refuses the landing gear in supercruise and says why")
async def test_should_refuse_the_landing_gear_in_supercruise_and_say_why(edceleste):
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

        with allure.step("And the game reports the ship in supercruise"):
            edceleste.write_status_file(flags=STATUS_SUPERCRUISE)
            await edceleste.wait_until(
                pilot,
                lambda: label_text(pilot.app, "#navigation-status") == "SUPERCRUISE",
                "SUPERCRUISE in navigation",
            )

        with allure.step("When the Commander sends 'deploy the landing gear' in COMMS"):
            await send_comms_message(pilot, DEPLOY_LANDING_GEAR)

        with allure.step(
            "Then COMMS says the landing gear is unavailable in supercruise"
        ):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Instinct's reply in COMMS",
            )
            assert comms_entries(pilot.app, "user-command") == [DEPLOY_LANDING_GEAR]
            assert comms_entries(pilot.app, "llm-response") == [
                GEAR_UNAVAILABLE_IN_SUPERCRUISE
            ]

        with allure.step("And no key is pressed in the game"):
            assert edceleste.fake_keyboard.keyboard_log == []

        with allure.step("And Celeste (the LLM) is not asked anything"):
            assert prompts_sent_to_llm == []


@allure.title("Celeste is told the cargo scoop is unavailable while docked")
async def test_should_tell_the_llm_why_the_cargo_scoop_is_unavailable_when_docked(
    edceleste,
):
    tool_answers_seen_by_llm: list[str] = []

    with allure.step("Given game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step(
        "And the LLM toggles the cargo scoop and repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            tell_the_pilot_what_the_scoop_tool_answered(tool_answers_seen_by_llm)
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the game reports the ship docked"):
            edceleste.write_status_file(fuel_main=12.5, flags=STATUS_DOCKED)
            await edceleste.wait_until(
                pilot,
                lambda: fuel_in_the_hud(pilot.app) == "12.5",
                "12.5 tonnes of fuel in the HUD, the Status.json was read",
            )

        with allure.step("When the Commander sends 'scoop' in COMMS"):
            await send_comms_message(pilot, "scoop")

        with allure.step(
            "Then COMMS shows Celeste telling why the scoop is unavailable"
        ):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer after the game action",
            )
            assert comms_entries(pilot.app, "llm-response") == [
                f"Negative, Commander. {SCOOP_UNAVAILABLE_WHEN_DOCKED}"
            ]

        with allure.step("And COMMS shows no action or error line"):
            assert set(comms_entry_types(pilot.app)) <= PILOT_AND_CELESTE_ENTRIES

        with allure.step("And the LLM was told the scoop is unavailable while docked"):
            assert tool_answers_seen_by_llm == [SCOOP_UNAVAILABLE_WHEN_DOCKED]

        with allure.step("And no key is pressed in the game"):
            assert edceleste.fake_keyboard.keyboard_log == []


@allure.title("The landing gear works again once the ship leaves supercruise")
async def test_should_deploy_the_landing_gear_after_the_ship_leaves_supercruise(
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

        with allure.step("And the game reports the ship in supercruise"):
            edceleste.write_status_file(flags=STATUS_SUPERCRUISE)
            await edceleste.wait_until(
                pilot,
                lambda: label_text(pilot.app, "#navigation-status") == "SUPERCRUISE",
                "SUPERCRUISE in navigation",
            )

        with allure.step("And the ship drops out of supercruise"):
            edceleste.write_status_file()
            await edceleste.wait_until(
                pilot,
                lambda: label_text(pilot.app, "#navigation-status") == "NORMAL SPACE",
                "NORMAL SPACE in navigation",
            )

        with allure.step("When the Commander sends 'deploy the landing gear' in COMMS"):
            await send_comms_message(pilot, DEPLOY_LANDING_GEAR)

        with allure.step("Then COMMS shows the reply 'Landing gear deployed'"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Instinct's reply in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == ["Landing gear deployed"]

        with allure.step("And the landing gear key Shift+L is pressed in the game"):
            assert edceleste.fake_keyboard.keyboard_log == LANDING_GEAR_KEYS

        with allure.step("And Celeste (the LLM) is not asked anything"):
            assert prompts_sent_to_llm == []


@allure.title("Celeste says out loud that the landing gear is unavailable")
async def test_should_speak_that_the_landing_gear_is_unavailable_in_supercruise(
    edceleste,
):
    with allure.step("Given game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step(
        "And Instinct on the GPU picks the gear for 'deploy the landing gear'"
    ):
        instinct_model = edceleste.turn_instinct_on()
        instinct_model.choices_by_message[DEPLOY_LANDING_GEAR] = "LandingGearToggle"

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the game reports the ship in supercruise"):
            edceleste.write_status_file(flags=STATUS_SUPERCRUISE)
            await edceleste.wait_until(
                pilot,
                lambda: label_text(pilot.app, "#navigation-status") == "SUPERCRUISE",
                "SUPERCRUISE in navigation",
            )

        with allure.step("When the Commander sends 'deploy the landing gear' in COMMS"):
            await send_comms_message(pilot, DEPLOY_LANDING_GEAR)

        with allure.step("Then COMMS shows 'Landing gear unavailable'"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Instinct's reply in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [
                GEAR_UNAVAILABLE_IN_SUPERCRUISE
            ]

        with allure.step("And Celeste says 'Landing gear unavailable' out loud"):
            await edceleste.wait_until(
                pilot,
                lambda: edceleste.spoken_texts != [],
                "the refusal handed to the voice engine",
            )
            assert edceleste.spoken_texts == [GEAR_UNAVAILABLE_IN_SUPERCRUISE]

        with allure.step("And no key is pressed in the game"):
            assert edceleste.fake_keyboard.keyboard_log == []
