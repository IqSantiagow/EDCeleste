import logging
from typing import Any

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from services.models.journal_event import KNOWN_EVENTS, JournalEventType

logger = logging.getLogger(__name__)


class PathModel(BaseModel):
    journal_path: str = Field(
        description="The path to the journal file",
    )
    keybindings_path: str = Field(
        description="The path to the keybindings file",
    )


class TTSModel(BaseModel, validate_assignment=True):
    voice: str = Field(
        description="The voice to use for text-to-speech",
    )
    volume: float = Field(
        ge=0.0,
        le=1.0,
        description="The volume of speech for text-to-speech",
    )


class LLMModel(BaseModel):
    api_key: str = Field(
        description="The Anthropic API key for the LLM",
    )

    system_prompt: str = Field(
        description="The system prompt for the LLM",
    )
    user_prompt: str = Field(
        description="The user prompt for the LLM",
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
    event_reaction: EventReactionModel = Field(
        description="The event reaction settings",
        default_factory=EventReactionModel,
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
