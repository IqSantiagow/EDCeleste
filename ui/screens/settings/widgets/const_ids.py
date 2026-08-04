from enum import Enum

from services.models.settings_model import LLMModel, PathModel


class SettingsSection(Enum):
    # This bounds section names to the actual model classes, so we can use
    # them in a type-safe way. This is also bound to settings naming itself
    # so PATHS is paths, LLM is llm.
    PATHS = PathModel
    LLM = LLMModel


class SettingsInputWidgetIds(Enum):
    JOURNAL_PATH_INPUT = "journal-path-input"
    KEYBINDS_PATH_INPUT = "keybinds-path-input"


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
}
