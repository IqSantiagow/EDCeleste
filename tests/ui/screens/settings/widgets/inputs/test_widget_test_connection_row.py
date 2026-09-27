import asyncio
import unittest

from textual.app import App, ComposeResult
from textual.widgets import Label

from edceleste.ui.screens.settings.widgets.inputs.widget_button import WidgetButton
from edceleste.ui.screens.settings.widgets.inputs.widget_test_connection_row import (
    WidgetTestConnectionRow,
)


class FakeConnectionTest:
    """Waits until the test lets it answer, so the running state can be checked."""

    def __init__(self, error_message: str | None) -> None:
        self.error_message = error_message
        self.call_count = 0
        self.may_answer = asyncio.Event()

    async def __call__(self) -> str | None:
        self.call_count += 1
        await self.may_answer.wait()
        return self.error_message


class RowTestApp(App):
    def __init__(self, fake_connection_test: FakeConnectionTest) -> None:
        super().__init__()
        self.fake_connection_test = fake_connection_test

    def compose(self) -> ComposeResult:
        yield WidgetTestConnectionRow(self.fake_connection_test)


def result_text(app: App) -> str:
    return str(app.query_one("#test-connection-result", Label).content)


class TestWidgetTestConnectionRow(unittest.IsolatedAsyncioTestCase):
    async def test_should_show_connected_when_the_test_passes(self):
        fake_connection_test = FakeConnectionTest(error_message=None)
        app = RowTestApp(fake_connection_test)

        async with app.run_test() as pilot:
            await pilot.click("#test-connection-button")
            fake_connection_test.may_answer.set()
            await app.workers.wait_for_complete()
            await pilot.pause()

            self.assertEqual(result_text(app), "✓ Connected")
            result_label = app.query_one("#test-connection-result", Label)
            self.assertTrue(result_label.has_class("success"))

    async def test_should_show_the_reason_when_the_test_fails(self):
        fake_connection_test = FakeConnectionTest(error_message="401 Unauthorized")
        app = RowTestApp(fake_connection_test)

        async with app.run_test() as pilot:
            await pilot.click("#test-connection-button")
            fake_connection_test.may_answer.set()
            await app.workers.wait_for_complete()
            await pilot.pause()

            self.assertEqual(result_text(app), "✗ 401 Unauthorized")
            result_label = app.query_one("#test-connection-result", Label)
            self.assertTrue(result_label.has_class("error"))

    async def test_should_show_a_multi_line_error_as_plain_text(self):
        # Provider errors can span lines and hold "[...]" - neither may be
        # lost or read as Textual markup.
        error_message = "HTTP 401: key [REDACTED API KEY] rejected\nsee [/] docs"
        fake_connection_test = FakeConnectionTest(error_message=error_message)
        fake_connection_test.may_answer.set()
        app = RowTestApp(fake_connection_test)

        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.click("#test-connection-button")
            await app.workers.wait_for_complete()
            await pilot.pause()

            self.assertEqual(result_text(app), f"✗ {error_message}")
            result_label = app.query_one("#test-connection-result", Label)
            self.assertGreater(result_label.size.height, 1)

    async def test_should_block_the_button_while_the_test_runs(self):
        fake_connection_test = FakeConnectionTest(error_message=None)
        app = RowTestApp(fake_connection_test)

        async with app.run_test() as pilot:
            await pilot.click("#test-connection-button")
            await pilot.click("#test-connection-button")

            button = app.query_one("#test-connection-button", WidgetButton)
            self.assertTrue(button.disabled)
            self.assertEqual(fake_connection_test.call_count, 1)

            fake_connection_test.may_answer.set()
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertFalse(button.disabled)

    async def test_should_drop_the_result_when_cleared(self):
        fake_connection_test = FakeConnectionTest(error_message="401 Unauthorized")
        fake_connection_test.may_answer.set()
        app = RowTestApp(fake_connection_test)

        async with app.run_test() as pilot:
            await pilot.click("#test-connection-button")
            await app.workers.wait_for_complete()
            await pilot.pause()

            app.query_one(WidgetTestConnectionRow).clear_result()

            self.assertEqual(result_text(app), "")

    async def test_should_stop_a_running_test_when_cleared(self):
        # The running test checks the old values, its answer must not show up.
        fake_connection_test = FakeConnectionTest(error_message=None)
        app = RowTestApp(fake_connection_test)

        async with app.run_test() as pilot:
            await pilot.click("#test-connection-button")

            app.query_one(WidgetTestConnectionRow).clear_result()
            fake_connection_test.may_answer.set()
            await pilot.pause()

            self.assertEqual(result_text(app), "")
            button = app.query_one("#test-connection-button", WidgetButton)
            self.assertFalse(button.disabled)


if __name__ == "__main__":
    unittest.main()
