import pytest
from textual.app import App

from edceleste.ui.screens.dashboard.widgets.comms.widget_comms_entry import (
    WidgetCommsEntry,
)

pytestmark = pytest.mark.anyio


def comms_entries(app: App, entry_type: str) -> list[str]:
    # app.query() looks only at the first screen, the dashboard is pushed on top
    return [
        entry.content
        for entry in app.screen.query(WidgetCommsEntry)
        if entry.entry_type == entry_type
    ]


async def test_should_show_and_speak_celestes_answer(edceleste):
    async def answer_copy_that(messages, agent_info):
        yield "Copy that, "
        yield "Commander."

    edceleste.use_scripted_model(answer_copy_that)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        await pilot.click("#comms-input")
        await pilot.press(*"hello")
        await pilot.press("enter")

        await edceleste.wait_until(
            pilot,
            lambda: comms_entries(pilot.app, "llm-response") != [],
            "Celeste's answer in COMMS",
        )
        assert comms_entries(pilot.app, "user-command") == ["hello"]
        assert comms_entries(pilot.app, "llm-response") == ["Copy that, Commander."]
        assert edceleste.spoken_texts == ["Copy that, Commander."]
