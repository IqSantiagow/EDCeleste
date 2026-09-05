from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label
from textual_slider import Slider

from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)


from edceleste.ui.screens.settings.widgets.inputs.widget_base_input import (
    WidgetBaseInput,
)


class WidgetLabeledSliderRow(WidgetBaseInput):
    """A labeled row with a slider for picking a decimal value.

    The Slider widget we build on only understands whole numbers, so this
    row scales the real min/max/value up by `1 / step` before handing them
    to the Slider, and scales the Slider's value back down to a float
    whenever it moves.
    """

    DEFAULT_CLASSES = "entry-row-full"

    def __init__(
        self,
        label: str,
        minimum: float,
        maximum: float,
        value: float,
        step: float = 0.1,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, value=value, initial_value=value, **kwargs)
        self.label = label
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        assert self.id is not None, "WidgetLabeledSliderRow must have an id"

    def _steps_per_unit(self) -> int:
        return round(1 / self.step)

    def _to_slider_steps(self, value: float) -> int:
        return round(value * self._steps_per_unit())

    def _from_slider_steps(self, steps: int) -> float:
        return steps / self._steps_per_unit()

    def compose(self) -> ComposeResult:
        with HorizontalGroup(id="settings-entry-row-container"):
            yield Label(self.label, classes="entry-label")
            yield Slider(
                self._to_slider_steps(self.minimum),
                self._to_slider_steps(self.maximum),
                value=self._to_slider_steps(self.value),
                classes="entry-slider",
            )
            yield Label(
                f"{self.value:g}",
                classes="entry-value",
                id="slider-value-label",
            )

    def on_slider_changed(self, event: Slider.Changed) -> None:
        self.value = self._from_slider_steps(event.value)
        self.query_one("#slider-value-label", Label).update(f"{self.value:g}")
        self.post_message(ValueChanged(self.id, self.value))  # type: ignore
