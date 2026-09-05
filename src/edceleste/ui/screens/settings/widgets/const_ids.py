from enum import Enum

from edceleste.services.models.settings_model import (
    EventReactionModel,
    GameActionsModel,
    LLMModel,
    PathModel,
    SttModel,
    TTSModel,
)


class SettingsSection(Enum):
    # This bounds section names to the actual model classes, so we can use
    # them in a type-safe way. This is also bound to settings naming itself
    # so PATHS is paths, LLM is llm.
    PATHS = PathModel
    LLM = LLMModel
    TTS = TTSModel
    STT = SttModel
    EVENT_REACTIONS = EventReactionModel
    GAME_ACTIONS = GameActionsModel
