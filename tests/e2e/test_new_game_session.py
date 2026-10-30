import allure
import pytest

from tests.e2e.conftest import (
    comms_entries,
    recorded_journal_line,
    send_comms_message,
    ship_log_events,
)
from tests.e2e.test_journal_to_dashboard_stats import header_value, label_text
from tests.e2e.test_service_status_dots import JOURNAL_DOT, dot_state
from tests.e2e.test_startup_loading import (
    WELCOME_MESSAGE,
    fuel_in_the_hud,
    remember_prompts_and_answer,
    write_the_files_of_a_session_in_progress,
)

pytestmark = [pytest.mark.anyio, allure.feature("Celeste follows a new game session")]

# Celeste looks for a newer journal file every 3 s
SECONDS_TO_NOTICE_A_NEW_JOURNAL = 10

NEW_SESSION_CREDITS = "1000"
FILE_HEADER_OF_A_NEW_SESSION = (
    '{ "timestamp":"2026-10-05T18:00:00Z", "event":"Fileheader", "part":1, '
    '"language":"English/UK", "Odyssey":true }'
)
FILE_HEADER_OF_THE_SECOND_PART = (
    '{ "timestamp":"2026-10-05T18:00:00Z", "event":"Fileheader", "part":2, '
    '"language":"English/UK", "Odyssey":true }'
)


def load_game_line_with_new_session_credits() -> str:
    return recorded_journal_line("LoadGame").replace(
        '"Credits":575382', f'"Credits":{NEW_SESSION_CREDITS}'
    )


def the_new_session_lines() -> list[str]:
    return [
        FILE_HEADER_OF_A_NEW_SESSION,
        load_game_line_with_new_session_credits(),
        recorded_journal_line("Commander"),
        recorded_journal_line("Loadout"),
    ]


@allure.title(
    "After the game restarts the header and the navigation show the new session"
)
async def test_should_show_the_new_session_after_the_game_restarts(edceleste):
    with allure.step(
        "Given Celeste started in a session at Beta Sculptoris with 575382 CR"
    ):
        write_the_files_of_a_session_in_progress(edceleste)

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("And the header and navigation show that session"):
            await edceleste.wait_until(
                pilot,
                lambda: header_value(pilot.app, "#stat-credits") == "575382",
                "575382 CR in the header",
            )
            await edceleste.wait_until(
                pilot,
                lambda: (
                    label_text(pilot.app, "#navigation-system") == "Beta Sculptoris"
                ),
                "Beta Sculptoris in navigation",
            )

        with allure.step(
            "When the game is restarted and writes a new journal with 1000 CR"
        ):
            edceleste.game_writes_a_new_journal_file(the_new_session_lines())

        with allure.step("Then the header shows 1000 CR"):
            await edceleste.wait_until(
                pilot,
                lambda: header_value(pilot.app, "#stat-credits") == NEW_SESSION_CREDITS,
                "1000 CR of the new session in the header",
                timeout_seconds=SECONDS_TO_NOTICE_A_NEW_JOURNAL,
            )
            assert header_value(pilot.app, "#stat-cmdr") == "SANTIAGOW"

        with allure.step("And navigation no longer shows Beta Sculptoris"):
            assert label_text(pilot.app, "#navigation-system") != "Beta Sculptoris"


@allure.title(
    "After the game restarts Celeste stays silent about the new journal "
    "and reacts to the next jump"
)
async def test_should_stay_silent_about_the_new_journal_and_react_to_the_next_jump(
    edceleste,
):
    prompts_sent_to_llm: list[str] = []

    with allure.step("Given Celeste started in a session in progress"):
        write_the_files_of_a_session_in_progress(edceleste)

    with allure.step("And LoadGame, Commander, Loadout and FSDJump have a reaction"):
        for event_name in ["LoadGame", "Commander", "Loadout", "FSDJump"]:
            edceleste.react_to_event(event_name)

    with allure.step("And the LLM answers 'Jump complete, Commander.'"):
        edceleste.use_scripted_model(
            remember_prompts_and_answer(
                prompts_sent_to_llm, "Jump complete, Commander."
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("And the HUD shows the fuel of that session"):
            await edceleste.wait_until(
                pilot,
                lambda: fuel_in_the_hud(pilot.app) == "12.5",
                "12.5 tonnes of fuel in the HUD",
            )

        with allure.step(
            "When the game is restarted and writes a new journal with "
            "LoadGame, Commander and Loadout"
        ):
            edceleste.game_writes_a_new_journal_file(the_new_session_lines())

        with allure.step("Then the header shows the new session"):
            await edceleste.wait_until(
                pilot,
                lambda: header_value(pilot.app, "#stat-credits") == NEW_SESSION_CREDITS,
                "1000 CR of the new session in the header",
                timeout_seconds=SECONDS_TO_NOTICE_A_NEW_JOURNAL,
            )

        with allure.step("And Celeste asked the LLM nothing and said nothing aloud"):
            assert prompts_sent_to_llm == []
            assert comms_entries(pilot.app, "llm-response") == []
            assert comms_entries(pilot.app, "system-message") == [WELCOME_MESSAGE]
            assert edceleste.spoken_texts == []

        with allure.step("And the ship log has no entry"):
            assert ship_log_events(pilot.app) == []

        with allure.step("And the game writes an FSDJump to the new journal"):
            edceleste.append_journal_event("FSDJump")

        with allure.step("And COMMS shows Celeste's answer to that jump"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's reaction to the jump in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [
                "Jump complete, Commander."
            ]

        with allure.step("And the ship log shows only the new FSDJump"):
            await edceleste.wait_until(
                pilot,
                lambda: ship_log_events(pilot.app) == ["FSDJump"],
                "only FSDJump in the ship log",
            )

        with allure.step("And the LLM was asked about the FSDJump once"):
            assert len(prompts_sent_to_llm) == 1
            assert '"event":"FSDJump"' in prompts_sent_to_llm[0]


@allure.title(
    "Celeste started before the game follows the journal the game opens later"
)
async def test_should_follow_the_journal_the_game_opens_after_celeste_started(
    edceleste,
):
    prompts_sent_to_llm: list[str] = []

    with allure.step("Given Celeste started with an empty journal, before the game"):
        assert edceleste.journal_file.read_text() == ""

    with allure.step("And the LLM remembers every prompt it receives"):
        edceleste.use_scripted_model(
            remember_prompts_and_answer(prompts_sent_to_llm, "Copy that, Commander.")
        )

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("When the game starts and writes a new journal with LoadGame"):
            edceleste.game_writes_a_new_journal_file(
                [FILE_HEADER_OF_A_NEW_SESSION, recorded_journal_line("LoadGame")]
            )

        with allure.step("Then the header shows SANTIAGOW"):
            await edceleste.wait_until(
                pilot,
                lambda: header_value(pilot.app, "#stat-cmdr") == "SANTIAGOW",
                "the commander name in the header",
                timeout_seconds=SECONDS_TO_NOTICE_A_NEW_JOURNAL,
            )

        with allure.step("And the game docks and writes Docked to the new journal"):
            edceleste.append_journal_event("Docked")

        with allure.step("And the ship log shows Docked"):
            await edceleste.wait_until(
                pilot,
                lambda: "Docked" in ship_log_events(pilot.app),
                "Docked in the ship log",
            )

        with allure.step("And the JRNL dot is green"):
            assert dot_state(pilot.app, JOURNAL_DOT) == "ok"

        with allure.step("And the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("And Celeste answers, because her game state is set"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == ["Copy that, Commander."]


@allure.title(
    "The second part of a long session keeps what Celeste knows and is followed"
)
async def test_should_keep_the_state_when_the_game_continues_in_a_second_journal_part(
    edceleste,
):
    prompts_sent_to_llm: list[str] = []

    with allure.step("Given Celeste started in a session at Beta Sculptoris"):
        write_the_files_of_a_session_in_progress(edceleste)

    with allure.step("And Location and FSDJump have a reaction"):
        edceleste.react_to_event("Location")
        edceleste.react_to_event("FSDJump")

    with allure.step("And the LLM answers 'Jump complete, Commander.'"):
        edceleste.use_scripted_model(
            remember_prompts_and_answer(
                prompts_sent_to_llm, "Jump complete, Commander."
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("And the header shows SANTIAGOW with 575382 CR"):
            await edceleste.wait_until(
                pilot,
                lambda: header_value(pilot.app, "#stat-credits") == "575382",
                "575382 CR in the header",
            )

        with allure.step(
            "When the game continues the session in a second journal part "
            "that starts at HIP 115966"
        ):
            edceleste.game_writes_a_new_journal_file(
                [FILE_HEADER_OF_THE_SECOND_PART, recorded_journal_line("Location")]
            )

        with allure.step("Then navigation shows HIP 115966 from the second part"):
            await edceleste.wait_until(
                pilot,
                lambda: label_text(pilot.app, "#navigation-system") == "HIP 115966",
                "HIP 115966 in navigation",
                timeout_seconds=SECONDS_TO_NOTICE_A_NEW_JOURNAL,
            )

        with allure.step("And the header still shows SANTIAGOW with 575382 CR"):
            assert header_value(pilot.app, "#stat-cmdr") == "SANTIAGOW"
            assert header_value(pilot.app, "#stat-credits") == "575382"

        with allure.step("And Celeste asked the LLM nothing about the loaded part"):
            assert prompts_sent_to_llm == []
            assert comms_entries(pilot.app, "llm-response") == []

        with allure.step("And the game writes an FSDJump to the second part"):
            edceleste.append_journal_event("FSDJump")

        with allure.step("And COMMS shows Celeste's answer to that jump"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's reaction to the jump in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [
                "Jump complete, Commander."
            ]
