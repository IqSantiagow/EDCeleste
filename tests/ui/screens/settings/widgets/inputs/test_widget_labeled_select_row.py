import unittest

from textual.app import App, ComposeResult
from textual.widgets import Select

from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    WidgetLabeledSelectRow,
)

ROW_ID = "device-input"
DEVICES = ["auto", "cuda", "cpu"]


class RowTestApp(App):
    def __init__(
        self,
        saved_value: str = "cpu",
        blank_means_empty: bool = False,
    ) -> None:
        super().__init__()
        self.saved_value = saved_value
        self.blank_means_empty = blank_means_empty
        self.value_changed_events: list[ValueChanged] = []

    def compose(self) -> ComposeResult:
        yield WidgetLabeledSelectRow(
            "Device",
            DEVICES,
            self.saved_value,
            blank_means_empty=self.blank_means_empty,
            id=ROW_ID,
        )

    def on_value_changed(self, event: ValueChanged) -> None:
        self.value_changed_events.append(event)


class TestWidgetLabeledSelectRow(unittest.IsolatedAsyncioTestCase):
    async def test_should_keep_the_value_when_the_blank_entry_is_picked(self):
        app = RowTestApp(saved_value="cpu")

        async with app.run_test() as pilot:
            await pilot.pause()
            app.value_changed_events.clear()

            app.query_one(Select).value = Select.NULL
            await pilot.pause()

            self.assertEqual("cpu", app.query_one(WidgetLabeledSelectRow).value)
            self.assertEqual([], app.value_changed_events)

    async def test_should_keep_the_saved_value_when_it_is_not_among_the_options(self):
        app = RowTestApp(saved_value="removed-voice")

        async with app.run_test() as pilot:
            await pilot.pause()

            self.assertEqual(
                "removed-voice", app.query_one(WidgetLabeledSelectRow).value
            )
            self.assertEqual([], app.value_changed_events)

    async def test_should_set_empty_value_when_blank_means_empty(self):
        app = RowTestApp(saved_value="cpu", blank_means_empty=True)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.value_changed_events.clear()

            app.query_one(Select).value = Select.NULL
            await pilot.pause()

            self.assertEqual("", app.query_one(WidgetLabeledSelectRow).value)
            self.assertEqual(
                [""], [event.new_value for event in app.value_changed_events]
            )

    async def test_should_store_a_normal_entry(self):
        app = RowTestApp(saved_value="cpu")

        async with app.run_test() as pilot:
            await pilot.pause()
            app.value_changed_events.clear()

            app.query_one(Select).value = "cuda"
            await pilot.pause()

            self.assertEqual("cuda", app.query_one(WidgetLabeledSelectRow).value)
            self.assertEqual(
                ["cuda"], [event.new_value for event in app.value_changed_events]
            )
