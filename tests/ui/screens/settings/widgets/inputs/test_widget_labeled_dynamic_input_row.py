import unittest

from textual.app import App
from textual.app import ComposeResult
from textual.pilot import Pilot
from textual.widgets import Input, Label

from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_dynamic_input_row import (  # noqa: E501
    WidgetLabeledDynamicInputRow,
)

SAVED_VALUE = "C:/Saved Games/Journal"
ROW_ID = "journal-path-input"


class RowTestApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.submitted_values: list[str] = []
        self.value_changed_events: list[ValueChanged] = []

    def compose(self) -> ComposeResult:
        yield WidgetLabeledDynamicInputRow(
            "Journal path",
            SAVED_VALUE,
            on_submit=self.submitted_values.append,
            type="text",
            id=ROW_ID,
        )

    def on_value_changed(self, event: ValueChanged) -> None:
        self.value_changed_events.append(event)


def value_label_is_yellow(app: App) -> bool:
    """The value label must exist, query_one fails when the row shows an Input."""
    value_label = app.query_one(f"#{ROW_ID} .entry-value", Label)
    return value_label.has_class("warning-label")


async def open_the_row_and_press_keys(pilot: Pilot, *keys: str) -> None:
    """Clicks the row, so it turns into an Input, and presses the keys there."""
    await pilot.click(f"#{ROW_ID}")
    await pilot.pause()
    await pilot.press("end", *keys)
    await pilot.pause()


class TestWidgetLabeledDynamicInputRow(unittest.IsolatedAsyncioTestCase):
    async def test_should_turn_the_label_yellow_when_the_value_is_not_saved(self):
        app = RowTestApp()

        async with app.run_test() as pilot:
            await open_the_row_and_press_keys(pilot, *"_new", "enter")

            self.assertTrue(value_label_is_yellow(app))
            await pilot.pause()
            self.assertTrue(value_label_is_yellow(app))

    async def test_should_remove_the_yellow_mark_after_the_changed_value_is_saved(
        self,
    ):
        app = RowTestApp()

        async with app.run_test() as pilot:
            await open_the_row_and_press_keys(pilot, *"_new", "enter")
            self.assertTrue(value_label_is_yellow(app))

            app.query_one(WidgetLabeledDynamicInputRow).mark_current_value_as_saved()
            await pilot.pause()

            self.assertFalse(value_label_is_yellow(app))

    async def test_should_not_turn_the_label_yellow_when_the_old_value_is_typed_back(
        self,
    ):
        app = RowTestApp()

        async with app.run_test() as pilot:
            await open_the_row_and_press_keys(pilot, "x", "backspace", "enter")

            row = app.query_one(WidgetLabeledDynamicInputRow)
            self.assertEqual(row.value, SAVED_VALUE)
            self.assertFalse(row.is_modified())
            self.assertFalse(value_label_is_yellow(app))

    async def test_should_do_nothing_when_enter_is_pressed_without_changing_the_text(
        self,
    ):
        app = RowTestApp()

        async with app.run_test() as pilot:
            await open_the_row_and_press_keys(pilot, "enter")

            self.assertEqual(app.value_changed_events, [])
            self.assertEqual(app.submitted_values, [])
            self.assertFalse(
                app.query_one(WidgetLabeledDynamicInputRow).is_being_edited
            )

    async def test_should_do_nothing_when_the_field_is_left_without_changing_the_text(
        self,
    ):
        app = RowTestApp()

        async with app.run_test() as pilot:
            await open_the_row_and_press_keys(pilot)
            app.query_one(Input).blur()
            await pilot.pause()

            self.assertEqual(app.value_changed_events, [])
            self.assertEqual(app.submitted_values, [])
            self.assertFalse(
                app.query_one(WidgetLabeledDynamicInputRow).is_being_edited
            )

    async def test_should_report_the_new_value_when_the_text_is_changed(self):
        app = RowTestApp()

        async with app.run_test() as pilot:
            await open_the_row_and_press_keys(pilot, *"_new", "enter")

            self.assertEqual(app.submitted_values, [SAVED_VALUE + "_new"])
            self.assertEqual(len(app.value_changed_events), 1)
            self.assertEqual(
                app.value_changed_events[0].new_value, SAVED_VALUE + "_new"
            )

    async def test_should_report_the_new_value_when_a_changed_field_is_left(self):
        app = RowTestApp()

        async with app.run_test() as pilot:
            await open_the_row_and_press_keys(pilot, *"_new")
            app.query_one(Input).blur()
            await pilot.pause()

            self.assertEqual(app.submitted_values, [SAVED_VALUE + "_new"])
            self.assertEqual(len(app.value_changed_events), 1)

    async def test_should_keep_the_typed_text_when_saved_while_editing(self):
        app = RowTestApp()

        async with app.run_test() as pilot:
            await open_the_row_and_press_keys(pilot, *"_new")

            app.query_one(WidgetLabeledDynamicInputRow).mark_current_value_as_saved()
            await pilot.pause()

            self.assertEqual(app.query_one(Input).value, SAVED_VALUE + "_new")


if __name__ == "__main__":
    unittest.main()
