import allure
import pytest
from pydantic_ai.messages import UserPromptPart

from tests.e2e.conftest import comms_entries

pytestmark = [pytest.mark.anyio, allure.feature("Reactions to game events")]


def remember_prompts_and_answer(prompts_seen_by_the_model: list[str], answer: str):
    async def scripted_answer(messages, agent_info):
        for part in messages[-1].parts:
            if isinstance(part, UserPromptPart):
                prompts_seen_by_the_model.append(str(part.content))
        yield answer

    return scripted_answer


@allure.title("Celeste speaks up on her own after a jump when FSDJump has a reaction")
async def test_should_answer_on_its_own_when_an_event_with_a_reaction_happens(
    edceleste,
):
    prompts_seen_by_the_model: list[str] = []

    with allure.step("Given the FSDJump reaction is on in the settings"):
        edceleste.react_to_event("FSDJump")

    with allure.step("And the LLM answers 'Jump complete, Commander.'"):
        edceleste.use_scripted_model(
            remember_prompts_and_answer(
                prompts_seen_by_the_model, "Jump complete, Commander."
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the game writes FSDJump to the journal"):
            edceleste.append_journal_event("FSDJump")

        with allure.step("Then Celeste's answer shows in COMMS without a message"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's reaction to FSDJump in COMMS",
            )
            assert comms_entries(pilot.app, "user-command") == []
            assert comms_entries(pilot.app, "llm-response") == [
                "Jump complete, Commander."
            ]

        with allure.step("And Celeste speaks the answer"):
            assert edceleste.spoken_texts == ["Jump complete, Commander."]

        with allure.step("And the LLM was asked about the FSDJump event once"):
            assert len(prompts_seen_by_the_model) == 1
            assert '"event":"FSDJump"' in prompts_seen_by_the_model[0]


@allure.title("Celeste stays quiet after an event that has no reaction")
async def test_should_not_react_to_an_event_without_a_reaction(edceleste):
    prompts_seen_by_the_model: list[str] = []

    with allure.step("Given only the FSDJump reaction is on in the settings"):
        edceleste.react_to_event("FSDJump")
        edceleste.use_scripted_model(
            remember_prompts_and_answer(
                prompts_seen_by_the_model, "Jump complete, Commander."
            )
        )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the game writes Docked and then FSDJump"):
            edceleste.append_journal_event("Docked")
            edceleste.append_journal_event("FSDJump")

        with allure.step("Then the LLM was asked only about FSDJump"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's reaction to FSDJump in COMMS",
            )
            assert len(prompts_seen_by_the_model) == 1
            assert '"event":"FSDJump"' in prompts_seen_by_the_model[0]
