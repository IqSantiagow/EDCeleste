import unittest

from textual.app import App, ComposeResult
from textual.widgets import Label

from edceleste.ui.screens.system_check.system_check_screen import (
    SystemCheckRow,
    row_name_for,
)


class RowTestApp(App):
    def compose(self) -> ComposeResult:
        yield SystemCheckRow("llm__instinct", id="row")


def row_texts(app: App) -> list[str]:
    return [str(label.content) for label in app.query_one("#row").query(Label)]


class TestRowNameFor(unittest.TestCase):
    def test_service_name_is_upper_case_without_underscores(self):
        self.assertEqual(row_name_for("event_reactions"), "EVENT REACTIONS")

    def test_child_service_is_drawn_under_its_parent(self):
        self.assertEqual(row_name_for("llm__instinct"), "└ INSTINCT")


class TestSystemCheckRow(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_row_shows_its_marker_and_disabled(self):
        app = RowTestApp()

        async with app.run_test() as pilot:
            app.query_one(SystemCheckRow).state = "disabled"
            await pilot.pause()

            self.assertEqual(row_texts(app), ["[--]", "└ INSTINCT", "Disabled"])

    async def test_row_in_progress_shows_its_progress_text(self):
        app = RowTestApp()

        async with app.run_test() as pilot:
            row = app.query_one(SystemCheckRow)
            row.progress_text = "Downloading model 42% · 630 MB of 1.5 GB"
            row.state = "in_progress"
            await pilot.pause()

            self.assertEqual(
                row_texts(app),
                ["[**]", "└ INSTINCT", "Downloading model 42% · 630 MB of 1.5 GB"],
            )
