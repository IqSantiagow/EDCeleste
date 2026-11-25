import json

import allure
import pytest

from tests.e2e.conftest import comms_entries, send_comms_message
from tests.e2e.test_edsm_system_lookup import (
    LOOKUPS_DISABLED,
    call_tools_then_tell_what_they_answered,
    celestes_last_reply,
)
from tests.e2e.test_journal_to_dashboard_stats import label_text
from tests.e2e.test_spansh_station_search import ask_and_wait_for_celestes_reply

pytestmark = [pytest.mark.anyio, allure.feature("System search")]

# Systems as Spansh describes them, not in distance order: the fake keeps
# only those inside the radius (and of the asked faction) and sorts them.
# Like the real Spansh, the searched system itself is in the list at 0 ly.
SOL_NEIGHBOURS = [
    {
        "name": "Wolf 359",
        "distance": 7.7812,
        "controlling_minor_faction": "Mother Gaia",
    },
    {
        "name": "Sol",
        "distance": 0.0,
        "controlling_minor_faction": "Mother Gaia",
    },
    {
        "name": "Far Gaia",
        "distance": 120.0,
        "controlling_minor_faction": "Mother Gaia",
    },
    {
        "name": "Alpha Centauri",
        "distance": 4.3812,
        "controlling_minor_faction": "Hutton Orbital Truckers",
    },
    {
        "name": "Test",
        "distance": 3.0,
        "controlling_minor_faction": "Mother Gaia",
    },
    {
        "name": "Barnard's Star",
        "distance": 5.9548,
        "controlling_minor_faction": "Barnard's Star Purple Hand",
    },
    {
        "name": "Ross 128",
        "distance": 10.9411,
        "controlling_minor_faction": "Ross 128 Partnership",
    },
]


def system_names_and_distances(answer: dict) -> list[tuple[str, float]]:
    return [(system["name"], system["distance_ly"]) for system in answer["systems"]]


def scripted_system_search(arguments: str):
    return call_tools_then_tell_what_they_answered([("find_systems", arguments)])


@allure.title(
    "Celeste lists the systems near the Commander, nearest first, with distances"
)
async def test_should_list_the_systems_near_the_commander_nearest_first(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And Spansh knows the systems around Sol"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.systems_around["Sol"] = SOL_NEIGHBOURS

    with allure.step(
        "And the LLM searches for systems within 10 light years of where the "
        "Commander is and repeats what the tool answers"
    ):
        edceleste.use_scripted_model(scripted_system_search('{"max_distance_ly": 10}'))

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

        with allure.step("When the Commander asks which systems are within 10 ly"):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Which systems are within 10 light years?"
            )

        with allure.step(
            "Then COMMS lists Sol and its neighbours within 10 ly, nearest first, "
            "each with its distance"
        ):
            answer = json.loads(celestes_last_reply(pilot.app))
            assert answer["from_system"] == "Sol"
            assert system_names_and_distances(answer) == [
                ("Sol", 0.0),
                ("Alpha Centauri", 4.38),
                ("Barnard's Star", 5.95),
                ("Wolf 359", 7.78),
            ]

        with allure.step("And the junk system Test is left out"):
            assert "Test" not in [system["name"] for system in answer["systems"]]

        with allure.step("And COMMS says no system was left out"):
            assert answer["systems_left_out"] == 0

        with allure.step(
            "And Spansh was asked once, about Sol, with only a system name and a radius"
        ):
            assert len(fake_spansh.requests) == 1
            body = fake_spansh.sent_bodies()[0]
            assert body["reference_system"] == "Sol"
            assert set(body) == {"filters", "sort", "size", "page", "reference_system"}
            assert set(body["filters"]) == {"distance"}
            assert float(body["filters"]["distance"]["max"]) == 10


@allure.title(
    "A very large radius shows only the ten nearest systems and says how many more"
)
async def test_should_show_only_the_ten_nearest_systems_and_count_the_rest(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And Spansh knows Sol and 24 more systems around it"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.systems_around["Sol"] = [{"name": "Sol", "distance": 0.0}] + [
            {"name": f"Neighbour {number:02}", "distance": float(number)}
            for number in range(1, 25)
        ]

    with allure.step(
        "And the LLM searches for systems within 1000 light years of Sol and "
        "repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            scripted_system_search('{"from_system": "Sol", "max_distance_ly": 1000}')
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "When the Commander asks which systems are within 1000 ly of Sol"
        ):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Which systems are within 1000 light years of Sol?"
            )

        with allure.step(
            "Then COMMS lists only the ten nearest systems, nearest first"
        ):
            answer = json.loads(celestes_last_reply(pilot.app))
            assert system_names_and_distances(answer) == [("Sol", 0.0)] + [
                (f"Neighbour {number:02}", float(number)) for number in range(1, 10)
            ]

        with allure.step("And COMMS says 15 more systems were left out"):
            assert answer["systems_left_out"] == 15


@allure.title("With no other system in range Celeste says so, not an error")
async def test_should_answer_with_only_the_searched_system_when_nothing_is_in_range(
    edceleste,
):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And the nearest neighbour of Lonely Rock is 30 light years away"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.systems_around["Lonely Rock"] = [
            {"name": "Lonely Rock", "distance": 0.0},
            {"name": "Nearest Neighbour", "distance": 30.0},
        ]

    with allure.step(
        "And the LLM searches for systems within 1 light year of Lonely Rock and "
        "repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            scripted_system_search(
                '{"from_system": "Lonely Rock", "max_distance_ly": 1}'
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "When the Commander asks which systems are within 1 ly of Lonely Rock"
        ):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Is anything within 1 light year of Lonely Rock?"
            )

        with allure.step(
            "Then COMMS lists only Lonely Rock itself, with nothing left out"
        ):
            answer = json.loads(celestes_last_reply(pilot.app))
            assert answer == {
                "from_system": "Lonely Rock",
                "systems": [{"name": "Lonely Rock", "distance_ly": 0.0}],
                "systems_left_out": 0,
            }

        with allure.step("And Spansh was asked to look only within 1 light year"):
            assert len(fake_spansh.requests) == 1
            body = fake_spansh.sent_bodies()[0]
            assert float(body["filters"]["distance"]["max"]) == 1


@allure.title("Celeste finds the systems a faction controls, with their distances")
async def test_should_find_the_systems_a_faction_controls(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And Spansh knows systems of Mother Gaia and of other factions"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.systems_around["Sol"] = SOL_NEIGHBOURS

    with allure.step(
        "And the LLM searches for the systems of Mother Gaia within 1000 light "
        "years of Sol and repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            scripted_system_search(
                '{"from_system": "Sol", "max_distance_ly": 1000, '
                '"faction": "Mother Gaia"}'
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "When the Commander asks where the systems of Mother Gaia are"
        ):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Where are the systems of Mother Gaia?"
            )

        with allure.step(
            "Then COMMS lists only the systems of Mother Gaia, nearest first, "
            "with their distances"
        ):
            answer = json.loads(celestes_last_reply(pilot.app))
            assert answer["from_system"] == "Sol"
            assert system_names_and_distances(answer) == [
                ("Sol", 0.0),
                ("Wolf 359", 7.78),
                ("Far Gaia", 120.0),
            ]
            assert answer["systems_left_out"] == 0

        with allure.step("And Spansh was asked for Mother Gaia by its exact name"):
            assert len(fake_spansh.requests) == 1
            body = fake_spansh.sent_bodies()[0]
            assert body["filters"]["controlling_minor_faction"] == {
                "value": ["Mother Gaia"]
            }


@allure.title("A faction nobody has gives an empty list, not an error")
async def test_should_answer_an_empty_list_for_a_faction_nobody_has(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And Spansh knows systems of Mother Gaia around Sol"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.systems_around["Sol"] = SOL_NEIGHBOURS

    with allure.step(
        "And the LLM searches for the faction written in small letters, which "
        "no system has, and repeats what the tool answers"
    ):
        edceleste.use_scripted_model(
            scripted_system_search(
                '{"from_system": "Sol", "max_distance_ly": 1000, '
                '"faction": "mother gaia"}'
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(
            "When the Commander asks where the systems of mother gaia are"
        ):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Where are the systems of mother gaia?"
            )

        with allure.step("Then COMMS shows an empty list of systems, not an error"):
            answer = json.loads(celestes_last_reply(pilot.app))
            assert answer == {
                "from_system": "Sol",
                "systems": [],
                "systems_left_out": 0,
            }


@allure.title("With lookups off Celeste says the system search is disabled")
async def test_should_say_system_search_is_disabled_and_send_no_request_when_off(
    edceleste,
):
    with allure.step("Given outside lookups are off, as they are by default"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.systems_around["Sol"] = SOL_NEIGHBOURS

    with allure.step(
        "And the LLM tries the system search around Sol and repeats the answer"
    ):
        edceleste.use_scripted_model(scripted_system_search('{"from_system": "Sol"}'))

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks which systems are near Sol"):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Which systems are near Sol?"
            )

        with allure.step("Then COMMS says the lookups are disabled"):
            assert comms_entries(pilot.app, "llm-response") == [LOOKUPS_DISABLED]

        with allure.step("And no request left the computer"):
            assert fake_spansh.requests == []


@allure.title(
    "A system Spansh does not know is reported as unknown and Celeste goes on"
)
async def test_should_report_an_unknown_system_and_go_on(edceleste):
    with allure.step("Given outside lookups are allowed in the settings"):
        edceleste.allow_external_apis()

    with allure.step("And Spansh knows Sol but not Nowhere"):
        fake_spansh = edceleste.use_fake_spansh()
        fake_spansh.systems_around["Sol"] = SOL_NEIGHBOURS

    with allure.step(
        "And the LLM searches for systems around Nowhere and repeats what the "
        "tool answers"
    ):
        edceleste.use_scripted_model(
            scripted_system_search('{"from_system": "Nowhere"}')
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander asks which systems are near Nowhere"):
            await ask_and_wait_for_celestes_reply(
                edceleste, pilot, "Which systems are near Nowhere?"
            )

        with allure.step("Then COMMS says the system Nowhere was not found"):
            assert comms_entries(pilot.app, "llm-response") == [
                "System 'Nowhere' not found"
            ]

        with allure.step("And Celeste answers the next question too"):
            await send_comms_message(pilot, "And now?")
            await edceleste.wait_until(
                pilot,
                lambda: len(comms_entries(pilot.app, "llm-response")) == 2,
                "Celeste's second reply in COMMS",
            )
            assert celestes_last_reply(pilot.app) == "System 'Nowhere' not found"
