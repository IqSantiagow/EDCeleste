from textual.timer import Timer
from textual.widgets import Static


class WidgetSpinner(Static):
    """A small spinning braille-dot icon, optionally followed by a text label.

    Starts out empty. Call start()/stop() to turn the spinning animation on
    and off.
    """

    SPINNER_FRAMES = [
        "⠋",
        "⠙",
        "⠹",
        "⠸",
        "⠼",
        "⠴",
        "⠦",
        "⠧",
        "⠇",
        "⠏",
    ]

    def __init__(self, label: str = "", **kwargs) -> None:
        """Starts empty and not spinning. No timer exists until start()."""
        super().__init__("", **kwargs)
        self.label_text = label
        self._spinner_index = 0
        self._spinner_timer: Timer | None = None

    def start(self) -> None:
        """Starts a 0.1 s timer that draws the next frame, and draws the first
        frame at once. Calling it while already spinning does nothing, so the
        animation never runs twice as fast."""
        if self._spinner_timer is not None:
            return
        self._spinner_index = 0
        self._spinner_timer = self.set_interval(0.1, self._advance_spinner)
        self._advance_spinner()

    def stop(self, final_text: str = "") -> None:
        """Stops the timer, when there is one, and replaces the spinner and
        label with final_text. The default empty text clears the widget. Safe
        to call when not spinning."""
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self.update(final_text)

    def _advance_spinner(self) -> None:
        """Timer callback. Draws the next frame, with the label after it when
        there is one, and wraps back to the first frame after the last."""
        frame = self.SPINNER_FRAMES[self._spinner_index % len(self.SPINNER_FRAMES)]
        self._spinner_index += 1
        self.update(f"{frame} {self.label_text}" if self.label_text else frame)
