import allure
import numpy as np
import pytest

from edceleste.services.models.settings_model import DEFAULT_EDGE_VOICE, TTSModel
from tests.e2e.conftest import comms_entries, send_comms_message, ship_log_events
from tests.e2e.test_game_state_prompt import prompt_remembering_llm
from tests.e2e.test_instinct_spoken_reply import write_prepared_reply_clip
from tests.e2e.test_journal_to_dashboard_stats import label_text
from tests.e2e.test_startup_loading import (
    fuel_in_the_hud,
    write_the_files_of_a_session_in_progress,
)

pytestmark = [pytest.mark.anyio, allure.feature("Ship replies")]

# The bits of the Flags field the game writes to Status.json
STATUS_LANDING_GEAR_DOWN = 4
STATUS_FLIGHT_ASSIST_OFF = 32
STATUS_LIGHTS_ON = 256
STATUS_FSD_CHARGING = 131072
STATUS_LOW_FUEL = 524288

FUEL_IN_THE_BASELINE = 12.5
SAVED_VOLUME = 0.5
CLIP_SAMPLE_RATE = 24000
GEAR_LIT_IN_THE_SHIP_PANEL = "● gear"

SET_THROTTLE_TO_ZERO = "set throttle to zero"
THROTTLE_ZERO_KEYS = ["press x"]
ENGAGE_SUPERCRUISE = "engage supercruise"
SUPERCRUISE_KEYS = ["press g"]


async def game_writes_first_status_file(edceleste, pilot, flags: int) -> None:
    """The first Status.json Celeste sees is never spoken about, it is only what
    the next change is compared with. The test waits until the HUD shows it."""
    edceleste.write_status_file(fuel_main=FUEL_IN_THE_BASELINE, flags=flags)
    await edceleste.wait_until(
        pilot,
        lambda: fuel_in_the_hud(pilot.app) == str(FUEL_IN_THE_BASELINE),
        "the fuel of the first Status.json in the HUD",
    )


def game_changes_the_flags(edceleste, flags: int) -> None:
    edceleste.write_status_file(fuel_main=FUEL_IN_THE_BASELINE, flags=flags)


async def wait_for_the_gear_in_the_ship_panel(edceleste, pilot) -> None:
    await edceleste.wait_until(
        pilot,
        lambda: label_text(pilot.app, "#ship-flag-gear") == GEAR_LIT_IN_THE_SHIP_PANEL,
        "the gear lit in the SHIP panel",
    )


async def wait_for_instinct_reply_in_comms(edceleste, pilot) -> None:
    await edceleste.wait_until(
        pilot,
        lambda: comms_entries(pilot.app, "llm-response") != [],
        "Instinct's reply in COMMS",
    )


def let_instinct_pick(edceleste, message: str, action_name: str) -> list[str]:
    """Game actions allowed, Instinct on the GPU picks the action for the message
    and the LLM remembers its prompts. Returns the list of those prompts."""
    prompts_sent_to_llm: list[str] = []
    edceleste.allow_game_actions()
    instinct_model = edceleste.turn_instinct_on()
    instinct_model.choices_by_message[message] = action_name
    edceleste.use_scripted_model(prompt_remembering_llm(prompts_sent_to_llm))
    return prompts_sent_to_llm


@allure.title("When the game reports the landing gear down Celeste plays her clip")
async def test_should_play_the_prepared_clip_when_the_game_reports_the_gear_down(
    edceleste,
):
    with allure.step(
        "Given Edge speaks at volume 0.5 with the ship effect on and has a "
        "prepared clip of 'Landing gear deployed'"
    ):
        edceleste.save_tts_settings(TTSModel(volume=SAVED_VOLUME, ship_effect=True))
        clip_samples = write_prepared_reply_clip(
            edceleste, DEFAULT_EDGE_VOICE, "Landing gear deployed"
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the game reports the gear up, Celeste says nothing"):
            await game_writes_first_status_file(edceleste, pilot, flags=0)
            assert edceleste.played_audio == []
            assert edceleste.spoken_texts == []

        with allure.step("When the game reports the landing gear down"):
            game_changes_the_flags(edceleste, STATUS_LANDING_GEAR_DOWN)

        with allure.step("Then the speakers play the prepared clip once"):
            await edceleste.wait_until(
                pilot, lambda: edceleste.played_audio != [], "the clip played"
            )
            await pilot.pause(0.5)
            assert len(edceleste.played_audio) == 1
            played = edceleste.played_audio[0]
            assert played["sample_rate"] == CLIP_SAMPLE_RATE
            np.testing.assert_allclose(played["samples"], clip_samples, atol=1e-3)

        with allure.step("And it is played at the saved volume with the ship effect"):
            assert played["volume"] == SAVED_VOLUME
            assert played["with_ship_effect"] is True

        with allure.step("And the voice engine is not asked to say anything"):
            assert edceleste.spoken_texts == []


SHIP_SWITCHES = [
    pytest.param(
        STATUS_LANDING_GEAR_DOWN, 0, "Landing gear retracted", id="gear-retracted"
    ),
    pytest.param(STATUS_LIGHTS_ON, 0, "Lights off", id="lights-off"),
    pytest.param(
        0, STATUS_FLIGHT_ASSIST_OFF, "Flight assist off", id="flight-assist-off"
    ),
    pytest.param(0, STATUS_LOW_FUEL, "Main fuel tank low", id="low-fuel"),
]


@allure.title("When the game reports a ship switch Celeste says '{reply_text}'")
@pytest.mark.parametrize("flags_before, flags_after, reply_text", SHIP_SWITCHES)
async def test_should_say_the_reply_of_the_ship_switch_the_game_reports(
    edceleste, flags_before, flags_after, reply_text
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the game reports the ship as it is now"):
            await game_writes_first_status_file(edceleste, pilot, flags_before)
            assert edceleste.spoken_texts == []

        with allure.step("When the game reports the switch changed"):
            game_changes_the_flags(edceleste, flags_after)

        with allure.step(f"Then Celeste says '{reply_text}'"):
            await edceleste.wait_until(
                pilot,
                lambda: edceleste.spoken_texts != [],
                "the reply handed to the voice engine",
            )
            await pilot.pause(0.5)
            assert edceleste.spoken_texts == [reply_text]


JOURNAL_EVENTS_WITH_A_VOICE_LINE = [
    pytest.param("DockingGranted", "Docking request granted", id="docking-granted"),
    pytest.param("Docked", "Docking successful", id="docked"),
    pytest.param("RefuelAll", "Fuel replenished", id="refuel-all"),
]


@allure.title(
    "When the game writes {event_name} to the journal Celeste says '{reply_text}'"
)
@pytest.mark.parametrize("event_name, reply_text", JOURNAL_EVENTS_WITH_A_VOICE_LINE)
async def test_should_say_the_reply_of_the_journal_event_the_game_writes(
    edceleste, event_name, reply_text
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step(f"When the game writes {event_name} to the journal"):
            edceleste.append_journal_event(event_name)

        with allure.step(f"Then Celeste says '{reply_text}'"):
            await edceleste.wait_until(
                pilot,
                lambda: edceleste.spoken_texts != [],
                "the reply handed to the voice engine",
            )
            await pilot.pause(0.5)
            assert edceleste.spoken_texts == [reply_text]


@allure.title("Celeste says nothing about what the game set before she started")
async def test_should_stay_silent_about_the_game_state_from_before_the_start(
    edceleste,
):
    with allure.step(
        "Given the game wrote a session with the gear down, low fuel, a docking "
        "and a refuel"
    ):
        write_the_files_of_a_session_in_progress(edceleste)
        edceleste.append_journal_event("DockingGranted")
        edceleste.append_journal_event("Docked")
        edceleste.append_journal_event("RefuelAll")
        edceleste.write_status_file(
            fuel_main=FUEL_IN_THE_BASELINE,
            flags=STATUS_LANDING_GEAR_DOWN | STATUS_LOW_FUEL,
        )

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="When")

        with allure.step("Then the ship panel shows the gear down"):
            await wait_for_the_gear_in_the_ship_panel(edceleste, pilot)

        with allure.step("And Celeste said and played nothing"):
            await pilot.pause(0.5)
            assert edceleste.spoken_texts == []
            assert edceleste.played_audio == []


@allure.title("With Ship replies off Celeste says nothing when the game state changes")
async def test_should_stay_silent_about_the_game_state_when_ship_replies_are_off(
    edceleste,
):
    with allure.step("Given Ship replies are off in the settings"):
        edceleste.save_tts_settings(TTSModel(volume=1.0, play_ship_replies=False))

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the game reports the landing gear up"):
            await game_writes_first_status_file(edceleste, pilot, flags=0)

        with allure.step(
            "When the game reports the gear down and writes DockingGranted"
        ):
            game_changes_the_flags(edceleste, STATUS_LANDING_GEAR_DOWN)
            edceleste.append_journal_event("DockingGranted")

        with allure.step("Then the ship panel shows the gear down"):
            await wait_for_the_gear_in_the_ship_panel(edceleste, pilot)

        with allure.step("And the ship log shows DockingGranted"):
            await edceleste.wait_until(
                pilot,
                lambda: "DockingGranted" in ship_log_events(pilot.app),
                "DockingGranted in the ship log",
            )

        with allure.step("And Celeste said and played nothing"):
            await pilot.pause(0.5)
            assert edceleste.spoken_texts == []
            assert edceleste.played_audio == []


@allure.title("With Ship replies off a command is answered in COMMS but not spoken")
async def test_should_write_but_not_speak_the_command_reply_when_ship_replies_are_off(
    edceleste,
):
    with allure.step("Given Ship replies are off in the settings"):
        edceleste.save_tts_settings(TTSModel(volume=1.0, play_ship_replies=False))

    with allure.step(
        "And Instinct on the GPU picks the throttle for 'set throttle to zero'"
    ):
        prompts_sent_to_llm = let_instinct_pick(
            edceleste, SET_THROTTLE_TO_ZERO, "SetSpeedZero"
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'set throttle to zero' in COMMS"):
            await send_comms_message(pilot, SET_THROTTLE_TO_ZERO)

        with allure.step("Then COMMS shows the reply 'Throttle zero'"):
            await wait_for_instinct_reply_in_comms(edceleste, pilot)
            assert comms_entries(pilot.app, "llm-response") == ["Throttle zero"]

        with allure.step("And the throttle key is pressed once"):
            assert edceleste.fake_keyboard.keyboard_log == THROTTLE_ZERO_KEYS

        with allure.step("And Celeste (the LLM) is not asked anything"):
            assert prompts_sent_to_llm == []

        with allure.step("And Celeste said and played nothing"):
            await pilot.pause(0.5)
            assert edceleste.spoken_texts == []
            assert edceleste.played_audio == []


@allure.title("After a throttle command Celeste says the reply right away")
async def test_should_speak_the_reply_of_a_command_the_game_state_does_not_confirm(
    edceleste,
):
    with allure.step(
        "Given Instinct on the GPU picks the throttle for 'set throttle to zero'"
    ):
        prompts_sent_to_llm = let_instinct_pick(
            edceleste, SET_THROTTLE_TO_ZERO, "SetSpeedZero"
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'set throttle to zero' in COMMS"):
            await send_comms_message(pilot, SET_THROTTLE_TO_ZERO)

        with allure.step("Then COMMS shows the reply 'Throttle zero'"):
            await wait_for_instinct_reply_in_comms(edceleste, pilot)
            assert comms_entries(pilot.app, "llm-response") == ["Throttle zero"]

        with allure.step("And Celeste says 'Throttle zero' once"):
            await edceleste.wait_until(
                pilot,
                lambda: edceleste.spoken_texts != [],
                "the reply handed to the voice engine",
            )
            await pilot.pause(0.5)
            assert edceleste.spoken_texts == ["Throttle zero"]

        with allure.step("And the throttle key is pressed once"):
            assert edceleste.fake_keyboard.keyboard_log == THROTTLE_ZERO_KEYS

        with allure.step("And Celeste (the LLM) is not asked anything"):
            assert prompts_sent_to_llm == []


@allure.title("An FSD command is written in COMMS, the voice comes with the game")
async def test_should_say_the_frame_shift_drive_once_when_the_game_reports_the_charge(
    edceleste,
):
    with allure.step(
        "Given Instinct on the GPU picks supercruise for 'engage supercruise'"
    ):
        prompts_sent_to_llm = let_instinct_pick(
            edceleste, ENGAGE_SUPERCRUISE, "Supercruise"
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the game reports the ship as it is now"):
            await game_writes_first_status_file(edceleste, pilot, flags=0)

        with allure.step("When the Commander sends 'engage supercruise' in COMMS"):
            await send_comms_message(pilot, ENGAGE_SUPERCRUISE)

        with allure.step("Then COMMS shows the reply 'Engaging supercruise'"):
            await wait_for_instinct_reply_in_comms(edceleste, pilot)
            assert comms_entries(pilot.app, "llm-response") == ["Engaging supercruise"]

        with allure.step("And the supercruise key is pressed once"):
            assert edceleste.fake_keyboard.keyboard_log == SUPERCRUISE_KEYS

        with allure.step("And Celeste (the LLM) is not asked anything"):
            assert prompts_sent_to_llm == []

        with allure.step("And Celeste has not said anything yet"):
            await pilot.pause(0.5)
            assert edceleste.spoken_texts == []

        with allure.step("And the game reports the frame shift drive charging"):
            game_changes_the_flags(edceleste, STATUS_FSD_CHARGING)

        with allure.step("And Celeste says 'Frame shift drive charging' once"):
            await edceleste.wait_until(
                pilot,
                lambda: edceleste.spoken_texts != [],
                "the reply handed to the voice engine",
            )
            await pilot.pause(0.5)
            assert edceleste.spoken_texts == ["Frame shift drive charging"]
