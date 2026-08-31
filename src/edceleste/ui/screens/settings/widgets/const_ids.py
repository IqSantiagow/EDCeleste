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
    EVENT_REACTION = EventReactionModel
    GAME_ACTIONS = GameActionsModel


class SettingsInputWidgetIds(Enum):
    JOURNAL_PATH_INPUT = "journal-path-input"
    KEYBINDS_PATH_INPUT = "keybinds-path-input"
    TTS_PROVIDER_TYPE_INPUT = "tts-provider-type-input"
    VOICE_INPUT = "voice-input"
    TTS_PROFILE_INPUT = "tts-profile-input"
    TTS_EXAGGERATION_INPUT = "tts-exaggeration-input"
    TTS_CFG_WEIGHT_INPUT = "tts-cfg-weight-input"
    TTS_DEVICE_INPUT = "tts-device-input"
    TTS_NANO_INPUT = "tts-nano-input"
    VOLUME_INPUT = "volume-input"
    STT_ENABLED_INPUT = "stt-enabled-input"
    STT_MODEL_INPUT = "stt-model-input"
    STT_INPUT_DEVICE_INPUT = "stt-input-device-input"
    GAME_ACTIONS_ENABLED_INPUT = "game-actions-enabled-input"


SECTION_ERROR_FIELD_TO_SECTION_TO_INPUT_WIDGET_ID = {
    # Key is error field name, value is a tuple of (SettingsSection, input widget id)
    "journal_path": (
        SettingsSection.PATHS,
        SettingsInputWidgetIds.JOURNAL_PATH_INPUT.value,
    ),
    "keybindings_path": (
        SettingsSection.PATHS,
        SettingsInputWidgetIds.KEYBINDS_PATH_INPUT.value,
    ),
    "voice": (SettingsSection.TTS, SettingsInputWidgetIds.VOICE_INPUT.value),
    "profile": (SettingsSection.TTS, SettingsInputWidgetIds.TTS_PROFILE_INPUT.value),
    "volume": (SettingsSection.TTS, SettingsInputWidgetIds.VOLUME_INPUT.value),
    "model": (SettingsSection.STT, SettingsInputWidgetIds.STT_MODEL_INPUT.value),
}
