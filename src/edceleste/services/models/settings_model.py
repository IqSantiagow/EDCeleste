import logging
from typing import Annotated, Any, Union

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)
from typing import Literal

from edceleste.services.models.journal_event import KNOWN_EVENTS, JournalEventType

logger = logging.getLogger(__name__)


class PathModel(BaseModel):
    journal_path: str = Field(
        description="The path to the journal file",
    )
    keybindings_path: str = Field(
        description="The path to the keybindings file",
    )


class SttModel(BaseModel, validate_assignment=True):
    enabled: bool = Field(
        default=True,
        description="Whether speech-to-text is enabled",
    )
    model: str = Field(
        description="The model to use for speech-to-text",
    )
    input_device: int | None = Field(
        default=None,
        description="The sounddevice index of the audio input device (None means system default)",  # noqa: E501
    )

    @field_validator("input_device", mode="before")
    @classmethod
    def migrate_string_device_to_none(cls, value: object) -> int | None:
        """
        Older settings files stored the device as a human-readable string name.
        We can't reliably map that back to an index (the index depends on the
        current machine and driver state), so we drop legacy string values and
        fall back to the system default (None).  Numeric values pass through.
        """
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        logger.warning(
            "input_device value %r is not an integer index; resetting to None (system default).",  # noqa: E501
            value,
        )
        return None


DEFAULT_EDGE_VOICE = "en-GB-SoniaNeural"


class ChatterboxParamsModel(BaseModel, validate_assignment=True, extra="forbid"):
    type: Literal["chatterbox"] = Field(
        description="The type of the text-to-speech provider", exclude=True
    )
    profile: str = Field(
        description="The name of the voice profile (a reference audio clip stored in "
        "the voices directory) that the clonable TTS provider clones",
    )
    device: Literal["auto", "cuda", "cpu"] = Field(
        default="auto",
        description="The device Chatterbox runs on ('auto' picks CUDA when available)",
    )
    exaggeration: float = Field(
        default=0.5,
        ge=0.0,
        le=2.0,
        description="How strongly Chatterbox exaggerates the emotion of the speech",
    )
    cfg_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How closely Chatterbox follows the reference clip pacing",
    )
    nano: bool = Field(
        default=True,
        description="Whether to use the lighter Nano model. The Nano model loads and "
        "generates much faster, but it ignores exaggeration and cfg_weight",
    )


class EdgeParamsModel(BaseModel, validate_assignment=True, extra="forbid"):
    type: Literal["edge"] = Field(
        description="The type of the text-to-speech provider", exclude=True
    )
    voice: str = Field(
        description="The Microsoft Edge voice short name to use for text-to-speech",
    )


TtsProviderParams = Annotated[
    Union[ChatterboxParamsModel, EdgeParamsModel], Field(discriminator="type")
]


class VoiceLabModel(BaseModel, validate_assignment=True):
    enabled: bool = Field(
        default=True,
        description="Whether the voice effects are applied to the speech",
    )
    clarity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How much the high tones are boosted, for a sharp and clear voice",
    )
    reverb: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How much and how long the voice rings in the ship's cabin",
    )
    stereo_width: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How wide the voice sounds (0 is mono)",
    )


class TTSModel(BaseModel, validate_assignment=True):
    provider: Literal["edge", "chatterbox"] = Field(
        description="The type of the text-to-speech provider", default="edge"
    )
    params: TtsProviderParams = Field(
        default_factory=lambda: EdgeParamsModel(type="edge", voice=DEFAULT_EDGE_VOICE),
        description="The parameters specific to the chosen TTS provider",
    )
    volume: float = Field(
        ge=0.0,
        le=1.0,
        description="The volume of speech for text-to-speech",
    )
    voice_lab: VoiceLabModel = Field(
        default_factory=VoiceLabModel,
        description="The voice effects applied to the speech of every provider",
    )

    @model_validator(mode="before")
    @classmethod
    def copy_provider_into_params_type_key(cls, data: Any) -> Any:
        """Makes the params findable by pydantic. Runs before the fields are
        validated and changes only a copy of the input.

        Pydantic picks the params model (Edge or Chatterbox) by the "type" key
        inside the params. A config.yaml has no such key (it would repeat
        provider), so params["type"] gets the value of provider ("edge" when
        provider is missing). Returns the input as it is when it is not a dict
        (e.g. a model that is assigned) or when params is not a dict.
        """
        if not isinstance(data, dict):
            return data

        data = dict(data)
        if isinstance(data.get("params"), dict):
            data["params"] = {**data["params"], "type": data.get("provider", "edge")}
        return data


# Every provider pydantic_ai can build from an api key. The six that need an
# extra package installed (bedrock, cohere, groq, mistral, voyageai, xai) are
# offered too, LLMService.validate_settings reports the missing package.
SUPPORTED_LLM_PROVIDER_TYPES = [
    "alibaba",
    "anthropic",
    "azure",
    "azure-responses",
    "bedrock",
    "bedrock-mantle",
    "cerebras",
    "cohere",
    "crusoe",
    "deepseek",
    "fireworks",
    "github",
    "github-copilot",
    "google",
    "google-cloud",
    "groq",
    "heroku",
    "huggingface",
    "litellm",
    "mistral",
    "moonshotai",
    "nebius",
    "ollama",
    "openai",
    "openai-chat",
    "openai-responses",
    "openrouter",
    "ovhcloud",
    "sambanova",
    "together",
    "typesafe",
    "vercel",
    "vllm",
    "voyageai",
    "xai",
    "zai",
]

DEFAULT_LLM_PROVIDER_TYPE = "openrouter"
DEFAULT_LLM_MODEL = "anthropic/claude-haiku-4.5"


class LLMProviderModel(BaseModel):
    """One shape for every provider - pydantic_ai knows how to build each one."""

    type: str = Field(
        description="The provider name, one of SUPPORTED_LLM_PROVIDER_TYPES",
    )
    model: str = Field(
        description="The model to use, as the provider names it",
    )
    api_key: str = Field(
        default="",
        description="The API key for the provider",
    )
    base_url: str = Field(
        default="",
        description="Custom endpoint of the provider, empty means its default one",
    )


class InstinctModel(BaseModel, validate_assignment=True):
    enabled: bool = Field(
        default=False,
        description="Whether Instinct presses keys for commands before Celeste answers",
    )
    # The GPU memory is shared with the game, so the pilot can keep it on the CPU
    device: Literal["auto", "cuda", "cpu"] = Field(
        default="auto",
        description="The device the Instinct model runs on ('auto' picks CUDA when available)",  # noqa: E501
    )


class LLMModel(BaseModel):
    provider: LLMProviderModel = Field(
        default_factory=lambda: LLMProviderModel(
            type=DEFAULT_LLM_PROVIDER_TYPE, model=DEFAULT_LLM_MODEL
        ),
        description="The LLM provider",
    )

    instinct: InstinctModel = Field(
        default_factory=InstinctModel,
        description="The settings of Instinct, the fast-command model",
    )

    system_prompt: str = Field(
        description="The system prompt for the LLM",
    )
    user_prompt: str = Field(
        description="The user prompt for the LLM",
    )


class GameActionsModel(BaseModel, validate_assignment=True):
    enabled: bool = Field(
        default=False,
        description="Whether the LLM is allowed to perform in-game actions",
    )


DEFAULT_EVENT_REACTION_SETTINGS = {JournalEventType.LoadGame.value: True}


class EventReactionModel(BaseModel):
    reactions: dict[str, bool] = Field(
        description="The event reaction settings",
        default_factory=lambda: DEFAULT_EVENT_REACTION_SETTINGS.copy(),
        validate_default=True,
    )

    @field_validator("reactions", mode="after")
    @classmethod
    def prepare_potentially_malformed_events_and_validate(
        cls,
        events: dict[str, Any],
    ) -> dict[str, Any]:
        """Makes old or hand edited config.yaml files work, instead of failing.

        1. Drops event names that are not in KNOWN_EVENTS, with a warning.
        2. Adds every known event that is missing, switched off (False).
        3. Raises ValueError if the result still does not hold exactly the
           known events.
        So after loading, reactions always has one entry per known event.
        """
        if not isinstance(events, dict):
            raise ValueError("Event reaction settings must be a dictionary")
        for event in list(events):
            if event not in [e.value for e in KNOWN_EVENTS]:
                events.pop(event)
                logger.warning(
                    f"Event reaction settings contains unknown event: {event}. "
                    "Skipping..."
                )
        for event in KNOWN_EVENTS:
            if event.value not in events:
                events[event.value] = False

        if len(events) != len(KNOWN_EVENTS):
            # Probably dead code but just to be sure, validate that all known
            # events are present in the event_reaction mapping
            raise ValueError(
                f"Event reaction settings must contain all known events: {KNOWN_EVENTS}"
            )

        return events


class SettingsModel(BaseModel):
    paths: PathModel = Field(
        description="The paths to the journal and keybindings files",
    )
    tts: TTSModel = Field(
        description="The text-to-speech settings for the LLM",
    )
    llm: LLMModel = Field(
        description="The LLM connection settings",
    )
    event_reactions: EventReactionModel = Field(
        description="The event reaction settings",
        default_factory=EventReactionModel,
    )
    stt: SttModel = Field(
        description="The speech-to-text settings",
    )
    game_actions: GameActionsModel = Field(
        description="The game actions settings",
        default_factory=GameActionsModel,
    )


class SettingsIssueModel(BaseModel):
    section: str = Field(
        description="The section of the settings that has an issue",
    )

    field: str = Field(
        description="The field of the settings that has an issue",
    )

    message: str = Field(
        description="The message describing the issue with the settings",
    )
