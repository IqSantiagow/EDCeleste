import allure
import pytest

from tests.e2e.conftest import (
    docking_journal_line,
    recorded_journal_line,
    ship_log_counter,
    ship_log_details,
    ship_log_events,
    ship_log_systems,
    wide_ship_log_counter,
    wide_ship_log_systems,
)

pytestmark = [pytest.mark.anyio, allure.feature("Ship log")]

MAX_ROWS = 200
BURST_SYSTEMS = [f"System {number}" for number in range(1, 211)]

DOCKING_EVENTS_IN_THE_SHIP_LOG = [
    pytest.param(
        "DockingRequested",
        "Newberry Hydroponics Holding · requested",
        id="docking-requested",
    ),
    pytest.param("DockingGranted", "Hammel Terminal · pad 44", id="docking-granted"),
    pytest.param(
        "DockingDenied",
        "Newberry Hydroponics Holding · denied: NoSpace",
        id="docking-denied",
    ),
    pytest.param("DockingCancelled", "Galileo · cancelled", id="docking-cancelled"),
    pytest.param("DockingTimeout", "Galileo · timed out", id="docking-timeout"),
]


@allure.title("An event the game writes to the journal shows in the ship log")
async def test_should_show_an_event_written_to_the_journal_in_the_ship_log(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("When the game writes FSDJump to the journal"):
            edceleste.append_journal_event("FSDJump")

        with allure.step("Then the ship log shows FSDJump"):
            await edceleste.wait_until(
                pilot,
                lambda: "FSDJump" in ship_log_events(pilot.app),
                "FSDJump in the ship log",
            )


@allure.title("Cyrillic and Polish letters in the journal do not stop the ship log")
async def test_should_keep_showing_events_after_a_journal_line_with_non_english_letters(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step(
            "When the game writes a Docked line with the station name "
            "Привет, Łódź and then an FSDJump to the journal"
        ):
            docked_line = recorded_journal_line("Docked").replace(
                "Fan Horizons", "Привет, Łódź"
            )
            with edceleste.journal_file.open("a", encoding="utf-8") as journal:
                journal.write(docked_line + "\n")
            edceleste.append_journal_event("FSDJump")

        with allure.step("Then the ship log shows FSDJump"):
            await edceleste.wait_until(
                pilot,
                lambda: "FSDJump" in ship_log_events(pilot.app),
                "FSDJump in the ship log after the line with non-English letters",
            )


@allure.title("After a burst of 210 jumps the ship log in the rail keeps 200 rows")
async def test_should_keep_at_most_200_rows_in_the_rail_ship_log_after_a_burst(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("When the game writes 210 jumps to the journal in one go"):
            edceleste.append_fsd_jumps_to_systems(BURST_SYSTEMS)

        with allure.step("Then the last jump is the last row of the ship log"):
            await edceleste.wait_until(
                pilot,
                lambda: ship_log_systems(pilot.app)[-1:] == ["System 210"],
                "System 210 as the last row of the ship log in the rail",
            )

        with allure.step("And the ship log shows at most 200 rows"):
            await edceleste.wait_until(
                pilot,
                lambda: len(ship_log_systems(pilot.app)) <= MAX_ROWS,
                "at most 200 rows in the ship log in the rail",
                timeout_seconds=15,
            )

        with allure.step("And the first jump is gone from the ship log"):
            assert "System 1" not in ship_log_systems(pilot.app)

        with allure.step("And the counter still says 211 events"):
            assert ship_log_counter(pilot.app) == "211 events"


@allure.title("After a burst of 210 jumps the full-width ship log keeps 200 rows")
async def test_should_keep_at_most_200_rows_in_the_full_width_ship_log_after_a_burst(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("When the game writes 210 jumps to the journal in one go"):
            edceleste.append_fsd_jumps_to_systems(BURST_SYSTEMS)

        with allure.step("And the Commander opens the ship log full width"):
            await pilot.press("ctrl+e")

        with allure.step("Then the last jump is the last row of the ship log"):
            await edceleste.wait_until(
                pilot,
                lambda: wide_ship_log_systems(pilot.app)[-1:] == ["System 210"],
                "System 210 as the last row of the full-width ship log",
            )

        with allure.step("And the ship log shows at most 200 rows"):
            await edceleste.wait_until(
                pilot,
                lambda: len(wide_ship_log_systems(pilot.app)) <= MAX_ROWS,
                "at most 200 rows in the full-width ship log",
                timeout_seconds=15,
            )

        with allure.step("And the first jump is gone from the ship log"):
            assert "System 1" not in wide_ship_log_systems(pilot.app)

        with allure.step("And the counter still says 211 events this session"):
            assert wide_ship_log_counter(pilot.app) == "211 events this session"


@allure.title("When the game writes {event_name} the ship log shows '{details}'")
@pytest.mark.parametrize("event_name, details", DOCKING_EVENTS_IN_THE_SHIP_LOG)
async def test_should_show_how_a_docking_request_went_in_the_ship_log(
    edceleste, event_name, details
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step(f"When the game writes {event_name} to the journal"):
            edceleste.append_journal_line(docking_journal_line(event_name))

        with allure.step(f"Then the ship log shows {event_name}"):
            await edceleste.wait_until(
                pilot,
                lambda: event_name in ship_log_events(pilot.app),
                f"{event_name} in the ship log",
            )

        with allure.step(f"And its row tells the station and the outcome: {details}"):
            row_number = ship_log_events(pilot.app).index(event_name)
            assert details in ship_log_details(pilot.app)[row_number]
