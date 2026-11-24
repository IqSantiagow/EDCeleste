import json

import allure
import pytest

from tests.e2e.conftest import (
    comms_entries,
    send_comms_message,
)
from tests.e2e.test_edsm_system_lookup import (
    LOOKUPS_DISABLED,
    call_tools_then_tell_what_they_answered,
    celestes_last_reply,
)
from tests.e2e.test_journal_to_dashboard_stats import label_text

pytestmark = [pytest.mark.anyio, allure.feature("Station search")]

MATERIAL_TRADER_SEARCH = ("find_stations", '{"services": ["Material Trader"]}')

# Stations as Spansh describes them: the fake keeps only those inside the
# radius, with every asked service, and not of a type the search leaves out
SOL_STATIONS = [
    {
        "name": "Trader Hub",
        "system_name": "Sol",
        "distance": 0.0,
        "distance_to_arrival": 1234.6,
        "type": "Coriolis Starport",
        "services": ["Dock", "Market", "Material Trader"],
        "material_trader": "Encoded",
    },
    {
        "name": "Far Trader",
        "system_name": "Alpha Centauri",
        "distance": 4.3812,
        "distance_to_arrival": 300,
        "type": "Outpost",
        "services": ["Dock", "Material Trader"],
        "material_trader": "Manufactured",
    },
    {
        "name": "Plain Port",
        "system_name": "Sol",
        "distance": 0.0,
        "distance_to_arrival": 50,
        "type": "Orbis Starport",
        "services": ["Dock", "Market"],
    },
    {
        "name": "Drifter",
        "system_name": "Sol",
        "distance": 0.5,
        "distance_to_arrival": 10,
        "type": "Drake-Class Carrier",
        "services": ["Dock", "Material Trader"],
        "material_trader": "Raw",
    },
]

COLONIA_STATIONS = [
    {
        "name": "Colonia Hub",
        "system_name": "Colonia",
        "distance": 0.0,
        "distance_to_arrival": 700,
        "type": "Coriolis Starport",
        "services": ["Dock", "Interstellar Factors Contact"],
    },
    {
        "name": "Jaques Station",
        "system_name": "Colonia",
        "distance": 0.0,
        "distance_to_arrival": 70,
        "type": "Outpost",
        "services": ["Dock", "Market"],
    },
]

REPAIR_AND_REFUEL_STATIONS = [
    {
        "name": "Full Service",
        "system_name": "Sol",
        "distance": 2.0,
        "distance_to_arrival": 100,
        "type": "Coriolis Starport",
        "services": ["Dock", "Repair", "Refuel"],
    },
    {
        "name": "Repair Only",
        "system_name": "Sol",
        "distance": 0.0,
        "distance_to_arrival": 100,
        "type": "Outpost",
        "services": ["Dock", "Repair"],
    },
    {
        "name": "Refuel Only",
        "system_name": "Sol",
        "distance": 1.0,
        "distance_to_arrival": 100,
        "type": "Outpost",
        "services": ["Dock", "Refuel"],
    },
]


def station_names(answer: dict) -> list[str]:
    return [station["name"] for station in answer["stations"]]


def assert_only_a_system_name_a_radius_and_service_names_were_sent(body: dict) -> None:
    assert set(body) == {"filters", "sort", "size", "page", "reference_system"}
    assert set(body["filters"]) <= {"distance", "type", "services"}
    assert set(body["filters"]["distance"]) == {"min", "max"}
    for service in body["filters"].get("services", []):
        assert set(service) == {"name"}


async def ask_and_wait_for_celestes_reply(edceleste, pilot, question: str) -> None:
    await send_comms_message(pilot, question)
    await edceleste.wait_until(
        pilot,
        lambda: comms_entries(pilot.app, "llm-response") != [],
        "Celeste's reply in COMMS",
    )


@allure.title("Celeste finds the nearest Material Trader with its kind of materials")
async def test_should_find_the_nearest_material_trader_with_its_kind_of_materials(
    edceleste,
):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And Spansh knows two Material Traders and a fleet carrier"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.stations_around["Sol"] = SOL_STATIONS

    with allure.step(
        "And the LLM searches for a Material Trader near the Commander and "
        "repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered([MATERIAL_TRADER_SEARCH])
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander is in the Sol system"):
            edceleste.append_fsd_jumps_to_systems(["Sol"])
            edceleste.write_status_file()
            await edceleste.wait_until(
                pilot,
                lambda: label_text(pilot.app, "#navigation-system") == "Sol",
                "Sol as the current system on the dashboard",
            )

        with allure.step(
            "When the Commander asks where the nearest Material Trader is"
        ):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Where is the nearest Material Trader?"
            )

        with allure.step("Then COMMS lists both traders, the nearest first"):
            answer = json.loads(celestes_last_reply(pilot.app))
            assert answer["from_system"] == "Sol"
            assert station_names(answer) == ["Trader Hub", "Far Trader"]

        with allure.step("And COMMS shows for each its system and distances"):
            assert [
                (s["system"], s["distance_ly"], s["distance_from_arrival_ls"])
                for s in answer["stations"]
            ] == [("Sol", 0.0, 1235), ("Alpha Centauri", 4.38, 300)]

        with allure.step("And COMMS shows which materials each trader buys"):
            assert [s["material_trader_kind"] for s in answer["stations"]] == [
                "Encoded",
                "Manufactured",
            ]

        with allure.step("And the fleet carrier is left out"):
            assert "Drifter" not in celestes_last_reply(pilot.app)

        with allure.step("And Spansh was asked once, about Sol, with only a search"):
            assert len(fake_spansh.requests) == 1
            body = fake_spansh.sent_bodies()[0]
            assert body["reference_system"] == "Sol"
            assert_only_a_system_name_a_radius_and_service_names_were_sent(body)
            assert body["filters"]["services"] == [{"name": "Material Trader"}]


@allure.title("Celeste finds a service around the system the Commander names")
async def test_should_find_a_service_around_a_named_system(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And Spansh knows stations around Sol and around Colonia"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.stations_around["Sol"] = SOL_STATIONS
        fake_spansh.stations_around["Colonia"] = COLONIA_STATIONS

    with allure.step(
        "And the LLM searches for Interstellar Factors around Colonia, with the "
        "service written in small letters, and repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [
                    (
                        "find_stations",
                        '{"from_system": "Colonia", '
                        '"services": ["interstellar factors contact"]}',
                    )
                ]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the Commander is in the Sol system, far from Colonia"):
            edceleste.append_fsd_jumps_to_systems(["Sol"])
            edceleste.write_status_file()
            await edceleste.wait_until(
                pilot,
                lambda: label_text(pilot.app, "#navigation-system") == "Sol",
                "Sol as the current system on the dashboard",
            )

        with allure.step(
            "When the Commander asks for Interstellar Factors near Colonia"
        ):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Is there Interstellar Factors near Colonia?"
            )

        with allure.step("Then COMMS lists only the Colonia station that has it"):
            answer = json.loads(celestes_last_reply(pilot.app))
            assert answer["from_system"] == "Colonia"
            assert station_names(answer) == ["Colonia Hub"]
            assert answer["stations"][0]["system"] == "Colonia"

        with allure.step("And Spansh was asked about Colonia, not about Sol"):
            assert [b["reference_system"] for b in fake_spansh.sent_bodies()] == [
                "Colonia"
            ]

        with allure.step("And the service was asked for as Spansh spells it"):
            body = fake_spansh.sent_bodies()[0]
            assert body["filters"]["services"] == [
                {"name": "Interstellar Factors Contact"}
            ]


@allure.title("Asking for repair and refuel shows only stations that have both")
async def test_should_show_only_stations_that_have_both_asked_services(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step(
        "And Spansh knows one station with repair and refuel and two with only one"
    ):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.stations_around["Sol"] = REPAIR_AND_REFUEL_STATIONS

    with allure.step(
        "And the LLM searches for repair and refuel around Sol and repeats "
        "what the tool answers"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [
                    (
                        "find_stations",
                        '{"from_system": "Sol", "services": ["repair", "refuel"]}',
                    )
                ]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks where to repair and refuel"):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Where can I repair and refuel?"
            )

        with allure.step("Then COMMS lists only the station with both services"):
            answer = json.loads(celestes_last_reply(pilot.app))
            assert station_names(answer) == ["Full Service"]

        with allure.step("And Spansh was asked for both services, only as names"):
            assert len(fake_spansh.requests) == 1
            body = fake_spansh.sent_bodies()[0]
            assert_only_a_system_name_a_radius_and_service_names_were_sent(body)
            assert body["filters"]["services"] == [
                {"name": "Repair"},
                {"name": "Refuel"},
            ]


@allure.title("A service that does not exist makes Celeste list the services she knows")
async def test_should_list_the_known_services_when_a_service_does_not_exist(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And Spansh knows stations around Sol"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.stations_around["Sol"] = SOL_STATIONS

    with allure.step(
        "And the LLM searches for a Hot Tub around Sol and repeats what the "
        "tool answers"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [("find_stations", '{"from_system": "Sol", "services": ["Hot Tub"]}')]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks where a Hot Tub is"):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Where can I find a Hot Tub?"
            )

        with allure.step("Then COMMS says the service Hot Tub is unknown"):
            assert "Unknown service: 'Hot Tub'" in celestes_last_reply(pilot.app)

        with allure.step("And COMMS lists the services Celeste knows"):
            reply = celestes_last_reply(pilot.app)
            assert "Known services:" in reply
            for known_service in ["Repair", "Refuel", "Material Trader"]:
                assert known_service in reply

        with allure.step("And Spansh was not asked anything"):
            assert fake_spansh.requests == []


@allure.title("With no station in range Celeste says nothing was found, not an error")
async def test_should_say_nothing_was_found_when_no_station_is_in_range(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And the nearest Material Trader is 25 light years from Sol"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.stations_around["Sol"] = [
            {
                "name": "Distant Trader",
                "system_name": "Faraway",
                "distance": 25.0,
                "distance_to_arrival": 100,
                "type": "Outpost",
                "services": ["Dock", "Material Trader"],
                "material_trader": "Raw",
            }
        ]

    with allure.step(
        "And the LLM searches for a Material Trader within 10 light years of Sol "
        "and repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [
                    (
                        "find_stations",
                        '{"from_system": "Sol", "max_distance_ly": 10, '
                        '"services": ["Material Trader"]}',
                    )
                ]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks for a Material Trader within 10 ly"):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Is there a Material Trader within 10 light years?"
            )

        with allure.step("Then COMMS shows an empty list of stations"):
            answer = json.loads(celestes_last_reply(pilot.app))
            assert answer == {"from_system": "Sol", "stations": []}

        with allure.step("And Spansh was asked to look only within 10 light years"):
            assert len(fake_spansh.requests) == 1
            body = fake_spansh.sent_bodies()[0]
            assert float(body["filters"]["distance"]["max"]) == 10


@allure.title("With lookups off Celeste says they are disabled and nothing is sent")
async def test_should_say_station_search_is_disabled_and_send_no_request_when_off(
    edceleste,
):
    with allure.step("Given outside lookups are off, as they are by default"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.stations_around["Sol"] = SOL_STATIONS
        fake_edsm = edceleste.use_fake_edsm()

    with allure.step(
        "And the LLM tries the station search and an EDSM lookup and repeats "
        "the answers"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [
                    ("find_stations", '{"from_system": "Sol"}'),
                    ("get_system_stations", '{"system": "Sol"}'),
                ]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks for stations near Sol"):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Which stations are near Sol?"
            )

        with allure.step("Then COMMS says the lookups are disabled, twice"):
            assert comms_entries(pilot.app, "llm-response") == [
                " | ".join([LOOKUPS_DISABLED] * 2)
            ]

        with allure.step("And no request left the computer"):
            assert fake_spansh.requests == []
            assert fake_edsm.requests == []


@pytest.mark.parametrize(
    ("trouble", "asked_system", "what_celeste_says"),
    [
        ("not answering in time", "Sol", "Spansh did not answer in time."),
        (
            "answering with an error code",
            "Sol",
            "Spansh answered with an error code: 500.",
        ),
        ("not reachable because the network is off", "Sol", "Spansh did not answer."),
        ("not knowing the system", "Nowhere", "System 'Nowhere' not found"),
    ],
)
@allure.title("Spansh {trouble} is told to the Commander and Celeste goes on")
async def test_should_tell_the_commander_when_spansh_has_trouble(
    edceleste, trouble, asked_system, what_celeste_says
):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step(f"And Spansh is {trouble}"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.stations_around["Sol"] = SOL_STATIONS
        if trouble == "not answering in time":
            fake_spansh.time_out()
        elif trouble == "answering with an error code":
            fake_spansh.answer_with_error_code(500)
        elif trouble == "not reachable because the network is off":
            fake_spansh.cannot_be_reached()

    with allure.step(
        f"And the LLM searches for a Material Trader near {asked_system} and "
        "repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [
                    (
                        "find_stations",
                        f'{{"from_system": "{asked_system}", '
                        '"services": ["Material Trader"]}',
                    )
                ]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "When the Commander asks where the nearest Material Trader is"
        ):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Where is the nearest Material Trader?"
            )

        with allure.step("Then COMMS tells the Commander what went wrong"):
            assert comms_entries(pilot.app, "llm-response") == [what_celeste_says]

        with allure.step("And Celeste answers the next question too"):
            await send_comms_message(pilot, "And now?")
            await edceleste.wait_until(
                pilot,
                lambda: len(comms_entries(pilot.app, "llm-response")) == 2,
                "Celeste's second reply in COMMS",
            )
            assert celestes_last_reply(pilot.app) == what_celeste_says
