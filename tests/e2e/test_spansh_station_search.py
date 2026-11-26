import json
from datetime import UTC, datetime, timedelta

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


def spansh_time_days_ago(days: int) -> str:
    # The extra hour keeps the whole number of days the same during the test
    moment = datetime.now(UTC) - timedelta(days=days, hours=1)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def spansh_module(name: str, module_class: int, rating: str) -> dict:
    return {"name": name, "class": module_class, "rating": rating}


def outfitting_station(
    name: str, distance: float, modules: list[dict], data_age_days: int = 3
) -> dict:
    return {
        "name": name,
        "system_name": "Sol" if distance == 0 else "Alpha Centauri",
        "distance": distance,
        "distance_to_arrival": 100,
        "type": "Coriolis Starport",
        "services": ["Dock", "Outfitting"],
        "modules": modules,
        "outfitting_updated_at": spansh_time_days_ago(data_age_days),
    }


def shipyard_station(
    name: str,
    distance: float,
    ships: list[str],
    services: list[str],
    shipyard_updated_at: str | None,
) -> dict:
    return {
        "name": name,
        "system_name": "Sol",
        "distance": distance,
        "distance_to_arrival": 100,
        "type": "Coriolis Starport",
        "services": ["Dock", *services],
        "ships": [{"name": ship} for ship in ships],
        "shipyard_updated_at": shipyard_updated_at,
    }


FSD_5A = spansh_module("Frame Shift Drive", 5, "A")
FSD_5C = spansh_module("Frame Shift Drive", 5, "C")
THRUSTERS_4D = spansh_module("Thrusters", 4, "D")


def assert_only_a_system_name_a_radius_and_names_to_buy_were_sent(body: dict) -> None:
    assert set(body) == {"filters", "sort", "size", "page", "reference_system"}
    assert set(body["filters"]) <= {"distance", "type", "services", "modules", "ships"}
    assert set(body["filters"]["distance"]) == {"min", "max"}
    for module in body["filters"].get("modules", []):
        assert set(module) <= {"name", "class", "rating"}
    for ship in body["filters"].get("ships", []):
        assert set(ship) == {"name"}


@allure.title(
    "Celeste finds where to buy a 5A frame shift drive, nearest first, "
    "with the age of the data"
)
async def test_should_find_where_to_buy_a_module_nearest_first_with_data_age(
    edceleste,
):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step(
        "And Spansh knows a station selling a 5A frame shift drive, a farther one "
        "seen 400 days ago and one selling only a 5C drive"
    ):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.stations_around["Sol"] = [
            outfitting_station("Old Outfitter", 4.3812, [FSD_5A], data_age_days=400),
            outfitting_station("Wrong Rating", 0.0, [FSD_5C, THRUSTERS_4D]),
            outfitting_station("Fresh Outfitter", 0.0, [FSD_5C, FSD_5A]),
        ]

    with allure.step(
        "And the LLM searches for a 5A frame shift drive near Sol, written in "
        "small letters, and repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [
                    (
                        "find_stations",
                        '{"from_system": "Sol", "modules": '
                        '[{"name": "frame shift drive", "class": 5, "rating": "a"}]}',
                    )
                ]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "When the Commander asks where to buy a 5A frame shift drive near Sol"
        ):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Where can I buy a 5A frame shift drive near Sol?"
            )

        with allure.step("Then COMMS lists both stations selling it, nearest first"):
            answer = json.loads(celestes_last_reply(pilot.app))
            assert answer["from_system"] == "Sol"
            assert station_names(answer) == ["Fresh Outfitter", "Old Outfitter"]

        with allure.step(
            "And COMMS shows how many days ago each outfitting was seen, the old "
            "one too"
        ):
            assert [s["outfitting_data_age_days"] for s in answer["stations"]] == [
                3,
                400,
            ]

        with allure.step("And the station selling only a 5C drive is left out"):
            assert "Wrong Rating" not in celestes_last_reply(pilot.app)

        with allure.step(
            "And Spansh was asked once, only for the module as Spansh spells it"
        ):
            assert len(fake_spansh.requests) == 1
            body = fake_spansh.sent_bodies()[0]
            assert body["reference_system"] == "Sol"
            assert_only_a_system_name_a_radius_and_names_to_buy_were_sent(body)
            assert body["filters"]["modules"] == [
                {
                    "name": {"value": ["Frame Shift Drive"]},
                    "class": {"value": ["5"]},
                    "rating": {"value": ["A"]},
                }
            ]


@allure.title(
    "Asking for a 5A frame shift drive and a 4D thruster shows only stations "
    "that sell both"
)
async def test_should_show_only_stations_that_sell_both_asked_modules(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step(
        "And Spansh knows one station selling both modules and two selling only one"
    ):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.stations_around["Sol"] = [
            outfitting_station("Drive Only", 0.0, [FSD_5A]),
            outfitting_station("Thrusters Only", 1.0, [THRUSTERS_4D]),
            outfitting_station("Both Modules", 2.0, [THRUSTERS_4D, FSD_5A]),
        ]

    with allure.step(
        "And the LLM searches for both modules near Sol and repeats what the "
        "tool answers"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [
                    (
                        "find_stations",
                        '{"from_system": "Sol", "modules": ['
                        '{"name": "Frame Shift Drive", "class": 5, "rating": "A"}, '
                        '{"name": "Thrusters", "class": 4, "rating": "D"}]}',
                    )
                ]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "When the Commander asks where to buy a 5A frame shift drive and a "
            "4D thruster"
        ):
            await ask_and_wait_for_celestes_reply(
                edceleste,
                pilot,
                "Where can I buy a 5A frame shift drive and a 4D thruster?",
            )

        with allure.step("Then COMMS lists only the station selling both"):
            answer = json.loads(celestes_last_reply(pilot.app))
            assert station_names(answer) == ["Both Modules"]


@allure.title("Celeste names the stations that sell a ship nearby")
async def test_should_name_the_stations_that_sell_a_ship_nearby(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step(
        "And Spansh knows two stations selling an Anaconda, one of them with no "
        "shipyard time, and one selling other ships"
    ):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.stations_around["Sol"] = [
            shipyard_station("Small Ships", 0.0, ["Sidewinder", "Hauler"], [], None),
            shipyard_station(
                "Big Yard", 1.0, ["Anaconda", "Python"], [], spansh_time_days_ago(2)
            ),
            shipyard_station("Unknown Age Yard", 3.0, ["Anaconda"], [], None),
        ]

    with allure.step(
        "And the LLM searches for an Anaconda near Sol, written in small letters, "
        "and repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [("find_stations", '{"from_system": "Sol", "ships": ["anaconda"]}')]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks where to buy an Anaconda"):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Where can I buy an Anaconda?"
            )

        with allure.step("Then COMMS lists both stations selling it, nearest first"):
            answer = json.loads(celestes_last_reply(pilot.app))
            assert station_names(answer) == ["Big Yard", "Unknown Age Yard"]

        with allure.step(
            "And COMMS shows how many days ago each shipyard was seen, unknown "
            "when Spansh does not say"
        ):
            assert [s["shipyard_data_age_days"] for s in answer["stations"]] == [
                2,
                None,
            ]

        with allure.step("And Spansh was asked for the ship as Spansh spells it"):
            body = fake_spansh.sent_bodies()[0]
            assert_only_a_system_name_a_radius_and_names_to_buy_were_sent(body)
            assert body["filters"]["ships"] == [{"name": {"value": ["Anaconda"]}}]


@allure.title(
    "Asking for repair and an Anaconda in one question shows only stations "
    "that have both"
)
async def test_should_show_only_stations_with_the_asked_service_and_ship(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step(
        "And Spansh knows one station with repair and an Anaconda, one with only "
        "repair and one with only the Anaconda"
    ):
        fake_spansh = edceleste.use_fake_spansh()
        one_day_ago = spansh_time_days_ago(1)
        fake_spansh.stations_around["Sol"] = [
            shipyard_station(
                "Repair Only", 0.0, ["Sidewinder"], ["Repair"], one_day_ago
            ),
            shipyard_station("Anaconda Only", 1.0, ["Anaconda"], [], one_day_ago),
            shipyard_station(
                "Repair And Anaconda", 2.0, ["Anaconda"], ["Repair"], one_day_ago
            ),
        ]

    with allure.step(
        "And the LLM searches for repair and an Anaconda near Sol in one search "
        "and repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [
                    (
                        "find_stations",
                        '{"from_system": "Sol", "services": ["Repair"], '
                        '"ships": ["Anaconda"]}',
                    )
                ]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks where to repair and buy an Anaconda"):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Where can I repair and buy an Anaconda?"
            )

        with allure.step("Then COMMS lists only the station with both"):
            answer = json.loads(celestes_last_reply(pilot.app))
            assert station_names(answer) == ["Repair And Anaconda"]

        with allure.step("And Spansh was asked once for the service and the ship"):
            assert len(fake_spansh.requests) == 1
            body = fake_spansh.sent_bodies()[0]
            assert_only_a_system_name_a_radius_and_names_to_buy_were_sent(body)
            assert body["filters"]["services"] == [{"name": "Repair"}]
            assert body["filters"]["ships"] == [{"name": {"value": ["Anaconda"]}}]


@allure.title(
    "With no station selling the module in range Celeste says nothing was "
    "found, not an error"
)
async def test_should_say_nothing_was_found_when_no_station_in_range_sells_the_module(
    edceleste,
):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step(
        "And the only station selling a 5A frame shift drive is 25 light years from Sol"
    ):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.stations_around["Sol"] = [
            outfitting_station("Distant Outfitter", 25.0, [FSD_5A])
        ]

    with allure.step(
        "And the LLM searches for a 5A frame shift drive within 10 light years "
        "of Sol and repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [
                    (
                        "find_stations",
                        '{"from_system": "Sol", "max_distance_ly": 10, '
                        '"modules": [{"name": "Frame Shift Drive", "class": 5, '
                        '"rating": "A"}]}',
                    )
                ]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "When the Commander asks for a 5A frame shift drive within 10 ly"
        ):
            await ask_and_wait_for_celestes_reply(
                edceleste,
                pilot,
                "Can I buy a 5A frame shift drive within 10 light years?",
            )

        with allure.step("Then COMMS shows an empty list of stations"):
            answer = json.loads(celestes_last_reply(pilot.app))
            assert answer == {"from_system": "Sol", "stations": []}


@pytest.mark.parametrize(
    ("kind", "tool_arguments", "unknown_name", "close_name"),
    [
        (
            "module",
            '{"from_system": "Sol", "modules": [{"name": "Frame Shift Driv"}]}',
            "Frame Shift Driv",
            "Frame Shift Drive",
        ),
        (
            "ship",
            '{"from_system": "Sol", "ships": ["Anakonda"]}',
            "Anakonda",
            "Anaconda",
        ),
    ],
)
@allure.title(
    "A {kind} that does not exist makes Celeste say she does not know it and "
    "give close names"
)
async def test_should_say_an_unknown_name_to_buy_is_unknown_and_give_close_names(
    edceleste, kind, tool_arguments, unknown_name, close_name
):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And Spansh knows stations around Sol"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.stations_around["Sol"] = [
            outfitting_station("Fresh Outfitter", 0.0, [FSD_5A])
        ]

    with allure.step(
        f"And the LLM searches for a {kind} named {unknown_name} and repeats what "
        "the tool answers"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered([("find_stations", tool_arguments)])
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(f"When the Commander asks where to buy {unknown_name}"):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, f"Where can I buy a {unknown_name}?"
            )

        with allure.step(f"Then COMMS says the {kind} {unknown_name} is unknown"):
            reply = celestes_last_reply(pilot.app)
            assert f"Unknown {kind}: '{unknown_name}'" in reply

        with allure.step(f"And COMMS names {close_name} as a close name"):
            assert f"closest: {close_name}" in reply

        with allure.step("And Spansh was not asked anything"):
            assert fake_spansh.requests == []


@allure.title(
    "With lookups off a module or ship search says lookups are disabled and "
    "nothing is sent"
)
async def test_should_say_lookups_are_disabled_for_a_module_or_ship_search_when_off(
    edceleste,
):
    with allure.step("Given outside lookups are off, as they are by default"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.stations_around["Sol"] = [
            outfitting_station("Fresh Outfitter", 0.0, [FSD_5A])
        ]

    with allure.step(
        "And the LLM searches for a 5A frame shift drive and an Anaconda near Sol "
        "and repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            call_tools_then_tell_what_they_answered(
                [
                    (
                        "find_stations",
                        '{"from_system": "Sol", "modules": [{"name": '
                        '"Frame Shift Drive", "class": 5, "rating": "A"}], '
                        '"ships": ["Anaconda"]}',
                    )
                ]
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "When the Commander asks where to buy a 5A frame shift drive and an "
            "Anaconda"
        ):
            await ask_and_wait_for_celestes_reply(
                edceleste,
                pilot,
                "Where can I buy a 5A frame shift drive and an Anaconda?",
            )

        with allure.step("Then COMMS says the lookups are disabled"):
            assert comms_entries(pilot.app, "llm-response") == [LOOKUPS_DISABLED]

        with allure.step("And no request left the computer"):
            assert fake_spansh.requests == []
