import pytest
from pydantic_ai.messages import UserPromptPart

from tests.e2e.conftest import comms_entries

pytestmark = pytest.mark.anyio


def remember_prompts_and_answer(prompts_seen_by_the_model: list[str], answer: str):
    async def scripted_answer(messages, agent_info):
        for part in messages[-1].parts:
            if isinstance(part, UserPromptPart):
                prompts_seen_by_the_model.append(str(part.content))
        yield answer

    return scripted_answer


async def test_should_answer_on_its_own_when_an_event_with_a_reaction_happens(
    edceleste,
):
    prompts_seen_by_the_model: list[str] = []
    edceleste.react_to_event("FSDJump")
    edceleste.use_scripted_model(
        remember_prompts_and_answer(
            prompts_seen_by_the_model, "Jump complete, Commander."
        )
    )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        edceleste.append_journal_event("FSDJump")

        await edceleste.wait_until(
            pilot,
            lambda: comms_entries(pilot.app, "llm-response") != [],
            "Celeste's reaction to FSDJump in COMMS",
        )
        assert comms_entries(pilot.app, "user-command") == []
        assert comms_entries(pilot.app, "llm-response") == ["Jump complete, Commander."]
        assert edceleste.spoken_texts == ["Jump complete, Commander."]
        assert len(prompts_seen_by_the_model) == 1
        assert '"event":"FSDJump"' in prompts_seen_by_the_model[0]


async def test_should_not_react_to_an_event_without_a_reaction(edceleste):
    prompts_seen_by_the_model: list[str] = []
    edceleste.react_to_event("FSDJump")
    edceleste.use_scripted_model(
        remember_prompts_and_answer(
            prompts_seen_by_the_model, "Jump complete, Commander."
        )
    )

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        edceleste.append_journal_event("Docked")
        edceleste.append_journal_event("FSDJump")

        await edceleste.wait_until(
            pilot,
            lambda: comms_entries(pilot.app, "llm-response") != [],
            "Celeste's reaction to FSDJump in COMMS",
        )
        assert len(prompts_seen_by_the_model) == 1
        assert '"event":"FSDJump"' in prompts_seen_by_the_model[0]
