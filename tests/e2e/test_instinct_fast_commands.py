import allure
import pytest

from tests.e2e.conftest import comms_entries, send_comms_message
from tests.e2e.test_game_state_prompt import prompt_remembering_llm

pytestmark = [pytest.mark.anyio, allure.feature("Instinct fast commands")]

DEPLOY_LANDING_GEAR = "deploy the landing gear"
LANDING_GEAR_KEYS = ["keyDown shiftleft", "press l", "keyUp shiftleft"]
LLM_ANSWER = "Copy that, Commander."


@allure.title("Instinct deploys the landing gear without asking Celeste")
async def test_should_press_the_key_and_reply_without_asking_the_llm(edceleste):
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

        with allure.step("When the Commander sends 'deploy the landing gear' in COMMS"):
            await send_comms_message(pilot, DEPLOY_LANDING_GEAR)

        with allure.step("Then COMMS shows the reply 'Landing gear deployed'"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Instinct's reply in COMMS",
            )
            assert comms_entries(pilot.app, "user-command") == [DEPLOY_LANDING_GEAR]
            assert comms_entries(pilot.app, "llm-response") == ["Landing gear deployed"]

        with allure.step("And the landing gear key Shift+L is pressed in the game"):
            assert edceleste.fake_keyboard.keyboard_log == LANDING_GEAR_KEYS

        with allure.step("And Celeste (the LLM) is not asked anything"):
            assert prompts_sent_to_llm == []


@allure.title("A message that only mentions the landing gear goes to Celeste")
async def test_should_send_a_message_that_is_no_command_to_celeste_and_press_no_key(
    edceleste,
):
    message = "the landing gear on the Anaconda looks nice"
    prompts_sent_to_llm: list[str] = []

    with allure.step("Given game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step("And Instinct runs on the GPU and finds no ship action to do"):
        instinct_model = edceleste.turn_instinct_on()

    with allure.step("And the LLM remembers every prompt it receives"):
        edceleste.use_scripted_model(prompt_remembering_llm(prompts_sent_to_llm))

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step(f"When the Commander sends '{message}' in COMMS"):
            await send_comms_message(pilot, message)

        with allure.step("Then Celeste answers in COMMS"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [LLM_ANSWER]

        with allure.step("And Celeste (the LLM) received the message"):
            assert len(prompts_sent_to_llm) == 1
            assert message in prompts_sent_to_llm[0]

        with allure.step("And Instinct was asked about the message"):
            assert instinct_model.messages_asked == [message]

        with allure.step("And no key is pressed in the game"):
            assert edceleste.fake_keyboard.keyboard_log == []


@allure.title("After a fast command Celeste says it and knows what was done")
async def test_should_speak_the_fast_command_reply_and_tell_celeste_about_it(
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

        with allure.step("And Instinct has already deployed the landing gear"):
            await send_comms_message(pilot, DEPLOY_LANDING_GEAR)
            await edceleste.wait_until(
                pilot,
                lambda: (
                    "Landing gear deployed" in comms_entries(pilot.app, "llm-response")
                ),
                "Instinct's reply in COMMS",
            )

        with allure.step("When the Commander asks 'what did you just do?' in COMMS"):
            await send_comms_message(pilot, "what did you just do?")

        with allure.step("Then Celeste's prompt has the command and Instinct's reply"):
            await edceleste.wait_until(
                pilot,
                lambda: len(prompts_sent_to_llm) == 1,
                "the question reaching the LLM",
            )
            assert (
                f"Human: {DEPLOY_LANDING_GEAR}\n"
                "Celeste: Landing gear deployed\n"
                "Human: what did you just do?"
            ) in prompts_sent_to_llm[0]

        with allure.step("And Instinct's reply was spoken before Celeste's answer"):
            await edceleste.wait_until(
                pilot,
                lambda: LLM_ANSWER in edceleste.spoken_texts,
                "Celeste's answer spoken",
            )
            assert edceleste.spoken_texts == ["Landing gear deployed", LLM_ANSWER]


@allure.title("When the game is not running Celeste says nothing was pressed")
async def test_should_say_nothing_was_pressed_when_the_game_window_is_not_found(
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

    with allure.step("And the game window is not found"):
        edceleste.close_the_game_window()

    with allure.step("And the LLM remembers every prompt it receives"):
        edceleste.use_scripted_model(prompt_remembering_llm(prompts_sent_to_llm))

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'deploy the landing gear' in COMMS"):
            await send_comms_message(pilot, DEPLOY_LANDING_GEAR)

        with allure.step("Then COMMS says that nothing was pressed"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "the game window warning in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [
                "Game window not found, nothing was pressed."
            ]

        with allure.step("And no key is pressed in the game"):
            assert edceleste.fake_keyboard.keyboard_log == []

        with allure.step("And Celeste (the LLM) is not asked anything"):
            assert prompts_sent_to_llm == []


@allure.title("With game actions turned off Instinct presses no key")
async def test_should_press_no_key_when_game_actions_are_off_and_instinct_is_on(
    edceleste,
):
    prompts_sent_to_llm: list[str] = []

    with allure.step("Given game actions are off in the settings"):
        assert edceleste.settings.game_actions.enabled is False

    with allure.step(
        "And Instinct on the GPU picks the gear for 'deploy the landing gear'"
    ):
        instinct_model = edceleste.turn_instinct_on()
        instinct_model.choices_by_message[DEPLOY_LANDING_GEAR] = "LandingGearToggle"

    with allure.step("And the LLM remembers every prompt it receives"):
        edceleste.use_scripted_model(prompt_remembering_llm(prompts_sent_to_llm))

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'deploy the landing gear' in COMMS"):
            await send_comms_message(pilot, DEPLOY_LANDING_GEAR)

        with allure.step("Then Celeste answers in COMMS"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [LLM_ANSWER]

        with allure.step("And Celeste (the LLM) received the message"):
            assert len(prompts_sent_to_llm) == 1
            assert DEPLOY_LANDING_GEAR in prompts_sent_to_llm[0]

        with allure.step("And no key is pressed in the game"):
            assert edceleste.fake_keyboard.keyboard_log == []

        with allure.step("And Instinct was not asked"):
            assert instinct_model.messages_asked == []


@allure.title("A model that runs on the CPU is not used for commands")
async def test_should_send_the_command_to_celeste_when_the_model_runs_on_the_cpu(
    edceleste,
):
    prompts_sent_to_llm: list[str] = []

    with allure.step("Given game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step(
        "And Instinct on the CPU picks the gear for 'deploy the landing gear'"
    ):
        instinct_model = edceleste.turn_instinct_on(device="cpu")
        instinct_model.choices_by_message[DEPLOY_LANDING_GEAR] = "LandingGearToggle"

    with allure.step("And the LLM remembers every prompt it receives"):
        edceleste.use_scripted_model(prompt_remembering_llm(prompts_sent_to_llm))

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'deploy the landing gear' in COMMS"):
            await send_comms_message(pilot, DEPLOY_LANDING_GEAR)

        with allure.step("Then Celeste answers in COMMS"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [LLM_ANSWER]

        with allure.step("And Celeste (the LLM) received the message"):
            assert len(prompts_sent_to_llm) == 1
            assert DEPLOY_LANDING_GEAR in prompts_sent_to_llm[0]

        with allure.step("And no key is pressed in the game"):
            assert edceleste.fake_keyboard.keyboard_log == []

        with allure.step("And Instinct was not asked"):
            assert instinct_model.messages_asked == []


@allure.title("A slow Instinct model does not hold the message back")
async def test_should_send_the_command_to_celeste_when_the_model_is_too_slow(
    edceleste,
):
    prompts_sent_to_llm: list[str] = []

    with allure.step("Given game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step("And Instinct knows 'deploy the landing gear' but is too slow"):
        instinct_model = edceleste.turn_instinct_on()
        instinct_model.choices_by_message[DEPLOY_LANDING_GEAR] = "LandingGearToggle"
        instinct_model.make_the_model_slow()

    with allure.step("And the LLM remembers every prompt it receives"):
        edceleste.use_scripted_model(prompt_remembering_llm(prompts_sent_to_llm))

    async with edceleste.run_app() as pilot:
        try:
            await edceleste.boot_to_dashboard(pilot, step_keyword="And")

            with allure.step(
                "When the Commander sends 'deploy the landing gear' in COMMS"
            ):
                await send_comms_message(pilot, DEPLOY_LANDING_GEAR)

            with allure.step("Then Celeste answers in COMMS, the app did not hang"):
                await edceleste.wait_until(
                    pilot,
                    lambda: comms_entries(pilot.app, "llm-response") != [],
                    "Celeste's answer in COMMS",
                )
                assert comms_entries(pilot.app, "llm-response") == [LLM_ANSWER]

            with allure.step("And Celeste (the LLM) received the message"):
                assert len(prompts_sent_to_llm) == 1
                assert DEPLOY_LANDING_GEAR in prompts_sent_to_llm[0]

            with allure.step("And Instinct was asked but had no answer in time"):
                assert instinct_model.messages_asked == [DEPLOY_LANDING_GEAR]

            with allure.step("And no key is pressed in the game"):
                assert edceleste.fake_keyboard.keyboard_log == []
        finally:
            instinct_model.let_the_model_answer()


@allure.title("When the game is not running Celeste also says nothing was pressed")
async def test_should_speak_that_nothing_was_pressed_when_the_game_window_is_not_found(
    edceleste,
):
    with allure.step("Given game actions are allowed in the settings"):
        edceleste.allow_game_actions()

    with allure.step(
        "And Instinct on the GPU picks the gear for 'deploy the landing gear'"
    ):
        instinct_model = edceleste.turn_instinct_on()
        instinct_model.choices_by_message[DEPLOY_LANDING_GEAR] = "LandingGearToggle"

    with allure.step("And the game window is not found"):
        edceleste.close_the_game_window()

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'deploy the landing gear' in COMMS"):
            await send_comms_message(pilot, DEPLOY_LANDING_GEAR)

        with allure.step("Then COMMS shows that nothing was pressed"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "the game window warning in COMMS",
            )
            assert comms_entries(pilot.app, "llm-response") == [
                "Game window not found, nothing was pressed."
            ]

        with allure.step("And Celeste says the same words out loud"):
            await edceleste.wait_until(
                pilot,
                lambda: edceleste.spoken_texts != [],
                "the warning handed to the voice engine",
            )
            assert edceleste.spoken_texts == [
                "Game window not found, nothing was pressed."
            ]

        with allure.step("And no key is pressed in the game"):
            assert edceleste.fake_keyboard.keyboard_log == []
