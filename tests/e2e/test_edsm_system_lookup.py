import json

import allure
import pytest
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from tests.e2e.conftest import (
    comms_entries,
    open_settings_section,
    send_comms_message,
)
from tests.e2e.test_journal_to_dashboard_stats import label_text
from tests.e2e.test_settings import save_state_text

pytestmark = [pytest.mark.anyio, allure.feature("Outside system lookups")]

LOOKUPS_DISABLED = "Outside lookups are disabled by the user."

SOL = {
    "name": "Sol",
    "coords": {"x": 0, "y": 0, "z": 0},
    "requirePermit": True,
    "permitName": "Sol",
    "information": {
        "allegiance": "Federation",
        "government": "Democracy",
        "faction": "Mother Gaia",
        "population": 18320926115,
        "security": "High",
        "economy": "Refinery",
        "secondEconomy": "Service",
    },
}
ALPHA_CENTAURI = {
    "name": "Alpha Centauri",
    "coords": {"x": 3.03125, "y": -0.09375, "z": 3.15625},
}

SOL_STATIONS = {
    "name": "Sol",
    "stations": [
        {
            "name": "Daedalus",
            "type": "Orbis Starport",
            "distanceToArrival": 500,
            "haveMarket": True,
            "haveShipyard": True,
            "haveOutfitting": True,
            "otherServices": ["Refuel", "Repair"],
        },
        {
            "name": "Galileo",
            "type": "Coriolis Starport",
            "distanceToArrival": 12,
            "haveMarket": True,
            "haveShipyard": False,
            "haveOutfitting": False,
            "otherServices": ["Refuel"],
        },
        {
            "name": "Hauler's Rest",
            "type": "Fleet Carrier",
            "distanceToArrival": 3,
            "haveMarket": True,
            "haveShipyard": False,
            "haveOutfitting": False,
            "otherServices": [],
        },
    ],
}


def call_tools_then_tell_what_they_answered(tool_calls: list[tuple[str, str]]):
    """The LLM calls the given tools (name and JSON arguments) and then repeats
    every tool answer as its reply, one after another, so COMMS shows what the
    tools answered"""

    async def call_the_tools_then_relay_their_answers(messages, agent_info):
        tool_answers = [
            part for part in messages[-1].parts if isinstance(part, ToolReturnPart)
        ]
        if not tool_answers:
            yield {
                number: DeltaToolCall(name=tool_name, json_args=json_args)
                for number, (tool_name, json_args) in enumerate(tool_calls)
            }
        else:
            yield " | ".join(
                json.dumps(answer.content)
                if isinstance(answer.content, dict)
                else str(answer.content)
                for answer in tool_answers
            )

    return call_the_tools_then_relay_their_answers


def celestes_last_reply(app) -> str:
    return comms_entries(app, "llm-response")[-1]


@allure.title("Celeste describes a system from outside data when lookups are on")
async def test_should_describe_a_system_from_outside_data_when_lookups_are_on(
    edceleste,
):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And EDSM knows Sol"):
        fake_edsm = edceleste.use_fake_edsm()
        fake_edsm.systems["Sol"] = SOL

    with allure.step("And the LLM looks up Sol and repeats what the tool answers"):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [("get_system_info", '{"system": "Sol"}')]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks Celeste about Sol"):
            await send_comms_message(pilot, "What is Sol like?")

        with allure.step("Then COMMS shows the allegiance, government and economy"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's reply in COMMS",
            )
            facts = json.loads(celestes_last_reply(pilot.app))
            assert facts["name"] == "Sol"
            assert facts["allegiance"] == "Federation"
            assert facts["government"] == "Democracy"
            assert facts["economy"] == "Refinery"
            assert facts["second_economy"] == "Service"

        with allure.step("And COMMS shows the security and that Sol needs a permit"):
            assert facts["security"] == "High"
            assert facts["requires_permit"] is True
            assert facts["permit_name"] == "Sol"

        with allure.step("And EDSM was asked only for the name Sol"):
            assert len(fake_edsm.requests) == 1
            assert fake_edsm.requests[0].url.params["systemName"] == "Sol"
            sent_fields = set(fake_edsm.requests[0].url.params.keys())
            assert sent_fields <= {
                "systemName",
                "showCoordinates",
                "showInformation",
                "showPermit",
            }


@allure.title("'This system' means the system the Commander is in now")
async def test_should_look_up_the_current_system_when_no_name_is_given(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And EDSM knows Sol"):
        fake_edsm = edceleste.use_fake_edsm()
        fake_edsm.systems["Sol"] = SOL

    with allure.step("And the LLM looks up 'this system' with no name"):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [("get_system_info", '{"system": ""}')]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander jumps into Sol"):
            edceleste.append_fsd_jumps_to_systems(["Sol"])
            edceleste.write_status_file()
            await edceleste.wait_until(
                pilot,
                lambda: label_text(pilot.app, "#navigation-system") == "Sol",
                "Sol as the current system on the dashboard",
            )

        with allure.step("When the Commander asks about this system"):
            await send_comms_message(pilot, "Tell me about this system")

        with allure.step("Then COMMS describes Sol"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's reply in COMMS",
            )
            facts = json.loads(celestes_last_reply(pilot.app))
            assert facts["name"] == "Sol"
            assert facts["allegiance"] == "Federation"

        with allure.step("And EDSM was asked about Sol"):
            assert [r.url.params["systemName"] for r in fake_edsm.requests] == ["Sol"]


@allure.title("Celeste says an unknown system was not found and invents nothing")
async def test_should_say_an_unknown_system_was_not_found(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And EDSM does not know the system Nowhere"):
        fake_edsm = edceleste.use_fake_edsm()

    with allure.step("And the LLM looks up Nowhere and repeats what the tool answers"):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [("get_system_info", '{"system": "Nowhere"}')]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks Celeste about Nowhere"):
            await send_comms_message(pilot, "What is Nowhere like?")

        with allure.step("Then COMMS says the system Nowhere was not found"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's reply in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [
                "System 'Nowhere' not found"
            ]

        with allure.step("And EDSM was asked about Nowhere"):
            assert [r.url.params["systemName"] for r in fake_edsm.requests] == [
                "Nowhere"
            ]


@allure.title("Celeste lists the real stations of a system with their types")
async def test_should_list_the_stations_of_a_system_without_fleet_carriers(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And EDSM knows two stations and a fleet carrier in Sol"):
        fake_edsm = edceleste.use_fake_edsm()
        fake_edsm.stations["Sol"] = SOL_STATIONS

    with allure.step("And the LLM lists the stations of Sol and repeats the answer"):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [("get_system_stations", '{"system": "Sol"}')]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks for the stations of Sol"):
            await send_comms_message(pilot, "Which stations are in Sol?")

        with allure.step("Then COMMS lists the two stations with their types"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's reply in COMMS",
            )
            answer = json.loads(celestes_last_reply(pilot.app))
            assert answer["system"] == "Sol"
            assert [(s["name"], s["type"]) for s in answer["stations"]] == [
                ("Galileo", "Coriolis Starport"),
                ("Daedalus", "Orbis Starport"),
            ]

        with allure.step("And the stations are in order, the nearest first"):
            distances = [s["distance_from_arrival_ls"] for s in answer["stations"]]
            assert distances == [12, 500]

        with allure.step("And the fleet carrier is left out and counted"):
            assert "Hauler's Rest" not in celestes_last_reply(pilot.app)
            assert answer["fleet_carriers_not_listed"] == 1


@allure.title("A system without stations says there are none, with no error")
async def test_should_say_a_system_has_no_stations_without_an_error(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And EDSM knows the system Lonely with no stations"):
        fake_edsm = edceleste.use_fake_edsm()
        fake_edsm.stations["Lonely"] = {"name": "Lonely", "stations": []}

    with allure.step("And the LLM lists the stations of Lonely and repeats the answer"):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [("get_system_stations", '{"system": "Lonely"}')]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks for the stations of Lonely"):
            await send_comms_message(pilot, "Which stations are in Lonely?")

        with allure.step("Then COMMS shows Lonely with an empty list of stations"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's reply in COMMS",
            )
            answer = json.loads(celestes_last_reply(pilot.app))
            assert answer["system"] == "Lonely"
            assert answer["stations"] == []


@allure.title("With lookups off Celeste says they are disabled and nothing is sent")
async def test_should_say_lookups_are_disabled_and_send_no_request_when_they_are_off(
    edceleste,
):
    with allure.step("Given outside lookups are off, as they are by default"):
        fake_edsm = edceleste.use_fake_edsm()
        fake_edsm.systems["Sol"] = SOL
        fake_edsm.systems["Alpha Centauri"] = ALPHA_CENTAURI
        fake_edsm.stations["Sol"] = SOL_STATIONS

    with allure.step("And the LLM tries all three EDSM tools and repeats the answers"):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [
                    ("get_system_info", '{"system": "Sol"}'),
                    ("get_system_stations", '{"system": "Sol"}'),
                    (
                        "get_distance",
                        '{"from_system": "Sol", "to_system": "Alpha Centauri"}',
                    ),
                ]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks Celeste about Sol"):
            await send_comms_message(pilot, "Tell me about Sol")

        with allure.step("Then COMMS says the lookups are disabled, three times"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's reply in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [
                " | ".join([LOOKUPS_DISABLED] * 3)
            ]

        with allure.step("And no request left the computer"):
            assert fake_edsm.requests == []


@allure.title("Turning lookups on in the settings works at once, with no restart")
async def test_should_answer_lookups_right_after_they_are_turned_on_in_the_settings(
    edceleste,
):
    with allure.step("Given outside lookups are off, as they are by default"):
        fake_edsm = edceleste.use_fake_edsm()
        fake_edsm.systems["Sol"] = SOL

    with allure.step("And the LLM looks up Sol and repeats what the tool answers"):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [("get_system_info", '{"system": "Sol"}')]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And Celeste refused the first question about Sol"):
            await send_comms_message(pilot, "What is Sol like?")
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's first reply in COMMS",
            )
            assert celestes_last_reply(pilot.app) == LOOKUPS_DISABLED
            assert fake_edsm.requests == []

        with allure.step(
            "When the Commander turns lookups on in the settings and saves"
        ):
            await open_settings_section(edceleste, pilot, "settings-external_apis")
            await pilot.click("#external-apis-enabled-input Switch")
            await pilot.pause()
            await pilot.press("ctrl+s")
            await edceleste.wait_until(
                pilot,
                lambda: save_state_text(pilot.app) == "◉ SAVED",
                "SAVED in the settings header",
            )
            await pilot.press("escape")
            await edceleste.wait_until(
                pilot,
                lambda: isinstance(pilot.app.screen, DashboardScreen),
                "the dashboard after Escape",
            )

        with allure.step("And the Commander asks about Sol again"):
            await send_comms_message(pilot, "What is Sol like?")

        with allure.step("Then COMMS describes Sol"):
            await edceleste.wait_until(
                pilot,
                lambda: len(comms_entries(pilot.app, "llm-response")) == 2,
                "Celeste's second reply in COMMS",
            )
            facts = json.loads(celestes_last_reply(pilot.app))
            assert facts["name"] == "Sol"
            assert facts["allegiance"] == "Federation"

        with allure.step("And EDSM was asked about Sol once"):
            assert [r.url.params["systemName"] for r in fake_edsm.requests] == ["Sol"]


@allure.title("The distance between two systems shows both names and two decimals")
async def test_should_show_the_distance_between_two_systems_with_two_decimals(
    edceleste,
):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And EDSM knows where Sol and Alpha Centauri are"):
        fake_edsm = edceleste.use_fake_edsm()
        fake_edsm.systems["Sol"] = SOL
        fake_edsm.systems["Alpha Centauri"] = ALPHA_CENTAURI

    with allure.step(
        "And the LLM measures the distance and repeats what the tool says"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [
                    (
                        "get_distance",
                        '{"from_system": "Sol", "to_system": "Alpha Centauri"}',
                    )
                ]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks how far Alpha Centauri is from Sol"):
            await send_comms_message(pilot, "How far is Alpha Centauri from Sol?")

        with allure.step("Then COMMS shows both names and 4.38 light years"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's reply in COMMS",
            )
            assert json.loads(celestes_last_reply(pilot.app)) == {
                "from_system": "Sol",
                "to_system": "Alpha Centauri",
                "distance_ly": 4.38,
            }


@pytest.mark.parametrize(
    ("trouble", "what_edsm_does", "what_celeste_says"),
    [
        ("not answering in time", "time_out", "EDSM did not answer in time."),
        (
            "answering with an error code",
            "answer_with_error_code",
            "EDSM answered with an error code: 500.",
        ),
    ],
)
@allure.title("EDSM {trouble} is told to the Commander and the reply still comes")
async def test_should_tell_the_commander_when_edsm_has_trouble(
    edceleste, trouble, what_edsm_does, what_celeste_says
):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step(f"And EDSM is {trouble}"):
        fake_edsm = edceleste.use_fake_edsm()
        if what_edsm_does == "time_out":
            fake_edsm.time_out()
        else:
            fake_edsm.answer_with_error_code(500)

    with allure.step("And the LLM looks up Sol and repeats what the tool answers"):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [("get_system_info", '{"system": "Sol"}')]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks Celeste about Sol"):
            await send_comms_message(pilot, "What is Sol like?")

        with allure.step("Then COMMS tells the Commander what went wrong"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's reply in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [what_celeste_says]
