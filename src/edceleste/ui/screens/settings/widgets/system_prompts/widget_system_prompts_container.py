import enum

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widgets import Label, LoadingIndicator
from dependency_injector.wiring import Provide, inject

from edceleste.containers.main_container import Container
from edceleste.services.models.settings_model import (
    SUPPORTED_LLM_PROVIDER_TYPES,
    LLMModel,
    LLMProviderModel,
)
from edceleste.ui.screens.settings.events.settings_events import SectionSettingsChanged
from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.widgets.const_ids import SettingsSection
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_dynamic_input_row import (  # noqa: E501
    WidgetLabeledDynamicInputRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    ValueChanged,
    WidgetLabeledSelectRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_textarea_row import (
    WidgetLabeledTextAreaRow,
)
from edceleste.ui.screens.settings.widgets.widget_base_settings_container import (
    WidgetBaseSettingsContainer,
)
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader

PROVIDER_OPTIONS = SUPPORTED_LLM_PROVIDER_TYPES
PROVIDER_VALUES = SUPPORTED_LLM_PROVIDER_TYPES


class SystemPromptsInputWidgetIds(enum.Enum):
    LLM_PROVIDER_TYPE_INPUT = "llm-provider-type-input"
    LLM_MODEL_INPUT = "llm-model-input"
    LLM_API_KEY_INPUT = "llm-api-key-input"
    LLM_BASE_URL_INPUT = "llm-base-url-input"
    LLM_SYSTEM_PROMPT_INPUT = "llm-system-prompt-input"
    LLM_USER_PROMPT_INPUT = "llm-user-prompt-input"


class WidgetSystemPromptsContainer(WidgetBaseSettingsContainer):
    DEFAULT_CLASSES = "settings-container"
    BORDER_TITLE = "LLM & PROMPTS"

    provider: reactive[LLMProviderModel | None] = reactive(None, recompose=True)
    models: reactive[list[str] | None] = reactive(None, recompose=True)

    @inject
    def __init__(
        self,
        llm_model: LLMModel,
        settings_repository: SettingsRepository = Provide[
            Container.settings_repository
        ],
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.llm_model = llm_model
        self.settings_repository = settings_repository
        self.provider = llm_model.provider

    def on_mount(self) -> None:
        self.call_later(self.fetch_models)

    async def fetch_models(self) -> None:
        provider = self.provider
        assert provider is not None, "provider must be set before fetch_models runs"
        try:
            self.models = await self.settings_repository.get_llm_models(provider)
        except Exception as e:
            self.log(f"Error fetching models for {provider.type}: {e}")
            self.notify(
                f"Error fetching models for {provider.type}. Is the API key ok?"
            )
            self.models = []

    def refetch_models(self) -> None:
        """The old list belongs to the old provider, key or endpoint - drop it so
        the loading indicator shows instead of the wrong models."""
        self.models = None
        self.call_later(self.fetch_models)

    def compose(self) -> ComposeResult:
        yield from super().compose()
        with VerticalScroll():
            yield WidgetSectionHeader("LLM SETTINGS")
            provider = self.provider
            assert provider is not None, "provider must be set before compose() runs"
            yield WidgetLabeledSelectRow(
                "Provider: ",
                PROVIDER_OPTIONS,
                provider.type,
                values=PROVIDER_VALUES,
                id=SystemPromptsInputWidgetIds.LLM_PROVIDER_TYPE_INPUT.value,
            )
            yield WidgetLabeledDynamicInputRow(
                "API Key:",
                provider.api_key,
                lambda value: self.log("API key submitted"),
                type="text",
                password=True,
                id=SystemPromptsInputWidgetIds.LLM_API_KEY_INPUT.value,
            )
            yield WidgetLabeledDynamicInputRow(
                "Base URL:",
                provider.base_url,
                lambda value: self.log(f"Base URL submitted: {value}"),
                type="text",
                id=SystemPromptsInputWidgetIds.LLM_BASE_URL_INPUT.value,
            )
            yield from self.mount_model_settings(provider)

            yield WidgetSectionHeader("PROMPTS")
            yield WidgetLabeledTextAreaRow(
                "System Prompt:",
                self.llm_model.system_prompt,
                # TODO: Implement validation logic
                lambda value: self.log(f"System prompt submitted: {value}"),
                id=SystemPromptsInputWidgetIds.LLM_SYSTEM_PROMPT_INPUT.value,
            )
            yield WidgetLabeledTextAreaRow(
                "User Prompt:",
                self.llm_model.user_prompt,
                # TODO: Implement validation logic. Not wired into LLMService yet.
                lambda value: self.log(f"User prompt submitted: {value}"),
                id=SystemPromptsInputWidgetIds.LLM_USER_PROMPT_INPUT.value,
            )

    def mount_model_settings(self, provider: LLMProviderModel) -> ComposeResult:
        if self.models is None:
            yield LoadingIndicator(id="loading-llm-models-indicator")
            return
        if not self.models:
            yield Label(
                f"'{provider.type}' does not publish a model list, type it by hand.",
                classes="no-profiles-message",
            )
            yield WidgetLabeledDynamicInputRow(
                "Model:",
                provider.model,
                lambda value: self.log(f"Model submitted: {value}"),
                type="text",
                id=SystemPromptsInputWidgetIds.LLM_MODEL_INPUT.value,
            )
            return
        yield WidgetLabeledSelectRow(
            "Model: ",
            self.models,
            provider.model,
            id=SystemPromptsInputWidgetIds.LLM_MODEL_INPUT.value,
        )

    def on_value_changed(self, message: ValueChanged) -> None:
        provider = self.provider
        assert provider is not None, "provider must be set before on_value_changed runs"

        if (
            message.sender_id
            == SystemPromptsInputWidgetIds.LLM_PROVIDER_TYPE_INPUT.value
        ):
            if message.new_value != provider.type:
                new_provider = LLMProviderModel(type=message.new_value, model="")
                self.llm_model.provider = new_provider
                self.provider = new_provider
                self.refetch_models()
        elif message.sender_id == SystemPromptsInputWidgetIds.LLM_MODEL_INPUT.value:
            provider.model = message.new_value
        elif message.sender_id == SystemPromptsInputWidgetIds.LLM_API_KEY_INPUT.value:
            provider.api_key = message.new_value
            self.refetch_models()
        elif message.sender_id == SystemPromptsInputWidgetIds.LLM_BASE_URL_INPUT.value:
            provider.base_url = message.new_value
            self.refetch_models()
        elif (
            message.sender_id
            == SystemPromptsInputWidgetIds.LLM_SYSTEM_PROMPT_INPUT.value
        ):
            self.llm_model.system_prompt = message.new_value
        elif (
            message.sender_id == SystemPromptsInputWidgetIds.LLM_USER_PROMPT_INPUT.value
        ):
            self.llm_model.user_prompt = message.new_value

        self.post_message(
            SectionSettingsChanged(
                SettingsSection.LLM,
                new_value=self.llm_model,
            )
        )
