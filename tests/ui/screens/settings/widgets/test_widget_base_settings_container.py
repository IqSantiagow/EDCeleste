import unittest

from textual.app import App
from textual.app import ComposeResult
from textual.pilot import Pilot
from textual.widgets import Label

from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_dynamic_input_row import (  # noqa: E501
    WidgetLabeledDynamicInputRow,
)
from edceleste.ui.screens.settings.widgets.widget_base_settings_container import (
    WidgetBaseSettingsContainer,
)

JOURNAL_ROW_ID = "journal-path-input"
KEYBINDINGS_ROW_ID = "keybindings-path-input"


class PathsSection(WidgetBaseSettingsContainer):
    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield WidgetLabeledDynamicInputRow(
            "Journal path",
            "C:/Saved Games/Journal",
            on_submit=lambda _: None,
            type="text",
            id=JOURNAL_ROW_ID,
        )
        yield WidgetLabeledDynamicInputRow(
            "Keybindings path",
            "C:/Bindings",
            on_submit=lambda _: None,
            type="text",
            id=KEYBINDINGS_ROW_ID,
        )


class SectionTestApp(App):
    # Without ui/css.tcss every row would take the whole screen height, and the
    # second row would be out of reach for the click.
    CSS = """
    PathsSection { height: auto; }
    WidgetLabeledDynamicInputRow { height: 3; }
    """

    def compose(self) -> ComposeResult:
        yield PathsSection(id="settings-paths")


def value_label_is_yellow(app: App, row_id: str) -> bool:
    """The value label must exist, query_one fails when the row shows an Input."""
    value_label = app.query_one(f"#{row_id} .entry-value", Label)
    return value_label.has_class("warning-label")


async def append_text_to_the_row(pilot: Pilot, row_id: str, text: str) -> None:
    """Clicks the row, so it turns into an Input, types the text at the end and
    confirms it with Enter."""
    await pilot.click(f"#{row_id}")
    await pilot.pause()
    await pilot.press("end", *text, "enter")
    await pilot.pause()


class TestWidgetBaseSettingsContainer(unittest.IsolatedAsyncioTestCase):
    async def test_should_remove_the_yellow_mark_of_all_fields_when_section_is_saved(
        self,
    ):
        app = SectionTestApp()

        async with app.run_test() as pilot:
            await append_text_to_the_row(pilot, JOURNAL_ROW_ID, "_new")
            await append_text_to_the_row(pilot, KEYBINDINGS_ROW_ID, "_new")
            self.assertTrue(value_label_is_yellow(app, JOURNAL_ROW_ID))
            self.assertTrue(value_label_is_yellow(app, KEYBINDINGS_ROW_ID))

            app.query_one(PathsSection).hide_error_and_mark_values_as_saved()
            await pilot.pause()

            self.assertFalse(value_label_is_yellow(app, JOURNAL_ROW_ID))
            self.assertFalse(value_label_is_yellow(app, KEYBINDINGS_ROW_ID))


if __name__ == "__main__":
    unittest.main()
