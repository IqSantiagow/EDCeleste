from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Label, LoadingIndicator
from dependency_injector.wiring import Provide, inject

from edceleste.containers.main_container import Container
from edceleste.services.models.settings_model import (
    DEFAULT_CLAUDE_MODEL,
    ChatCompletionsModel,
    ClaudeAgentSdkModel,
    LLMModel,
    LmStudioModel,
)
from edceleste.ui.screens.settings.events.settings_events import SectionSettingsChanged
from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.widgets.const_ids import (
    SettingsInputWidgetIds,
    SettingsSection,
)
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
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader

PROVIDER_OPTIONS = ["Claude Agent SDK", "Chat Completions", "LM Studio"]
PROVIDER_VALUES = ["claude_agent_sdk", "chat_completions", "lm_studio"]

# Providers whose model comes from a fetched list (a Select) rather than
# free text typed by hand.
MODEL_LIST_PROVIDER_TYPES = ("claude_agent_sdk", "lm_studio")


def build_default_provider_for_type(
    provider_type: str,
) -> ClaudeAgentSdkModel | ChatCompletionsModel | LmStudioModel:
    if provider_type == "claude_agent_sdk":
        return ClaudeAgentSdkModel(type="claude_agent_sdk", model=DEFAULT_CLAUDE_MODEL)
    if provider_type == "lm_studio":
        return LmStudioModel(type="lm_studio", model="")
    return ChatCompletionsModel(
        type="chat_completions", model="", base_url="", bearer_token=""
    )


class WidgetSystemPromptsContainer(Vertical):
    provider: reactive[
        ClaudeAgentSdkModel | ChatCompletionsModel | LmStudioModel | None
    ] = reactive(None, recompose=True)
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

    def fetch_models(self) -> None:
        provider = self.provider
        assert provider is not None, "provider must be set before fetch_models runs"
        if provider.type not in MODEL_LIST_PROVIDER_TYPES:
            self.models = []
            return
        try:
            self.models = self.settings_repository.get_llm_models(provider.type)
        except Exception as e:
            self.log(f"Error fetching models for {provider.type}: {e}")
            self.notify(f"Error fetching models for {provider.type}. Is it running?")
            self.models = []

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield WidgetSectionHeader("LLM SETTINGS")
            provider = self.provider
            assert provider is not None, "provider must be set before compose() runs"
            yield WidgetLabeledSelectRow(
                "Provider: ",
                PROVIDER_OPTIONS,
                provider.type,
                values=PROVIDER_VALUES,
                id=SettingsInputWidgetIds.LLM_PROVIDER_TYPE_INPUT.value,
            )
            if isinstance(provider, (ClaudeAgentSdkModel, LmStudioModel)):
                yield from self.mount_model_select_settings(provider)
            elif isinstance(provider, ChatCompletionsModel):
                yield from self.mount_chat_completions_settings(provider)

            yield WidgetSectionHeader("PROMPTS")
            yield WidgetLabeledTextAreaRow(
                "System Prompt:",
                self.llm_model.system_prompt,
                # TODO: Implement validation logic
                lambda value: self.log(f"System prompt submitted: {value}"),
                id=SettingsInputWidgetIds.LLM_SYSTEM_PROMPT_INPUT.value,
            )
            yield WidgetLabeledTextAreaRow(
                "User Prompt:",
                self.llm_model.user_prompt,
                # TODO: Implement validation logic. Not wired into LLMService yet.
                lambda value: self.log(f"User prompt submitted: {value}"),
                id=SettingsInputWidgetIds.LLM_USER_PROMPT_INPUT.value,
            )

    def mount_model_select_settings(
        self, provider: ClaudeAgentSdkModel | LmStudioModel
    ) -> ComposeResult:
        if self.models is None:
            yield LoadingIndicator(id="loading-llm-models-indicator")
            return
        if not self.models:
            yield Label(
                f"No models found for '{provider.type}'.",
                classes="no-profiles-message",
            )
            return
        # TODO: The app crashes when there are no models and the user changes
        # the settings because the select widget is not mounted. Refactor this
        # in the future to avoid the issue.
        yield WidgetLabeledSelectRow(
            "Model: ",
            self.models,
            provider.model,
            id=SettingsInputWidgetIds.LLM_MODEL_INPUT.value,
        )

    def mount_chat_completions_settings(
        self, provider: ChatCompletionsModel
    ) -> ComposeResult:
        yield WidgetLabeledDynamicInputRow(
            "Model:",
            provider.model,
            lambda value: self.log(f"Chat Completions model submitted: {value}"),
            type="text",
            id=SettingsInputWidgetIds.LLM_CHAT_COMPLETIONS_MODEL_INPUT.value,
        )
        yield WidgetLabeledDynamicInputRow(
            "Base URL:",
            provider.base_url,
            lambda value: self.log(f"Base URL submitted: {value}"),
            type="text",
            id=SettingsInputWidgetIds.LLM_BASE_URL_INPUT.value,
        )
        yield WidgetLabeledDynamicInputRow(
            "Bearer Token:",
            provider.bearer_token,
            lambda value: self.log(f"Bearer token submitted: {value}"),
            type="text",
            password=True,
            id=SettingsInputWidgetIds.LLM_BEARER_TOKEN_INPUT.value,
        )

    def on_value_changed(self, message: ValueChanged) -> None:
        provider = self.provider
        assert provider is not None, "provider must be set before on_value_changed runs"

        if message.sender_id == SettingsInputWidgetIds.LLM_PROVIDER_TYPE_INPUT.value:
            if message.new_value != provider.type:
                new_provider = build_default_provider_for_type(message.new_value)
                self.llm_model.provider = new_provider
                self.provider = new_provider
                # The fetched model list belongs to the old provider - drop it
                # so mount_model_select_settings shows a loading indicator
                # instead of the wrong provider's models while we refetch.
                self.models = None
                self.call_later(self.fetch_models)
        elif message.sender_id == SettingsInputWidgetIds.LLM_MODEL_INPUT.value:
            if isinstance(provider, (ClaudeAgentSdkModel, LmStudioModel)):
                provider.model = message.new_value
        elif (
            message.sender_id
            == SettingsInputWidgetIds.LLM_CHAT_COMPLETIONS_MODEL_INPUT.value
        ):
            if isinstance(provider, ChatCompletionsModel):
                provider.model = message.new_value
        elif message.sender_id == SettingsInputWidgetIds.LLM_BASE_URL_INPUT.value:
            if isinstance(provider, ChatCompletionsModel):
                provider.base_url = message.new_value
        elif message.sender_id == SettingsInputWidgetIds.LLM_BEARER_TOKEN_INPUT.value:
            if isinstance(provider, ChatCompletionsModel):
                provider.bearer_token = message.new_value
        elif message.sender_id == SettingsInputWidgetIds.LLM_SYSTEM_PROMPT_INPUT.value:
            self.llm_model.system_prompt = message.new_value
        elif message.sender_id == SettingsInputWidgetIds.LLM_USER_PROMPT_INPUT.value:
            self.llm_model.user_prompt = message.new_value

        self.post_message(
            SectionSettingsChanged(
                SettingsSection.LLM,
                new_value=self.llm_model,
            )
        )
