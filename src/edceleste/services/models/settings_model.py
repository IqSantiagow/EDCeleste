import logging
from typing import Any, Union

from pydantic import (
    BaseModel,
    Field,
    field_validator,
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


class EdgeTTSProviderModel(BaseModel, validate_assignment=True):
    type: Literal["edge"] = Field(
        description="The type of the text-to-speech provider",
    )
    voice: str = Field(
        description="The Microsoft Edge voice short name to use for text-to-speech",
    )


class ChatterboxTTSProviderModel(BaseModel, validate_assignment=True):
    type: Literal["chatterbox"] = Field(
        description="The type of the text-to-speech provider",
    )
    profile: str = Field(
        description="The name of the voice profile (a reference audio clip stored in "
        "the voices directory) that Chatterbox clones",
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
    device: Literal["auto", "cuda", "cpu"] = Field(
        default="auto",
        description="The device Chatterbox runs on ('auto' picks CUDA when available)",
    )
    nano: bool = Field(
        default=True,
        description="Whether to use the lighter Nano model. The Nano model loads and "
        "generates much faster, but it ignores exaggeration and cfg_weight",
    )


class TTSModel(BaseModel, validate_assignment=True):
    provider: Union[EdgeTTSProviderModel, ChatterboxTTSProviderModel] = Field(
        default_factory=lambda: EdgeTTSProviderModel(
            type="edge", voice=DEFAULT_EDGE_VOICE
        ),
        description="The text-to-speech provider",
        discriminator="type",
    )
    volume: float = Field(
        ge=0.0,
        le=1.0,
        description="The volume of speech for text-to-speech",
    )


class ChatCompletionsModel(BaseModel):
    type: Literal["chat_completions"] = Field(
        description="The type of LLM model",
    )

    model: str = Field(
        description="The model to use for chat completions",
    )

    base_url: str = Field(description="The base URL for the chat completions API")

    bearer_token: str = Field(
        description="The bearer token for the chat completions API"
    )


class ClaudeAgentSdkModel(BaseModel):
    type: Literal["claude_agent_sdk"] = Field(
        description="The type of LLM model",
    )
    model: str = Field(
        description="The model to use for the Claude Agent SDK",
    )


class LmStudioModel(BaseModel):
    type: Literal["lm_studio"] = Field(
        description="The type of LLM model",
    )
    model: str = Field(
        description="The model to use for LM Studio",
    )


DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5-20251001"


class LLMModel(BaseModel):
    provider: Union[ChatCompletionsModel, ClaudeAgentSdkModel, LmStudioModel] = Field(
        default_factory=lambda: ClaudeAgentSdkModel(
            type="claude_agent_sdk", model=DEFAULT_CLAUDE_MODEL
        ),
        description="The LLM provider",
        discriminator="type",
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
