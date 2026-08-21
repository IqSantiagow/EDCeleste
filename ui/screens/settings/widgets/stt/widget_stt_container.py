from dependency_injector.wiring import Provide, inject
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import LoadingIndicator

from containers.main_container import Container
from services.models.settings_model import SttModel
from ui.screens.settings.events.settings_events import SectionSettingsChanged
from ui.screens.settings.settings_repository import SettingsRepository
from ui.screens.settings.widgets.const_ids import (
    SettingsInputWidgetIds,
    SettingsSection,
)
from ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    ValueChanged,
    WidgetLabeledSelectRow,
)
from ui.screens.settings.widgets.inputs.widget_labeled_switch_row import (
    WidgetLabeledSwitchRow,
)
from ui.widgets.common.widget_section_header import WidgetSectionHeader


class WidgetSttContainer(Vertical):
    models: reactive[list[str] | None] = reactive(None, recompose=True)

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
        super().__init__(*args, **kwargs)
        self.stt_model = stt_model
        self.settings_repository = settings_repository

    def on_mount(self) -> None:
        self.call_later(self.fetch_models)

    def compose(self) -> ComposeResult:
        if self.models is None:
            yield LoadingIndicator(id="loading-models-indicator")
        else:
            with Vertical():
                yield WidgetSectionHeader("STT SETTINGS")
                yield WidgetLabeledSwitchRow(
                    "Enabled: ",
                    value=self.stt_model.enabled,
                    id=SettingsInputWidgetIds.STT_ENABLED_INPUT.value,
                )
                yield WidgetLabeledSelectRow(
                    "Model: ",
                    options=self.models,
                    value=self.stt_model.model,
                    id=SettingsInputWidgetIds.STT_MODEL_INPUT.value,
                )

    @work
    async def fetch_models(self) -> None:
        try:
            self.models = self.settings_repository.get_stt_models()
        except Exception as e:
            self.log(f"Error fetching STT models: {e}")
            self.notify("Error fetching STT models. Please check your STT service.")
            self.models = [self.stt_model.model]

    def on_value_changed(self, message: ValueChanged) -> None:
        if message.sender_id == SettingsInputWidgetIds.STT_ENABLED_INPUT.value:
            self.stt_model.enabled = message.new_value
        elif message.sender_id == SettingsInputWidgetIds.STT_MODEL_INPUT.value:
            self.stt_model.model = message.new_value

        self.post_message(
            SectionSettingsChanged(
                SettingsSection.STT,
                new_value=self.stt_model,
            )
        )
