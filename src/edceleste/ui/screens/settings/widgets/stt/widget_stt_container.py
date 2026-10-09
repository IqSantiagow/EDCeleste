import enum

from dependency_injector.wiring import Provide, inject
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import LoadingIndicator

from edceleste.containers.main_container import Container
from edceleste.services.models.settings_model import SttModel
from edceleste.ui.screens.settings.events.settings_events import SectionSettingsChanged
from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.widgets.const_ids import SettingsSection
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    ValueChanged,
    WidgetLabeledSelectRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_switch_row import (
    WidgetLabeledSwitchRow,
)
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader


from edceleste.ui.screens.settings.widgets.widget_base_settings_container import (
    WidgetBaseSettingsContainer,
)


class SttInputWidgetIds(enum.StrEnum):
    STT_ENABLED_INPUT = "stt-enabled-input"
    STT_MODEL_INPUT = "stt-model-input"
    STT_INPUT_DEVICE_INPUT = "stt-input-device-input"


class WidgetSttContainer(WidgetBaseSettingsContainer):
    DEFAULT_CLASSES = "settings-container"
    BORDER_TITLE = "SPEECH TO TEXT"

    models: reactive[list[str] | None] = reactive(None, recompose=True)
    input_devices: reactive[list[tuple[str, int]] | None] = reactive(
        None, recompose=True
    )

    @inject
    def __init__(
        self,
        stt_model: SttModel,
        settings_repository: SettingsRepository = Provide[
            Container.settings_repository
        ],
        *args,
        **kwargs,
    ) -> None:
        """stt_model is part of the screen's working copy of the settings and
        is changed in place. settings_repository comes from the DI
        container."""
        super().__init__(*args, **kwargs)
        self.stt_model = stt_model
        self.settings_repository = settings_repository

    def on_mount(self) -> None:
        """Starts loading the model and microphone lists. Until both are in,
        compose() shows only a loading indicator."""
        self.call_later(self.fetch_stt_models_and_input_devices)

    def compose(self) -> ComposeResult:
        """Runs again when models or input_devices change.

        - one of the lists still None -> only a loading indicator,
        - both loaded -> the enabled switch, the model select and the
          microphone select. The microphone select shows device names but
          holds the device index as text. No saved device means "".
        """
        yield from super().compose()
        if self.models is None or self.input_devices is None:
            yield LoadingIndicator(id="loading-models-indicator")
        else:
            with Vertical():
                yield WidgetSectionHeader("STT SETTINGS")
                yield WidgetLabeledSwitchRow(
                    "Enabled: ",
                    value=self.stt_model.enabled,
                    id=SttInputWidgetIds.STT_ENABLED_INPUT,
                )
                yield WidgetLabeledSelectRow(
                    "Model: ",
                    options=self.models,
                    value=self.stt_model.model,
                    id=SttInputWidgetIds.STT_MODEL_INPUT,
                )
                device_labels = [name for name, _ in self.input_devices]
                device_values = [str(index) for _, index in self.input_devices]
                yield WidgetLabeledSelectRow(
                    "Input device: ",
                    options=device_labels,
                    values=device_values,
                    value=str(self.stt_model.input_device)
                    if self.stt_model.input_device is not None
                    else "",
                    id=SttInputWidgetIds.STT_INPUT_DEVICE_INPUT,
                )

    @work
    async def fetch_stt_models_and_input_devices(self) -> None:
        """Worker. Asks the repository for the STT model names and the
        microphones. Both calls are synchronous, so they block the app while
        they run.

        Each list fails on its own: a notification is shown and a fallback is
        used, only the saved model for the models, an empty list for the
        devices. Setting each list recomposes the section.
        """
        try:
            self.models = self.settings_repository.get_stt_models()
        except Exception as e:
            self.log(f"Error fetching STT models: {e}")
            self.notify("Error fetching STT models. Please check your STT service.")
            self.models = [self.stt_model.model]
        try:
            self.input_devices = self.settings_repository.get_stt_input_devices()
        except Exception as e:
            self.log(f"Error fetching STT input devices: {e}")
            self.notify(
                "Error fetching STT input devices. Please check your audio setup."
            )
            self.input_devices = []

    def on_value_changed(self, message: ValueChanged) -> None:
        """Runs when a row posts ValueChanged. Writes the new value into
        stt_model and posts SectionSettingsChanged(STT) to the settings screen.
        Nothing is saved here.

        The microphone comes as the device index in text. Anything that is not
        a number (blank select) becomes None, the system default device.
        """
        if message.sender_id == SttInputWidgetIds.STT_ENABLED_INPUT:
            self.stt_model.enabled = message.new_value
        elif message.sender_id == SttInputWidgetIds.STT_MODEL_INPUT:
            self.stt_model.model = message.new_value
        elif message.sender_id == SttInputWidgetIds.STT_INPUT_DEVICE_INPUT:
            selected_device_index_text = message.new_value
            self.stt_model.input_device = (
                int(selected_device_index_text)
                if selected_device_index_text and selected_device_index_text.isdigit()
                else None
            )

        self.post_message(
            SectionSettingsChanged(
                SettingsSection.STT,
                new_value=self.stt_model,
            )
        )
