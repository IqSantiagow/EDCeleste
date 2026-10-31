import unittest

from textual.app import App, ComposeResult

from edceleste.ui.screens.dashboard.widgets.comms.widget_comms_entry import (
    WidgetCommsEntry,
)

PILOT_TEXT_WITH_BRACKETS = "set [/red] and [bold on the radar"
LLM_TEXT_WITH_BRACKETS = "Roger, [pause] scanning, Commander."
ERROR_TEXT_WITH_BRACKETS = "LLM turn failed: [retry in 20s] [/limit]"


class EntryApp(App):
    """Shows one COMMS entry and nothing else."""

    def __init__(self, entry: WidgetCommsEntry) -> None:
        super().__init__()
        self.entry = entry

    def compose(self) -> ComposeResult:
        yield self.entry


class WidgetCommsEntryTest(unittest.IsolatedAsyncioTestCase):
    async def check_entry_shows_text_exactly(self, entry_type: str, text: str) -> None:
        """Mounts one entry, lets Textual draw it and checks that the content
        label holds `text` unchanged. A bracket tag that Textual reads as markup
        would either crash the draw or be cut out of the text."""
        entry = WidgetCommsEntry(entry_type, text)
        async with EntryApp(entry).run_test() as pilot:
            await pilot.pause(0.2)
            content_label = entry.query_one(".comms-entry-content")
            self.assertEqual(text, content_label.render().plain)

    async def test_pilot_message_with_closing_tag_shows_exactly_as_typed(self):
        await self.check_entry_shows_text_exactly(
            "user-command", PILOT_TEXT_WITH_BRACKETS
        )

    async def test_llm_answer_with_opening_tag_keeps_the_brackets(self):
        await self.check_entry_shows_text_exactly(
            "llm-response", LLM_TEXT_WITH_BRACKETS
        )

    async def test_system_line_with_error_text_shows_exactly_as_reported(self):
        await self.check_entry_shows_text_exactly(
            "system-message", ERROR_TEXT_WITH_BRACKETS
        )


if __name__ == "__main__":
    unittest.main()
