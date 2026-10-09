import enum

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widgets import Label, LoadingIndicator
from dependency_injector.wiring import Provide, inject

from edceleste.containers.main_container import Container
from edceleste.services.decision_model_download_service import (
    MODEL_REPO,
    MODEL_VERSION,
)
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
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_switch_row import (
    WidgetLabeledSwitchRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_textarea_row import (
    WidgetLabeledTextAreaRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_test_connection_row import (
    WidgetTestConnectionRow,
)
from edceleste.ui.screens.settings.widgets.system_prompts.widget_instinct_status_row import (  # noqa: E501
    WidgetInstinctStatusRow,
)
from edceleste.ui.screens.settings.widgets.widget_base_settings_container import (
    WidgetBaseSettingsContainer,
)
from edceleste.ui.widgets.common.widget_labeled_value_row import WidgetLabeledValueRow
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader

PROVIDER_OPTIONS = SUPPORTED_LLM_PROVIDER_TYPES
PROVIDER_VALUES = SUPPORTED_LLM_PROVIDER_TYPES
INSTINCT_DEVICE_OPTIONS = ["auto", "cuda", "cpu"]
INSTINCT_MODEL_NAME = f"{MODEL_REPO.split('/')[-1]} · {MODEL_VERSION} · fixed"


class SystemPromptsInputWidgetIds(enum.StrEnum):
    LLM_PROVIDER_TYPE_INPUT = "llm-provider-type-input"
    LLM_MODEL_INPUT = "llm-model-input"
    LLM_API_KEY_INPUT = "llm-api-key-input"
    LLM_BASE_URL_INPUT = "llm-base-url-input"
    LLM_SYSTEM_PROMPT_INPUT = "llm-system-prompt-input"
    LLM_USER_PROMPT_INPUT = "llm-user-prompt-input"
    INSTINCT_ENABLED_INPUT = "instinct-enabled-input"
    INSTINCT_DEVICE_INPUT = "instinct-device-input"


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
        """llm_model is part of the screen's working copy of the settings and
        is changed in place. provider is set without triggering a recompose,
        because nothing is composed yet."""
        super().__init__(*args, **kwargs)
        self.llm_model = llm_model
        self.settings_repository = settings_repository
        self.set_reactive(WidgetSystemPromptsContainer.provider, llm_model.provider)

    def on_mount(self) -> None:
        """Starts loading the model list of the provider on screen. Until it is
        in, the model row shows a loading indicator."""
        self.call_later(self.fetch_models)

    async def fetch_models(self) -> None:
        """Asks the provider on screen (with its key and base URL, not the saved
        ones) for its model names over the network. Not a worker, it runs in
        this widget's message loop, so the widget waits for the answer.

        On error it shows a notification and sets an empty list, which makes
        compose_model_row() offer a text input for the model name. Setting
        models recomposes the section.
        """
        provider = self.provider
        assert provider is not None, "provider must be set before fetch_models runs"
        try:
            self.models = await self.settings_repository.fetch_available_model_names(
                provider
            )
        except Exception as e:
            self.log(f"Error fetching models for {provider.type}: {e}")
            self.notify(
                f"Error fetching models for {provider.type}. Is the API key ok?"
            )
            self.models = []

    def refetch_models(self) -> None:
        """The old list belongs to the old provider, key or endpoint - drop it so
        the loading indicator shows instead of the wrong models.

        Then fetches the list again and clears the connection test result,
        which also described the old values."""
        self.models = None
        self.call_later(self.fetch_models)
        self.clear_connection_test_result()

    async def test_llm_connection(self) -> str | None:
        """Tests the values on screen, not the saved ones. Passed to
        WidgetTestConnectionRow as its button callback. Sends one real request
        to the LLM, which costs a few tokens. Returns None when it works,
        otherwise a short error text."""
        provider = self.provider
        assert provider is not None, "provider must be set before testing it"
        return await self.settings_repository.find_llm_connection_error(provider)

    def clear_connection_test_result(self) -> None:
        """Called when the provider, key, endpoint or model changes, so an old
        "✓ Connected" does not stay next to new values. Also cancels a test
        that is still running."""
        self.query_one(WidgetTestConnectionRow).clear_result()

    def compose(self) -> ComposeResult:
        """Runs again when provider or models change. Three groups:

        1. CELESTE: provider select, API key (hidden), base URL, the model row
           (see compose_model_row) and the test connection row.
        2. INSTINCT: enabled switch, device select, the fixed model name and
           the download status row.
        3. PROMPTS: system prompt and user prompt text areas.

        The on_submit callbacks of the rows only log, the values reach
        llm_model through on_value_changed().
        """
        yield from super().compose()
        with VerticalScroll():
            yield WidgetSectionHeader("CELESTE")
            provider = self.provider
            assert provider is not None, "provider must be set before compose() runs"
            yield WidgetLabeledSelectRow(
                "Provider: ",
                PROVIDER_OPTIONS,
                provider.type,
                values=PROVIDER_VALUES,
                id=SystemPromptsInputWidgetIds.LLM_PROVIDER_TYPE_INPUT,
            )
            yield WidgetLabeledDynamicInputRow(
                "API Key:",
                provider.api_key,
                lambda value: self.log("API key submitted"),
                type="text",
                password=True,
                id=SystemPromptsInputWidgetIds.LLM_API_KEY_INPUT,
            )
            yield WidgetLabeledDynamicInputRow(
                "Base URL:",
                provider.base_url,
                lambda value: self.log(f"Base URL submitted: {value}"),
                type="text",
                id=SystemPromptsInputWidgetIds.LLM_BASE_URL_INPUT,
            )
            yield from self.compose_model_row(provider)
            yield WidgetTestConnectionRow(self.test_llm_connection)

            yield WidgetSectionHeader("INSTINCT · FAST COMMANDS")
            yield WidgetLabeledSwitchRow(
                "Enabled:",
                self.llm_model.instinct.enabled,
                hint="commands press keys before Celeste answers",
                id=SystemPromptsInputWidgetIds.INSTINCT_ENABLED_INPUT,
            )
            yield WidgetLabeledSelectRow(
                "Device: ",
                INSTINCT_DEVICE_OPTIONS,
                self.llm_model.instinct.device,
                id=SystemPromptsInputWidgetIds.INSTINCT_DEVICE_INPUT,
            )
            yield WidgetLabeledValueRow("Model:", INSTINCT_MODEL_NAME)
            yield WidgetInstinctStatusRow(self.settings_repository)

            yield WidgetSectionHeader("PROMPTS")
            yield WidgetLabeledTextAreaRow(
                "System Prompt:",
                self.llm_model.system_prompt,
                # TODO: Implement validation logic
                lambda value: self.log(f"System prompt submitted: {value}"),
                id=SystemPromptsInputWidgetIds.LLM_SYSTEM_PROMPT_INPUT,
            )
            yield WidgetLabeledTextAreaRow(
                "User Prompt:",
                self.llm_model.user_prompt,
                # TODO: Implement validation logic. Not wired into LLMService yet.
                lambda value: self.log(f"User prompt submitted: {value}"),
                id=SystemPromptsInputWidgetIds.LLM_USER_PROMPT_INPUT,
            )

    def compose_model_row(self, provider: LLMProviderModel) -> ComposeResult:
        """Part of compose(), it does not mount anything by itself.

        - models None (still loading) -> a loading indicator,
        - models empty (the provider has no model list or the request failed)
          -> a hint and a text input to type the model name,
        - otherwise -> a select with the model names.
        """
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
                id=SystemPromptsInputWidgetIds.LLM_MODEL_INPUT,
            )
            return
        yield WidgetLabeledSelectRow(
            "Model: ",
            self.models,
            provider.model,
            id=SystemPromptsInputWidgetIds.LLM_MODEL_INPUT,
        )

    def on_value_changed(self, message: ValueChanged) -> None:
        """Runs when a row posts ValueChanged. Writes the new value into
        llm_model and always posts SectionSettingsChanged(LLM) to the settings
        screen. Nothing is saved here.

        Extra steps for some rows:
        - provider type changed -> a new provider with an empty model, API key
          and base URL, then the model list is fetched again,
        - API key or base URL -> the model list is fetched again (network),
        - model -> the connection test result is cleared.
        """
        provider = self.provider
        assert provider is not None, "provider must be set before on_value_changed runs"

        if message.sender_id == SystemPromptsInputWidgetIds.LLM_PROVIDER_TYPE_INPUT:
            if message.new_value != provider.type:
                new_provider = LLMProviderModel(type=message.new_value, model="")
                self.llm_model.provider = new_provider
                self.provider = new_provider
                self.refetch_models()
        elif message.sender_id == SystemPromptsInputWidgetIds.LLM_MODEL_INPUT:
            provider.model = message.new_value
            self.clear_connection_test_result()
        elif message.sender_id == SystemPromptsInputWidgetIds.LLM_API_KEY_INPUT:
            provider.api_key = message.new_value
            self.refetch_models()
        elif message.sender_id == SystemPromptsInputWidgetIds.LLM_BASE_URL_INPUT:
            provider.base_url = message.new_value
            self.refetch_models()
        elif message.sender_id == SystemPromptsInputWidgetIds.LLM_SYSTEM_PROMPT_INPUT:
            self.llm_model.system_prompt = message.new_value
        elif message.sender_id == SystemPromptsInputWidgetIds.LLM_USER_PROMPT_INPUT:
            self.llm_model.user_prompt = message.new_value
        elif message.sender_id == SystemPromptsInputWidgetIds.INSTINCT_ENABLED_INPUT:
            self.llm_model.instinct.enabled = message.new_value
        elif message.sender_id == SystemPromptsInputWidgetIds.INSTINCT_DEVICE_INPUT:
            self.llm_model.instinct.device = message.new_value

        self.post_message(
            SectionSettingsChanged(
                SettingsSection.LLM,
                new_value=self.llm_model,
            )
        )
