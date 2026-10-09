from collections.abc import Awaitable, Callable

from textual import on, work
from textual.app import ComposeResult
from textual.content import Content
from textual.containers import HorizontalGroup
from textual.widgets import Button, Label

from edceleste.ui.screens.settings.widgets.inputs.widget_button import WidgetButton
from edceleste.ui.widgets.common.widget_spinner import WidgetSpinner


class WidgetTestConnectionRow(HorizontalGroup):
    """[Test connection] button, a spinner while it runs, and the result.

    test_connection returns None when the connection works, otherwise
    a short error text. The row never saves anything.
    """

    DEFAULT_CLASSES = "test-connection-row"

    def __init__(
        self, test_connection: Callable[[], Awaitable[str | None]], **kwargs
    ) -> None:
        """test_connection is called on every press of the button. It must not
        raise, errors come back as the returned text."""
        super().__init__(**kwargs)
        self.test_connection = test_connection

    def compose(self) -> ComposeResult:
        """The spinner is stopped and the result label is empty until the
        first press."""
        yield WidgetButton("Test connection", id="test-connection-button")
        yield WidgetSpinner("Testing...", id="test-connection-spinner")
        yield Label("", id="test-connection-result")

    @on(Button.Pressed, "#test-connection-button")
    def handle_test_connection_pressed(self, event: Button.Pressed) -> None:
        """Stops the press here, so the settings screen does not see it, and
        starts the test in a worker."""
        event.stop()
        self.run_connection_test()

    @work(exclusive=True)
    async def run_connection_test(self) -> None:
        """Worker, exclusive, so a new run cancels the old one.

        1. Disables the button, clears the old result, starts the spinner.
        2. Awaits test_connection(), which usually goes to the network.
        3. Stops the spinner, enables the button again.
        4. Shows "✓ Connected" in green or "✗ <error>" in red.
        """
        button = self.query_one("#test-connection-button", WidgetButton)
        spinner = self.query_one("#test-connection-spinner", WidgetSpinner)

        # A disabled button cannot be pressed twice, so only one request goes out.
        button.disabled = True
        self.show_result("", "")
        spinner.start()

        error_message = await self.test_connection()

        spinner.stop()
        button.disabled = False

        if error_message is None:
            self.show_result("✓ Connected", "success")
        else:
            self.show_result(f"✗ {error_message}", "error")

    def show_result(self, text: str, status_class: str) -> None:
        """status_class "success" or "error" colours the text. Empty text and
        empty class leave the row blank."""
        result_label = self.query_one("#test-connection-result", Label)
        # Content, not str - a provider error can hold "[...]", which Textual
        # would read as markup and swallow or crash on.
        result_label.update(Content(text))
        result_label.set_classes(status_class)

    def clear_result(self) -> None:
        """The result describes the old values - drop it when they change.
        A test that is still running checks the old values too, so stop it."""
        self.workers.cancel_node(self)
        self.query_one("#test-connection-spinner", WidgetSpinner).stop()
        self.query_one("#test-connection-button", WidgetButton).disabled = False
        self.show_result("", "")
